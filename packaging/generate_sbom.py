#!/usr/bin/env python3
"""Generate a reproducible CycloneDX SBOM from a hashed Python wheel lock."""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import re
import shlex
import stat
import sys
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence
from urllib.parse import quote


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SPEC_VERSION = "1.5"
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
VERSION_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}\Z")
REQUIREMENT_PATTERN = re.compile(
    r"(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"==(?P<version>[^\s;]+)\Z"
)
DIRECT_DEPENDENCY_PATTERN = re.compile(
    r"\s*(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
    r"\s*==\s*(?P<version>[^\s;]+)\s*\Z"
)
NAME_PREFIX_PATTERN = re.compile(
    r"(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
)
WHEEL_TAG_PATTERN = re.compile(r"[A-Za-z0-9_.]+\Z")
BUILD_TAG_PATTERN = re.compile(r"[0-9][A-Za-z0-9_]*\Z")
CONVENTIONAL_LICENSE_PATTERN = re.compile(
    r"(?:licen[cs]e|copying|notice)(?:[._-].*)?\Z", re.IGNORECASE
)
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_LICENSE_BYTES = 4 * 1024 * 1024
TARGET_MARKER_ENVIRONMENT: Mapping[str, str] = {
    "implementation_name": "cpython",
    "implementation_version": "3.11.6",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "platform_python_implementation": "CPython",
    "platform_release": "",
    "platform_system": "Linux",
    "platform_version": "",
    "python_full_version": "3.11.6",
    "python_version": "3.11",
    "sys_platform": "linux",
    "extra": "",
}
VERSION_MARKER_NAMES = {
    "implementation_version",
    "python_full_version",
    "python_version",
}
MARKER_TOKEN_PATTERN = re.compile(
    r"\s*(?:"
    r"(?P<string>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')|"
    r"(?P<operator>===|~=|==|!=|<=|>=|<|>)|"
    r"(?P<lparen>\()|(?P<rparen>\))|"
    r"(?P<word>[A-Za-z_][A-Za-z0-9_]*)"
    r")"
)


class SbomError(ValueError):
    """Raised when an input cannot satisfy the strict SBOM contract."""


@dataclass(frozen=True)
class LockedRequirement:
    name: str
    version: str
    sha256: str


@dataclass(frozen=True)
class DirectDependency:
    name: str
    version: str


@dataclass(frozen=True)
class WheelRequirement:
    name: str
    marker: str | None
    applies: bool


@dataclass(frozen=True)
class ProjectIdentity:
    name: str
    version: str
    direct_dependencies: tuple[DirectDependency, ...]


@dataclass(frozen=True)
class LicenseFile:
    path: str
    sha256: str
    content_type: str
    content_base64: str


@dataclass(frozen=True)
class WheelRecord:
    name: str
    version: str
    filename: str
    size: int
    sha256: str
    requires_dist: tuple[WheelRequirement, ...]
    license_expressions: tuple[str, ...]
    license_classifiers: tuple[str, ...]
    legacy_license: str | None
    license_files: tuple[LicenseFile, ...]


def canonicalize_name(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise SbomError("package name must be a non-empty string")
    if CONTROL_CHARACTER_PATTERN.search(value):
        raise SbomError("package name contains a control character")
    if NAME_PREFIX_PATTERN.fullmatch(value) is None:
        raise SbomError(f"invalid package name: {value!r}")
    return re.sub(r"[-_.]+", "-", value).lower()


def project_identity_from_document(document: object) -> ProjectIdentity:
    if not isinstance(document, Mapping):
        raise SbomError("pyproject.toml root must be a table")
    project = document.get("project")
    if not isinstance(project, Mapping):
        raise SbomError("pyproject.toml [project] must be a table")
    name = project.get("name")
    version = project.get("version")
    if type(name) is not str:
        raise SbomError("pyproject.toml project name must be a string")
    try:
        canonicalize_name(name)
    except SbomError as exc:
        raise SbomError("pyproject.toml project name is invalid") from exc
    if type(version) is not str:
        raise SbomError("pyproject.toml project version must be a string")
    if VERSION_PATTERN.fullmatch(version) is None:
        raise SbomError("pyproject.toml project version is invalid")
    dependency_values = project.get("dependencies")
    if isinstance(dependency_values, bool) or not isinstance(
        dependency_values, list
    ):
        raise SbomError("pyproject.toml project dependencies must be an array")
    if not dependency_values:
        raise SbomError(
            "pyproject.toml project dependencies must contain at least one exact pin"
        )
    dependencies: dict[str, DirectDependency] = {}
    for index, value in enumerate(dependency_values):
        if type(value) is not str:
            raise SbomError(
                f"pyproject.toml project dependencies[{index}] must be a string"
            )
        match = DIRECT_DEPENDENCY_PATTERN.fullmatch(value)
        if match is None:
            raise SbomError(
                f"pyproject.toml project dependencies[{index}] must use name==version"
            )
        dependency_name = canonicalize_name(match.group("name"))
        dependency_version = match.group("version")
        if VERSION_PATTERN.fullmatch(dependency_version) is None:
            raise SbomError(
                f"pyproject.toml project dependencies[{index}] version is invalid"
            )
        if dependency_name in dependencies:
            raise SbomError(
                f"duplicate pyproject.toml direct dependency: {dependency_name}"
            )
        dependencies[dependency_name] = DirectDependency(
            name=dependency_name,
            version=dependency_version,
        )
    return ProjectIdentity(
        name=name,
        version=version,
        direct_dependencies=tuple(
            dependencies[dependency_name]
            for dependency_name in sorted(dependencies)
        ),
    )


def read_project_identity(
    project_root: Path | None = None,
    pyproject_path: Path | None = None,
) -> ProjectIdentity:
    try:
        if pyproject_path is None:
            root = DEFAULT_ROOT if project_root is None else Path(project_root)
            if root.is_symlink():
                raise SbomError("project root must not be a symbolic link")
            if not root.is_dir():
                raise SbomError("project root is not a directory")
            path = root.resolve(strict=True) / "pyproject.toml"
        else:
            path = Path(pyproject_path)
    except (TypeError, ValueError) as exc:
        raise SbomError("project root or pyproject path is invalid") from exc
    if path.is_symlink():
        raise SbomError("pyproject.toml must not be a symbolic link")
    if not path.is_file():
        raise SbomError("pyproject.toml is not a regular file")
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise SbomError("pyproject.toml must be UTF-8 text") from exc
    except tomllib.TOMLDecodeError as exc:
        raise SbomError("pyproject.toml is not valid TOML") from exc
    return project_identity_from_document(document)


def _validate_identity_override(
    label: str, override: str | None, expected: str
) -> None:
    if override is None:
        return
    if type(override) is not str:
        raise SbomError(f"application {label} override must be a string")
    if override != expected:
        raise SbomError(
            f"application {label} override does not match pyproject.toml"
        )


def _logical_lock_lines(text: str) -> Iterable[tuple[int, str]]:
    pending: list[str] = []
    first_line = 0
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        if not pending:
            first_line = line_number
        continued = stripped.endswith("\\")
        if continued:
            stripped = stripped[:-1].rstrip()
        pending.append(stripped)
        if continued:
            continue
        combined = " ".join(part for part in pending if part)
        pending.clear()
        if combined:
            yield first_line, combined
    if pending:
        raise SbomError(f"lock line {first_line} has a dangling continuation")


def _strip_inline_comment(line: str) -> str:
    for index, character in enumerate(line):
        if character == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].rstrip()
    return line


def parse_lock(lock_path: Path) -> tuple[LockedRequirement, ...]:
    path = Path(lock_path)
    if path.is_symlink():
        raise SbomError("requirements lock must not be a symbolic link")
    if not path.is_file():
        raise SbomError("requirements lock is not a regular file")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SbomError("requirements lock must be UTF-8 text") from exc

    requirements: dict[str, LockedRequirement] = {}
    for line_number, logical_line in _logical_lock_lines(text):
        content = _strip_inline_comment(logical_line)
        if not content:
            continue
        try:
            tokens = shlex.split(content, comments=False, posix=True)
        except ValueError as exc:
            raise SbomError(f"cannot parse lock line {line_number}") from exc
        if not tokens:
            continue
        match = REQUIREMENT_PATTERN.fullmatch(tokens[0])
        if match is None:
            raise SbomError(
                f"lock line {line_number} must use an exact name==version pin"
            )

        hashes: list[str] = []
        index = 1
        while index < len(tokens):
            token = tokens[index]
            if token == "--hash":
                index += 1
                if index >= len(tokens):
                    raise SbomError(f"lock line {line_number} has no hash value")
                hash_value = tokens[index]
            elif token.startswith("--hash="):
                hash_value = token.removeprefix("--hash=")
            else:
                raise SbomError(
                    f"lock line {line_number} contains an unsupported option"
                )
            if not hash_value.lower().startswith("sha256:"):
                raise SbomError(f"lock line {line_number} must use SHA-256")
            digest = hash_value.split(":", 1)[1]
            if SHA256_PATTERN.fullmatch(digest) is None:
                raise SbomError(f"lock line {line_number} has an invalid SHA-256")
            hashes.append(digest.lower())
            index += 1
        if len(hashes) != 1:
            raise SbomError(
                f"lock line {line_number} must contain exactly one SHA-256"
            )

        name = canonicalize_name(match.group("name"))
        version = match.group("version")
        if CONTROL_CHARACTER_PATTERN.search(version):
            raise SbomError(f"lock line {line_number} has an invalid version")
        if name in requirements:
            raise SbomError(f"duplicate locked package: {name}")
        requirements[name] = LockedRequirement(name, version, hashes[0])

    if not requirements:
        raise SbomError("requirements lock must contain at least one package")
    return tuple(requirements[name] for name in sorted(requirements))


def validate_direct_dependency_lock(
    identity: ProjectIdentity,
    requirements: Sequence[LockedRequirement],
) -> None:
    locked_by_name = {
        requirement.name: requirement for requirement in requirements
    }
    for dependency in identity.direct_dependencies:
        locked = locked_by_name.get(dependency.name)
        if locked is None:
            raise SbomError(
                "pyproject.toml direct dependency is missing from lock: "
                f"{dependency.name}"
            )
        if locked.version != dependency.version:
            raise SbomError(
                "locked version does not match pyproject.toml direct dependency: "
                f"{dependency.name}"
            )


def _parse_wheel_filename(filename: str) -> tuple[str, str]:
    if not filename.endswith(".whl") or filename != Path(filename).name:
        raise SbomError(f"invalid wheel filename: {filename!r}")
    parts = filename[:-4].split("-")
    if len(parts) not in (5, 6):
        raise SbomError(f"invalid wheel filename: {filename!r}")
    distribution, version = parts[0], parts[1]
    if len(parts) == 6 and BUILD_TAG_PATTERN.fullmatch(parts[2]) is None:
        raise SbomError(f"invalid wheel build tag: {filename!r}")
    for tag in parts[-3:]:
        if WHEEL_TAG_PATTERN.fullmatch(tag) is None:
            raise SbomError(f"invalid wheel compatibility tag: {filename!r}")
    name = canonicalize_name(distribution)
    if not version or CONTROL_CHARACTER_PATTERN.search(version):
        raise SbomError(f"invalid wheel version: {filename!r}")
    return name, version


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _validate_archive_member(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if not name or "\\" in name or "\x00" in name:
        raise SbomError("wheel contains an unsafe archive member")
    if name.startswith("/") or re.match(r"[A-Za-z]:", name):
        raise SbomError("wheel contains an absolute archive member")
    trimmed = name[:-1] if name.endswith("/") else name
    parts = trimmed.split("/")
    if not trimmed or any(part in ("", ".", "..") for part in parts):
        raise SbomError("wheel contains a path-traversal archive member")
    member = PurePosixPath(trimmed)
    if member.is_absolute() or ".." in member.parts:
        raise SbomError("wheel contains a path-traversal archive member")
    mode = (info.external_attr >> 16) & 0xFFFF
    if mode and stat.S_ISLNK(mode):
        raise SbomError("wheel contains a symbolic-link archive member")
    if info.flag_bits & 0x1:
        raise SbomError("wheel contains an encrypted archive member")
    return trimmed


def _single_header(message, header: str, *, required: bool) -> str | None:
    values = message.get_all(header, [])
    if required and len(values) != 1:
        raise SbomError(f"wheel METADATA must contain exactly one {header} header")
    if not required and len(values) > 1:
        raise SbomError(f"wheel METADATA contains duplicate {header} headers")
    if not values:
        return None
    value = str(values[0]).strip()
    if not value or CONTROL_CHARACTER_PATTERN.search(value):
        raise SbomError(f"wheel METADATA has an invalid {header} header")
    return value


def _multi_headers(message, header: str) -> tuple[str, ...]:
    values: list[str] = []
    for raw_value in message.get_all(header, []):
        value = str(raw_value).strip()
        if not value or CONTROL_CHARACTER_PATTERN.search(value):
            raise SbomError(f"wheel METADATA has an invalid {header} header")
        values.append(value)
    return tuple(values)


def _tokenize_marker(marker: str) -> tuple[tuple[str, str], ...]:
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(marker):
        if not marker[position:].strip():
            break
        match = MARKER_TOKEN_PATTERN.match(marker, position)
        if match is None:
            raise SbomError("Requires-Dist contains an invalid environment marker")
        kind = match.lastgroup
        assert kind is not None
        tokens.append((kind, match.group(kind)))
        position = match.end()
    if not tokens:
        raise SbomError("Requires-Dist contains an empty environment marker")
    return tuple(tokens)


def _numeric_version(value: str) -> tuple[int, ...]:
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value) is None:
        raise SbomError("Requires-Dist marker uses an unsupported version value")
    return tuple(int(part) for part in value.split("."))


def _compare_versions(
    left: str, right: str, operator: str
) -> bool:
    left_parts = _numeric_version(left)
    right_parts = _numeric_version(right)
    width = max(len(left_parts), len(right_parts))
    padded_left = left_parts + (0,) * (width - len(left_parts))
    padded_right = right_parts + (0,) * (width - len(right_parts))
    if operator in ("==", "==="):
        return padded_left == padded_right
    if operator == "!=":
        return padded_left != padded_right
    if operator == "<":
        return padded_left < padded_right
    if operator == "<=":
        return padded_left <= padded_right
    if operator == ">":
        return padded_left > padded_right
    if operator == ">=":
        return padded_left >= padded_right
    if operator == "~=":
        prefix = right_parts[:-1]
        return padded_left >= padded_right and left_parts[: len(prefix)] == prefix
    raise SbomError("Requires-Dist marker uses an unsupported version operator")


class _MarkerParser:
    def __init__(self, marker: str) -> None:
        self.tokens = _tokenize_marker(marker)
        self.position = 0

    def parse(self) -> bool:
        result = self._parse_or()
        if self.position != len(self.tokens):
            raise SbomError("Requires-Dist environment marker has trailing tokens")
        return result

    def _current(self) -> tuple[str, str] | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position]

    def _accept(self, kind: str, value: str | None = None) -> bool:
        current = self._current()
        if current is None or current[0] != kind:
            return False
        if value is not None and current[1].lower() != value:
            return False
        self.position += 1
        return True

    def _parse_or(self) -> bool:
        result = self._parse_and()
        while self._accept("word", "or"):
            next_result = self._parse_and()
            result = result or next_result
        return result

    def _parse_and(self) -> bool:
        result = self._parse_atom()
        while self._accept("word", "and"):
            next_result = self._parse_atom()
            result = result and next_result
        return result

    def _parse_atom(self) -> bool:
        if self._accept("lparen"):
            result = self._parse_or()
            if not self._accept("rparen"):
                raise SbomError("Requires-Dist environment marker is unbalanced")
            return result
        return self._parse_comparison()

    def _parse_operand(self) -> tuple[str, str | None]:
        current = self._current()
        if current is None:
            raise SbomError("Requires-Dist environment marker is incomplete")
        kind, raw_value = current
        self.position += 1
        if kind == "word":
            if raw_value not in TARGET_MARKER_ENVIRONMENT:
                raise SbomError(
                    "Requires-Dist marker uses an unknown environment variable"
                )
            return TARGET_MARKER_ENVIRONMENT[raw_value], raw_value
        if kind == "string":
            try:
                value = ast.literal_eval(raw_value)
            except (SyntaxError, ValueError) as exc:
                raise SbomError(
                    "Requires-Dist marker contains an invalid string"
                ) from exc
            if type(value) is not str or CONTROL_CHARACTER_PATTERN.search(value):
                raise SbomError(
                    "Requires-Dist marker contains an invalid string"
                )
            return value, None
        raise SbomError("Requires-Dist marker operand is invalid")

    def _parse_operator(self) -> str:
        current = self._current()
        if current is None:
            raise SbomError("Requires-Dist environment marker is incomplete")
        if current[0] == "operator":
            self.position += 1
            return current[1]
        if self._accept("word", "in"):
            return "in"
        if self._accept("word", "not"):
            if not self._accept("word", "in"):
                raise SbomError("Requires-Dist marker has an invalid not operator")
            return "not in"
        raise SbomError("Requires-Dist environment marker has no comparison")

    def _parse_comparison(self) -> bool:
        left, left_variable = self._parse_operand()
        operator = self._parse_operator()
        right, right_variable = self._parse_operand()
        if operator == "in":
            return left in right
        if operator == "not in":
            return left not in right
        if (
            left_variable in VERSION_MARKER_NAMES
            or right_variable in VERSION_MARKER_NAMES
        ):
            return _compare_versions(left, right, operator)
        if operator in ("==", "==="):
            return left == right
        if operator == "!=":
            return left != right
        if operator == "<":
            return left < right
        if operator == "<=":
            return left <= right
        if operator == ">":
            return left > right
        if operator == ">=":
            return left >= right
        raise SbomError("Requires-Dist marker uses an invalid comparison")


def _split_requires_dist_marker(value: str) -> tuple[str, str | None]:
    quote_character: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if quote_character is not None and character == "\\":
            escaped = True
            continue
        if character in ("'", '"'):
            if quote_character is None:
                quote_character = character
            elif quote_character == character:
                quote_character = None
            continue
        if character == ";" and quote_character is None:
            requirement = value[:index].strip()
            marker = value[index + 1 :].strip()
            if not marker:
                raise SbomError("Requires-Dist contains an empty environment marker")
            return requirement, marker
    if quote_character is not None:
        raise SbomError("Requires-Dist contains an unterminated quote")
    return value.strip(), None


def _parse_requires_dist(value: str) -> WheelRequirement:
    requirement, marker = _split_requires_dist_marker(value)
    match = NAME_PREFIX_PATTERN.match(requirement)
    if match is None:
        raise SbomError(f"invalid Requires-Dist value: {value!r}")
    remainder = requirement[match.end() :].lstrip()
    if remainder and remainder[0] not in "[<(=>!~@":
        raise SbomError(f"invalid Requires-Dist value: {value!r}")
    return WheelRequirement(
        name=canonicalize_name(match.group("name")),
        marker=marker,
        applies=True if marker is None else _MarkerParser(marker).parse(),
    )


def _safe_license_header_path(value: str) -> PurePosixPath:
    if "\\" in value or "\x00" in value or value.startswith("/"):
        raise SbomError("License-File contains an unsafe path")
    raw_parts = value.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise SbomError("License-File contains a path-traversal path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise SbomError("License-File contains a path-traversal path")
    return path


def _license_content_type(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in (".htm", ".html"):
        return "text/html"
    if suffix in (".md", ".markdown"):
        return "text/markdown"
    return "text/plain"


def _collect_license_members(
    archive: zipfile.ZipFile,
    members: Mapping[str, zipfile.ZipInfo],
    dist_info_directory: str,
    declared_values: Sequence[str],
) -> tuple[LicenseFile, ...]:
    selected: set[str] = set()
    for value in declared_values:
        relative = _safe_license_header_path(value).as_posix()
        candidates = (
            f"{dist_info_directory}/licenses/{relative}",
            f"{dist_info_directory}/{relative}",
        )
        matches = [candidate for candidate in candidates if candidate in members]
        if len(matches) != 1 or members[matches[0]].is_dir():
            raise SbomError(f"declared License-File is missing or ambiguous: {value}")
        selected.add(matches[0])

    for name, info in members.items():
        if info.is_dir():
            continue
        basename = PurePosixPath(name).name
        if CONVENTIONAL_LICENSE_PATTERN.fullmatch(basename):
            selected.add(name)

    license_files: list[LicenseFile] = []
    for name in sorted(selected):
        info = members[name]
        if info.file_size > MAX_LICENSE_BYTES:
            raise SbomError(f"wheel license file is too large: {PurePosixPath(name).name}")
        payload = archive.read(info)
        digest = hashlib.sha256(payload).hexdigest()
        license_files.append(
            LicenseFile(
                path=name,
                sha256=digest,
                content_type=_license_content_type(name),
                content_base64=base64.b64encode(payload).decode("ascii"),
            )
        )
    return tuple(license_files)


def inspect_wheel(
    wheel_path: Path,
    locked: LockedRequirement,
    filename_name: str,
    filename_version: str,
) -> WheelRecord:
    if filename_name != locked.name:
        raise SbomError(f"wheel name does not match lock: {wheel_path.name}")
    if filename_version != locked.version:
        raise SbomError(f"wheel version does not match lock: {wheel_path.name}")
    size, digest = sha256_file(wheel_path)
    if digest != locked.sha256:
        raise SbomError(f"wheel SHA-256 does not match lock: {wheel_path.name}")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise SbomError("wheel size must be a non-negative integer")

    try:
        with zipfile.ZipFile(wheel_path, "r") as archive:
            members: dict[str, zipfile.ZipInfo] = {}
            casefolded: set[str] = set()
            for info in archive.infolist():
                safe_name = _validate_archive_member(info)
                folded = safe_name.casefold()
                if safe_name in members or folded in casefolded:
                    raise SbomError("wheel contains duplicate archive members")
                members[safe_name] = info
                casefolded.add(folded)

            metadata_names = [
                name
                for name, info in members.items()
                if not info.is_dir()
                and len(PurePosixPath(name).parts) == 2
                and name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise SbomError("wheel must contain exactly one .dist-info/METADATA")
            metadata_name = metadata_names[0]
            metadata_info = members[metadata_name]
            if metadata_info.file_size > MAX_METADATA_BYTES:
                raise SbomError("wheel METADATA is too large")
            dist_info_directory = PurePosixPath(metadata_name).parts[0]
            expected_dist_info = (
                f"{wheel_path.name[:-4].split('-')[0]}-{filename_version}.dist-info"
            )
            if dist_info_directory.casefold() != expected_dist_info.casefold():
                raise SbomError("wheel .dist-info directory does not match filename")

            message = BytesParser(policy=policy.default).parsebytes(
                archive.read(metadata_info)
            )
            if message.defects:
                raise SbomError("wheel METADATA is malformed")
            metadata_name_value = _single_header(message, "Name", required=True)
            metadata_version = _single_header(message, "Version", required=True)
            assert metadata_name_value is not None
            assert metadata_version is not None
            if canonicalize_name(metadata_name_value) != locked.name:
                raise SbomError("wheel METADATA name does not match lock")
            if metadata_version != locked.version:
                raise SbomError("wheel METADATA version does not match lock")

            raw_requires = _multi_headers(message, "Requires-Dist")
            parsed_requires = [_parse_requires_dist(item) for item in raw_requires]
            unique_requires = {
                (item.name, item.marker): item for item in parsed_requires
            }
            requires = tuple(
                unique_requires[key]
                for key in sorted(
                    unique_requires,
                    key=lambda item: (item[0], item[1] or ""),
                )
            )
            license_expression = _single_header(
                message, "License-Expression", required=False
            )
            classifiers = tuple(
                sorted(
                    {
                        value
                        for value in _multi_headers(message, "Classifier")
                        if value.startswith("License ::")
                    }
                )
            )
            legacy_license = _single_header(message, "License", required=False)
            if legacy_license is not None and legacy_license.upper() == "UNKNOWN":
                legacy_license = None
            declared_license_files = _multi_headers(message, "License-File")
            if len(set(declared_license_files)) != len(declared_license_files):
                raise SbomError("wheel METADATA contains duplicate License-File headers")
            license_files = _collect_license_members(
                archive,
                members,
                dist_info_directory,
                declared_license_files,
            )
    except zipfile.BadZipFile as exc:
        raise SbomError(f"invalid wheel archive: {wheel_path.name}") from exc

    return WheelRecord(
        name=locked.name,
        version=locked.version,
        filename=wheel_path.name,
        size=size,
        sha256=digest,
        requires_dist=requires,
        license_expressions=(license_expression,) if license_expression else (),
        license_classifiers=classifiers,
        legacy_license=legacy_license,
        license_files=license_files,
    )


def collect_wheels(
    wheelhouse: Path, requirements: Sequence[LockedRequirement]
) -> tuple[WheelRecord, ...]:
    directory = Path(wheelhouse)
    if directory.is_symlink():
        raise SbomError("wheelhouse must not be a symbolic link")
    if not directory.is_dir():
        raise SbomError("wheelhouse is not a directory")
    resolved_directory = directory.resolve(strict=True)
    locked_by_name = {requirement.name: requirement for requirement in requirements}
    if len(locked_by_name) != len(requirements):
        raise SbomError("requirements contain duplicate package names")

    records: dict[str, WheelRecord] = {}
    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    non_wheels = [
        path.name for path in entries if not path.name.lower().endswith(".whl")
    ]
    if non_wheels:
        raise SbomError(
            "wheelhouse contains a non-wheel entry: "
            f"{', '.join(non_wheels)}"
        )
    wheel_paths = entries
    for wheel_path in wheel_paths:
        if wheel_path.is_symlink() or not wheel_path.is_file():
            raise SbomError(f"wheel is not a regular file: {wheel_path.name}")
        resolved_wheel = wheel_path.resolve(strict=True)
        if resolved_wheel.parent != resolved_directory:
            raise SbomError(f"wheel escapes the wheelhouse: {wheel_path.name}")
        filename_name, filename_version = _parse_wheel_filename(wheel_path.name)
        locked = locked_by_name.get(filename_name)
        if locked is None:
            raise SbomError(f"extra wheel not present in lock: {wheel_path.name}")
        if filename_name in records:
            raise SbomError(f"duplicate wheel for locked package: {filename_name}")
        records[filename_name] = inspect_wheel(
            resolved_wheel,
            locked,
            filename_name,
            filename_version,
        )

    missing = sorted(set(locked_by_name) - set(records))
    if missing:
        raise SbomError(f"missing wheel for locked package: {', '.join(missing)}")
    return tuple(records[name] for name in sorted(records))


def validate_requires_dist_closure(
    records: Sequence[WheelRecord],
    requirements: Sequence[LockedRequirement],
) -> None:
    locked_names = {requirement.name for requirement in requirements}
    for record in records:
        for dependency in record.requires_dist:
            if dependency.applies and dependency.name not in locked_names:
                raise SbomError(
                    "applicable wheel dependency is missing from lock: "
                    f"{record.name} -> {dependency.name}"
                )


def _source_date_epoch(value: int | None) -> int:
    if value is None:
        raw = os.environ.get("SOURCE_DATE_EPOCH")
        if raw is None or not raw.strip():
            raise SbomError("SOURCE_DATE_EPOCH is required")
        raw = raw.strip()
        if re.fullmatch(r"[0-9]+", raw) is None:
            raise SbomError("SOURCE_DATE_EPOCH must be a non-negative integer")
        value = int(raw)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SbomError("SOURCE_DATE_EPOCH must be a non-negative integer")
    return value


def _timestamp(epoch: int) -> str:
    try:
        return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OSError, OverflowError, ValueError) as exc:
        raise SbomError("SOURCE_DATE_EPOCH is outside the supported UTC range") from exc


def _purl(name: str, version: str) -> str:
    return f"pkg:pypi/{quote(name, safe='._~-')}@{quote(version, safe='._~-')}"


def _license_objects(record: WheelRecord) -> list[dict[str, object]]:
    licenses: list[dict[str, object]] = []
    for classifier in record.license_classifiers:
        license_name = classifier.split(" :: ")[-1]
        licenses.append({"license": {"name": license_name}})
    if record.legacy_license:
        licenses.append({"license": {"name": record.legacy_license}})
    for license_file in record.license_files:
        licenses.append(
            {
                "license": {
                    "name": f"License file: {PurePosixPath(license_file.path).name}",
                    "text": {
                        "content": license_file.content_base64,
                        "contentType": license_file.content_type,
                        "encoding": "base64",
                    },
                }
            }
        )
    return licenses


def _licenses(record: WheelRecord) -> list[dict[str, object]]:
    if record.license_expressions:
        # CycloneDX 1.5 licenseChoice permits either one SPDX expression or a
        # list of license objects, but never a mixture of the two.
        return [{"expression": record.license_expressions[0]}]
    return _license_objects(record)


def _component(record: WheelRecord) -> dict[str, object]:
    properties: list[dict[str, str]] = [
        {"name": "mcgs:wheel:filename", "value": record.filename},
        {"name": "mcgs:wheel:size", "value": str(record.size)},
    ]
    for index, dependency in enumerate(record.requires_dist):
        properties.extend(
            (
                {
                    "name": f"mcgs:python:requires-dist:{index:04d}",
                    "value": dependency.name,
                },
                {
                    "name": f"mcgs:python:requires-dist:{index:04d}:applies",
                    "value": "true" if dependency.applies else "false",
                },
            )
        )
        if dependency.marker is not None:
            properties.append(
                {
                    "name": f"mcgs:python:requires-dist:{index:04d}:marker",
                    "value": dependency.marker,
                }
            )
    properties.extend(
        {
            "name": f"mcgs:python:license-expression:{index:04d}",
            "value": expression,
        }
        for index, expression in enumerate(record.license_expressions)
    )
    properties.extend(
        {
            "name": f"mcgs:python:license-classifier:{index:04d}",
            "value": classifier,
        }
        for index, classifier in enumerate(record.license_classifiers)
    )
    if record.legacy_license:
        properties.append(
            {"name": "mcgs:python:legacy-license", "value": record.legacy_license}
        )
    for index, license_file in enumerate(record.license_files):
        properties.extend(
            (
                {
                    "name": f"mcgs:wheel:license-file:{index:04d}:path",
                    "value": license_file.path,
                },
                {
                    "name": f"mcgs:wheel:license-file:{index:04d}:sha256",
                    "value": license_file.sha256,
                },
            )
        )
    purl = _purl(record.name, record.version)
    component: dict[str, object] = {
        "bom-ref": purl,
        "type": "library",
        "name": record.name,
        "version": record.version,
        "purl": purl,
        "hashes": [{"alg": "SHA-256", "content": record.sha256}],
        "licenses": _licenses(record),
        "properties": sorted(properties, key=lambda item: (item["name"], item["value"])),
    }
    evidence_licenses = _license_objects(record)
    if record.license_expressions and evidence_licenses:
        component["evidence"] = {"licenses": evidence_licenses}
    return component


def build_sbom(
    lock_path: Path,
    wheelhouse: Path,
    *,
    project_root: Path | None = None,
    pyproject_path: Path | None = None,
    application_name: str | None = None,
    application_version: str | None = None,
    source_date_epoch: int | None = None,
) -> dict[str, object]:
    identity = read_project_identity(project_root, pyproject_path)
    _validate_identity_override("name", application_name, identity.name)
    _validate_identity_override("version", application_version, identity.version)
    root_name = canonicalize_name(identity.name)
    epoch = _source_date_epoch(source_date_epoch)
    timestamp = _timestamp(epoch)
    requirements = parse_lock(Path(lock_path))
    validate_direct_dependency_lock(identity, requirements)
    records = collect_wheels(Path(wheelhouse), requirements)
    validate_requires_dist_closure(records, requirements)
    components = [_component(record) for record in records]
    component_refs = {record.name: _purl(record.name, record.version) for record in records}
    root_ref = _purl(root_name, identity.version)
    if root_ref in component_refs.values():
        raise SbomError("root application bom-ref collides with a locked component")

    dependencies: list[dict[str, object]] = [
        {
            "ref": root_ref,
            "dependsOn": sorted(
                component_refs[dependency.name]
                for dependency in identity.direct_dependencies
            ),
        }
    ]
    for record in records:
        depends_on = sorted(
            {
                component_refs[dependency.name]
                for dependency in record.requires_dist
                if dependency.applies
                and dependency.name in component_refs
                and dependency.name != record.name
            }
        )
        dependencies.append({"ref": component_refs[record.name], "dependsOn": depends_on})

    root_component: dict[str, object] = {
        "bom-ref": root_ref,
        "type": "application",
        "name": identity.name,
        "version": identity.version,
        "purl": root_ref,
        "licenses": [{"expression": "Apache-2.0"}],
    }
    sbom: dict[str, object] = {
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "component": root_component,
            "properties": [
                {"name": "mcgs:source-date-epoch", "value": str(epoch)}
            ],
        },
        "components": components,
        "dependencies": dependencies,
    }
    if isinstance(sbom["version"], bool) or not isinstance(sbom["version"], int):
        raise SbomError("CycloneDX document version must be an integer")
    return sbom


def serialize_sbom(sbom: Mapping[str, object]) -> bytes:
    return (
        json.dumps(sbom, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _stage_file(directory: Path, prefix: str, payload: bytes) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="wb", prefix=prefix, suffix=".tmp", dir=directory, delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def write_sbom(output_path: Path, sbom: Mapping[str, object]) -> tuple[str, Path]:
    output = Path(output_path)
    if not output.name or output.name in (".", ".."):
        raise SbomError("output must name a file")
    if "\n" in output.name or "\r" in output.name or "\x00" in output.name:
        raise SbomError("output filename contains an unsafe character")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.is_dir():
        raise SbomError("output path is a directory")
    sidecar = output.with_suffix(output.suffix + ".sha256")
    if sidecar.exists() and sidecar.is_dir():
        raise SbomError("checksum sidecar path is a directory")

    payload = serialize_sbom(sbom)
    digest = hashlib.sha256(payload).hexdigest()
    checksum_payload = f"{digest}  {output.name}\n".encode("utf-8")
    staged_output: Path | None = None
    staged_sidecar: Path | None = None
    try:
        staged_output = _stage_file(output.parent, f".{output.name}.", payload)
        staged_sidecar = _stage_file(
            sidecar.parent, f".{sidecar.name}.", checksum_payload
        )
        os.replace(staged_output, output)
        staged_output = None
        os.replace(staged_sidecar, sidecar)
        staged_sidecar = None
    finally:
        if staged_output is not None:
            staged_output.unlink(missing_ok=True)
        if staged_sidecar is not None:
            staged_sidecar.unlink(missing_ok=True)
    return digest, sidecar


def generate_sbom(
    lock_path: Path,
    wheelhouse: Path,
    output_path: Path,
    *,
    project_root: Path | None = None,
    pyproject_path: Path | None = None,
    application_name: str | None = None,
    application_version: str | None = None,
    source_date_epoch: int | None = None,
) -> dict[str, object]:
    sbom = build_sbom(
        lock_path,
        wheelhouse,
        project_root=project_root,
        pyproject_path=pyproject_path,
        application_name=application_name,
        application_version=application_version,
        source_date_epoch=source_date_epoch,
    )
    write_sbom(output_path, sbom)
    return sbom


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lock",
        "--requirements-lock",
        dest="lock_path",
        type=Path,
        required=True,
        help="fully hashed requirements lock",
    )
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="project root containing pyproject.toml (default: repository root)",
    )
    parser.add_argument(
        "--pyproject",
        "--pyproject-path",
        dest="pyproject_path",
        type=Path,
        help="explicit pyproject.toml path; takes precedence over --root",
    )
    parser.add_argument(
        "--application-name",
        "--project-name",
        help="optional assertion; must exactly match [project].name",
    )
    parser.add_argument(
        "--application-version",
        "--project-version",
        help="optional assertion; must exactly match [project].version",
    )
    args = parser.parse_args(argv)

    try:
        sbom = build_sbom(
            args.lock_path,
            args.wheelhouse,
            project_root=args.root,
            pyproject_path=args.pyproject_path,
            application_name=args.application_name,
            application_version=args.application_version,
        )
        digest, sidecar = write_sbom(args.output, sbom)
        print(
            json.dumps(
                {
                    "status": "passed",
                    "component_count": len(sbom["components"]),
                    "output": args.output.name,
                    "sha256": digest,
                    "checksum_file": sidecar.name,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, SbomError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
