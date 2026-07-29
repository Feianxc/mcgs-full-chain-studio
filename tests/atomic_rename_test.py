from __future__ import annotations

import errno
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "deploy" / "atomic_rename.py"
PROBE_KEYS = {
    "schema_version": int,
    "ok": bool,
    "error_number": int,
    "same_device": bool,
    "inode_preserved": bool,
    "source_removed": bool,
    "target_removed": bool,
    "source_directory_synced": bool,
    "target_directory_synced": bool,
}


def secure_platform_supported() -> bool:
    required_flags = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    required_dir_fd_functions = (os.open, os.rename, os.stat, os.unlink)
    return bool(
        os.name == "posix"
        and all(hasattr(os, name) for name in required_flags)
        and all(function in os.supports_dir_fd for function in required_dir_fd_functions)
        and hasattr(os, "fchmod")
    )


def run_process(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-I", os.fspath(HELPER), *arguments],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def run_helper(*arguments: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    completed = run_process(*arguments)
    lines = completed.stdout.splitlines()
    if len(lines) != 1:
        raise AssertionError("atomic rename helper must emit exactly one JSON line")
    payload = json.loads(lines[0])
    if not isinstance(payload, dict):
        raise AssertionError("atomic rename helper result must be a JSON object")
    return completed, payload


def load_helper_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("atomic_rename_under_test", HELPER)
    if spec is None or spec.loader is None:
        raise AssertionError("atomic rename helper could not be imported")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_contract(payload: dict[str, object], contract: dict[str, type]) -> None:
    if set(payload) != set(contract):
        raise AssertionError("atomic rename JSON keys do not match the strict contract")
    for key, expected_type in contract.items():
        if type(payload[key]) is not expected_type:
            raise AssertionError(f"atomic rename JSON field {key!r} has the wrong type")
    if payload["schema_version"] != 1:
        raise AssertionError("unexpected atomic rename schema version")


def assert_no_path_disclosure(
    completed: subprocess.CompletedProcess[str],
    paths: tuple[Path, ...],
) -> None:
    output = completed.stdout + completed.stderr
    for path in paths:
        if os.fspath(path) in output:
            raise AssertionError("atomic rename output disclosed an absolute path")


def test_probe_only_cli() -> None:
    parser = load_helper_module().build_parser()
    command_actions = [
        action for action in parser._actions if getattr(action, "dest", None) == "command"
    ]
    if len(command_actions) != 1 or set(command_actions[0].choices) != {"probe"}:
        raise AssertionError("atomic rename CLI command set is not exactly probe")

    help_result = run_process("--help")
    help_text = help_result.stdout + help_result.stderr
    if help_result.returncode != 0 or "probe" not in help_text:
        raise AssertionError("atomic rename helper did not advertise the probe command")
    if "replace" in help_text:
        raise AssertionError("atomic rename helper still advertises the removed write command")

    rejected = run_process("replace")
    if rejected.returncode == 0:
        raise AssertionError("removed atomic rename write command was unexpectedly accepted")
    if rejected.stdout:
        raise AssertionError("rejected atomic rename command emitted an operational result")


def test_same_filesystem(root: Path) -> None:
    source_dir = root / "source"
    target_dir = root / "target"
    source_dir.mkdir(mode=0o700)
    target_dir.mkdir(mode=0o700)

    completed, report = run_helper(
        "probe",
        "--source-dir",
        os.fspath(source_dir),
        "--target-dir",
        os.fspath(target_dir),
    )
    assert_contract(report, PROBE_KEYS)
    assert_no_path_disclosure(completed, (root, source_dir, target_dir))
    if completed.returncode != 0 or report["ok"] is not True:
        raise AssertionError("same-filesystem atomic rename probe failed")
    expected_true = (
        "same_device",
        "inode_preserved",
        "source_removed",
        "target_removed",
        "source_directory_synced",
        "target_directory_synced",
    )
    if any(report[key] is not True for key in expected_true) or report["error_number"] != 0:
        raise AssertionError("same-filesystem probe evidence is incomplete")
    if list(source_dir.iterdir()) or list(target_dir.iterdir()):
        raise AssertionError("atomic rename probe left a file behind")


def run_probe_with_names(
    module: ModuleType,
    source_dir: Path,
    target_dir: Path,
    source_name: str,
    target_name: str,
) -> dict[str, object]:
    original = module._new_probe_names
    module._new_probe_names = lambda: (source_name, target_name)
    try:
        report = module.probe(source_dir, target_dir)
    finally:
        module._new_probe_names = original
    if not isinstance(report, dict):
        raise AssertionError("direct atomic rename probe did not return an object")
    return report


def assert_collision_contract(
    report: dict[str, object],
    *,
    source_removed: bool,
    target_removed: bool,
) -> None:
    assert_contract(report, PROBE_KEYS)
    if report["ok"] is not False or report["error_number"] != errno.EEXIST:
        raise AssertionError("probe-name collision did not fail closed with EEXIST")
    if report["same_device"] is not True or report["inode_preserved"] is not False:
        raise AssertionError("probe-name collision evidence is inconsistent")
    if (
        report["source_removed"] is not source_removed
        or report["target_removed"] is not target_removed
        or report["source_directory_synced"] is not True
        or report["target_directory_synced"] is not True
    ):
        raise AssertionError("probe-name collision cleanup evidence is incomplete")


def test_probe_name_collisions(root: Path) -> None:
    module = load_helper_module()

    source_dir = root / "source-name-collision-source"
    target_dir = root / "source-name-collision-target"
    source_dir.mkdir(mode=0o700)
    target_dir.mkdir(mode=0o700)
    source_name = ".atomic-rename-probe-fixed-source.source"
    target_name = ".atomic-rename-probe-fixed-source.target"
    source_collision = source_dir / source_name
    source_collision.write_bytes(b"caller-owned source collision\n")

    report = run_probe_with_names(
        module, source_dir, target_dir, source_name, target_name
    )
    assert_collision_contract(report, source_removed=False, target_removed=True)
    if source_collision.read_bytes() != b"caller-owned source collision\n":
        raise AssertionError("source-name collision was changed or removed")
    if set(source_dir.iterdir()) != {source_collision} or list(target_dir.iterdir()):
        raise AssertionError("source-name collision left an unexpected probe residue")

    source_dir = root / "target-name-collision-source"
    target_dir = root / "target-name-collision-target"
    source_dir.mkdir(mode=0o700)
    target_dir.mkdir(mode=0o700)
    source_name = ".atomic-rename-probe-fixed-target.source"
    target_name = ".atomic-rename-probe-fixed-target.target"
    target_collision = target_dir / target_name
    target_collision.write_bytes(b"caller-owned target collision\n")

    report = run_probe_with_names(
        module, source_dir, target_dir, source_name, target_name
    )
    assert_collision_contract(report, source_removed=True, target_removed=False)
    if target_collision.read_bytes() != b"caller-owned target collision\n":
        raise AssertionError("target-name collision was changed or removed")
    if list(source_dir.iterdir()) or set(target_dir.iterdir()) != {target_collision}:
        raise AssertionError("target-name collision left an unexpected probe residue")


def cross_filesystem_target(source_root: Path) -> tempfile.TemporaryDirectory[str] | None:
    source_device = source_root.stat().st_dev
    for candidate in (Path("/dev/shm"), Path("/run"), Path("/var/tmp"), Path("/tmp")):
        try:
            if not candidate.is_dir() or candidate.stat().st_dev == source_device:
                continue
            temporary = tempfile.TemporaryDirectory(prefix="atomic-rename-crossfs-", dir=candidate)
            target = Path(temporary.name)
            target.chmod(0o700)
            if target.stat().st_dev != source_device:
                return temporary
            temporary.cleanup()
        except OSError:
            continue
    return None


def test_cross_filesystem_boundary(root: Path) -> bool:
    source_dir = root / "cross-source"
    source_dir.mkdir(mode=0o700)
    target_temporary = cross_filesystem_target(source_dir)
    if target_temporary is None:
        return False
    try:
        target_dir = Path(target_temporary.name)
        completed, report = run_helper(
            "probe",
            "--source-dir",
            os.fspath(source_dir),
            "--target-dir",
            os.fspath(target_dir),
        )
        assert_contract(report, PROBE_KEYS)
        assert_no_path_disclosure(completed, (root, source_dir, target_dir))
        if completed.returncode == 0 or report["ok"] is not False:
            raise AssertionError("cross-filesystem rename was unexpectedly accepted")
        if report["error_number"] != errno.EXDEV or report["same_device"] is not False:
            raise AssertionError("cross-filesystem rename did not fail with EXDEV")
        if (
            report["source_removed"] is not True
            or report["target_removed"] is not True
            or report["source_directory_synced"] is not True
            or report["target_directory_synced"] is not True
        ):
            raise AssertionError("cross-filesystem failure did not clean up durably")
        if list(source_dir.iterdir()) or list(target_dir.iterdir()):
            raise AssertionError("cross-filesystem probe left a file behind")
    finally:
        target_temporary.cleanup()
    return True


def test_unsupported_platform_contract(root: Path) -> None:
    source_dir = root / "unsupported-source"
    target_dir = root / "unsupported-target"
    source_dir.mkdir()
    target_dir.mkdir()
    completed, report = run_helper(
        "probe",
        "--source-dir",
        os.fspath(source_dir),
        "--target-dir",
        os.fspath(target_dir),
    )
    assert_contract(report, PROBE_KEYS)
    assert_no_path_disclosure(completed, (root, source_dir, target_dir))
    if completed.returncode == 0 or report["ok"] is not False:
        raise AssertionError("unsupported platform did not fail closed")
    if report["error_number"] != errno.ENOTSUP:
        raise AssertionError("unsupported platform did not report ENOTSUP")
    if list(source_dir.iterdir()) or list(target_dir.iterdir()):
        raise AssertionError("unsupported-platform probe left a file behind")


def main() -> int:
    test_probe_only_cli()
    supported = secure_platform_supported()
    with tempfile.TemporaryDirectory(prefix="atomic-rename-test-") as temporary:
        root = Path(temporary).resolve()
        if not supported:
            test_unsupported_platform_contract(root)
            report = {
                "status": "skipped",
                "platform_supported": False,
                "probe_only_cli_tested": True,
                "same_filesystem_tested": False,
                "collision_tested": False,
                "residual_cleanup_tested": False,
                "cross_filesystem_tested": False,
                "cross_filesystem_skipped": True,
            }
        else:
            test_same_filesystem(root)
            test_probe_name_collisions(root)
            cross_filesystem_tested = test_cross_filesystem_boundary(root)
            report = {
                "status": "passed" if cross_filesystem_tested else "passed_with_skip",
                "platform_supported": True,
                "probe_only_cli_tested": True,
                "same_filesystem_tested": True,
                "collision_tested": True,
                "residual_cleanup_tested": True,
                "cross_filesystem_tested": cross_filesystem_tested,
                "cross_filesystem_skipped": not cross_filesystem_tested,
            }

    if any(type(value) is not bool for key, value in report.items() if key != "status"):
        raise AssertionError("atomic rename test summary has invalid JSON types")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
