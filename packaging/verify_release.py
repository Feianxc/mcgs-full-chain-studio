#!/usr/bin/env python3
"""Verify a release archive or an extracted release tree against its manifest."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable, Sequence


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
CREATED_AT_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
ALLOWLIST_PATH = Path(__file__).resolve().with_name("release-allowlist.json")
REQUIRED_TREE_SENTINELS = {
    ".github": ".github/workflows/ci.yml",
    "assembly_studio": "assembly_studio/templates/index.html",
    "deploy": "deploy/deploy-release.sh",
    "mvp_generator": "mvp_generator/__init__.py",
    "packaging": "packaging/build_release.py",
    "protocol_studio": "protocol_studio/app.py",
    "resources": "resources/protocol/schemas/project-config.schema.json",
    "scripts": "scripts/validate_repository.py",
    "tests": "tests/run_all.py",
}


class VerificationError(RuntimeError):
    """Release contents do not satisfy the manifest contract."""


def load_path_policy(path: Path = ALLOWLIST_PATH) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError("release allowlist is not readable JSON") from exc
    required = {
        "schema_version",
        "project",
        "files",
        "trees",
        "excluded_names",
        "excluded_parts",
        "forbidden_parts",
        "forbidden_suffixes",
    }
    if not isinstance(policy, dict) or set(policy) != required:
        raise VerificationError("release allowlist keys do not match the contract")
    if (
        isinstance(policy["schema_version"], bool)
        or not isinstance(policy["schema_version"], int)
        or policy["schema_version"] != 1
        or policy["project"] != "mcgs-full-chain-studio"
    ):
        raise VerificationError("release allowlist project or schema is invalid")
    for key in required - {"schema_version", "project"}:
        if not isinstance(policy[key], list) or not all(
            isinstance(value, str) and value for value in policy[key]
        ):
            raise VerificationError(f"release allowlist {key} is invalid")
        if len(policy[key]) != len(set(policy[key])):
            raise VerificationError(f"release allowlist {key} contains duplicates")
    if not policy["files"]:
        raise VerificationError("release allowlist files must not be empty")
    if not policy["trees"]:
        raise VerificationError("release allowlist trees must not be empty")
    policy_trees = set(policy["trees"])
    required_trees = set(REQUIRED_TREE_SENTINELS)
    if policy_trees != required_trees:
        missing = sorted(required_trees - policy_trees)
        extra = sorted(policy_trees - required_trees)
        raise VerificationError(
            f"release allowlist tree set does not match the project contract; "
            f"missing={missing}, extra={extra}"
        )
    return policy


def enforce_path_policy(manifest: dict[str, Any], policy: dict[str, Any]) -> None:
    exact_files = set(policy["files"])
    tree_roots = tuple(f"{value.rstrip('/')}" for value in policy["trees"])
    excluded_names = set(policy["excluded_names"])
    excluded_parts = {value.casefold() for value in policy["excluded_parts"]}
    forbidden_parts = {value.casefold() for value in policy["forbidden_parts"]}
    forbidden_suffixes = {value.casefold() for value in policy["forbidden_suffixes"]}
    manifest_paths: set[str] = set()
    for item in manifest["files"]:
        value = item["path"]
        manifest_paths.add(value)
        pure = PurePosixPath(value)
        if value not in exact_files and not any(
            value.startswith(f"{root}/") for root in tree_roots
        ):
            raise VerificationError(f"manifest path is outside the release allowlist: {value}")
        folded_parts = {part.casefold() for part in pure.parts}
        if pure.name in excluded_names or folded_parts.intersection(excluded_parts):
            raise VerificationError(f"manifest contains an excluded path: {value}")
        if folded_parts.intersection(forbidden_parts):
            raise VerificationError(f"manifest contains a forbidden path: {value}")
        if pure.suffix.casefold() in forbidden_suffixes:
            raise VerificationError(f"manifest contains a forbidden file type: {value}")
    missing_exact_files = sorted(exact_files - manifest_paths)
    if missing_exact_files:
        raise VerificationError(
            "manifest is missing required release files: "
            + ", ".join(missing_exact_files)
        )
    missing_trees = sorted(
        root
        for root in policy["trees"]
        if not any(path.startswith(f"{root}/") for path in manifest_paths)
    )
    if missing_trees:
        raise VerificationError(
            "manifest is missing required release trees: " + ", ".join(missing_trees)
        )
    missing_sentinels = sorted(
        sentinel
        for root, sentinel in REQUIRED_TREE_SENTINELS.items()
        if root in policy["trees"] and sentinel not in manifest_paths
    )
    if missing_sentinels:
        raise VerificationError(
            "manifest is missing required tree sentinels: "
            + ", ".join(missing_sentinels)
        )


def safe_relative(value: str) -> PurePosixPath:
    if "\\" in value:
        raise VerificationError(f"backslash in manifest path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise VerificationError(f"unsafe manifest path: {value!r}")
    return path


def parse_manifest(payload: bytes, expected_version: str | None) -> dict[str, Any]:
    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError("release-manifest.json is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "project",
        "version",
        "created_at",
        "source_date_epoch",
        "files",
    }:
        raise VerificationError("manifest root keys do not match the contract")
    if (
        isinstance(manifest["schema_version"], bool)
        or not isinstance(manifest["schema_version"], int)
        or manifest["schema_version"] != 1
        or manifest["project"] != "mcgs-full-chain-studio"
    ):
        raise VerificationError("unsupported manifest schema or project")
    if not isinstance(manifest["version"], str) or not manifest["version"]:
        raise VerificationError("manifest version must be a non-empty string")
    if expected_version is not None and manifest["version"] != expected_version:
        raise VerificationError(
            f"version mismatch: manifest={manifest['version']!r}, expected={expected_version!r}"
        )
    if not isinstance(manifest["created_at"], str) or not CREATED_AT_PATTERN.fullmatch(
        manifest["created_at"]
    ):
        raise VerificationError("created_at must use UTC ISO-8601 format YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(manifest["created_at"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise VerificationError(
            "created_at must use UTC ISO-8601 format YYYY-MM-DDTHH:MM:SSZ"
        ) from exc
    if (
        isinstance(manifest["source_date_epoch"], bool)
        or not isinstance(manifest["source_date_epoch"], int)
        or manifest["source_date_epoch"] < 0
    ):
        raise VerificationError("source_date_epoch must be a non-negative integer")
    try:
        expected_created_at = datetime.fromtimestamp(
            manifest["source_date_epoch"], timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OSError, OverflowError, ValueError) as exc:
        raise VerificationError("source_date_epoch is outside the supported UTC range") from exc
    if manifest["created_at"] != expected_created_at:
        raise VerificationError("created_at does not match source_date_epoch UTC value")
    if not isinstance(manifest["files"], list):
        raise VerificationError("files must be an array")
    if not manifest["files"]:
        raise VerificationError("files must be a non-empty array")

    seen: set[str] = set()
    for index, item in enumerate(manifest["files"]):
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise VerificationError(f"files[{index}] keys do not match the contract")
        if not isinstance(item["path"], str):
            raise VerificationError(f"files[{index}].path must be a string")
        normalized = safe_relative(item["path"]).as_posix()
        if normalized != item["path"]:
            raise VerificationError(f"files[{index}].path is not normalized")
        if normalized in seen:
            raise VerificationError(f"duplicate manifest path: {normalized}")
        seen.add(normalized)
        if (
            isinstance(item["size"], bool)
            or not isinstance(item["size"], int)
            or item["size"] < 0
        ):
            raise VerificationError(f"files[{index}].size must be a non-negative integer")
        if not isinstance(item["sha256"], str) or not SHA256_PATTERN.fullmatch(
            item["sha256"]
        ):
            raise VerificationError(f"files[{index}].sha256 is invalid")
    if [item["path"] for item in manifest["files"]] != sorted(seen):
        raise VerificationError("manifest files must be sorted by path")
    return manifest


def digest_stream(handle: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := handle.read(1024 * 1024):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def verify_archive(path: Path, expected_version: str | None) -> dict[str, Any]:
    try:
        archive = tarfile.open(path, mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise VerificationError("cannot open release tar.gz") from exc
    with archive:
        members = archive.getmembers()
        if not members:
            raise VerificationError("archive is empty")
        roots: set[str] = set()
        directory_members: list[str] = []
        member_by_relative: dict[str, tarfile.TarInfo] = {}
        for member in members:
            pure = PurePosixPath(member.name)
            if (
                pure.is_absolute()
                or not pure.parts
                or any(part in {"", ".", ".."} for part in pure.parts)
            ):
                raise VerificationError(f"unsafe archive member: {member.name!r}")
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise VerificationError(f"unsupported archive member type: {member.name!r}")
            roots.add(pure.parts[0])
            if member.isdir():
                directory_members.append(member.name)
                continue
            if not member.isfile() or len(pure.parts) < 2:
                raise VerificationError(f"unexpected archive member: {member.name!r}")
            relative = PurePosixPath(*pure.parts[1:]).as_posix()
            if relative in member_by_relative:
                raise VerificationError(f"duplicate archive path: {relative}")
            member_by_relative[relative] = member
        if len(roots) != 1:
            raise VerificationError("archive must contain exactly one top-level directory")
        if directory_members:
            raise VerificationError(
                f"archive contains an unexpected directory member: {directory_members[0]!r}"
            )
        manifest_member = member_by_relative.get("release-manifest.json")
        if manifest_member is None:
            raise VerificationError("archive does not contain release-manifest.json")
        manifest_handle = archive.extractfile(manifest_member)
        if manifest_handle is None:
            raise VerificationError("cannot read release-manifest.json")
        manifest = parse_manifest(manifest_handle.read(), expected_version)
        archive_version = expected_version or manifest["version"]
        expected_root = f"mcgs-full-chain-studio-{archive_version}"
        actual_root = next(iter(roots))
        if actual_root != expected_root:
            raise VerificationError(
                f"archive top-level directory mismatch: actual={actual_root!r}, "
                f"expected={expected_root!r}"
            )
        enforce_path_policy(manifest, load_path_policy())

        expected_paths = {item["path"] for item in manifest["files"]}
        actual_paths = set(member_by_relative) - {"release-manifest.json"}
        if actual_paths != expected_paths:
            missing = sorted(expected_paths - actual_paths)
            extra = sorted(actual_paths - expected_paths)
            raise VerificationError(f"archive path mismatch; missing={missing[:5]}, extra={extra[:5]}")

        for item in manifest["files"]:
            member = member_by_relative[item["path"]]
            handle = archive.extractfile(member)
            if handle is None:
                raise VerificationError(f"cannot read {item['path']}")
            size, digest = digest_stream(handle)
            if size != item["size"] or digest != item["sha256"]:
                raise VerificationError(f"hash or size mismatch: {item['path']}")
    return manifest


def verify_tree(path: Path, expected_version: str | None) -> dict[str, Any]:
    root = path.resolve()
    manifest_path = root / "release-manifest.json"
    if not manifest_path.is_file():
        raise VerificationError("extracted tree does not contain release-manifest.json")
    manifest = parse_manifest(manifest_path.read_bytes(), expected_version)
    enforce_path_policy(manifest, load_path_policy())
    expected_paths = {item["path"] for item in manifest["files"]}
    actual_paths: set[str] = set()
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise VerificationError(
                f"symbolic link in extracted tree: {candidate.relative_to(root).as_posix()}"
            )
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root).as_posix()
        if relative != "release-manifest.json":
            actual_paths.add(relative)
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        raise VerificationError(f"tree path mismatch; missing={missing[:5]}, extra={extra[:5]}")
    for item in manifest["files"]:
        candidate = root.joinpath(*PurePosixPath(item["path"]).parts)
        with candidate.open("rb") as handle:
            size, digest = digest_stream(handle)
        if size != item["size"] or digest != item["sha256"]:
            raise VerificationError(f"hash or size mismatch: {item['path']}")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--expected-version")
    args = parser.parse_args(argv)
    try:
        path = args.candidate.resolve()
        manifest = (
            verify_tree(path, args.expected_version)
            if path.is_dir()
            else verify_archive(path, args.expected_version)
        )
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "passed",
                    "project": manifest["project"],
                    "version": manifest["version"],
                    "file_count": len(manifest["files"]),
                    "payload_bytes": sum(item["size"] for item in manifest["files"]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (OSError, VerificationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
