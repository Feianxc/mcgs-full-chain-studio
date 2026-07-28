#!/usr/bin/env python3
"""Build a deterministic, allowlist-only source release archive."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = Path(__file__).resolve().with_name("release-allowlist.json")
VERSION_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}\Z")


class ReleaseError(RuntimeError):
    """A bounded, user-facing release validation failure."""


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReleaseError(f"{path.name} root must be an object")
    return value


def validate_relative(value: str) -> PurePosixPath:
    if "\\" in value:
        raise ReleaseError(f"allowlist path must use POSIX separators: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ReleaseError(f"unsafe allowlist path: {value!r}")
    return pure


def ensure_inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ReleaseError("allowlisted path resolves outside the source root") from exc
    return resolved


def collect_files(root: Path, policy: dict[str, Any]) -> list[Path]:
    required_keys = {
        "schema_version",
        "project",
        "files",
        "trees",
        "excluded_names",
        "excluded_parts",
        "forbidden_parts",
        "forbidden_suffixes",
    }
    if set(policy) != required_keys:
        missing = sorted(required_keys - set(policy))
        extra = sorted(set(policy) - required_keys)
        raise ReleaseError(f"allowlist keys mismatch; missing={missing}, extra={extra}")
    if policy["schema_version"] != 1 or policy["project"] != "mcgs-full-chain-studio":
        raise ReleaseError("unsupported allowlist schema or project")
    list_keys = (
        "files",
        "trees",
        "excluded_names",
        "excluded_parts",
        "forbidden_parts",
        "forbidden_suffixes",
    )
    for key in list_keys:
        if not isinstance(policy[key], list) or not all(
            isinstance(item, str) and item for item in policy[key]
        ):
            raise ReleaseError(f"{key} must be a non-empty-string array")
        if len(policy[key]) != len(set(policy[key])):
            raise ReleaseError(f"{key} must not contain duplicates")

    for key in ("excluded_names", "excluded_parts", "forbidden_parts"):
        if any("/" in item or "\\" in item or item in {".", ".."} for item in policy[key]):
            raise ReleaseError(f"{key} entries must be single safe path components")
    if any(
        not item.startswith(".") or item != item.lower()
        for item in policy["forbidden_suffixes"]
    ):
        raise ReleaseError("forbidden_suffixes entries must be lowercase dot suffixes")

    excluded_names = set(policy["excluded_names"])
    excluded_parts = {item.lower() for item in policy["excluded_parts"]}
    forbidden_parts = {item.lower() for item in policy["forbidden_parts"]}
    forbidden_suffixes = {item.lower() for item in policy["forbidden_suffixes"]}
    selected: dict[str, Path] = {}

    def inspect(path: Path) -> tuple[Path, PurePosixPath] | None:
        # Check the directory entry before resolving it. Resolving first would
        # silently turn an in-tree symlink into a regular target path.
        if path.is_symlink():
            relative_hint = PurePosixPath(*path.relative_to(root).parts).as_posix()
            raise ReleaseError(f"symbolic links are forbidden: {relative_hint}")
        ensure_inside(root, path)
        relative = PurePosixPath(*path.relative_to(root).parts)
        relative_text = relative.as_posix()
        if path.name in excluded_names:
            return None
        if any(part.lower() in excluded_parts for part in relative.parts):
            return None
        blocked = sorted(
            part for part in relative.parts if part.lower() in forbidden_parts
        )
        if blocked:
            raise ReleaseError(
                f"private or mutable artifact path is forbidden: {relative_text}"
            )
        if path.suffix.lower() in forbidden_suffixes:
            raise ReleaseError(f"forbidden file type is allowlisted: {relative_text}")
        if relative.is_absolute() or ".." in relative.parts or "\\" in relative_text:
            raise ReleaseError(f"unsafe relative path: {relative_text}")
        return path, relative

    def consider(path: Path) -> None:
        inspected = inspect(path)
        if inspected is None:
            return
        path, relative = inspected
        relative_text = relative.as_posix()
        if not path.is_file():
            raise ReleaseError(f"allowlisted path is not a regular file: {relative_text}")
        selected[relative_text] = path

    for value in policy["files"]:
        relative = validate_relative(value)
        path = root.joinpath(*relative.parts)
        if path.is_symlink():
            raise ReleaseError(f"symbolic links are forbidden: {relative.as_posix()}")
        if not path.is_file():
            raise ReleaseError(f"required release file is missing: {relative.as_posix()}")
        consider(path)

    for value in policy["trees"]:
        relative = validate_relative(value)
        tree = root.joinpath(*relative.parts)
        if tree.is_symlink():
            raise ReleaseError(f"symbolic links are forbidden: {relative.as_posix()}")
        ensure_inside(root, tree)
        if not tree.is_dir():
            raise ReleaseError(f"required release tree is missing: {relative.as_posix()}")
        for current, directory_names, file_names in os.walk(
            tree, topdown=True, followlinks=False
        ):
            current_path = Path(current)
            retained: list[str] = []
            for name in sorted(directory_names):
                candidate = current_path / name
                inspected = inspect(candidate)
                if inspected is not None:
                    retained.append(name)
            directory_names[:] = retained
            for name in sorted(file_names):
                consider(current_path / name)

    return [selected[key] for key in sorted(selected)]


def relative_text(root: Path, path: Path) -> str:
    return PurePosixPath(*path.relative_to(root).parts).as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_epoch() -> int:
    raw = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if not raw:
        return int(datetime.now(timezone.utc).timestamp())
    try:
        value = int(raw)
    except ValueError as exc:
        raise ReleaseError("SOURCE_DATE_EPOCH must be an integer") from exc
    if value < 0:
        raise ReleaseError("SOURCE_DATE_EPOCH must not be negative")
    return value


def build_manifest(root: Path, files: Sequence[Path], version: str, epoch: int) -> dict[str, Any]:
    entries = [
        {
            "path": relative_text(root, path),
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in files
    ]
    return {
        "schema_version": 1,
        "project": "mcgs-full-chain-studio",
        "version": version,
        "created_at": datetime.fromtimestamp(epoch, timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "source_date_epoch": epoch,
        "files": entries,
    }


def tar_mode(path: str) -> int:
    return 0o755 if path.endswith(".sh") or path.startswith("scripts/") else 0o644


def add_bytes(archive: tarfile.TarFile, name: str, payload: bytes, epoch: int, mode: int) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mtime = epoch
    info.mode = mode
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    archive.addfile(info, io.BytesIO(payload))


def write_archive(
    root: Path,
    files: Sequence[Path],
    manifest: dict[str, Any],
    output: Path,
) -> None:
    prefix = f"mcgs-full-chain-studio-{manifest['version']}"
    epoch = int(manifest["source_date_epoch"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_handle = tempfile.NamedTemporaryFile(
        mode="wb",
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(temporary_handle.name)
    temporary_handle.close()
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as zipped:
                with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for path in files:
                        relative = relative_text(root, path)
                        add_bytes(
                            archive,
                            f"{prefix}/{relative}",
                            path.read_bytes(),
                            epoch,
                            tar_mode(relative),
                        )
                    manifest_bytes = (
                        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                    ).encode("utf-8")
                    add_bytes(
                        archive,
                        f"{prefix}/release-manifest.json",
                        manifest_bytes,
                        epoch,
                        0o644,
                    )
        os.replace(temporary, output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def run_privacy_gate(root: Path, files: Sequence[Path]) -> None:
    sys.path.insert(0, str(root))
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        from scripts.check_public_tree import load_deny_tokens, scan_paths
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        sys.path.pop(0)
    deny_tokens = load_deny_tokens(root, None)
    findings = scan_paths(root, files, deny_tokens=deny_tokens)
    if findings:
        preview = "; ".join(
            f"{item.code}:{item.path}:{item.detail}" for item in findings[:10]
        )
        suffix = "" if len(findings) <= 10 else f"; plus {len(findings) - 10} more"
        raise ReleaseError(f"privacy gate failed: {preview}{suffix}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--allowlist", type=Path, default=ALLOWLIST_PATH)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)

    if not VERSION_PATTERN.fullmatch(args.version):
        print("error: invalid release version", file=sys.stderr)
        return 2
    root = args.root.resolve()
    if not root.is_dir():
        print("error: source root is not a directory", file=sys.stderr)
        return 2

    try:
        policy = read_json_object(args.allowlist.resolve())
        files = collect_files(root, policy)
        run_privacy_gate(root, files)
        epoch = source_epoch()
        manifest = build_manifest(root, files, args.version, epoch)
        if any(
            PurePosixPath(item["path"]).is_absolute()
            or "\\" in item["path"]
            or ".." in PurePosixPath(item["path"]).parts
            for item in manifest["files"]
        ):
            raise ReleaseError("manifest contains a non-relative path")

        summary = {
            "schema_version": 1,
            "status": "passed",
            "mode": "check-only" if args.check_only else "built",
            "version": args.version,
            "file_count": len(files),
            "payload_bytes": sum(item["size"] for item in manifest["files"]),
        }
        if args.check_only:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0

        output_dir = (args.output_dir or root / "dist").resolve()
        output = output_dir / f"mcgs-full-chain-studio-{args.version}.tar.gz"
        write_archive(root, files, manifest, output)
        digest = sha256_file(output)
        checksum = output.with_suffix(output.suffix + ".sha256")
        checksum.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
        summary.update(
            {
                "archive": output.name,
                "archive_sha256": digest,
                "checksum_file": checksum.name,
            }
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ReleaseError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
