#!/usr/bin/env python3
"""Verify manifest-listed source files in an installed release with a .venv."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Sequence


ALLOWED_RUNTIME_ROOTS = {".venv"}


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("--expected-version")
    args = parser.parse_args(argv)
    root = args.release.resolve()
    manifest_path = root / "release-manifest.json"
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or manifest.get("project") != "mcgs-full-chain-studio"
            or not isinstance(manifest.get("files"), list)
        ):
            raise ValueError("manifest root is invalid")
        if args.expected_version and manifest.get("version") != args.expected_version:
            errors.append("manifest version does not match expected version")
        expected: set[str] = set()
        expected_directories: set[str] = set()
        for index, item in enumerate(manifest["files"]):
            if (
                not isinstance(item, dict)
                or set(item) != {"path", "size", "sha256"}
                or not isinstance(item["path"], str)
                or not isinstance(item["size"], int)
                or isinstance(item["size"], bool)
                or not isinstance(item["sha256"], str)
            ):
                errors.append(f"manifest file entry {index} is invalid")
                continue
            pure = PurePosixPath(item["path"])
            if (
                pure.is_absolute()
                or ".." in pure.parts
                or "\\" in item["path"]
                or pure.as_posix() != item["path"]
            ):
                errors.append(f"unsafe manifest path at entry {index}")
                continue
            expected.add(item["path"])
            for parent in pure.parents:
                if parent != PurePosixPath("."):
                    expected_directories.add(parent.as_posix())
            candidate = root.joinpath(*pure.parts)
            if not candidate.is_file() or candidate.is_symlink():
                errors.append(f"missing or non-regular source file: {item['path']}")
                continue
            if candidate.stat().st_size != item["size"] or hash_file(candidate) != item["sha256"]:
                errors.append(f"source hash mismatch: {item['path']}")

        for candidate in root.rglob("*"):
            relative = candidate.relative_to(root)
            relative_text = relative.as_posix()
            if relative.parts and relative.parts[0] in ALLOWED_RUNTIME_ROOTS:
                continue
            if candidate.is_symlink():
                errors.append(f"unexpected source symbolic link: {relative_text}")
                continue
            if candidate.is_dir():
                if relative_text not in expected_directories:
                    errors.append(f"unexpected installed directory: {relative_text}")
                continue
            if relative_text == "release-manifest.json" or relative_text in expected:
                continue
            errors.append(f"unexpected installed file: {relative_text}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"verification error: {type(exc).__name__}: {exc}")

    report = {
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "version": manifest.get("version") if "manifest" in locals() and isinstance(manifest, dict) else None,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
