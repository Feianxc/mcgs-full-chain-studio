#!/usr/bin/env python3
"""Validate production environment invariants without printing credentials."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence


TRUE_VALUES = {"1", "true", "yes", "on"}


def flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUE_VALUES


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-runs", type=Path, required=True)
    parser.add_argument("--security-db", type=Path, required=True)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--public-host", required=True)
    args = parser.parse_args(argv)
    errors: list[str] = []

    expected_runs = args.shared_runs.resolve()
    expected_database = args.security_db.resolve()
    configured_runs = Path(
        os.environ.get("PROTOCOL_STUDIO_RUNS_ROOT", "")
    ).expanduser()
    configured_database = Path(
        os.environ.get("PROTOCOL_STUDIO_SECURITY_DB", "")
    ).expanduser()

    if not flag("PROTOCOL_STUDIO_AUTH_ENABLED"):
        errors.append("authentication must be enabled")
    if not flag("PROTOCOL_STUDIO_COOKIE_SECURE"):
        errors.append("secure cookies must be enabled")
    if not os.environ.get("PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH", "").startswith("scrypt$"):
        errors.append("bootstrap password hash is missing or invalid")
    if configured_runs.resolve() != expected_runs:
        errors.append("runs root does not match the shared path")
    if configured_database.resolve() != expected_database:
        errors.append("security database does not match the shared path")
    if not expected_runs.is_dir():
        errors.append("shared runs directory does not exist")
    if not expected_database.is_file():
        errors.append("shared security database does not exist; deployment must not create it")
    if os.environ.get("PROTOCOL_STUDIO_EXTERNAL_ORIGIN", "").rstrip("/") != args.public_origin.rstrip("/"):
        errors.append("external origin does not match the production origin")
    allowed_hosts = {
        value.strip()
        for value in os.environ.get("PROTOCOL_STUDIO_ALLOWED_HOSTS", "").split(",")
        if value.strip()
    }
    if args.public_host not in allowed_hosts or "127.0.0.1" not in allowed_hosts:
        errors.append("allowed hosts must include the public host and 127.0.0.1")

    report = {
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "checks": {
            "authentication_enabled": flag("PROTOCOL_STUDIO_AUTH_ENABLED"),
            "secure_cookie": flag("PROTOCOL_STUDIO_COOKIE_SECURE"),
            "password_hash_present": os.environ.get(
                "PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH", ""
            ).startswith("scrypt$"),
            "shared_runs_preserved": configured_runs.resolve() == expected_runs
            and expected_runs.is_dir(),
            "shared_security_database_preserved": configured_database.resolve()
            == expected_database
            and expected_database.is_file(),
            "origin_restricted": not any(
                text in os.environ.get("PROTOCOL_STUDIO_ALLOWED_HOSTS", "")
                for text in ("*", "0.0.0.0")
            ),
        },
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
