#!/usr/bin/env python3
"""Create and verify self-contained SQLite backups without exposing their data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import stat
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import NoReturn


BUFFER_SIZE = 1024 * 1024
DEFAULT_DEADLINE_SECONDS = 300.0
MIN_DEADLINE_SECONDS = 0.05
MAX_DEADLINE_SECONDS = 900.0
MAX_SQLITE_BUSY_SECONDS = 30.0
SQLITE_PROGRESS_OPCODES = 1000
BACKUP_PAGES_PER_STEP = 256
BACKUP_BUSY_SLEEP_SECONDS = 0.01
INTEGER_PRAGMAS = (
    "page_count",
    "page_size",
    "user_version",
    "schema_version",
    "application_id",
)


class BackupFailure(Exception):
    """A failure that is safe to identify without including filesystem paths."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OperationDeadline:
    """One monotonic deadline shared by every phase of a helper command."""

    def __init__(
        self,
        seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(float(seconds))
            or float(seconds) < MIN_DEADLINE_SECONDS
            or float(seconds) > MAX_DEADLINE_SECONDS
        ):
            raise BackupFailure("invalid_arguments")
        self._clock = clock
        started = self._clock()
        if not math.isfinite(started):
            raise BackupFailure("operation_failed")
        self._expires_at = started + float(seconds)

    def expired(self) -> bool:
        return self._clock() >= self._expires_at

    def check(self) -> None:
        if self.expired():
            raise BackupFailure("deadline_exceeded")

    def remaining_seconds(self) -> float:
        remaining = self._expires_at - self._clock()
        if remaining <= 0:
            raise BackupFailure("deadline_exceeded")
        return remaining

    def sqlite_progress_handler(self) -> int:
        """Return non-zero to let SQLite interrupt the active virtual machine."""

        return 1 if self.expired() else 0

    def backup_progress(self, status: int, remaining: int, total: int) -> None:
        """Abort Connection.backup between bounded page-copy steps."""

        del status, remaining, total
        self.check()


class JsonArgumentParser(argparse.ArgumentParser):
    """Keep malformed CLI input on the same machine-readable error channel."""

    def error(self, message: str) -> NoReturn:  # noqa: ARG002 - argparse contract
        raise BackupFailure("invalid_arguments")


def _absolute_path(path: Path) -> Path:
    """Make a path absolute without following its final symlink."""

    try:
        return Path(os.path.abspath(os.fspath(path)))
    except (OSError, TypeError, ValueError) as exc:
        raise BackupFailure("invalid_path") from exc


def _same_file(first: os.stat_result, second: os.stat_result) -> bool:
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _path_stat(path: Path, *, failure_code: str) -> os.stat_result:
    try:
        value = path.lstat()
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise BackupFailure(failure_code) from exc
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise BackupFailure(failure_code)
    return value


def _open_regular_readonly(
    path: Path,
    deadline: OperationDeadline,
) -> tuple[int, os.stat_result, Path]:
    """Open and pin a regular, non-symlink file for later identity checks."""

    deadline.check()
    absolute = _absolute_path(path)
    before = _path_stat(absolute, failure_code="source_not_regular")
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except (OSError, ValueError) as exc:
        raise BackupFailure("source_not_regular") from exc
    try:
        deadline.check()
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_file(before, opened):
            raise BackupFailure("source_changed")
        resolved = absolute.resolve(strict=True)
        resolved_stat = _path_stat(resolved, failure_code="source_not_regular")
        if not _same_file(opened, resolved_stat):
            raise BackupFailure("source_changed")
        deadline.check()
        return descriptor, opened, resolved
    except Exception:
        os.close(descriptor)
        raise


def _assert_path_identity(
    path: Path,
    expected: os.stat_result,
    *,
    failure_code: str,
) -> None:
    current = _path_stat(path, failure_code=failure_code)
    if not _same_file(expected, current):
        raise BackupFailure(failure_code)


def _readonly_uri(path: Path, *, immutable: bool) -> str:
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    try:
        return path.as_uri() + suffix
    except ValueError as exc:
        raise BackupFailure("invalid_path") from exc


def _set_busy_timeout(
    connection: sqlite3.Connection,
    deadline: OperationDeadline,
) -> None:
    """Bound SQLite's lock wait to the time remaining in this operation."""

    remaining = min(MAX_SQLITE_BUSY_SECONDS, deadline.remaining_seconds())
    # SQLite accepts only whole milliseconds. Flooring is important: the
    # connection-level wait must never be longer than the remaining deadline.
    milliseconds = int(remaining * 1000)
    connection.execute(f"PRAGMA busy_timeout = {milliseconds}")
    deadline.check()


def _configure_connection(
    connection: sqlite3.Connection,
    deadline: OperationDeadline,
    *,
    query_only: bool,
) -> None:
    _set_busy_timeout(connection, deadline)
    connection.set_progress_handler(
        deadline.sqlite_progress_handler,
        SQLITE_PROGRESS_OPCODES,
    )
    if query_only:
        connection.execute("PRAGMA query_only = ON")
    deadline.check()


def _connect_readonly(
    path: Path,
    *,
    immutable: bool,
    deadline: OperationDeadline,
) -> sqlite3.Connection:
    timeout = min(MAX_SQLITE_BUSY_SECONDS, deadline.remaining_seconds())
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            _readonly_uri(path, immutable=immutable),
            uri=True,
            timeout=timeout,
        )
        _configure_connection(connection, deadline, query_only=True)
        return connection
    except Exception:
        if connection is not None:
            connection.close()
        raise


def _connect_writable(
    path: Path,
    deadline: OperationDeadline,
) -> sqlite3.Connection:
    timeout = min(MAX_SQLITE_BUSY_SECONDS, deadline.remaining_seconds())
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(path, timeout=timeout)
        _configure_connection(connection, deadline, query_only=False)
        return connection
    except Exception:
        if connection is not None:
            connection.close()
        raise


def _execute(
    connection: sqlite3.Connection,
    statement: str,
    deadline: OperationDeadline,
) -> sqlite3.Cursor:
    deadline.check()
    _set_busy_timeout(connection, deadline)
    try:
        cursor = connection.execute(statement)
    except sqlite3.Error as exc:
        if deadline.expired():
            raise BackupFailure("deadline_exceeded") from exc
        raise
    deadline.check()
    return cursor


def _fetchone(
    cursor: sqlite3.Cursor,
    deadline: OperationDeadline,
) -> tuple[object, ...] | None:
    deadline.check()
    try:
        row = cursor.fetchone()
    except sqlite3.Error as exc:
        if deadline.expired():
            raise BackupFailure("deadline_exceeded") from exc
        raise
    deadline.check()
    return row


def _pragma_integer(
    connection: sqlite3.Connection,
    name: str,
    deadline: OperationDeadline,
) -> int:
    if name not in INTEGER_PRAGMAS:
        raise BackupFailure("verification_failed")
    cursor = _execute(connection, f"PRAGMA {name}", deadline)
    try:
        row = _fetchone(cursor, deadline)
    finally:
        cursor.close()
    if (
        row is None
        or len(row) != 1
        or isinstance(row[0], bool)
        or not isinstance(row[0], int)
    ):
        raise BackupFailure("verification_failed")
    return row[0]


def _schema_sha256(
    connection: sqlite3.Connection,
    deadline: OperationDeadline,
) -> str:
    cursor = _execute(
        connection,
        "SELECT type, name, tbl_name, sql FROM sqlite_schema "
        "ORDER BY type COLLATE BINARY, name COLLATE BINARY, "
        "tbl_name COLLATE BINARY, sql COLLATE BINARY",
        deadline,
    )
    digest = hashlib.sha256()
    digest.update(b"[")
    first = True
    try:
        while True:
            row = _fetchone(cursor, deadline)
            if row is None:
                break
            if len(row) != 4 or any(
                value is not None and not isinstance(value, str) for value in row
            ):
                raise BackupFailure("verification_failed")
            if not first:
                digest.update(b",")
            digest.update(
                json.dumps(
                    list(row),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            deadline.check()
            first = False
    finally:
        cursor.close()
    digest.update(b"]")
    deadline.check()
    return digest.hexdigest()


def _database_metadata(
    connection: sqlite3.Connection,
    deadline: OperationDeadline,
) -> dict[str, int | str]:
    integrity_cursor = _execute(connection, "PRAGMA integrity_check", deadline)
    try:
        integrity_row = _fetchone(integrity_cursor, deadline)
        extra_row = _fetchone(integrity_cursor, deadline)
    finally:
        integrity_cursor.close()
    if integrity_row != ("ok",) or extra_row is not None:
        raise BackupFailure("integrity_check_failed")
    result: dict[str, int | str] = {
        "integrity_check": "ok",
        "schema_sha256": _schema_sha256(connection, deadline),
    }
    for name in INTEGER_PRAGMAS:
        deadline.check()
        result[name] = _pragma_integer(connection, name, deadline)
    return result


def _hash_descriptor(
    descriptor: int,
    deadline: OperationDeadline,
) -> tuple[str, int]:
    try:
        deadline.check()
        os.lseek(descriptor, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        size = 0
        while True:
            deadline.check()
            chunk = os.read(descriptor, BUFFER_SIZE)
            deadline.check()
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        deadline.check()
        current_size = os.fstat(descriptor).st_size
    except OSError as exc:
        if deadline.expired():
            raise BackupFailure("deadline_exceeded") from exc
        raise BackupFailure("verification_failed") from exc
    if isinstance(size, bool) or size != current_size:
        raise BackupFailure("source_changed")
    return digest.hexdigest(), size


def inspect_database(
    source: Path,
    deadline: OperationDeadline,
) -> dict[str, int | str]:
    """Verify one self-contained SQLite file and return its non-secret evidence."""

    descriptor, identity, resolved = _open_regular_readonly(source, deadline)
    try:
        with closing(
            _connect_readonly(
                resolved,
                immutable=True,
                deadline=deadline,
            )
        ) as connection:
            metadata = _database_metadata(connection, deadline)
        deadline.check()
        _assert_path_identity(resolved, identity, failure_code="source_changed")
        sha256, size_bytes = _hash_descriptor(descriptor, deadline)
        _assert_path_identity(resolved, identity, failure_code="source_changed")
        deadline.check()
        return {
            "basename": resolved.name,
            "sha256": sha256,
            "size_bytes": size_bytes,
            **metadata,
        }
    except BackupFailure:
        raise
    except (OSError, sqlite3.Error, UnicodeError, ValueError) as exc:
        if deadline.expired():
            raise BackupFailure("deadline_exceeded") from exc
        raise BackupFailure("verification_failed") from exc
    finally:
        os.close(descriptor)


def _validate_destination(
    destination: Path,
    deadline: OperationDeadline,
) -> tuple[Path, Path]:
    deadline.check()
    absolute = _absolute_path(destination)
    try:
        absolute.lstat()
    except FileNotFoundError:
        pass
    except (NotADirectoryError, OSError) as exc:
        raise BackupFailure("invalid_destination") from exc
    else:
        raise BackupFailure("destination_exists")

    parent = absolute.parent
    try:
        parent_stat = parent.lstat()
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        raise BackupFailure("invalid_destination") from exc
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise BackupFailure("invalid_destination")
    try:
        resolved_parent = parent.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BackupFailure("invalid_destination") from exc
    deadline.check()
    return absolute, resolved_parent


def _safe_unlink(path: Path, expected: os.stat_result | None) -> bool:
    if expected is None:
        return False
    try:
        current = path.lstat()
    except (FileNotFoundError, NotADirectoryError, OSError):
        return False
    if stat.S_ISREG(current.st_mode) and _same_file(expected, current):
        try:
            path.unlink()
        except OSError:
            return False
        return True
    return False


def _fsync_directory_unchecked(directory: Path) -> None:
    """Persist a directory mutation; callers define the deadline boundary."""

    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise BackupFailure("publish_failed") from exc


def _fsync_directory(directory: Path, deadline: OperationDeadline) -> None:
    deadline.check()
    _fsync_directory_unchecked(directory)


def create_backup(
    source: Path,
    destination: Path,
    deadline: OperationDeadline,
) -> dict[str, int | str]:
    """Create, verify, and atomically publish an online SQLite backup."""

    destination_absolute, destination_parent = _validate_destination(
        destination,
        deadline,
    )
    source_descriptor, source_identity, source_resolved = _open_regular_readonly(
        source,
        deadline,
    )
    temporary_path: Path | None = None
    temporary_identity: os.stat_result | None = None
    destination_created = False
    publication_committed = False
    try:
        deadline.check()
        try:
            temporary_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination_absolute.name}.",
                suffix=".sqlite-backup-tmp",
                dir=destination_parent,
            )
        except OSError as exc:
            raise BackupFailure("invalid_destination") from exc
        temporary_path = Path(temporary_name)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(temporary_descriptor, 0o600)
            temporary_identity = os.fstat(temporary_descriptor)
        finally:
            os.close(temporary_descriptor)
        deadline.check()

        try:
            with closing(
                _connect_readonly(
                    source_resolved,
                    immutable=False,
                    deadline=deadline,
                )
            ) as source_connection:
                with closing(
                    _connect_writable(temporary_path, deadline)
                ) as target_connection:
                    _set_busy_timeout(source_connection, deadline)
                    _set_busy_timeout(target_connection, deadline)
                    source_connection.backup(
                        target_connection,
                        pages=BACKUP_PAGES_PER_STEP,
                        progress=deadline.backup_progress,
                        sleep=BACKUP_BUSY_SLEEP_SECONDS,
                    )
                    deadline.check()
            _assert_path_identity(
                source_resolved,
                source_identity,
                failure_code="source_changed",
            )
            _assert_path_identity(
                temporary_path,
                temporary_identity,
                failure_code="verification_failed",
            )
        except BackupFailure:
            raise
        except (OSError, sqlite3.Error, ValueError) as exc:
            if deadline.expired():
                raise BackupFailure("deadline_exceeded") from exc
            raise BackupFailure("backup_failed") from exc

        evidence = inspect_database(temporary_path, deadline)
        if evidence["integrity_check"] != "ok":
            raise BackupFailure("integrity_check_failed")

        try:
            deadline.check()
            # Windows requires a writable handle for fsync/FlushFileBuffers.
            with temporary_path.open("r+b") as handle:
                os.fsync(handle.fileno())
            deadline.check()
            os.link(
                temporary_path,
                destination_absolute,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise BackupFailure("destination_exists") from exc
        except OSError as exc:
            raise BackupFailure("publish_failed") from exc
        destination_created = True
        _assert_path_identity(
            destination_absolute,
            temporary_identity,
            failure_code="publish_failed",
        )
        # Publication commits only after the complete hard link has been
        # identity-checked and its parent directory has been persisted. A
        # deadline observed after this point must preserve the valid backup.
        _fsync_directory(destination_parent, deadline)
        publication_committed = True
        deadline.check()

        try:
            temporary_path.unlink()
        except OSError as exc:
            raise BackupFailure("post_publish_cleanup_failed") from exc
        try:
            # Once the helper removes a directory entry, persist that deletion
            # even if the monotonic deadline expires during the fsync syscall.
            _fsync_directory_unchecked(destination_parent)
        except BackupFailure as exc:
            raise BackupFailure("post_publish_cleanup_failed") from exc
        deadline.check()

        evidence["basename"] = destination_absolute.name
        deadline.check()
        return evidence
    finally:
        os.close(source_descriptor)
        directory_changed = False
        if temporary_path is not None:
            directory_changed = _safe_unlink(
                temporary_path,
                temporary_identity,
            )
        # Before the durable publication commit, failures must not leave our
        # destination. After commit, preserve the complete backup even when
        # hidden-temporary cleanup, its fsync, or result return later fails.
        if destination_created and not publication_committed:
            directory_changed = (
                _safe_unlink(destination_absolute, temporary_identity)
                or directory_changed
            )
        if directory_changed:
            try:
                _fsync_directory_unchecked(destination_parent)
            except BackupFailure as exc:
                code = (
                    "post_publish_cleanup_failed"
                    if publication_committed
                    else "publish_failed"
                )
                raise BackupFailure(code) from exc


def _deadline_seconds_argument(value: str) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("invalid deadline") from exc
    if (
        not math.isfinite(seconds)
        or seconds < MIN_DEADLINE_SECONDS
        or seconds > MAX_DEADLINE_SECONDS
    ):
        raise argparse.ArgumentTypeError("invalid deadline")
    return seconds


def _add_deadline_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--deadline-seconds",
        type=_deadline_seconds_argument,
        default=DEFAULT_DEADLINE_SECONDS,
        metavar="SECONDS",
        help=(
            "total operation deadline "
            f"({MIN_DEADLINE_SECONDS:g}-{MAX_DEADLINE_SECONDS:g}; "
            f"default {DEFAULT_DEADLINE_SECONDS:g})"
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser(
        "backup",
        help="create and verify a new online backup",
    )
    backup_parser.add_argument("--source", type=Path, required=True)
    backup_parser.add_argument("--destination", type=Path, required=True)
    _add_deadline_argument(backup_parser)

    for command in ("inspect", "verify"):
        inspect_parser = subparsers.add_parser(
            command,
            help="inspect and verify an existing self-contained backup",
        )
        inspect_parser.add_argument("--source", type=Path, required=True)
        _add_deadline_argument(inspect_parser)
    return parser


def _configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_output()
    try:
        args = _parser().parse_args(argv)
        deadline = OperationDeadline(args.deadline_seconds)
        if args.command == "backup":
            result = create_backup(args.source, args.destination, deadline)
        else:
            result = inspect_database(args.source, deadline)
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except BackupFailure as exc:
        print(
            json.dumps(
                {"error": exc.code},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2
    except (OSError, sqlite3.Error, UnicodeError, ValueError):
        print('{"error":"operation_failed"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
