#!/usr/bin/env python3
"""Validate repository text encodings, Python, JavaScript and structured files."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


SKIP_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "venv",
}
TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}


def relative(root: Path, path: Path) -> str:
    return PurePosixPath(*path.relative_to(root).parts).as_posix()


def candidate_files(root: Path) -> list[Path]:
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(part in SKIP_PARTS for part in parts):
            continue
        result.append(path)
    return sorted(result, key=lambda item: relative(root, item))


def run_node_checks(root: Path, javascript_files: list[Path]) -> list[str]:
    node = shutil.which("node")
    if not node:
        return ["node executable not found; Node.js 20+ is required"]
    errors: list[str] = []
    env = os.environ.copy()
    env["NODE_NO_WARNINGS"] = "1"
    for path in javascript_files:
        if path.name.endswith(".min.js"):
            continue
        result = subprocess.run(
            [node, "--check", str(path)],
            cwd=root,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            errors.append(f"{relative(root, path)}: {detail[-1] if detail else 'node --check failed'}")
    return errors


def validate_requirement_pins(root: Path, path: Path) -> list[str]:
    errors: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = line.strip()
        if not value or value.startswith("#") or value.startswith("-r "):
            continue
        if "==" not in value:
            errors.append(
                f"{relative(root, path)}:{line_number}: direct dependency is not exactly pinned"
            )
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    files = candidate_files(root)
    errors: list[str] = []
    counts = {"text": 0, "python": 0, "javascript": 0, "json": 0, "yaml": 0, "toml": 0}

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        yaml = None

    javascript_files: list[Path] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix in TEXT_SUFFIXES or path.name in {"Dockerfile", "LICENSE", "NOTICE"}:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(f"{relative(root, path)}: not valid UTF-8")
                continue
            counts["text"] += 1
        else:
            continue

        try:
            if suffix == ".py":
                compile(text, relative(root, path), "exec")
                counts["python"] += 1
            elif suffix == ".js":
                javascript_files.append(path)
                counts["javascript"] += 1
            elif suffix == ".json":
                json.loads(text)
                counts["json"] += 1
            elif suffix in {".yml", ".yaml"}:
                if yaml is None:
                    errors.append(
                        f"{relative(root, path)}: PyYAML is required for YAML validation"
                    )
                else:
                    parsed: Any = yaml.safe_load(text)
                    if not isinstance(parsed, dict):
                        errors.append(f"{relative(root, path)}: YAML root must be a mapping")
                counts["yaml"] += 1
            elif suffix == ".toml":
                tomllib.loads(text)
                counts["toml"] += 1
        except (SyntaxError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{relative(root, path)}: {type(exc).__name__}: {exc}")
        except Exception as exc:  # keep the validator's report bounded and auditable
            errors.append(f"{relative(root, path)}: {type(exc).__name__}: {exc}")

    errors.extend(run_node_checks(root, javascript_files))
    for requirements_name in ("requirements.production.txt", "requirements.dev.txt"):
        path = root / requirements_name
        if path.exists():
            errors.extend(validate_requirement_pins(root, path))

    report = {
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "counts": counts,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
