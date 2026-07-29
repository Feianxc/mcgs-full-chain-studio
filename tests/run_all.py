from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

JAVASCRIPT_TESTS = [
    "assembly_studio/tests/cabinet-switch-aggregation.test.js",
    "tests/assembly/protocol-config.test.js",
    "tests/assembly/type-extension-core.test.js",
    "tests/assembly/workflow-core.test.js",
]

PYTHON_TESTS = [
    "tests/atomic_rename_test.py",
    "tests/deploy_contract_test.py",
    "tests/transaction_contract_test.py",
    "tests/environment_file_contract_test.py",
    "tests/packaging_contract_test.py",
    "tests/sbom_test.py",
    "tests/release_path_policy_test.py",
    "tests/release_workflow_contract_test.py",
    "tests/runtime_fingerprint_test.py",
    "tests/sqlite_backup_test.py",
    "tests/integration_auth_test.py",
    "tests/three_file_generation_test.py",
    "tests/protocol/protocol_studio_dynamic_module_sequence_test.py",
    "tests/protocol/protocol_studio_dynamic_topology_test.py",
    "tests/protocol/protocol_studio_pointset_contract_test.py",
    "tests/protocol/protocol_studio_program_upload_test.py",
    "tests/protocol/protocol_studio_security_test.py",
    "tests/protocol/protocol_studio_two_column_topology_test.py",
    "tests/protocol/protocol_studio_unified_master_test.py",
    "tests/protocol/protocol_studio_unified_workflow_test.py",
]


def run_case(command: list[str], relative_path: str, env: dict[str, str]) -> dict[str, object]:
    started_at = time.perf_counter()
    completed = subprocess.run(
        [*command, relative_path],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        text=True,
        encoding="utf-8",
    )
    elapsed = time.perf_counter() - started_at
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return {"path": relative_path, "status": "passed", "elapsed_seconds": round(elapsed, 3)}


def main() -> int:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required for assembly core tests")

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    reports: list[dict[str, object]] = []
    for test_path in JAVASCRIPT_TESTS:
        reports.append(run_case([node], test_path, env))
    for test_path in PYTHON_TESTS:
        reports.append(run_case([sys.executable], test_path, env))

    print(json.dumps({"status": "passed", "tests": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
