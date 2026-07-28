#!/usr/bin/env python3
"""Extract the verified source archive without traversal, links or devices."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Sequence


MAX_FILES = 20_000
MAX_TOTAL_BYTES = 500 * 1024 * 1024


class ExtractionError(RuntimeError):
    """The archive cannot be safely extracted."""


def safe_target(destination: Path, member_name: str) -> tuple[Path, PurePosixPath]:
    pure = PurePosixPath(member_name)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ExtractionError(f"unsafe archive path: {member_name!r}")
    if "\\" in member_name:
        raise ExtractionError(f"backslash in archive path: {member_name!r}")
    target = destination.joinpath(*pure.parts).resolve()
    try:
        target.relative_to(destination.resolve())
    except ValueError as exc:
        raise ExtractionError("archive member escapes destination") from exc
    return target, pure


def extract(archive_path: Path, destination: Path) -> str:
    if destination.exists() and any(destination.iterdir()):
        raise ExtractionError("destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    roots: set[str] = set()
    regular_files = 0
    total_bytes = 0
    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = archive.getmembers()
        if len(members) > MAX_FILES:
            raise ExtractionError("archive contains too many members")
        for member in members:
            target, pure = safe_target(destination, member.name)
            roots.add(pure.parts[0])
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ExtractionError(f"unsupported archive member type: {member.name!r}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ExtractionError(f"unexpected archive member: {member.name!r}")
            regular_files += 1
            total_bytes += member.size
            if regular_files > MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
                raise ExtractionError("archive exceeds extraction limits")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ExtractionError(f"cannot read archive member: {member.name!r}")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            os.chmod(target, 0o755 if member.mode & 0o111 else 0o644)
    if len(roots) != 1:
        raise ExtractionError("archive must have exactly one top-level directory")
    root_name = next(iter(roots))
    if not (destination / root_name).is_dir():
        raise ExtractionError("top-level archive entry is not a directory")
    return root_name


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        root_name = extract(args.archive.resolve(), args.destination.resolve())
        print(root_name)
        return 0
    except (OSError, tarfile.TarError, ExtractionError) as exc:
        print(f"safe extraction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
