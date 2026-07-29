from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "deploy" / "runtime_fingerprint.py"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MODE_PATTERN = re.compile(r"^[0-7]{4}$")
EXPECTED_FIELDS = frozenset(
    {
        "schema_version",
        "runtime_root_sha256",
        "release_root_sha256",
        "requirements_lock_sha256",
        "interpreter",
        "distributions",
        "distributions_sha256",
    }
)
EXPECTED_INTERPRETER_FIELDS = frozenset(
    {"realpath", "sha256", "mode", "uid", "gid"}
)
EXPECTED_VERIFY_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "release_id",
        "version",
        "release_manifest_sha256",
        "runtime_fingerprint_sha256",
        "baseline_sha256",
        "runtime_guard_helper_sha256",
    }
)
BASELINE_FIELDS = frozenset(
    {
        "schema_version",
        "project",
        "release_id",
        "version",
        "release_root",
        "archive_sha256",
        "release_manifest_sha256",
        "runtime_guard_helper_sha256",
        "runtime_fingerprint",
    }
)
PROJECT = "mcgs-full-chain-studio"
RELEASE_ID = "20260729-runtime-guard"
VERSION = "0.1.1"
ARCHIVE_SHA256 = "a" * 64


def run_helper(
    runtime_root: Path,
    interpreter: Path,
    *,
    lock: Path | None = None,
    release_root: Path | None = None,
    require_root_owned_immutable: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-I",
        "-B",
        str(HELPER),
        "--runtime-root",
        str(runtime_root),
        "--python",
        str(interpreter),
    ]
    if lock is not None:
        command.extend(("--lock", str(lock)))
    if release_root is not None:
        command.extend(("--release-root", str(release_root)))
    if require_root_owned_immutable:
        command.append("--require-root-owned-immutable")
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )


def run_verify_current(
    current_link: Path,
    releases_root: Path,
    baseline_directory: Path,
    *,
    expected_manifest_sha256: str | None = None,
    require_root_owned_immutable: bool = False,
    helper: Path = HELPER,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-I",
        "-B",
        str(helper),
        "--verify-current",
        str(current_link),
        "--releases-root",
        str(releases_root),
        "--baseline-directory",
        str(baseline_directory),
    ]
    if expected_manifest_sha256 is not None:
        command.extend(("--expected-manifest-sha256", expected_manifest_sha256))
    if require_root_owned_immutable:
        command.append("--require-root-owned-immutable")
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def run_verify_release(
    release_root: Path,
    releases_root: Path,
    baseline_directory: Path,
    *,
    expected_manifest_sha256: str | None = None,
    require_root_owned_immutable: bool = False,
    helper: Path = HELPER,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-I",
        "-B",
        str(helper),
        "--verify-release",
        str(release_root),
        "--releases-root",
        str(releases_root),
        "--baseline-directory",
        str(baseline_directory),
    ]
    if expected_manifest_sha256 is not None:
        command.extend(("--expected-manifest-sha256", expected_manifest_sha256))
    if require_root_owned_immutable:
        command.append("--require-root-owned-immutable")
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def assert_integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise AssertionError(f"{label} must be a JSON integer, not a boolean")
    return value


def assert_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise AssertionError(f"{label} must be a lowercase 64-character SHA-256")
    return value


def parse_success(process: subprocess.CompletedProcess[str]) -> dict[str, object]:
    if process.returncode != 0:
        raise AssertionError(
            f"runtime fingerprint failed with {process.returncode}: {process.stderr!r}"
        )
    if process.stderr != "":
        raise AssertionError(
            f"successful runtime fingerprint wrote stderr: {process.stderr!r}"
        )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError("helper stdout is not one strict JSON value") from exc
    if not isinstance(payload, dict) or isinstance(payload, list):
        raise AssertionError("helper stdout must be a JSON object")
    if set(payload) != EXPECTED_FIELDS:
        raise AssertionError(f"unexpected runtime fingerprint fields: {sorted(payload)}")
    if assert_integer(payload["schema_version"], "schema_version") != 2:
        raise AssertionError("runtime fingerprint contract must use schema_version 2")

    assert_sha256(payload["runtime_root_sha256"], "runtime_root_sha256")
    assert_sha256(payload["distributions_sha256"], "distributions_sha256")
    for optional_hash in ("release_root_sha256", "requirements_lock_sha256"):
        value = payload[optional_hash]
        if value is not None:
            assert_sha256(value, optional_hash)

    distributions = payload["distributions"]
    if not isinstance(distributions, list) or any(
        not isinstance(row, str) for row in distributions
    ):
        raise AssertionError("distributions must remain a JSON array of strings")

    interpreter = payload["interpreter"]
    if not isinstance(interpreter, dict) or isinstance(interpreter, list):
        raise AssertionError("interpreter must remain a JSON object")
    if set(interpreter) != EXPECTED_INTERPRETER_FIELDS:
        raise AssertionError(
            f"unexpected interpreter fields: {sorted(interpreter)}"
        )
    if not isinstance(interpreter["realpath"], str) or not interpreter["realpath"]:
        raise AssertionError("interpreter.realpath must be a non-empty JSON string")
    assert_sha256(interpreter["sha256"], "interpreter.sha256")
    if not isinstance(interpreter["mode"], str) or not MODE_PATTERN.fullmatch(
        interpreter["mode"]
    ):
        raise AssertionError("interpreter.mode must be a four-digit octal string")
    assert_integer(interpreter["uid"], "interpreter.uid")
    assert_integer(interpreter["gid"], "interpreter.gid")
    return payload


def canonical_json_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_json_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def replace_baseline_bytes(path: Path, payload: bytes) -> None:
    """Mutate the synthetic immutable baseline only inside negative tests."""

    if os.name == "posix":
        path.chmod(0o644)
    path.write_bytes(payload)
    if os.name == "posix":
        path.chmod(0o444)


def parse_verify_success(
    process: subprocess.CompletedProcess[str],
) -> dict[str, object]:
    if process.returncode != 0:
        raise AssertionError(
            f"runtime baseline verification failed with {process.returncode}: "
            f"{process.stderr!r}"
        )
    if process.stderr != "":
        raise AssertionError(
            f"successful runtime baseline verification wrote stderr: {process.stderr!r}"
        )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError("baseline verifier stdout is not strict JSON") from exc
    if not isinstance(payload, dict) or set(payload) != EXPECTED_VERIFY_FIELDS:
        raise AssertionError("baseline verifier JSON fields drifted")
    if assert_integer(payload["schema_version"], "verify.schema_version") != 1:
        raise AssertionError("baseline verifier schema must remain 1")
    if payload["status"] != "passed" or payload["release_id"] != RELEASE_ID:
        raise AssertionError("baseline verifier identity output is invalid")
    if payload["version"] != VERSION:
        raise AssertionError("baseline verifier version output is invalid")
    for name in (
        "release_manifest_sha256",
        "runtime_fingerprint_sha256",
        "baseline_sha256",
        "runtime_guard_helper_sha256",
    ):
        assert_sha256(payload[name], f"verify.{name}")
    return payload


def expect_verify_failure(
    process: subprocess.CompletedProcess[str], expected_fragment: str
) -> None:
    if process.returncode == 0:
        raise AssertionError("runtime baseline drift was unexpectedly accepted")
    if process.stdout != "":
        raise AssertionError("failed baseline verification must not publish JSON stdout")
    if expected_fragment not in process.stderr:
        raise AssertionError(
            f"baseline failure did not identify {expected_fragment!r}: {process.stderr!r}"
        )


def expect_failure(
    process: subprocess.CompletedProcess[str], expected_fragment: str
) -> None:
    if process.returncode == 0:
        raise AssertionError("unsafe release permissions were unexpectedly accepted")
    if process.stdout != "":
        raise AssertionError("failed runtime fingerprint must not publish JSON stdout")
    if expected_fragment not in process.stderr:
        raise AssertionError(
            f"failure did not identify {expected_fragment!r}: {process.stderr!r}"
        )


def write_fixture(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    release_root = root / "releases" / RELEASE_ID
    runtime_root = release_root / ".venv"
    interpreter = runtime_root / "bin" / "python"
    metadata = runtime_root / "lib" / "example_pkg-1.2.3.dist-info" / "METADATA"
    runtime_marker = runtime_root / "runtime-marker.bin"
    lock = release_root / "requirements.production.lock.txt"
    source = release_root / "protocol_studio" / "app.py"
    manifest = release_root / "release-manifest.json"

    interpreter.parent.mkdir(parents=True)
    metadata.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    interpreter.write_bytes(b"synthetic interpreter fixture\n")
    metadata.write_text(
        "Metadata-Version: 2.1\nName: Example_Pkg\nVersion: 1.2.3\n\n",
        encoding="utf-8",
    )
    runtime_marker.write_bytes(b"runtime-v1\n")
    lock.write_text("example-pkg==1.2.3 --hash=sha256:fixture\n", encoding="utf-8")
    source.write_text("VALUE = 'source-v1'\n", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project": PROJECT,
                "version": VERSION,
                "created_at": "2026-07-29T00:00:00Z",
                "source_date_epoch": 1785283200,
                "files": [],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )

    if os.name == "posix":
        for directory in sorted(
            (path for path in release_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
        ):
            directory.chmod(0o755)
        release_root.chmod(0o755)
        for file_path in (metadata, runtime_marker, lock, source, manifest):
            file_path.chmod(0o644)
        interpreter.chmod(0o755)

    return release_root, runtime_root, interpreter, lock, runtime_marker


def exercise_runtime_baseline_guard(
    root: Path,
    release_root: Path,
    runtime_root: Path,
    interpreter: Path,
    lock: Path,
    fingerprint: dict[str, object],
) -> dict[str, object]:
    releases_root = release_root.parent
    current_link = root / "current"
    runtime_guard_directory = root / "runtime-guard"
    helper_copy = runtime_guard_directory / "runtime_fingerprint.py"
    baseline_directory = runtime_guard_directory / "baselines"
    baseline_directory.mkdir(parents=True)
    shutil.copyfile(HELPER, helper_copy)
    helper_sha256 = hashlib.sha256(helper_copy.read_bytes()).hexdigest()
    current_link.symlink_to(release_root, target_is_directory=True)
    manifest_path = release_root / "release-manifest.json"
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    baseline = {
        "schema_version": 1,
        "project": PROJECT,
        "release_id": RELEASE_ID,
        "version": VERSION,
        "release_root": str(release_root.resolve()),
        "archive_sha256": ARCHIVE_SHA256,
        "release_manifest_sha256": manifest_sha256,
        "runtime_guard_helper_sha256": helper_sha256,
        "runtime_fingerprint": fingerprint,
    }
    if set(baseline) != BASELINE_FIELDS:
        raise AssertionError("test baseline fixture fields drifted")
    baseline_path = baseline_directory / f"{RELEASE_ID}.json"

    expect_verify_failure(
        run_verify_current(
            current_link,
            releases_root,
            baseline_directory,
            expected_manifest_sha256=manifest_sha256,
            helper=helper_copy,
        ),
        "runtime baseline is missing",
    )
    expect_verify_failure(
        run_verify_release(
            release_root,
            releases_root,
            baseline_directory,
            expected_manifest_sha256=manifest_sha256,
            helper=helper_copy,
        ),
        "runtime baseline is missing",
    )

    baseline_path.write_text(
        json.dumps(
            baseline,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    if os.name == "posix":
        baseline_directory.parent.chmod(0o755)
        baseline_directory.chmod(0o755)
        baseline_path.chmod(0o444)

    verified = parse_verify_success(
        run_verify_current(
            current_link,
            releases_root,
            baseline_directory,
            expected_manifest_sha256=manifest_sha256,
            helper=helper_copy,
        )
    )
    if verified["runtime_fingerprint_sha256"] != canonical_json_sha256(fingerprint):
        raise AssertionError("verified runtime fingerprint digest does not match baseline")
    if verified["baseline_sha256"] != hashlib.sha256(
        baseline_path.read_bytes()
    ).hexdigest():
        raise AssertionError("verified baseline digest does not match baseline bytes")
    if verified["runtime_guard_helper_sha256"] != helper_sha256:
        raise AssertionError("verified helper digest does not match executed helper bytes")
    verified_release = parse_verify_success(
        run_verify_release(
            release_root,
            releases_root,
            baseline_directory,
            expected_manifest_sha256=manifest_sha256,
            helper=helper_copy,
        )
    )
    if verified_release != verified:
        raise AssertionError("verify-current and verify-release evidence diverged")

    unrelated_baselines = []
    for index in range(3):
        unrelated = baseline_directory / f"unrelated-{index}.json"
        unrelated.write_text("{}\n", encoding="utf-8")
        unrelated_baselines.append(unrelated)
    try:
        with_unrelated = parse_verify_success(
            run_verify_current(
                current_link,
                releases_root,
                baseline_directory,
                expected_manifest_sha256=manifest_sha256,
                helper=helper_copy,
            )
        )
        if with_unrelated != verified:
            raise AssertionError("unrelated baselines changed canonical release evidence")
    finally:
        for unrelated in unrelated_baselines:
            unrelated.unlink()

    original_helper = helper_copy.read_bytes()
    helper_copy.write_bytes(original_helper + b"\n# helper-only drift\n")
    try:
        expect_verify_failure(
            run_verify_current(
                current_link,
                releases_root,
                baseline_directory,
                helper=helper_copy,
            ),
            "runtime guard helper digest mismatch",
        )
        expect_verify_failure(
            run_verify_release(
                release_root,
                releases_root,
                baseline_directory,
                helper=helper_copy,
            ),
            "runtime guard helper digest mismatch",
        )
    finally:
        helper_copy.write_bytes(original_helper)

    source = release_root / "protocol_studio" / "app.py"
    original_source = source.read_bytes()
    source.write_bytes(b"VALUE = 'tampered-source'\n")
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "runtime fingerprint mismatch",
        )
    finally:
        source.write_bytes(original_source)

    runtime_marker = runtime_root / "runtime-marker.bin"
    original_runtime = runtime_marker.read_bytes()
    runtime_marker.write_bytes(b"tampered-runtime\n")
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "runtime fingerprint mismatch",
        )
    finally:
        runtime_marker.write_bytes(original_runtime)

    original_manifest = manifest_path.read_bytes()
    manifest_path.write_bytes(original_manifest + b" ")
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "manifest digest mismatch",
        )
    finally:
        manifest_path.write_bytes(original_manifest)

    original_baseline = baseline_path.read_bytes()
    replace_baseline_bytes(
        baseline_path,
        original_baseline.replace(b'"schema_version":1', b'"schema_version":true', 1)
    )
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "baseline contract",
        )
    finally:
        replace_baseline_bytes(baseline_path, original_baseline)

    old_baseline = dict(baseline)
    old_baseline.pop("runtime_guard_helper_sha256")
    replace_baseline_bytes(baseline_path, canonical_json_line(old_baseline))
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "baseline contract",
        )
    finally:
        replace_baseline_bytes(baseline_path, original_baseline)

    boolean_helper_digest = dict(baseline)
    boolean_helper_digest["runtime_guard_helper_sha256"] = True
    replace_baseline_bytes(baseline_path, canonical_json_line(boolean_helper_digest))
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "baseline contract",
        )
    finally:
        replace_baseline_bytes(baseline_path, original_baseline)

    uppercase_helper_digest = dict(baseline)
    uppercase_helper_digest["runtime_guard_helper_sha256"] = helper_sha256.upper()
    replace_baseline_bytes(baseline_path, canonical_json_line(uppercase_helper_digest))
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "baseline contract",
        )
    finally:
        replace_baseline_bytes(baseline_path, original_baseline)

    extra_field = dict(baseline)
    extra_field["unexpected"] = None
    replace_baseline_bytes(baseline_path, canonical_json_line(extra_field))
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "baseline contract",
        )
    finally:
        replace_baseline_bytes(baseline_path, original_baseline)

    nan_payload = original_baseline.replace(
        f'"runtime_guard_helper_sha256":"{helper_sha256}"'.encode("ascii"),
        b'"runtime_guard_helper_sha256":NaN',
        1,
    )
    replace_baseline_bytes(baseline_path, nan_payload)
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "baseline JSON",
        )
    finally:
        replace_baseline_bytes(baseline_path, original_baseline)

    duplicate_payload = original_baseline.replace(
        b'{"archive_sha256"', b'{"schema_version":1,"archive_sha256"', 1
    )
    replace_baseline_bytes(baseline_path, duplicate_payload)
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "baseline JSON",
        )
    finally:
        replace_baseline_bytes(baseline_path, original_baseline)

    wrong_expected = "b" * 64
    expect_verify_failure(
        run_verify_current(
            current_link,
            releases_root,
            baseline_directory,
            expected_manifest_sha256=wrong_expected,
            helper=helper_copy,
        ),
        "expected manifest digest mismatch",
    )

    escaped_release = root / "escaped-release"
    escaped_release.mkdir()
    current_link.unlink()
    current_link.symlink_to(escaped_release, target_is_directory=True)
    try:
        expect_verify_failure(
            run_verify_current(
                current_link, releases_root, baseline_directory, helper=helper_copy
            ),
            "current release escaped releases root",
        )
    finally:
        current_link.unlink()
        current_link.symlink_to(release_root, target_is_directory=True)

    return {
        "status": "passed",
        "clean_verified": True,
        "zero_matching_baseline_rejected": True,
        "one_canonical_baseline_accepted": True,
        "multiple_unrelated_baselines_do_not_create_target_ambiguity": True,
        "source_drift_rejected": True,
        "runtime_drift_rejected": True,
        "manifest_drift_rejected": True,
        "helper_only_drift_rejected": True,
        "verify_current_and_release_bound_to_helper": True,
        "legacy_baseline_without_helper_rejected": True,
        "helper_digest_type_and_case_rejected": True,
        "baseline_extra_field_rejected": True,
        "baseline_nan_rejected": True,
        "baseline_type_drift_rejected": True,
        "duplicate_json_rejected": True,
        "external_expected_manifest_enforced": True,
        "current_link_escape_rejected": True,
    }


def check_permission_boundary(
    release_root: Path,
    runtime_root: Path,
    interpreter: Path,
    lock: Path,
) -> dict[str, object]:
    if os.name != "posix":
        return {
            "status": "skipped",
            "reason": "POSIX uid/gid/mode ownership semantics are unavailable on Windows",
            "root_owned_immutable_accepted": None,
            "non_root_owner_rejected": None,
            "group_writable_rejected": None,
        }

    if not hasattr(os, "geteuid"):
        raise AssertionError("POSIX runtime does not expose geteuid")
    if os.geteuid() != 0:
        rejected = run_helper(
            runtime_root,
            interpreter,
            lock=lock,
            release_root=release_root,
            require_root_owned_immutable=True,
        )
        expect_failure(rejected, "not owned by root:root")
        return {
            "status": "partial",
            "reason": "positive root-owned and mode checks require effective uid 0",
            "root_owned_immutable_accepted": None,
            "non_root_owner_rejected": True,
            "group_writable_rejected": None,
        }

    parse_success(
        run_helper(
            runtime_root,
            interpreter,
            lock=lock,
            release_root=release_root,
            require_root_owned_immutable=True,
        )
    )

    source = release_root / "protocol_studio" / "app.py"
    original_mode = stat.S_IMODE(source.stat().st_mode)
    source.chmod(original_mode | stat.S_IWGRP)
    try:
        expect_failure(
            run_helper(
                runtime_root,
                interpreter,
                lock=lock,
                release_root=release_root,
                require_root_owned_immutable=True,
            ),
            "writable by group or other",
        )
    finally:
        source.chmod(original_mode)

    original_uid = source.stat().st_uid
    original_gid = source.stat().st_gid
    os.chown(source, 1, original_gid)
    try:
        expect_failure(
            run_helper(
                runtime_root,
                interpreter,
                lock=lock,
                release_root=release_root,
                require_root_owned_immutable=True,
            ),
            "not owned by root:root",
        )
    finally:
        os.chown(source, original_uid, original_gid)

    return {
        "status": "passed",
        "reason": None,
        "root_owned_immutable_accepted": True,
        "non_root_owner_rejected": True,
        "group_writable_rejected": True,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="runtime-fingerprint-test-") as temporary:
        root = Path(temporary)
        release_root, runtime_root, interpreter, lock, runtime_marker = write_fixture(
            root
        )

        baseline = parse_success(
            run_helper(
                runtime_root,
                interpreter,
                lock=lock,
                release_root=release_root,
            )
        )
        if baseline["distributions"] != ["example-pkg==1.2.3"]:
            raise AssertionError("distribution inventory normalization changed")
        if baseline["requirements_lock_sha256"] != hashlib.sha256(
            lock.read_bytes()
        ).hexdigest():
            raise AssertionError("requirements lock SHA-256 does not match its bytes")

        runtime_baseline_guard = exercise_runtime_baseline_guard(
            root,
            release_root,
            runtime_root,
            interpreter,
            lock,
            baseline,
        )

        optional = parse_success(run_helper(runtime_root, interpreter))
        if optional["release_root_sha256"] is not None:
            raise AssertionError("omitted release root must remain JSON null")
        if optional["requirements_lock_sha256"] is not None:
            raise AssertionError("omitted requirements lock must remain JSON null")

        runtime_marker.write_bytes(b"runtime-v2\n")
        runtime_drift = parse_success(
            run_helper(
                runtime_root,
                interpreter,
                lock=lock,
                release_root=release_root,
            )
        )
        if runtime_drift["runtime_root_sha256"] == baseline["runtime_root_sha256"]:
            raise AssertionError("runtime content drift did not change the runtime digest")
        if runtime_drift["release_root_sha256"] != baseline["release_root_sha256"]:
            raise AssertionError("excluded .venv drift changed the release source digest")

        source = release_root / "protocol_studio" / "app.py"
        source.write_text("VALUE = 'source-v2'\n", encoding="utf-8")
        source_drift = parse_success(
            run_helper(
                runtime_root,
                interpreter,
                lock=lock,
                release_root=release_root,
            )
        )
        if source_drift["release_root_sha256"] == runtime_drift["release_root_sha256"]:
            raise AssertionError("release source drift did not change release_root_sha256")
        if source_drift["runtime_root_sha256"] != runtime_drift["runtime_root_sha256"]:
            raise AssertionError("release source drift unexpectedly changed runtime digest")

        lock.write_text("example-pkg==1.2.4 --hash=sha256:fixture-v2\n", encoding="utf-8")
        lock_drift = parse_success(
            run_helper(
                runtime_root,
                interpreter,
                lock=lock,
                release_root=release_root,
            )
        )
        if (
            lock_drift["requirements_lock_sha256"]
            == source_drift["requirements_lock_sha256"]
        ):
            raise AssertionError("requirements lock drift did not change its digest")
        if lock_drift["release_root_sha256"] == source_drift["release_root_sha256"]:
            raise AssertionError("lock drift inside the release did not change source digest")

        permission_boundary = check_permission_boundary(
            release_root, runtime_root, interpreter, lock
        )

    report = {
        "status": "passed",
        "schema_version": 2,
        "json_contract": True,
        "runtime_drift_detected": True,
        "release_tree_drift_detected": True,
        "lock_drift_detected": True,
        "runtime_baseline_guard": runtime_baseline_guard,
        "permission_boundary": permission_boundary,
    }
    assert_integer(report["schema_version"], "report.schema_version")
    if not isinstance(report["permission_boundary"], dict):
        raise AssertionError("permission boundary result must remain a JSON object")
    if not isinstance(report["runtime_baseline_guard"], dict):
        raise AssertionError("runtime baseline guard result must remain a JSON object")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
