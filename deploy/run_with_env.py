#!/usr/bin/env python3
"""Execute a command with a systemd-style EnvironmentFile without shell eval."""

from __future__ import annotations

import argparse
import errno
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence


KEY_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
PRIVILEGED_LOADER_KEYS = {
    "BASHOPTS",
    "BASH_ENV",
    "CDPATH",
    "ENV",
    "FORWARDED_ALLOW_IPS",
    "GCONV_PATH",
    "GLIBC_TUNABLES",
    "GLOBIGNORE",
    "LOCPATH",
    "OPENSSL_CONF",
    "OPENSSL_CONF_INCLUDE",
    "OPENSSL_ENGINES",
    "OPENSSL_MODULES",
    "PATH",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "SHELLOPTS",
    "WEB_CONCURRENCY",
    "_UVICORN_COMPLETE",
}

SAFE_BASE_ENVIRONMENT = {
    "PATH": "/usr/sbin:/usr/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONUNBUFFERED": "1",
}

# This launcher deliberately accepts less than systemd itself.  The supported
# contract is a one-line, no-continuation EnvironmentFile subset, not a shell
# fragment.  These tokens would be interpreted by a shell but are only literal
# text to systemd, which is an easy and dangerous configuration mistake.  A
# plain dollar sign remains valid because production scrypt hashes contain it
# and systemd never performs variable expansion in EnvironmentFile values.
UNSUPPORTED_SHELL_TOKENS = (
    "$(",
    "${",
    "`",
    "&&",
    "||",
    "|",
    "&",
    ";",
    "<",
    ">",
)

FD_ISOLATION_ERROR = "cannot isolate inherited file descriptors"


class FileDescriptorIsolationError(RuntimeError):
    """Raised without descriptor or path details when POSIX isolation fails."""


def _open_file_descriptors_from_proc() -> set[int]:
    try:
        entries = os.listdir("/proc/self/fd")
    except OSError:
        raise FileDescriptorIsolationError(FD_ISOLATION_ERROR) from None
    return {
        int(entry)
        for entry in entries
        if entry.isascii() and entry.isdecimal() and int(entry) > 2
    }


def close_inherited_file_descriptors() -> None:
    """Close and verify every open descriptor above stderr on Linux."""

    # ``listdir`` may report its own now-closed directory descriptor.  EBADF is
    # therefore expected for that one transient entry; every other close error
    # is fatal.  A second /proc snapshot plus fstat makes the operation
    # fail-closed instead of assuming that an ignored close error was harmless.
    descriptors = _open_file_descriptors_from_proc()
    for descriptor in sorted(descriptors, reverse=True):
        try:
            os.close(descriptor)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise FileDescriptorIsolationError(FD_ISOLATION_ERROR) from None

    for descriptor in _open_file_descriptors_from_proc():
        try:
            os.fstat(descriptor)
        except OSError as exc:
            if exc.errno == errno.EBADF:
                continue
            raise FileDescriptorIsolationError(FD_ISOLATION_ERROR) from None
        raise FileDescriptorIsolationError(FD_ISOLATION_ERROR) from None


def is_privileged_loader_key(key: str) -> bool:
    return key in PRIVILEGED_LOADER_KEYS or key.startswith(
        ("BASH_FUNC_", "LD_", "DYLD_", "PYTHON", "UVICORN_", "_UVICORN_")
    )


def is_unicode_noncharacter(character: str) -> bool:
    codepoint = ord(character)
    return 0xFDD0 <= codepoint <= 0xFDEF or codepoint & 0xFFFF in {0xFFFE, 0xFFFF}


def validate_value_characters(value: str, line_number: int) -> None:
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError(f"line {line_number}: control characters are not supported")
    if "\ufeff" in value or any(is_unicode_noncharacter(character) for character in value):
        raise ValueError(f"line {line_number}: invalid Unicode character")


def reject_shell_syntax(value: str, line_number: int) -> None:
    token = next(
        (candidate for candidate in UNSUPPORTED_SHELL_TOKENS if candidate in value),
        None,
    )
    if token is not None:
        raise ValueError(
            f"line {line_number}: shell syntax is not supported in EnvironmentFile values"
        )


def parse_value(raw: str, line_number: int) -> str:
    candidate = raw.strip(" \t\r")
    if not candidate:
        return ""

    # The strict subset intentionally does not implement systemd's backslash
    # escapes or physical-line continuation.  Rejecting every backslash also
    # ensures the same file cannot acquire different meanings when copied into
    # an accidental shell-based workflow.
    if "\\" in candidate:
        raise ValueError(
            f"line {line_number}: backslash escapes and continuations are not supported"
        )

    quote = candidate[0] if candidate[0] in {"'", '"'} else None
    if quote is not None:
        if len(candidate) < 2 or candidate[-1] != quote:
            raise ValueError(
                f"line {line_number}: partial or unterminated quoting is not supported"
            )
        value = candidate[1:-1]
        if quote in value:
            raise ValueError(f"line {line_number}: partial quoting is not supported")
    else:
        value = candidate
        if "'" in value or '"' in value:
            raise ValueError(f"line {line_number}: partial quoting is not supported")
        if any(character.isspace() for character in value):
            raise ValueError(f"line {line_number}: unquoted whitespace is not supported")

    validate_value_characters(value, line_number)
    reject_shell_syntax(value, line_number)
    return value


def load_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    content = path.read_text(encoding="utf-8")
    if (
        "\x00" in content
        or "\ufeff" in content
        or any(is_unicode_noncharacter(character) for character in content)
    ):
        raise ValueError("environment file contains an invalid Unicode character")
    for line_number, line in enumerate(content.split("\n"), start=1):
        stripped = line.strip(" \t\r")
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        if re.match(r"export(?:[ \t]+|$)", stripped):
            raise ValueError(f"line {line_number}: export prefixes are not supported")
        if "=" not in stripped:
            raise ValueError(f"line {line_number}: expected KEY=VALUE")
        key, raw = stripped.split("=", 1)
        if key != key.strip(" \t\r"):
            raise ValueError(
                f"line {line_number}: whitespace around environment keys is not supported"
            )
        if not KEY_PATTERN.fullmatch(key):
            raise ValueError(f"line {line_number}: invalid environment key")
        values[key] = parse_value(raw, line_number)
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--reject-privileged-loader-variables", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command and not args.validate_only:
        parser.error("a command is required after --")
    if not args.env_file.is_file():
        print("environment file does not exist", file=sys.stderr)
        return 2
    try:
        loaded = load_environment(args.env_file)
        # EnvironmentFile values are used to launch Python as root during
        # release validation and as the unprivileged service account during
        # canaries. Loader/search-path controls are never part of the supported
        # production contract, so reject them for every mode rather than only
        # for a caller-selected validation pass.
        forbidden = sorted(key for key in loaded if is_privileged_loader_key(key))
        if forbidden:
            raise ValueError(
                "privileged loader variables are forbidden: " + ", ".join(forbidden)
            )
        if args.validate_only:
            return 0
        # Never pass the invoking root shell's environment to release code.
        # In particular, deployment sessions can contain SSH agents, GitHub or
        # cloud credentials, proxy credentials and debugging hooks that are not
        # part of the service contract.  The root-owned EnvironmentFile is the
        # only supported source of deployment-specific values.
        environment = dict(SAFE_BASE_ENVIRONMENT)
        # Windows needs its system directory to initialize a child interpreter.
        # These two non-secret OS paths are never copied on Linux production.
        if os.name == "nt":
            for key in ("SystemRoot", "WINDIR"):
                if os.environ.get(key):
                    environment[key] = os.environ[key]
        environment.update(loaded)
        # ``os.execvpe`` is a true process replacement on Linux, which is the
        # production path.  On Windows CPython implements the exec family by
        # spawning a child and exiting immediately; a parent using
        # ``subprocess.run(..., capture_output=True)`` can therefore observe an
        # empty stream before that grandchild has flushed.  Keep the production
        # exec boundary, but wait for the diagnostic child on Windows so the
        # clean-environment contract is testable and exit codes are propagated.
        if os.name == "nt":
            return subprocess.run(command, env=environment, check=False).returncode
        close_inherited_file_descriptors()
        os.execvpe(command[0], command, environment)
    except FileDescriptorIsolationError:
        print(f"environment launch failed: {FD_ISOLATION_ERROR}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"environment launch failed: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
