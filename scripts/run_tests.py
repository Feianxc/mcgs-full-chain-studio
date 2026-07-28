#!/usr/bin/env python3
"""Run the repository's script-style Python and JavaScript regression tests."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Sequence


def relative(root: Path, path: Path) -> str:
    return PurePosixPath(*path.relative_to(root).parts).as_posix()


def run_one(command: list[str], root: Path, timeout: int) -> dict[str, object]:
    started = time.monotonic()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["NODE_NO_WARNINGS"] = "1"
    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        output_lines = (result.stdout + "\n" + result.stderr).strip().splitlines()
        return {
            "status": "passed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "tail": output_lines[-20:],
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return {
            "status": "timeout",
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "tail": (stdout + "\n" + stderr).strip().splitlines()[-20:],
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--python-only", action="store_true")
    mode.add_argument("--javascript-only", action="store_true")
    parser.add_argument("--filter", help="run paths containing this substring")
    parser.add_argument("--timeout", type=int, default=900, help="seconds per test")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)

    root = args.root.resolve()
    tests: list[tuple[Path, list[str]]] = []
    if not args.javascript_only:
        for path in sorted((root / "tests").glob("*_test.py")):
            tests.append((path, [sys.executable, str(path)]))
        for path in sorted((root / "tests" / "protocol").glob("*_test.py")):
            tests.append((path, [sys.executable, str(path)]))
    if not args.python_only:
        node = shutil.which("node")
        if not node:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "failed",
                        "tests": [],
                        "error": "node executable not found",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2
        javascript_tests = sorted(
            path
            for path in root.rglob("*.test.js")
            if not {
                ".git",
                ".venv",
                "dist",
                "node_modules",
                "venv",
            }.intersection(path.relative_to(root).parts)
        )
        for path in javascript_tests:
            tests.append((path, [node, str(path)]))

    if args.filter:
        tests = [item for item in tests if args.filter in relative(root, item[0])]
    if not tests:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "failed",
                    "tests": [],
                    "error": "no matching tests",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    reports: list[dict[str, object]] = []
    for path, command in tests:
        result = run_one(command, root, args.timeout)
        report = {"path": relative(root, path), **result}
        reports.append(report)
        state = str(result["status"]).upper()
        print(f"[{state}] {report['path']} ({result['duration_seconds']}s)", file=sys.stderr)

    passed = all(item["status"] == "passed" for item in reports)
    summary = {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "total": len(reports),
        "passed": sum(item["status"] == "passed" for item in reports),
        "failed": sum(item["status"] != "passed" for item in reports),
        "tests": reports,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
