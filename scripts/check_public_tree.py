#!/usr/bin/env python3
"""Fail when a candidate public tree contains common private artifacts.

This is a release gate, not a substitute for a human provenance review.
Client-specific deny tokens can be supplied through a gitignored local file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


FORBIDDEN_SUFFIXES = {
    ".7z",
    ".accdb",
    ".bak",
    ".csv",
    ".db",
    ".dwg",
    ".dxf",
    ".key",
    ".ldb",
    ".mcp",
    ".mdb",
    ".p12",
    ".pdf",
    ".pem",
    ".pfx",
    ".rar",
    ".sqlite",
    ".sqlite3",
    ".sql",
    ".tsv",
    ".xls",
    ".xlsb",
    ".xlsm",
    ".xlsx",
    ".xml",
    ".zip",
}

FORBIDDEN_PARTS = {
    ".audit-code",
    ".audit-output",
    ".codex-runtime",
    ".local",
    ".test_tmp",
    "__pycache__",
    "customer-data",
    "customer_data",
    "customers",
    "logs",
    "node_modules",
    "outputs",
    "protocol_runs",
    "runs",
    "shared",
    "交付包",
    "客户资料",
    "项目实例",
}

SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "dist",
    "venv",
}

TEXT_SUFFIXES = {
    "",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsonc",
    ".md",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}

MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024

CONTENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    ),
    (
        "aws-access-key",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "bearer-token",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    ),
    (
        "windows-absolute-path",
        re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]):[\\/]"),
    ),
    (
        "windows-unc-path",
        re.compile(r"\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9_$.-]+"),
    ),
    (
        "user-home-path",
        re.compile(r"(?:/Users/|/home/|\\Users\\)[^/\\\s\"']+"),
    ),
    (
        "internal-build-provenance",
        re.compile(r"(?i)(?:\.workspace[\\/]codex-swarm|source_evidence|upstream_artifacts)"),
    ),
    (
        "embedded-password-hash",
        re.compile(
            r"(?im)^PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH[ \t]*=[ \t]*"
            r"(?![ \t]*(?:$|REPLACE|CHANGEME|<))\S+"
        ),
    ),
)

SYNTHETIC_SECURITY_TEST = PurePosixPath(
    "tests/protocol/protocol_studio_security_test.py"
)
SCANNER_SOURCE = PurePosixPath("scripts/check_public_tree.py")
ASSEMBLY_DATA = PurePosixPath("assembly_studio/static/data.js")
ASSEMBLY_DATA_PRIVATE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "nonempty-project-identity",
        re.compile(
            r'"(?:project_id|project_name|site_name|room)"\s*:\s*"(?!\s*")'
        ),
    ),
    (
        "embedded-source-provenance",
        re.compile(
            r'"(?:projectInput|upstream_artifacts|source_evidence|sourceBuildId|sha256)"\s*:'
        ),
    ),
)


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


def normalize_relative(root: Path, path: Path) -> str:
    relative = path.resolve().relative_to(root.resolve())
    return PurePosixPath(*relative.parts).as_posix()


def iter_candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in SKIP_PARTS for part in relative_parts):
            continue
        if path.is_file() or path.is_symlink():
            files.append(path)
    return sorted(files, key=lambda item: normalize_relative(root, item))


def load_deny_tokens(root: Path, explicit: Path | None) -> list[str]:
    candidate = explicit or root / "packaging" / "private-markers.local.txt"
    if not candidate.exists():
        return []
    tokens: list[str] = []
    for line in candidate.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            tokens.append(value)
    return tokens


def is_text_candidate(path: Path, size: int) -> bool:
    if size > MAX_TEXT_BYTES:
        return False
    if path.name in {"Dockerfile", "LICENSE", "NOTICE"} or path.name.startswith(".env"):
        return True
    return path.suffix.lower() in TEXT_SUFFIXES


def scan_paths(
    root: Path,
    paths: Sequence[Path],
    *,
    deny_tokens: Sequence[str] = (),
) -> list[Finding]:
    root = root.resolve()
    findings: list[Finding] = []

    for path in paths:
        path = path.resolve()
        try:
            relative = normalize_relative(root, path)
        except ValueError:
            findings.append(
                Finding("outside-root", "<outside-root>", "candidate resolves outside the public root")
            )
            continue

        pure = PurePosixPath(relative)
        lower_parts = {part.lower() for part in pure.parts}
        forbidden_part = sorted(lower_parts.intersection(FORBIDDEN_PARTS))
        if forbidden_part:
            findings.append(
                Finding(
                    "forbidden-directory",
                    relative,
                    f"contains forbidden path component: {forbidden_part[0]}",
                )
            )

        if path.is_symlink():
            findings.append(Finding("symbolic-link", relative, "symbolic links are not publishable"))
            continue

        suffix = path.suffix.lower()
        if suffix in FORBIDDEN_SUFFIXES:
            findings.append(
                Finding("forbidden-file-type", relative, f"forbidden suffix: {suffix}")
            )

        try:
            size = path.stat().st_size
        except OSError as exc:
            findings.append(Finding("stat-failed", relative, type(exc).__name__))
            continue
        if size > MAX_FILE_BYTES:
            findings.append(
                Finding("oversized-file", relative, f"{size} bytes exceeds {MAX_FILE_BYTES}")
            )

        if not is_text_candidate(path, size):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(
                Finding("non-utf8-text", relative, "text candidate is not valid UTF-8")
            )
            continue

        for rule_name, pattern in CONTENT_RULES:
            if pure == SCANNER_SOURCE and rule_name in {
                "internal-build-provenance",
                "user-home-path",
            }:
                continue
            if pure == SYNTHETIC_SECURITY_TEST and rule_name in {
                "embedded-password-hash",
                "bearer-token",
            }:
                continue
            match = pattern.search(text)
            if match:
                line_number = text.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(rule_name, relative, f"matched on line {line_number}")
                )

        for token in deny_tokens:
            offset = text.find(token)
            if offset >= 0:
                line_number = text.count("\n", 0, offset) + 1
                findings.append(
                    Finding("local-deny-token", relative, f"matched on line {line_number}")
                )

        if pure == ASSEMBLY_DATA:
            for rule_name, pattern in ASSEMBLY_DATA_PRIVATE_RULES:
                match = pattern.search(text)
                if match:
                    line_number = text.count("\n", 0, match.start()) + 1
                    findings.append(
                        Finding(rule_name, relative, f"matched on line {line_number}")
                    )

    return sorted(findings, key=lambda item: (item.path, item.code, item.detail))


def scan_tree(root: Path, *, deny_file: Path | None = None) -> tuple[list[Path], list[Finding]]:
    root = root.resolve()
    paths = iter_candidate_files(root)
    tokens = load_deny_tokens(root, deny_file)
    return paths, scan_paths(root, paths, deny_tokens=tokens)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--deny-file",
        type=Path,
        help="optional UTF-8 file containing one private marker per line",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="optional report path; paths inside the report remain repository-relative",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: public root is not a directory: {root.name}", file=sys.stderr)
        return 2

    paths, findings = scan_tree(root, deny_file=args.deny_file)
    report = {
        "schema_version": 1,
        "status": "passed" if not findings else "failed",
        "files_scanned": len(paths),
        "findings": [item.as_dict() for item in findings],
    }

    if args.json_output:
        output = args.json_output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
