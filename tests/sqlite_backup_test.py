from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "deploy" / "sqlite_backup.py"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
STRING_FIELDS = ("basename", "sha256", "integrity_check", "schema_sha256")
INTEGER_FIELDS = (
    "size_bytes",
    "page_count",
    "page_size",
    "user_version",
    "schema_version",
    "application_id",
)
EXPECTED_FIELDS = frozenset((*STRING_FIELDS, *INTEGER_FIELDS))


def run_helper(*arguments: object) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-I", str(HELPER), *(str(value) for value in arguments)]
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=10.0,
    )


def load_helper_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "sqlite_backup_deadline_contract",
        HELPER,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load sqlite backup helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


class ExpiringHashDeadline:
    """Expire between fixed-size reads without depending on wall-clock timing."""

    def __init__(self, helper_module: object) -> None:
        self.helper_module = helper_module
        self.checks = 0

    def check(self) -> None:
        self.checks += 1
        if self.checks >= 4:
            raise self.helper_module.BackupFailure("deadline_exceeded")

    def expired(self) -> bool:
        return self.checks >= 4


def parse_success(
    process: subprocess.CompletedProcess[str],
    *,
    forbidden_path: Path,
) -> dict[str, object]:
    if process.returncode != 0:
        raise AssertionError(
            f"helper failed with {process.returncode}: {process.stderr!r}"
        )
    if process.stderr != "":
        raise AssertionError(f"successful helper call wrote stderr: {process.stderr!r}")
    if str(forbidden_path) in process.stdout:
        raise AssertionError("helper exposed an absolute path")
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError("helper stdout is not one strict JSON value") from exc
    if not isinstance(result, dict) or isinstance(result, list):
        raise AssertionError("helper stdout must be a JSON object")
    if set(result) != EXPECTED_FIELDS:
        raise AssertionError(f"unexpected result fields: {sorted(result)}")
    for field in STRING_FIELDS:
        if not isinstance(result[field], str):
            raise AssertionError(f"{field} must be a string")
    for field in INTEGER_FIELDS:
        if isinstance(result[field], bool) or not isinstance(result[field], int):
            raise AssertionError(f"{field} must be an integer, not a boolean")
    if result["integrity_check"] != "ok":
        raise AssertionError("integrity_check must be exactly 'ok'")
    if not SHA256_PATTERN.fullmatch(str(result["sha256"])):
        raise AssertionError("sha256 has the wrong shape")
    if not SHA256_PATTERN.fullmatch(str(result["schema_sha256"])):
        raise AssertionError("schema_sha256 has the wrong shape")
    if result["size_bytes"] < 0 or result["page_count"] < 0:
        raise AssertionError("database sizes cannot be negative")
    if result["page_size"] <= 0:
        raise AssertionError("page_size must be positive")
    return result


def parse_failure(
    process: subprocess.CompletedProcess[str],
    *,
    forbidden_path: Path,
) -> dict[str, object]:
    if process.returncode == 0:
        raise AssertionError("unsafe or invalid input was unexpectedly accepted")
    if process.stdout != "":
        raise AssertionError("failed helper call must not write stdout")
    if str(forbidden_path) in process.stderr:
        raise AssertionError("failed helper call exposed an absolute path")
    try:
        result = json.loads(process.stderr)
    except json.JSONDecodeError as exc:
        raise AssertionError("helper stderr is not one strict JSON value") from exc
    if not isinstance(result, dict) or set(result) != {"error"}:
        raise AssertionError("failure output has the wrong JSON contract")
    if not isinstance(result["error"], str) or not result["error"]:
        raise AssertionError("failure error code must be a non-empty string")
    return result


def create_fixture(path: Path, schema_count: int) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA user_version = 17")
        connection.execute("PRAGMA application_id = 1296258899")
        for index in range(schema_count):
            connection.execute(
                f'CREATE TABLE "fixture_{index}" '
                "(id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
            )
            connection.execute(
                f'INSERT INTO "fixture_{index}" (payload) VALUES (?)',
                ("ACCOUNT-CONTENT-MUST-NOT-LEAK",),
            )
        connection.commit()


def main() -> int:
    schema_hashes: list[str] = []
    symlink_checks = 0
    helper_module = load_helper_module()

    fake_clock = FakeClock()
    synthetic_deadline = helper_module.OperationDeadline(0.05, clock=fake_clock)
    if synthetic_deadline.sqlite_progress_handler() != 0:
        raise AssertionError("fresh SQLite progress handler requested interruption")
    fake_clock.advance(0.10)
    if synthetic_deadline.sqlite_progress_handler() != 1:
        raise AssertionError("expired SQLite progress handler did not interrupt")
    try:
        synthetic_deadline.backup_progress(0, 1, 1)
    except helper_module.BackupFailure as exc:
        if exc.code != "deadline_exceeded":
            raise AssertionError("backup callback returned the wrong deadline code")
    else:
        raise AssertionError("backup progress callback ignored an expired deadline")

    busy_clock = FakeClock()
    busy_deadline = helper_module.OperationDeadline(0.05, clock=busy_clock)
    recording_connection = RecordingConnection()
    helper_module._set_busy_timeout(recording_connection, busy_deadline)
    if len(recording_connection.statements) != 1:
        raise AssertionError("busy-timeout configuration was not singular")
    match = re.fullmatch(
        r"PRAGMA busy_timeout = ([0-9]+)",
        recording_connection.statements[0],
    )
    if match is None or int(match.group(1)) > 50:
        raise AssertionError("SQLite busy timeout exceeded remaining deadline")

    with tempfile.TemporaryDirectory(prefix="sqlite-backup-test-") as temporary:
        root = Path(temporary)

        hash_fixture = root / "deadline-hash-fixture.bin"
        hash_fixture.write_bytes(b"x" * (helper_module.BUFFER_SIZE + 1))
        hash_descriptor = os.open(hash_fixture, os.O_RDONLY)
        hash_deadline = ExpiringHashDeadline(helper_module)
        try:
            try:
                helper_module._hash_descriptor(hash_descriptor, hash_deadline)
            except helper_module.BackupFailure as exc:
                if exc.code != "deadline_exceeded":
                    raise AssertionError("hash deadline returned the wrong error code")
            else:
                raise AssertionError("hash loop did not check its deadline")
        finally:
            os.close(hash_descriptor)

        before_source = root / "deadline-before-publication-source.sqlite3"
        before_destination = root / "deadline-before-publication.sqlite3"
        create_fixture(before_source, 1)
        original_fsync_directory = helper_module._fsync_directory
        original_fsync_directory_unchecked = (
            helper_module._fsync_directory_unchecked
        )
        rollback_fsync_calls = 0

        def fail_before_publication(directory: Path, deadline: object) -> None:
            del directory, deadline
            raise helper_module.BackupFailure("deadline_exceeded")

        def record_rollback_fsync(directory: Path) -> None:
            nonlocal rollback_fsync_calls
            rollback_fsync_calls += 1
            original_fsync_directory_unchecked(directory)

        helper_module._fsync_directory = fail_before_publication
        helper_module._fsync_directory_unchecked = record_rollback_fsync
        try:
            try:
                helper_module.create_backup(
                    before_source,
                    before_destination,
                    helper_module.OperationDeadline(5.0),
                )
            except helper_module.BackupFailure as exc:
                if exc.code != "deadline_exceeded":
                    raise AssertionError(
                        "pre-publication deadline returned the wrong error code"
                    )
            else:
                raise AssertionError("pre-publication deadline was ignored")
        finally:
            helper_module._fsync_directory = original_fsync_directory
            helper_module._fsync_directory_unchecked = (
                original_fsync_directory_unchecked
            )
        if before_destination.exists() or before_destination.is_symlink():
            raise AssertionError("pre-publication deadline left a destination")
        if rollback_fsync_calls != 1:
            raise AssertionError("pre-publication rollback deletion was not fsynced")

        after_source = root / "deadline-after-publication-source.sqlite3"
        after_destination = root / "deadline-after-publication.sqlite3"
        create_fixture(after_source, 1)
        after_clock = FakeClock()
        after_cleanup_fsync_calls = 0

        def record_after_fsync(directory: Path) -> None:
            nonlocal after_cleanup_fsync_calls
            after_cleanup_fsync_calls += 1
            original_fsync_directory_unchecked(directory)

        def commit_then_expire(directory: Path, deadline: object) -> None:
            original_fsync_directory(directory, deadline)
            after_clock.advance(10.0)

        helper_module._fsync_directory_unchecked = record_after_fsync
        helper_module._fsync_directory = commit_then_expire
        try:
            try:
                helper_module.create_backup(
                    after_source,
                    after_destination,
                    helper_module.OperationDeadline(5.0, clock=after_clock),
                )
            except helper_module.BackupFailure as exc:
                if exc.code != "deadline_exceeded":
                    raise AssertionError(
                        "post-publication deadline returned the wrong error code"
                    )
            else:
                raise AssertionError("post-publication deadline was ignored")
        finally:
            helper_module._fsync_directory = original_fsync_directory
            helper_module._fsync_directory_unchecked = (
                original_fsync_directory_unchecked
            )
        if not after_destination.is_file() or after_destination.is_symlink():
            raise AssertionError("durably published destination was removed")
        after_inspect_process = run_helper("inspect", "--source", after_destination)
        after_inspect = parse_success(after_inspect_process, forbidden_path=root)
        if after_inspect["basename"] != after_destination.name:
            raise AssertionError("preserved destination could not be inspected")
        if after_cleanup_fsync_calls != 2:
            raise AssertionError("post-publication temporary cleanup was not fsynced")

        cleanup_source = root / "cleanup-failure-source.sqlite3"
        cleanup_destination = root / "cleanup-failure-preserved.sqlite3"
        create_fixture(cleanup_source, 1)
        cleanup_fsync_calls = 0

        def fail_post_publish_cleanup_fsync(directory: Path) -> None:
            nonlocal cleanup_fsync_calls
            cleanup_fsync_calls += 1
            if cleanup_fsync_calls == 2:
                raise helper_module.BackupFailure("publish_failed")
            original_fsync_directory_unchecked(directory)

        helper_module._fsync_directory_unchecked = fail_post_publish_cleanup_fsync
        try:
            try:
                helper_module.create_backup(
                    cleanup_source,
                    cleanup_destination,
                    helper_module.OperationDeadline(5.0),
                )
            except helper_module.BackupFailure as exc:
                if exc.code != "post_publish_cleanup_failed":
                    raise AssertionError(
                        "post-publication cleanup returned the wrong error code"
                    )
            else:
                raise AssertionError("post-publication cleanup failure was ignored")
        finally:
            helper_module._fsync_directory_unchecked = (
                original_fsync_directory_unchecked
            )
        if not cleanup_destination.is_file() or cleanup_destination.is_symlink():
            raise AssertionError("cleanup failure removed a published destination")
        cleanup_inspect_process = run_helper(
            "inspect",
            "--source",
            cleanup_destination,
        )
        parse_success(cleanup_inspect_process, forbidden_path=root)

        concurrent_source = root / "concurrent-replacement-source.sqlite3"
        concurrent_destination = root / "concurrent-replacement.sqlite3"
        displaced_destination = root / "concurrent-helper-backup.sqlite3"
        concurrent_sentinel = b"CONCURRENT DESTINATION MUST SURVIVE"
        create_fixture(concurrent_source, 1)

        def replace_before_failure(directory: Path, deadline: object) -> None:
            del directory, deadline
            concurrent_destination.replace(displaced_destination)
            concurrent_destination.write_bytes(concurrent_sentinel)
            raise helper_module.BackupFailure("deadline_exceeded")

        helper_module._fsync_directory = replace_before_failure
        try:
            try:
                helper_module.create_backup(
                    concurrent_source,
                    concurrent_destination,
                    helper_module.OperationDeadline(5.0),
                )
            except helper_module.BackupFailure as exc:
                if exc.code != "deadline_exceeded":
                    raise AssertionError(
                        "concurrent replacement returned the wrong error code"
                    )
            else:
                raise AssertionError("concurrent replacement failure was ignored")
        finally:
            helper_module._fsync_directory = original_fsync_directory
        if concurrent_destination.read_bytes() != concurrent_sentinel:
            raise AssertionError("concurrent destination was removed or modified")
        displaced_inspect_process = run_helper(
            "inspect",
            "--source",
            displaced_destination,
        )
        parse_success(displaced_inspect_process, forbidden_path=root)

        for schema_count in (0, 1, 4):
            source_name = (
                "源数据库-1.sqlite3"
                if schema_count == 1
                else f"source-{schema_count}.sqlite3"
            )
            destination_name = (
                "备份-1.sqlite3"
                if schema_count == 1
                else f"backup-{schema_count}.sqlite3"
            )
            source = root / source_name
            destination = root / destination_name
            create_fixture(source, schema_count)

            backup_process = run_helper(
                "backup",
                "--source",
                source,
                "--destination",
                destination,
            )
            backup = parse_success(backup_process, forbidden_path=root)
            if backup["basename"] != destination.name:
                raise AssertionError(
                    "backup report did not use the destination basename"
                )
            if backup["sha256"] != hashlib.sha256(destination.read_bytes()).hexdigest():
                raise AssertionError("backup SHA-256 does not match the published file")
            if backup["size_bytes"] != destination.stat().st_size:
                raise AssertionError("backup size does not match the published file")
            if backup["user_version"] != 17:
                raise AssertionError("user_version was not preserved")
            if backup["application_id"] != 1296258899:
                raise AssertionError("application_id was not preserved")
            if "ACCOUNT-CONTENT-MUST-NOT-LEAK" in backup_process.stdout:
                raise AssertionError("database content leaked into backup evidence")

            inspect_process = run_helper("inspect", "--source", destination)
            inspected = parse_success(inspect_process, forbidden_path=root)
            if inspected != backup:
                raise AssertionError("inspect evidence differs from backup evidence")

            verify_process = run_helper("verify", "--source", destination)
            verified = parse_success(verify_process, forbidden_path=root)
            if verified != backup:
                raise AssertionError("verify evidence differs from backup evidence")

            schema_hashes.append(str(backup["schema_sha256"]))

        if len(set(schema_hashes)) != 3:
            raise AssertionError("0/1/N schemas did not produce distinct schema hashes")

        live_source = root / "live-wal-source.sqlite3"
        live_destination = root / "live-wal-backup.sqlite3"
        live_connection = sqlite3.connect(live_source)
        try:
            live_connection.execute("PRAGMA journal_mode = WAL")
            live_connection.execute("PRAGMA wal_autocheckpoint = 0")
            live_connection.execute(
                "CREATE TABLE live_values (id INTEGER PRIMARY KEY, payload TEXT)"
            )
            live_connection.execute(
                "INSERT INTO live_values (payload) VALUES (?)",
                ("live-value-not-for-json",),
            )
            live_connection.commit()
            live_backup_process = run_helper(
                "backup",
                "--source",
                live_source,
                "--destination",
                live_destination,
            )
            live_backup = parse_success(live_backup_process, forbidden_path=root)
            if live_backup["basename"] != live_destination.name:
                raise AssertionError("live backup reported the wrong basename")
        finally:
            live_connection.close()
        with closing(sqlite3.connect(live_destination)) as backup_connection:
            live_value = backup_connection.execute(
                "SELECT payload FROM live_values WHERE id = 1"
            ).fetchone()
        if live_value != ("live-value-not-for-json",):
            raise AssertionError("online backup omitted a committed WAL value")
        if "live-value-not-for-json" in live_backup_process.stdout:
            raise AssertionError("online backup leaked a row value")

        source = root / "source-for-collisions.sqlite3"
        create_fixture(source, 1)
        existing_destination = root / "must-not-overwrite.sqlite3"
        sentinel = b"EXISTING DESTINATION MUST SURVIVE"
        existing_destination.write_bytes(sentinel)
        collision = run_helper(
            "backup",
            "--source",
            source,
            "--destination",
            existing_destination,
        )
        collision_error = parse_failure(collision, forbidden_path=root)
        if collision_error["error"] != "destination_exists":
            raise AssertionError("destination collision returned the wrong error code")
        if existing_destination.read_bytes() != sentinel:
            raise AssertionError("an existing destination was modified")

        invalid_deadline_checks = 0
        for invalid_deadline in ("nan", "inf", "0.01", "901"):
            invalid_deadline_process = run_helper(
                "inspect",
                "--source",
                source,
                "--deadline-seconds",
                invalid_deadline,
            )
            invalid_deadline_error = parse_failure(
                invalid_deadline_process,
                forbidden_path=root,
            )
            if invalid_deadline_error["error"] != "invalid_arguments":
                raise AssertionError("invalid deadline returned the wrong error code")
            invalid_deadline_checks += 1

        locked_source = root / "locked-source.sqlite3"
        locked_destination = root / "deadline-must-not-publish.sqlite3"
        create_fixture(locked_source, 1)
        lock_connection = sqlite3.connect(locked_source, timeout=0.0)
        try:
            lock_connection.execute("BEGIN EXCLUSIVE")
            deadline_started = time.monotonic()
            locked_backup = run_helper(
                "backup",
                "--source",
                locked_source,
                "--destination",
                locked_destination,
                "--deadline-seconds",
                "0.05",
            )
            deadline_elapsed = time.monotonic() - deadline_started
            locked_error = parse_failure(locked_backup, forbidden_path=root)
            if locked_error["error"] != "deadline_exceeded":
                raise AssertionError("persistent lock returned the wrong error code")
            if deadline_elapsed >= 2.0:
                raise AssertionError("persistent lock was not stopped by the deadline")
            if locked_destination.exists() or locked_destination.is_symlink():
                raise AssertionError("deadline failure published a destination")
        finally:
            lock_connection.rollback()
            lock_connection.close()

        damaged = root / "damaged.sqlite3"
        damaged.write_bytes(b"not a sqlite database\x00ACCOUNT-CONTENT-MUST-NOT-LEAK")
        damaged_inspect = run_helper("inspect", "--source", damaged)
        parse_failure(damaged_inspect, forbidden_path=root)
        if "ACCOUNT-CONTENT-MUST-NOT-LEAK" in damaged_inspect.stderr:
            raise AssertionError("damaged database content leaked into an error")

        damaged_destination = root / "damaged-backup-must-not-exist.sqlite3"
        damaged_backup = run_helper(
            "backup",
            "--source",
            damaged,
            "--destination",
            damaged_destination,
        )
        parse_failure(damaged_backup, forbidden_path=root)
        if damaged_destination.exists() or damaged_destination.is_symlink():
            raise AssertionError("a failed backup published a destination")

        directory_source = root / "directory-is-not-a-database"
        directory_source.mkdir()
        parse_failure(
            run_helper("inspect", "--source", directory_source),
            forbidden_path=root,
        )

        symlink_source = root / "source-link.sqlite3"
        symlink_destination = root / "destination-link.sqlite3"
        destination_target = root / "destination-link-target.sqlite3"
        destination_target.write_bytes(sentinel)
        try:
            os.symlink(source, symlink_source)
            os.symlink(destination_target, symlink_destination)
        except (NotImplementedError, OSError):
            pass
        else:
            source_link_failure = run_helper("inspect", "--source", symlink_source)
            source_link_error = parse_failure(source_link_failure, forbidden_path=root)
            if source_link_error["error"] != "source_not_regular":
                raise AssertionError("source symlink returned the wrong error code")
            destination_link_failure = run_helper(
                "backup",
                "--source",
                source,
                "--destination",
                symlink_destination,
            )
            destination_link_error = parse_failure(
                destination_link_failure,
                forbidden_path=root,
            )
            if destination_link_error["error"] != "destination_exists":
                raise AssertionError(
                    "destination symlink returned the wrong error code"
                )
            if destination_target.read_bytes() != sentinel:
                raise AssertionError("destination symlink target was modified")
            symlink_checks = 2

        temporary_artifacts = [
            path for path in root.rglob("*") if ".sqlite-backup-tmp" in path.name
        ]
        if temporary_artifacts:
            raise AssertionError("handled failures left temporary backup files")

    report = {
        "status": "passed",
        "schema_cardinalities": [0, 1, 4],
        "successful_backups": 4,
        "online_wal_backup": True,
        "failure_cases": 9 + invalid_deadline_checks + symlink_checks,
        "deadline_checks": 7,
        "publication_boundary_checks": 4,
        "preserved_published_backups": 3,
        "invalid_deadline_checks": invalid_deadline_checks,
        "symlink_checks": symlink_checks,
    }
    if not isinstance(report["schema_cardinalities"], list):
        raise AssertionError("schema cardinalities must remain a JSON array")
    if isinstance(report["symlink_checks"], bool):
        raise AssertionError("symlink check count must remain a JSON number")
    if isinstance(report["deadline_checks"], bool):
        raise AssertionError("deadline check count must remain a JSON number")
    if isinstance(report["publication_boundary_checks"], bool):
        raise AssertionError("publication boundary count must remain a JSON number")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
