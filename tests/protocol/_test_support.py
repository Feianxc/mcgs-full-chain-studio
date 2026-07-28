from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def add_repo_to_import_path() -> Path:
    repo_text = str(REPO_ROOT)
    if repo_text not in sys.path:
        sys.path.insert(0, repo_text)
    return REPO_ROOT


def configure_process_runtime(prefix: str, *, auth_enabled: bool = False) -> Path:
    """Give a standalone test process an external, disposable state directory."""

    runtime_root = Path(tempfile.mkdtemp(prefix=f"{prefix}-"))
    runs_root = runtime_root / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    os.environ["PROTOCOL_STUDIO_AUTH_ENABLED"] = "true" if auth_enabled else "false"
    os.environ["MCGS_FULL_CHAIN_RUNS_ROOT"] = str(runs_root)
    os.environ["PROTOCOL_STUDIO_RUNS_ROOT"] = str(runs_root)
    os.environ["PROTOCOL_STUDIO_SECURITY_DB"] = str(runtime_root / "security.sqlite3")

    atexit.register(shutil.rmtree, runtime_root, True)
    return runtime_root


def generated_artifact_path(app_module: object, payload: dict, key: str) -> Path:
    """Resolve an API artifact reference without depending on leaked absolute paths."""

    run_id = payload.get("run_id")
    raw_path = payload.get("artifacts", {}).get(key)
    if not isinstance(run_id, str) or not run_id:
        raise AssertionError("generation payload has no run_id")
    if not isinstance(raw_path, str) or not raw_path:
        raise AssertionError(f"generation payload has no artifact reference: {key}")

    run_root = Path(getattr(app_module, "RUNS_ROOT")).resolve()
    run_dir = (run_root / run_id).resolve()
    if run_dir.parent != run_root:
        raise AssertionError("run_id escaped the configured test runs root")
    artifact_path = (run_dir / Path(raw_path).name).resolve()
    if artifact_path.parent != run_dir:
        raise AssertionError(f"artifact escaped the generated run directory: {key}")
    return artifact_path
