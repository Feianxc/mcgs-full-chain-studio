#!/usr/bin/env python3
"""Fail closed while probing an atomic-rename deployment boundary.

The calling deployment script must pass canonical directories whose complete
parent chains have already been established as root-trusted.  This helper then
binds the final directories and probe leaves to file descriptors, rejects
symlinks, uses only ``os.rename`` (never a copy fallback), and makes every
directory mutation durable with ``fsync``.

Every operational result is a compact JSON object containing only booleans and
integers.  In particular, errors never echo a caller-supplied path.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import secrets
import stat
from pathlib import Path
from typing import Sequence


SCHEMA_VERSION = 1
PROBE_PREFIX = ".atomic-rename-probe-"


def _error_number(error: BaseException) -> int:
    value = getattr(error, "errno", None)
    return value if type(value) is int and value > 0 else errno.EIO


def _require_secure_platform() -> None:
    required_flags = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    required_dir_fd_functions = (os.open, os.rename, os.stat, os.unlink)
    if (
        os.name != "posix"
        or any(not hasattr(os, name) for name in required_flags)
        or any(function not in os.supports_dir_fd for function in required_dir_fd_functions)
        or not hasattr(os, "fchmod")
    ):
        raise OSError(errno.ENOTSUP, "secure atomic rename is not supported")


def _canonical_absolute(path: Path) -> Path:
    if not path.is_absolute():
        raise OSError(errno.EINVAL, "path must be absolute")
    lexical = Path(os.path.abspath(os.fspath(path)))
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise OSError(_error_number(exc), "path cannot be resolved") from None
    if lexical != resolved:
        raise OSError(errno.ELOOP, "symbolic-link path is forbidden")
    return lexical


def _open_real_directory(path: Path) -> tuple[int, os.stat_result]:
    canonical = _canonical_absolute(path)
    before = os.lstat(canonical)
    if not stat.S_ISDIR(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise OSError(errno.ENOTDIR, "directory must be real")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(canonical, flags)
    try:
        after = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(after.st_mode)
            or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise OSError(getattr(errno, "ESTALE", errno.EIO), "directory changed")
        if (
            after.st_uid != os.geteuid()
            or after.st_gid != os.getegid()
            or stat.S_IMODE(after.st_mode) & 0o022
        ):
            raise OSError(errno.EPERM, "directory is not trusted by the control identity")
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, after


def _stat_leaf(directory_fd: int, name: str) -> os.stat_result:
    return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)


def _leaf_is_absent(directory_fd: int, name: str) -> bool:
    try:
        _stat_leaf(directory_fd, name)
    except FileNotFoundError:
        return True
    return False


def _fsync_directory(directory_fd: int) -> None:
    os.fsync(directory_fd)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "short probe write")
        offset += written


def _create_exclusive_file(
    directory_fd: int,
    name: str,
    payload: bytes,
    owned: set[tuple[int, int]],
) -> os.stat_result:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    try:
        value = os.fstat(descriptor)
        if not stat.S_ISREG(value.st_mode):
            raise OSError(errno.EPERM, "exclusive file is not regular")
        owned.add((value.st_dev, value.st_ino))
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        value = os.fstat(descriptor)
        if not stat.S_ISREG(value.st_mode) or stat.S_IMODE(value.st_mode) != 0o600:
            raise OSError(errno.EPERM, "exclusive file security check failed")
        return value
    finally:
        os.close(descriptor)


def _unlink_if_owned(
    directory_fd: int,
    name: str,
    owned: set[tuple[int, int]],
) -> bool:
    try:
        value = _stat_leaf(directory_fd, name)
    except FileNotFoundError:
        return True
    if not stat.S_ISREG(value.st_mode) or (value.st_dev, value.st_ino) not in owned:
        return False
    try:
        os.unlink(name, dir_fd=directory_fd)
    except FileNotFoundError:
        return True
    return _leaf_is_absent(directory_fd, name)


def _new_probe_names() -> tuple[str, str]:
    token = secrets.token_hex(16)
    return f"{PROBE_PREFIX}{token}.source", f"{PROBE_PREFIX}{token}.target"


def _record_close_error(
    descriptor: int | None,
    result: dict[str, bool | int],
) -> None:
    if descriptor is None:
        return
    try:
        os.close(descriptor)
    except OSError:
        if result["error_number"] == 0:
            result["error_number"] = errno.EIO


def probe(source_dir: Path, target_dir: Path) -> dict[str, bool | int]:
    result: dict[str, bool | int] = {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "error_number": 0,
        "same_device": False,
        "inode_preserved": False,
        "source_removed": False,
        "target_removed": False,
        "source_directory_synced": False,
        "target_directory_synced": False,
    }
    source_directory_fd: int | None = None
    target_directory_fd: int | None = None
    owned: set[tuple[int, int]] = set()
    source_name, target_name = _new_probe_names()
    renamed = False

    try:
        _require_secure_platform()
        source_directory_fd, source_directory_stat = _open_real_directory(source_dir)
        target_directory_fd, target_directory_stat = _open_real_directory(target_dir)
        result["same_device"] = (
            source_directory_stat.st_dev == target_directory_stat.st_dev
        )

        probe_stat = _create_exclusive_file(
            source_directory_fd,
            source_name,
            b"atomic-rename-probe-v1\n",
            owned,
        )
        _fsync_directory(source_directory_fd)

        if not _leaf_is_absent(target_directory_fd, target_name):
            raise OSError(errno.EEXIST, "probe target already exists")
        current_source = _stat_leaf(source_directory_fd, source_name)
        if (current_source.st_dev, current_source.st_ino) not in owned:
            raise OSError(getattr(errno, "ESTALE", errno.EIO), "probe source changed")

        os.rename(
            source_name,
            target_name,
            src_dir_fd=source_directory_fd,
            dst_dir_fd=target_directory_fd,
        )
        renamed = True
        moved = _stat_leaf(target_directory_fd, target_name)
        result["inode_preserved"] = (
            stat.S_ISREG(moved.st_mode)
            and (moved.st_dev, moved.st_ino) == (probe_stat.st_dev, probe_stat.st_ino)
        )
        if not result["inode_preserved"] or not _leaf_is_absent(
            source_directory_fd, source_name
        ):
            raise OSError(errno.EIO, "atomic rename identity check failed")
    except OSError as exc:
        result["error_number"] = _error_number(exc)
    except Exception:
        result["error_number"] = errno.EIO
    finally:
        cleanup_error = False
        if source_directory_fd is not None:
            try:
                result["source_removed"] = _unlink_if_owned(
                    source_directory_fd, source_name, owned
                )
            except OSError:
                cleanup_error = True
        if target_directory_fd is not None:
            try:
                result["target_removed"] = _unlink_if_owned(
                    target_directory_fd, target_name, owned
                )
            except OSError:
                cleanup_error = True
        if source_directory_fd is not None:
            try:
                _fsync_directory(source_directory_fd)
                result["source_directory_synced"] = True
            except OSError:
                cleanup_error = True
        if target_directory_fd is not None:
            try:
                _fsync_directory(target_directory_fd)
                result["target_directory_synced"] = True
            except OSError:
                cleanup_error = True
        if cleanup_error and result["error_number"] == 0:
            result["error_number"] = errno.EIO
        _record_close_error(source_directory_fd, result)
        _record_close_error(target_directory_fd, result)

    result["ok"] = bool(
        renamed
        and result["inode_preserved"]
        and result["source_removed"]
        and result["target_removed"]
        and result["source_directory_synced"]
        and result["target_directory_synced"]
        and result["error_number"] == 0
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe_parser = subparsers.add_parser("probe", help="prove an atomic rename boundary")
    probe_parser.add_argument("--source-dir", type=Path, required=True)
    probe_parser.add_argument("--target-dir", type=Path, required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = probe(args.source_dir, args.target_dir)
    except Exception:
        report = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "error_number": errno.EIO,
            "same_device": False,
            "inode_preserved": False,
            "source_removed": False,
            "target_removed": False,
            "source_directory_synced": False,
            "target_directory_synced": False,
        }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
