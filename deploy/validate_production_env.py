#!/usr/bin/env python3
"""Validate production environment invariants without printing credentials."""

from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Sequence
from urllib.parse import urlsplit


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
PASSWORD_SCHEME = "scrypt"
PASSWORD_N = 2**14
PASSWORD_R = 8
PASSWORD_P = 1
PASSWORD_DKLEN = 32
PASSWORD_SALT_BYTES = 16
ADMIN_USERNAME_PATTERN = re.compile(r"[A-Z0-9_.-]{2,64}\Z")
SESSION_IDLE_MIN_SECONDS = 15 * 60
SESSION_ABSOLUTE_MIN_SECONDS = 60 * 60
# Keep expiry arithmetic comfortably below ``datetime.max`` in production.
SESSION_MAX_SECONDS = 366 * 24 * 60 * 60
HOSTNAME_PATTERN = re.compile(
    r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\Z"
)
VALIDATED_ENVIRONMENT_KEYS = {
    "MCGS_FULL_CHAIN_RUNS_ROOT",
    "PROTOCOL_STUDIO_ADMIN_FORCE_PASSWORD_CHANGE",
    "PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH",
    "PROTOCOL_STUDIO_ADMIN_USERNAME",
    "PROTOCOL_STUDIO_ALLOWED_HOSTS",
    "PROTOCOL_STUDIO_AUTH_ENABLED",
    "PROTOCOL_STUDIO_COOKIE_SECURE",
    "PROTOCOL_STUDIO_EXTERNAL_ORIGIN",
    "PROTOCOL_STUDIO_MCGS_DRIVER_LIBRARY_PATH",
    "PROTOCOL_STUDIO_RESOURCES_ROOT",
    "PROTOCOL_STUDIO_RUNS_ROOT",
    "PROTOCOL_STUDIO_SECURITY_DB",
    "PROTOCOL_STUDIO_SESSION_ABSOLUTE_SECONDS",
    "PROTOCOL_STUDIO_SESSION_IDLE_SECONDS",
    "PROTOCOL_STUDIO_SOURCE_COMPARE_METADATA",
    "PROTOCOL_STUDIO_SOURCE_WORKBOOKS_ROOT",
}
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
PRIVILEGED_LOADER_PREFIXES = (
    "BASH_FUNC_",
    "LD_",
    "DYLD_",
    "PYTHON",
    "UVICORN_",
    "_UVICORN_",
)
SAFE_RUNTIME_ENVIRONMENT = {
    "PATH": "/usr/sbin:/usr/bin",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUNBUFFERED": "1",
}


def flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUE_VALUES


def parse_boolean_value(
    value: object,
    *,
    default: bool | None = None,
) -> tuple[bool | None, bool]:
    if value is None:
        return default, default is not None
    if type(value) is not str:
        return None, False
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True, True
    if normalized in FALSE_VALUES:
        return False, True
    return None, False


def normalized_admin_username(value: object) -> str | None:
    if type(value) is not str:
        return None
    normalized = re.sub(r"\s+", "", value).upper()
    if ADMIN_USERNAME_PATTERN.fullmatch(normalized) is None:
        return None
    return normalized


def parse_session_seconds(
    value: object,
    *,
    default: int,
    minimum: int,
) -> tuple[int | None, bool]:
    if value is None:
        return default, True
    if type(value) is not str:
        return None, False
    normalized = value.strip()
    if re.fullmatch(r"(?:0|[1-9][0-9]*)", normalized) is None:
        return None, False
    maximum_text = str(SESSION_MAX_SECONDS)
    if len(normalized) > len(maximum_text) or (
        len(normalized) == len(maximum_text) and normalized > maximum_text
    ):
        return None, False
    parsed = int(normalized)
    if parsed < minimum:
        return None, False
    return parsed, True


def decode_canonical_urlsafe_base64(
    value: object,
    *,
    expected_length: int,
) -> bytes | None:
    if type(value) is not str or not value:
        return None
    if re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        return None
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        return None
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if len(decoded) != expected_length or canonical != value:
        return None
    return decoded


def valid_scrypt_password_hash(value: object) -> bool:
    """Match the bounded, canonical output contract of security.hash_password."""

    if type(value) is not str or not value or len(value) > 256:
        return False
    components = value.split("$")
    if len(components) != 4:
        return False
    scheme, params_text, salt_text, digest_text = components
    if scheme != PASSWORD_SCHEME:
        return False

    expected_params = {
        "n": PASSWORD_N,
        "r": PASSWORD_R,
        "p": PASSWORD_P,
        "dk": PASSWORD_DKLEN,
    }
    parsed_params: dict[str, int] = {}
    items = params_text.split(",")
    if len(items) != len(expected_params):
        return False
    for item in items:
        if item.count("=") != 1:
            return False
        key, encoded_integer = item.split("=", 1)
        if key not in expected_params or key in parsed_params:
            return False
        if re.fullmatch(r"(?:0|[1-9][0-9]*)", encoded_integer) is None:
            return False
        parsed_params[key] = int(encoded_integer)
    if parsed_params != expected_params:
        return False

    salt = decode_canonical_urlsafe_base64(
        salt_text,
        expected_length=PASSWORD_SALT_BYTES,
    )
    digest = decode_canonical_urlsafe_base64(
        digest_text,
        expected_length=PASSWORD_DKLEN,
    )
    return salt is not None and digest is not None


def canonical_absolute_path(value: str | os.PathLike[str]) -> Path | None:
    raw = os.fspath(value)
    if not raw or "\x00" in raw:
        return None
    path = Path(raw)
    normalized = Path(os.path.normpath(raw))
    if (
        not path.is_absolute()
        or path != normalized
        or (os.name == "posix" and os.path.normpath(raw) != raw)
    ):
        return None
    return path


def configured_path(name: str) -> tuple[Path | None, bool]:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None, True
    path = canonical_absolute_path(raw)
    return path, path is not None


def has_safe_existing_identity(path: Path | None, expected_kind: str) -> bool:
    if path is None:
        return False
    current = Path(path.anchor)
    components = [current]
    for part in path.parts[1:]:
        current /= part
        components.append(current)
    try:
        statuses = [component.lstat() for component in components]
    except OSError:
        return False
    if any(stat.S_ISLNK(status.st_mode) for status in statuses):
        return False
    target_mode = statuses[-1].st_mode
    if expected_kind == "directory":
        return stat.S_ISDIR(target_mode)
    if expected_kind == "regular_file":
        return stat.S_ISREG(target_mode)
    raise ValueError(f"unsupported path kind: {expected_kind}")


def valid_host(value: str) -> bool:
    if value in {"*", "0.0.0.0"}:
        return False
    try:
        return not ipaddress.ip_address(value).is_unspecified
    except ValueError:
        return HOSTNAME_PATTERN.fullmatch(value) is not None


def valid_public_dns_host(value: str) -> bool:
    if (
        value != value.casefold()
        or "." not in value
        or not any(character.isalpha() for character in value.rsplit(".", 1)[1])
    ):
        return False
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return HOSTNAME_PATTERN.fullmatch(value) is not None
    return False


def is_forbidden_environment_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        codepoint < 0x20
        or codepoint == 0x7F
        or character == "\ufeff"
        or 0xFDD0 <= codepoint <= 0xFDEF
        or (codepoint & 0xFFFF) in {0xFFFE, 0xFFFF}
    )


def invalid_environment_value_names() -> list[str]:
    """Return names only, so validation reports never disclose credentials."""

    return sorted(
        name
        for name in VALIDATED_ENVIRONMENT_KEYS
        if any(
            is_forbidden_environment_character(character)
            for character in os.environ.get(name, "")
        )
    )


def privileged_loader_environment_names() -> list[str]:
    """Return dangerous environment names only, never their values."""

    rejected: list[str] = []
    for name, value in os.environ.items():
        if name in SAFE_RUNTIME_ENVIRONMENT:
            if value != SAFE_RUNTIME_ENVIRONMENT[name]:
                rejected.append(name)
            continue
        if name in PRIVILEGED_LOADER_KEYS or name.startswith(
            PRIVILEGED_LOADER_PREFIXES
        ):
            rejected.append(name)
    return sorted(rejected)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-runs", type=Path, required=True)
    parser.add_argument("--security-db", type=Path, required=True)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--public-host", required=True)
    args = parser.parse_args(argv)
    errors: list[str] = []

    expected_runs = canonical_absolute_path(args.shared_runs)
    expected_database = canonical_absolute_path(args.security_db)
    configured_runs, configured_runs_canonical = configured_path(
        "PROTOCOL_STUDIO_RUNS_ROOT"
    )
    configured_mcgs_runs, configured_mcgs_runs_canonical = configured_path(
        "MCGS_FULL_CHAIN_RUNS_ROOT"
    )
    configured_database, configured_database_canonical = configured_path(
        "PROTOCOL_STUDIO_SECURITY_DB"
    )
    expected_paths_canonical = expected_runs is not None and expected_database is not None
    configured_paths_canonical = (
        configured_runs_canonical
        and configured_mcgs_runs_canonical
        and configured_database_canonical
    )
    runs_identity_safe = has_safe_existing_identity(expected_runs, "directory")
    database_identity_safe = has_safe_existing_identity(
        expected_database, "regular_file"
    )
    # A production release must use its own immutable ``resources/protocol``
    # tree.  Reject the override by key presence (including an empty value)
    # instead of trusting a path supplied by the EnvironmentFile itself.
    resources_override_configured = "PROTOCOL_STUDIO_RESOURCES_ROOT" in os.environ
    invalid_value_names = invalid_environment_value_names()
    privileged_loader_names = privileged_loader_environment_names()
    authentication_enabled, authentication_flag_valid = parse_boolean_value(
        os.environ.get("PROTOCOL_STUDIO_AUTH_ENABLED"),
        default=False,
    )
    secure_cookie, secure_cookie_flag_valid = parse_boolean_value(
        os.environ.get("PROTOCOL_STUDIO_COOKIE_SECURE"),
        default=False,
    )
    force_password_change, force_password_change_valid = parse_boolean_value(
        os.environ.get("PROTOCOL_STUDIO_ADMIN_FORCE_PASSWORD_CHANGE"),
        default=True,
    )
    admin_username = normalized_admin_username(
        os.environ.get("PROTOCOL_STUDIO_ADMIN_USERNAME", "FEIAN")
    )
    password_hash_valid = valid_scrypt_password_hash(
        os.environ.get("PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH", "").strip()
    )
    session_idle_seconds, session_idle_valid = parse_session_seconds(
        os.environ.get("PROTOCOL_STUDIO_SESSION_IDLE_SECONDS"),
        default=12 * 60 * 60,
        minimum=SESSION_IDLE_MIN_SECONDS,
    )
    session_absolute_seconds, session_absolute_valid = parse_session_seconds(
        os.environ.get("PROTOCOL_STUDIO_SESSION_ABSOLUTE_SECONDS"),
        default=7 * 24 * 60 * 60,
        minimum=SESSION_ABSOLUTE_MIN_SECONDS,
    )
    session_lifetime_order_valid = (
        session_idle_valid
        and session_absolute_valid
        and session_idle_seconds is not None
        and session_absolute_seconds is not None
        and session_idle_seconds <= session_absolute_seconds
    )

    if invalid_value_names:
        errors.append(
            "production environment contains forbidden control or Unicode characters: "
            + ", ".join(invalid_value_names)
        )
    if privileged_loader_names:
        errors.append(
            "production environment contains privileged loader or startup controls: "
            + ", ".join(privileged_loader_names)
        )
    if not authentication_flag_valid:
        errors.append("authentication flag is invalid")
    elif authentication_enabled is not True:
        errors.append("authentication must be enabled")
    if not secure_cookie_flag_valid:
        errors.append("secure-cookie flag is invalid")
    elif secure_cookie is not True:
        errors.append("secure cookies must be enabled")
    if admin_username is None:
        errors.append("administrator username is missing or invalid")
    if not password_hash_valid:
        errors.append("bootstrap password hash is missing or invalid")
    if not force_password_change_valid:
        errors.append("administrator force-password-change flag is invalid")
    if not session_idle_valid:
        errors.append("session idle seconds is missing, noncanonical or out of range")
    if not session_absolute_valid:
        errors.append("session absolute seconds is missing, noncanonical or out of range")
    if session_idle_valid and session_absolute_valid and not session_lifetime_order_valid:
        errors.append("session idle seconds must not exceed session absolute seconds")
    if resources_override_configured:
        errors.append("production environment must use packaged protocol resources")
    if not expected_paths_canonical:
        errors.append("expected shared paths must be canonical absolute paths")
    if not configured_paths_canonical:
        errors.append("configured shared paths must be canonical absolute paths")
    if configured_runs is None or expected_runs is None or configured_runs != expected_runs:
        errors.append("runs root does not match the shared path")
    if configured_mcgs_runs is not None and (
        expected_runs is None
        or configured_mcgs_runs != expected_runs
    ):
        errors.append("higher-priority MCGS runs root does not match the shared path")
    if (
        configured_database is None
        or expected_database is None
        or configured_database != expected_database
    ):
        errors.append("security database does not match the shared path")
    if not runs_identity_safe:
        errors.append("shared runs path must be an existing non-symlink directory with no symlink ancestors")
    if not database_identity_safe:
        errors.append("shared security database must be an existing non-symlink regular file with no symlink ancestors")
    if os.environ.get("PROTOCOL_STUDIO_EXTERNAL_ORIGIN", "") != args.public_origin:
        errors.append("external origin does not match the production origin")
    parsed_origin = urlsplit(args.public_origin)
    try:
        parsed_origin_port = parsed_origin.port
    except ValueError:
        parsed_origin_port = -1
    if (
        not valid_public_dns_host(args.public_host)
        or parsed_origin.scheme != "https"
        or parsed_origin.hostname != args.public_host
        or parsed_origin_port is not None
        or parsed_origin.username is not None
        or parsed_origin.password is not None
        or parsed_origin.query
        or parsed_origin.fragment
        or parsed_origin.path
        or args.public_origin != f"https://{args.public_host}"
    ):
        errors.append(
            "public origin must be a canonical lowercase HTTPS DNS origin for the public host"
        )
    allowed_hosts_raw = os.environ.get("PROTOCOL_STUDIO_ALLOWED_HOSTS", "")
    allowed_host_parts = [value.strip() for value in allowed_hosts_raw.split(",")]
    normalized_hosts = [value.casefold() for value in allowed_host_parts if value]
    allowed_hosts = set(normalized_hosts)
    if not allowed_hosts_raw.strip() or any(not value for value in allowed_host_parts):
        errors.append("allowed hosts contains an empty entry")
    if len(normalized_hosts) != len(allowed_hosts):
        errors.append("allowed hosts contains duplicate entries")
    invalid_hosts = sorted({value for value in normalized_hosts if not valid_host(value)})
    if invalid_hosts:
        errors.append("allowed hosts contains wildcard, bind-all or invalid host entries")
    if args.public_host.casefold() not in allowed_hosts or "127.0.0.1" not in allowed_hosts:
        errors.append("allowed hosts must include the public host and 127.0.0.1")

    report = {
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "checks": {
            "environment_values_safe": not invalid_value_names,
            "privileged_loader_environment_safe": not privileged_loader_names,
            "authentication_flag_valid": authentication_flag_valid,
            "authentication_enabled": authentication_enabled is True,
            "secure_cookie_flag_valid": secure_cookie_flag_valid,
            "secure_cookie": secure_cookie is True,
            "admin_username_valid": admin_username is not None,
            "password_hash_present": password_hash_valid,
            "password_hash_valid": password_hash_valid,
            "force_password_change_valid": force_password_change_valid
            and force_password_change is not None,
            "session_idle_seconds_valid": session_idle_valid,
            "session_absolute_seconds_valid": session_absolute_valid,
            "session_lifetime_order_valid": session_lifetime_order_valid,
            "packaged_protocol_resources_enforced": not resources_override_configured,
            "shared_paths_canonical": expected_paths_canonical
            and configured_paths_canonical,
            "shared_runs_preserved": configured_runs is not None
            and expected_runs is not None
            and configured_runs == expected_runs
            and (
                configured_mcgs_runs is None
                or configured_mcgs_runs == expected_runs
            )
            and runs_identity_safe,
            "shared_security_database_preserved": configured_database is not None
            and expected_database is not None
            and configured_database == expected_database
            and database_identity_safe,
            "origin_restricted": bool(allowed_hosts_raw.strip())
            and not invalid_hosts
            and not any(not value for value in allowed_host_parts)
            and len(normalized_hosts) == len(allowed_hosts),
        },
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
