#!/usr/bin/env python3
"""Execute a command with a systemd-style EnvironmentFile without shell eval."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Sequence


KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def parse_value(raw: str, line_number: int) -> str:
    lexer = shlex.shlex(raw, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        parts = list(lexer)
    except ValueError as exc:
        raise ValueError(f"line {line_number}: invalid quoting") from exc
    if len(parts) > 1:
        raise ValueError(f"line {line_number}: unquoted whitespace is not supported")
    value = parts[0] if parts else ""
    if "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError(f"line {line_number}: invalid control character")
    return value


def load_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            raise ValueError(f"line {line_number}: expected KEY=VALUE")
        key, raw = stripped.split("=", 1)
        key = key.strip()
        if not KEY_PATTERN.fullmatch(key):
            raise ValueError(f"line {line_number}: invalid environment key")
        values[key] = parse_value(raw.strip(), line_number)
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("a command is required after --")
    if not args.env_file.is_file():
        print("environment file does not exist", file=sys.stderr)
        return 2
    try:
        environment = os.environ.copy()
        environment.update(load_environment(args.env_file))
        os.execvpe(command[0], command, environment)
    except (OSError, ValueError) as exc:
        print(f"environment launch failed: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
