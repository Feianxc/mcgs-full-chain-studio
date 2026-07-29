from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "deploy" / "deploy-release.sh"
ROLLBACK_SCRIPT = REPO_ROOT / "deploy" / "rollback-release.sh"
RECOVERY_SCRIPT = REPO_ROOT / "deploy" / "recover-transaction.sh"
CHECK_PRODUCTION_SCRIPT = REPO_ROOT / "deploy" / "check-production.sh"
ENV_RUNNER = REPO_ROOT / "deploy" / "run_with_env.py"
ENV_VALIDATOR = REPO_ROOT / "deploy" / "validate_production_env.py"
REFERENCE_SERVICE_UNIT = REPO_ROOT / "deploy" / "protocol-studio.service"
RUNTIME_FINGERPRINT_HELPER = REPO_ROOT / "deploy" / "runtime_fingerprint.py"
SHELL_SCRIPTS = (DEPLOY_SCRIPT, ROLLBACK_SCRIPT, RECOVERY_SCRIPT)
ALL_SHELL_SCRIPTS = (*SHELL_SCRIPTS, CHECK_PRODUCTION_SCRIPT)
EXPECTED_UNSET_ENVIRONMENT = tuple(
    (
        "BASHOPTS BASH_ENV CDPATH ENV GCONV_PATH GLIBC_TUNABLES GLOBIGNORE "
        "LD_ASSUME_KERNEL LD_AUDIT LD_BIND_NOT LD_BIND_NOW LD_DEBUG "
        "LD_DEBUG_OUTPUT LD_DYNAMIC_WEAK LD_HWCAP_MASK LD_LIBRARY_PATH "
        "LD_ORIGIN_PATH LD_POINTER_GUARD LD_PREFER_MAP_32BIT_EXEC LD_PRELOAD "
        "LD_PROFILE LD_PROFILE_OUTPUT LD_SHOW_AUXV LD_TRACE_LOADED_OBJECTS "
        "LD_TRACE_PRELINKING LD_USE_LOAD_BIAS LD_VERBOSE LD_WARN LOCPATH "
        "OPENSSL_CONF OPENSSL_CONF_INCLUDE OPENSSL_ENGINES OPENSSL_MODULES "
        "PATH PYTHONHOME PYTHONINSPECT PYTHONPATH PYTHONSTARTUP SHELLOPTS "
        "_UVICORN_COMPLETE FORWARDED_ALLOW_IPS UVICORN_ACCESS_LOG UVICORN_APP "
        "UVICORN_APP_DIR UVICORN_BACKLOG UVICORN_DATE_HEADER UVICORN_ENV_FILE "
        "UVICORN_FACTORY UVICORN_FD UVICORN_FORWARDED_ALLOW_IPS "
        "UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE UVICORN_HEADERS UVICORN_HOST "
        "UVICORN_HTTP UVICORN_INTERFACE UVICORN_LIFESPAN "
        "UVICORN_LIMIT_CONCURRENCY UVICORN_LIMIT_MAX_REQUESTS UVICORN_LOG_CONFIG "
        "UVICORN_LOG_LEVEL UVICORN_LOOP UVICORN_PORT UVICORN_PROXY_HEADERS "
        "UVICORN_RELOAD UVICORN_RELOAD_DELAY UVICORN_RELOAD_DIRS "
        "UVICORN_RELOAD_EXCLUDES UVICORN_RELOAD_INCLUDES UVICORN_ROOT_PATH "
        "UVICORN_SERVER_HEADER UVICORN_SSL_CA_CERTS UVICORN_SSL_CERTFILE "
        "UVICORN_SSL_CERT_REQS UVICORN_SSL_CIPHERS UVICORN_SSL_KEYFILE "
        "UVICORN_SSL_KEYFILE_PASSWORD UVICORN_SSL_VERSION "
        "UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN UVICORN_TIMEOUT_KEEP_ALIVE "
        "UVICORN_TIMEOUT_WORKER_HEALTHCHECK UVICORN_UDS UVICORN_USE_COLORS "
        "UVICORN_VERSION UVICORN_WORKERS UVICORN_WS UVICORN_WS_MAX_QUEUE "
        "UVICORN_WS_MAX_SIZE UVICORN_WS_PER_MESSAGE_DEFLATE "
        "UVICORN_WS_PING_INTERVAL UVICORN_WS_PING_TIMEOUT WEB_CONCURRENCY"
    ).split()
)


def require_fragments(content: str, fragments: list[str], label: str) -> None:
    missing = [fragment for fragment in fragments if fragment not in content]
    if missing:
        raise AssertionError(json.dumps({"label": label, "missing": missing}, ensure_ascii=False))


def require_in_order(content: str, fragments: list[str], label: str) -> None:
    positions: list[int] = []
    offset = 0
    for fragment in fragments:
        position = content.find(fragment, offset)
        if position < 0:
            raise AssertionError(
                json.dumps(
                    {"label": label, "missing_or_out_of_order": fragment, "positions": positions},
                    ensure_ascii=False,
                )
            )
        positions.append(position)
        offset = position + len(fragment)


def content_after(content: str, anchor: str, label: str) -> str:
    position = content.find(anchor)
    if position < 0:
        raise AssertionError(f"{label}: anchor is missing: {anchor}")
    return content[position:]


def function_body(content: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n(?P<body>.*?)(?=^[A-Za-z_][A-Za-z0-9_]*\(\) \{{|\Z)",
        content,
    )
    if not match:
        raise AssertionError(f"function is missing: {name}")
    return match.group("body")


def function_definition(content: str, name: str) -> str:
    return f"{name}() {{\n{function_body(content, name)}"


def simple_function_definition(content: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}[ \t]*$",
        content,
    )
    if not match:
        raise AssertionError(f"simple function is missing: {name}")
    return match.group(0)


def assert_deploy_activation_schema_fail_fast_contract(
    content: str,
) -> tuple[str, str, str, int]:
    legacy_definition = (
        'LEGACY_RELEASE_ID="${PROTOCOL_STUDIO_LEGACY_RELEASE_ID:-'
        '20260722-114300-620b1bcf9aa9}"'
    )
    if content.count(legacy_definition) != 1:
        raise AssertionError("deploy legacy release id must have one canonical definition")

    audit_source = simple_function_definition(content, "audit_current_activation_schema")
    gate_source = simple_function_definition(
        content, "require_activatable_passed_record_schema"
    )
    require_fragments(
        audit_source,
        [
            '[[ -L "$CURRENT_LINK" ]]',
            'current_target="$(readlink -f -- "$CURRENT_LINK")"',
            '"$RELEASES_DIR"/*)',
            'if [[ "$current_id" == "$LEGACY_RELEASE_ID" ]]; then',
            '[[ ! -e "$current_target/.venv" && ! -L "$current_target/.venv" ]]',
            'record="$DEPLOYMENT_DIR/$current_id.json"',
            'assert_trusted_record_file "$record"',
            "object_pairs_hook=strict_object",
            "parse_constant=",
            "type(schema) is not int",
            "schema not in {2, 3, 4, 5}",
            'require_activatable_passed_record_schema "$schema"',
        ],
        "deploy-activation-schema-read-only-audit",
    )
    forbidden_mutations = [
        fragment
        for fragment in (
            "systemctl ",
            "systemd-run ",
            "install ",
            "mv ",
            "rm ",
            "sqlite_backup.py",
            "install_runtime_guard_helper",
            "create_runtime_baseline",
        )
        if fragment in audit_source
    ]
    if forbidden_mutations:
        raise AssertionError(
            "deploy activation schema audit contains mutation-capable operations: "
            f"{forbidden_mutations}"
        )

    entry_match = re.search(
        r'(?m)^if \[\[ "\$MODE" == "switch" \]\]; then\n'
        r'  audit_current_activation_schema\nfi$',
        content,
    )
    if entry_match is None:
        raise AssertionError("deploy switch-only activation schema entry gate is missing")
    entry_block = entry_match.group(0)
    activation_entry = content[entry_match.start() :]
    side_effect_anchors = [
        "verify_atomic_rename_boundary \\",
        'TRUSTED_ARCHIVE="$CONTROL_DIR/.archive-$RELEASE_ID-$$.tar.gz"',
        'PREFLIGHT_ROOT="$APP_ROOT/.preflight-$RELEASE_ID-$$"',
        'backup --source "$SECURITY_DB" --destination "$PREFLIGHT_DB"',
        'systemd-run --quiet --collect --unit="$PREFLIGHT_UNIT"',
        'DROPIN_CANDIDATE="$LOG_DIR/.runtime-dropin-$RELEASE_ID-$$"',
        'UNIT_BACKUP="$BACKUP_DIR/$SERVICE-$BACKUP_STAMP-before-$RELEASE_ID"',
        'DROPIN_BACKUP="$BACKUP_DIR/$SERVICE-runtime-$BACKUP_STAMP-before-$RELEASE_ID.conf"',
        "install_runtime_guard_helper \\",
        "create_runtime_baseline \\",
        'mv -Tf -- "$TRANSACTION_TEMP" "$TRANSACTION_FILE"',
        'systemctl disable "$SERVICE"',
    ]
    require_in_order(
        activation_entry,
        [entry_block, *side_effect_anchors],
        "deploy-historical-schema-rejected-before-all-activation-side-effects",
    )
    return audit_source, gate_source, entry_block, len(side_effect_anchors)


def snapshot_activation_boundary(root: Path) -> dict[str, tuple[object, ...]]:
    snapshot: dict[str, tuple[object, ...]] = {}
    for path in sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if path.is_symlink():
            snapshot[relative] = ("symlink", os.readlink(path))
        elif path.is_dir():
            snapshot[relative] = ("directory", metadata.st_mode & 0o7777)
        elif path.is_file():
            snapshot[relative] = (
                "file",
                metadata.st_mode & 0o7777,
                path.read_bytes(),
            )
        else:
            snapshot[relative] = ("other", metadata.st_mode)
    return snapshot


def assert_deploy_activation_schema_fail_fast_behavior(
    bash: str,
    audit_source: str,
    gate_source: str,
    entry_block: str,
    temporary_root: Path,
) -> dict[str, object]:
    harness = temporary_root / "deploy-activation-schema-entry-harness.sh"
    harness.write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        "fail() { printf '%s\\n' \"$*\" >&2; exit 97; }\n"
        "assert_trusted_record_file() { [[ -f \"$1\" && ! -L \"$1\" ]] || fail \"untrusted record\"; }\n"
        "STATE_ROOT=\"$1\"\n"
        "PYTHON_BIN=\"$2\"\n"
        "MODE=\"$3\"\n"
        "LEGACY_RELEASE_ID=\"$4\"\n"
        "RELEASES_DIR=\"$(readlink -f -- \"$STATE_ROOT/releases\")\"\n"
        "CURRENT_LINK=\"$STATE_ROOT/current\"\n"
        "DEPLOYMENT_DIR=\"$(readlink -f -- \"$STATE_ROOT/deployments\")\"\n"
        "MUTATION_LOG=\"$STATE_ROOT/systemd-mutation.log\"\n"
        "systemctl() { printf 'systemctl %s\\n' \"$*\" >>\"$MUTATION_LOG\"; }\n"
        "systemd-run() { printf 'systemd-run %s\\n' \"$*\" >>\"$MUTATION_LOG\"; }\n"
        + gate_source
        + "\n"
        + audit_source
        + "\n"
        + entry_block
        + "\nprintf 'continued\\n' >\"$STATE_ROOT/continued\"\n",
        encoding="utf-8",
        newline="\n",
    )
    harness.chmod(0o755)

    legacy_id = "registered-legacy"
    protected_payloads = {
        "protected/process/main.pid": b"4242\n",
        "protected/systemd/base-unit": b"base-unit-v1\n",
        "protected/systemd/managed-dropin": b"managed-dropin-v1\n",
        "protected/systemd/transient-unit": b"absent-before-and-after\n",
        "protected/systemd/enablement": b"enabled\n",
        "protected/transaction/marker": b"no-active-marker\n",
        "protected/runtime/helper": b"immutable-helper\n",
        "protected/runtime/baseline": b"immutable-baseline\n",
        "protected/shared/security.sqlite3": b"database-bytes\n",
        "protected/backups/existing.sqlite3": b"existing-backup\n",
        "protected/preflight/state": b"no-preflight-created\n",
    }

    def create_case(name: str, current_id: str, record_payload: bytes | None) -> Path:
        case_root = temporary_root / name
        releases = case_root / "releases"
        current_target = releases / current_id
        deployments = case_root / "deployments"
        current_target.mkdir(parents=True)
        deployments.mkdir()
        if record_payload is not None:
            runtime_python = current_target / ".venv" / "bin" / "python"
            runtime_python.parent.mkdir(parents=True)
            runtime_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
            runtime_python.chmod(0o755)
            (deployments / f"{current_id}.json").write_bytes(record_payload)
        (case_root / "current").symlink_to(
            Path("releases") / current_id,
            target_is_directory=True,
        )
        for relative, payload in protected_payloads.items():
            target = case_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        (case_root / "systemd-mutation.log").write_bytes(b"")
        return case_root

    python_bin = Path(sys.executable).as_posix()
    historical_rejections = 0
    for schema in (2, 3, 4):
        case_root = create_case(
            f"historical-schema-{schema}",
            f"historical-{schema}",
            (json.dumps({"schema_version": schema}, separators=(",", ":")) + "\n").encode(
                "utf-8"
            ),
        )
        before = snapshot_activation_boundary(case_root)
        completed = subprocess.run(
            [
                bash,
                os.fspath(harness),
                case_root.as_posix(),
                python_bin,
                "switch",
                legacy_id,
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        after = snapshot_activation_boundary(case_root)
        if completed.returncode != 97 or "audit-only" not in completed.stderr:
            raise AssertionError(
                f"deploy switch entry did not fail closed for schema {schema}: "
                f"exit={completed.returncode} stdout={completed.stdout!r} "
                f"stderr={completed.stderr!r}"
            )
        if before != after:
            raise AssertionError(
                f"deploy schema {schema} entry changed protected or preflight state"
            )
        if (case_root / "continued").exists():
            raise AssertionError(f"deploy schema {schema} reached post-audit entry work")
        if (case_root / "systemd-mutation.log").read_bytes() != b"":
            raise AssertionError(f"deploy schema {schema} invoked systemctl/systemd-run")
        historical_rejections += 1

    schema5_root = create_case(
        "schema-5",
        "schema-5-current",
        b'{"schema_version":5}\n',
    )
    schema5 = subprocess.run(
        [
            bash,
            os.fspath(harness),
            schema5_root.as_posix(),
            python_bin,
            "switch",
            legacy_id,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if schema5.returncode != 0 or not (schema5_root / "continued").is_file():
        raise AssertionError(
            "deploy schema 5 failed the minimal gate instead of reaching full validation: "
            f"exit={schema5.returncode} stderr={schema5.stderr!r}"
        )

    legacy_root = create_case("registered-legacy", legacy_id, None)
    legacy = subprocess.run(
        [
            bash,
            os.fspath(harness),
            legacy_root.as_posix(),
            python_bin,
            "switch",
            legacy_id,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if legacy.returncode != 0 or not (legacy_root / "continued").is_file():
        raise AssertionError(
            "registered legacy deploy failed the minimal gate: "
            f"exit={legacy.returncode} stderr={legacy.stderr!r}"
        )

    prepare_root = create_case(
        "prepare-historical",
        "prepare-schema-2",
        b'{"schema_version":2}\n',
    )
    prepare = subprocess.run(
        [
            bash,
            os.fspath(harness),
            prepare_root.as_posix(),
            python_bin,
            "prepare",
            legacy_id,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if prepare.returncode != 0 or not (prepare_root / "continued").is_file():
        raise AssertionError(
            "prepare-only historical current was incorrectly activation-gated: "
            f"exit={prepare.returncode} stderr={prepare.stderr!r}"
        )

    mutation_calls = sum(
        1
        for case_root in (schema5_root, legacy_root, prepare_root)
        if (case_root / "systemd-mutation.log").read_bytes()
    )
    if mutation_calls != 0:
        raise AssertionError("minimal activation audit invoked a systemd mutation stub")
    return {
        "historical_switch_rejections": historical_rejections,
        "protected_artifact_count": len(protected_payloads),
        "schema5_reaches_full_validation": True,
        "registered_legacy_reaches_full_validation": True,
        "prepare_only_historical_current_allowed": True,
        "systemd_mutation_calls": 0,
    }


def assert_privileged_shell_entry_contract(content: str, label: str) -> None:
    expected_prefix = [
        "#!/usr/bin/bash -p",
        "if [[ ! -o privileged ]]; then",
        "  builtin printf 'ERROR: privileged Bash mode is required; execute this script directly or with /usr/bin/bash -p\\n' >&2",
        "  builtin exit 1",
        "fi",
        "builtin set -Eeuo pipefail",
        "builtin umask 027",
        "PATH=/usr/sbin:/usr/bin",
        "builtin export PATH",
        "builtin readonly PATH",
    ]
    actual_prefix = content.splitlines()[: len(expected_prefix)]
    if actual_prefix != expected_prefix:
        raise AssertionError(
            json.dumps(
                {
                    "label": f"{label}-privileged-entry-prefix",
                    "expected": expected_prefix,
                    "actual": actual_prefix,
                },
                ensure_ascii=False,
            )
        )
    require_in_order(
        content,
        [
            "builtin readonly PATH",
            "builtin unset BASH_ENV ENV CDPATH",
        ],
        f"{label}-startup-environment-reset",
    )
    if "#!/usr/bin/env bash" in content:
        raise AssertionError(f"{label}: env-resolved Bash shebang remains")


def assert_privileged_shell_entry_behavior(temporary_root: Path) -> dict[str, object]:
    if not sys.platform.startswith("linux"):
        return {
            "status": "not_run",
            "reason": "requires Linux shebang and Bash startup semantics",
            "executed": False,
            "cases": 0,
        }

    trusted_bash = Path("/usr/bin/bash")
    if not trusted_bash.is_file():
        raise AssertionError("Linux privileged-entry behavior requires /usr/bin/bash")

    sentinel = temporary_root / "bash-env-injection-sentinel"
    startup_hook = temporary_root / "bash-env-startup-hook.sh"
    startup_hook.write_text(
        'builtin printf injected >"$CODEX_BASH_ENV_SENTINEL"\n',
        encoding="utf-8",
        newline="\n",
    )
    harness = temporary_root / "privileged-entry-harness.sh"
    harness.write_text(
        "#!/usr/bin/bash -p\n"
        "if [[ ! -o privileged ]]; then\n"
        "  builtin printf 'ERROR: privileged Bash mode is required; execute this script directly or with /usr/bin/bash -p\\n' >&2\n"
        "  builtin exit 1\n"
        "fi\n"
        "builtin set -Eeuo pipefail\n"
        "builtin umask 027\n"
        "PATH=/usr/sbin:/usr/bin\n"
        "builtin export PATH\n"
        "builtin readonly PATH\n"
        "builtin unset BASH_ENV ENV CDPATH\n"
        "builtin printf 'entry-ok\\n'\n",
        encoding="utf-8",
        newline="\n",
    )
    harness.chmod(0o755)

    direct_environment = {
        **os.environ,
        "BASH_ENV": str(startup_hook),
        "ENV": str(startup_hook),
        "CODEX_BASH_ENV_SENTINEL": str(sentinel),
        "BASH_FUNC_entry_probe%%": "() { builtin printf function-injected; }",
    }
    direct = subprocess.run(
        [str(harness)],
        cwd=temporary_root,
        env=direct_environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if direct.returncode != 0 or direct.stdout != "entry-ok\n" or sentinel.exists():
        raise AssertionError(
            "direct privileged shebang did not isolate Bash startup hooks: "
            f"exit={direct.returncode} stdout={direct.stdout!r} stderr={direct.stderr!r} "
            f"sentinel={sentinel.exists()}"
        )

    explicit = subprocess.run(
        [str(trusted_bash), "-p", str(harness)],
        cwd=temporary_root,
        env=direct_environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if explicit.returncode != 0 or explicit.stdout != "entry-ok\n" or sentinel.exists():
        raise AssertionError("explicit /usr/bin/bash -p entry did not preserve isolation")

    nonprivileged = subprocess.run(
        [str(trusted_bash), str(harness)],
        cwd=temporary_root,
        env={"PATH": "/usr/sbin:/usr/bin", "LANG": "C", "LC_ALL": "C"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if (
        nonprivileged.returncode == 0
        or "privileged Bash mode is required" not in nonprivileged.stderr
    ):
        raise AssertionError("non-privileged Bash invocation did not fail closed")

    return {
        "status": "passed",
        "executed": True,
        "cases": 3,
        "bash_env_ignored": True,
        "exported_function_ignored": True,
        "nonprivileged_invocation_rejected": True,
    }


def assert_strict_health_status_contract(content: str, label: str) -> None:
    status_parser = simple_function_definition(
        content, "validate_single_http_response_status"
    )
    require_fragments(
        status_parser,
        [
            '[[ "$expected_status" =~ ^[0-9]{3}$ ]]',
            'if ($0 ~ /^HTTP\\/[0-9]+([.][0-9]+)?[ \\t]+[0-9][0-9][0-9]([ \\t]|$)/)',
            '[[ "${#response_statuses[@]}" == "1" ]]',
            '[[ "${response_statuses[0]}" == "$expected_status" ]]',
        ],
        f"{label}-single-http-response-parser",
    )
    for function_name in ("manifest_bound_health", "availability_health"):
        function_source = simple_function_definition(content, function_name)
        require_in_order(
            function_source,
            [
                "--dump-header - --output /dev/null",
                "--write-out $'\\n__MCGS_HTTP_STATUS__%{http_code}'",
                'response="$(curl "${curl_args[@]}" "$url")"',
                '[[ "$status_line" =~ ^__MCGS_HTTP_STATUS__([0-9]{3})$ ]]',
                '[[ "$http_status" == "200" ]]',
                'validate_single_http_response_status "$http_status" "$header_dump"',
            ],
            f"{label}-{function_name}-exact-single-200",
        )
        if re.search(r"(?<!\\S)(?:-L|--location)(?!\\S)", function_source):
            raise AssertionError(f"{label}: {function_name} follows redirects")
    login_parser = simple_function_definition(content, "validate_login_redirect_headers")
    require_in_order(
        login_parser,
        [
            '[[ "$http_status" == "302" || "$http_status" == "303" ]]',
            'validate_single_http_response_status "$http_status" "$header_dump"',
        ],
        f"{label}-login-single-response-status",
    )


def assert_curl_isolation_contract(content: str, label: str) -> int:
    require_fragments(
        content,
        [
            "unset CURL_HOME ALL_PROXY HTTPS_PROXY HTTP_PROXY NO_PROXY",
            "all_proxy https_proxy http_proxy no_proxy",
        ],
        f"{label}-curl-environment-isolation",
    )
    for function_name in ("manifest_bound_health", "availability_health", "strict_login_redirect"):
        function_source = simple_function_definition(content, function_name)
        require_fragments(
            function_source,
            [
                "--disable --noproxy '*'",
                'curl "${curl_args[@]}" "$url"',
            ],
            f"{label}-{function_name}-curl-options",
        )

    commands = list(
        re.finditer(
            r'(?m)(?:^[ \t]*|\$\()curl[ \t]+(?P<arguments>[^\n]+)',
            content,
        )
    )
    if not commands:
        raise AssertionError(f"{label}: no curl commands were found")
    unsafe: list[str] = []
    for command in commands:
        arguments = command.group("arguments").strip()
        if arguments.startswith('"${curl_args[@]}"'):
            continue
        if arguments.startswith("--disable --noproxy '*'"):
            continue
        unsafe.append(arguments)
    if unsafe:
        raise AssertionError(f"{label}: curl calls can load curlrc or ambient proxies: {unsafe}")
    return len(commands)


def assert_release_tree_cwd_behavior(
    bash: str,
    contents: dict[str, str],
    temporary_root: Path,
) -> dict[str, object]:
    mock_find = temporary_root / "mock-find.sh"
    mock_find.write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        "[[ \"$PWD\" == / ]]\n"
        "[[ \"$#\" == 5 && \"$2\" == -xdev && \"$3\" == -writable "
        "&& \"$4\" == -print && \"$5\" == -quit ]]\n"
        "printf '%s\\n' \"$PWD\" >\"$TRACE_PATH\"\n",
        encoding="utf-8",
        newline="\n",
    )
    mock_find.chmod(0o755)

    root_like_cwd = temporary_root / "root"
    root_like_cwd.mkdir()
    filesystem_root_cwd = Path("/")
    actual_root_cwd = False
    if os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0:
        linux_root = Path("/root")
        if linux_root.is_dir():
            root_like_cwd = linux_root
            actual_root_cwd = True

    completed_cases = 0
    for label, content in contents.items():
        function_source = simple_function_definition(content, "assert_release_tree_security")
        require_fragments(
            function_source,
            [
                'cd / && exec "$1" "$2" -xdev -writable -print -quit',
                'sh "$FIND_BIN" "$release_root"',
            ],
            f"{label}-release-tree-find-cwd-and-argument-isolation",
        )
        harness = temporary_root / f"release-tree-cwd-{label}.sh"
        harness.write_text(
            "#!/usr/bin/env bash\nset -Eeuo pipefail\n"
            "fail() { printf 'ERROR: %s\\n' \"$*\" >&2; exit 97; }\n"
            "getfacl() { return 0; }\n"
            "runuser() {\n"
            "  [[ \"$1\" == -u && \"$2\" == synthetic-service && \"$3\" == -- ]] || return 96\n"
            "  shift 3\n"
            "  \"$@\"\n"
            "}\n"
            "SH_BIN=/bin/sh\n"
            "FIND_BIN=\"$1\"\n"
            "TRACE_PATH=\"$2\"\n"
            "export TRACE_PATH\n"
            "release_root=\"$3/release tree\"\n"
            "mkdir -p -- \"$release_root\"\n"
            + function_source
            + "\nassert_release_tree_security \"$release_root\" synthetic-service\n"
            "[[ \"$(cat -- \"$TRACE_PATH\")\" == / ]]\n",
            encoding="utf-8",
            newline="\n",
        )
        harness.chmod(0o755)
        for cwd_name, cwd in (("root", root_like_cwd), ("filesystem-root", filesystem_root_cwd)):
            trace = temporary_root / f"release-tree-cwd-{label}-{cwd_name}.trace"
            case_root = temporary_root / f"release-tree-cwd-{label}-{cwd_name}"
            completed = subprocess.run(
                [bash, str(harness), str(mock_find), str(trace), str(case_root)],
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if completed.returncode != 0:
                raise AssertionError(
                    f"{label} release-tree cwd case {cwd_name!r} failed: "
                    f"exit={completed.returncode} stdout={completed.stdout!r} "
                    f"stderr={completed.stderr!r}"
                )
            completed_cases += 1
    return {
        "script_count": len(contents),
        "caller_cwd_cases": completed_cases,
        "actual_linux_root_cwd_exercised": actual_root_cwd,
        "inner_find_cwd": "/",
    }


def assert_health_response_parser(
    bash: str,
    contents: dict[str, str],
    check_production: str,
    temporary_root: Path,
) -> dict[str, int]:
    parser_sources = {**contents, CHECK_PRODUCTION_SCRIPT.name: check_production}
    expected = "a" * 64
    wrong = "b" * 64
    exact_headers = (
        f"HTTP/1.1 200 OK\\r\\nX-MCGS-Release-Manifest-SHA256: {expected}\\r\\n\\r\\n"
    )
    cases = {
        "exact_200": ("200", exact_headers, False, True, True),
        "case_insensitive_name": (
            "200",
            f"HTTP/2 200\\r\\nx-mcgs-release-manifest-sha256: {expected}\\r\\n\\r\\n",
            False,
            True,
            True,
        ),
        "wrong_digest_public_instance": (
            "200",
            f"HTTP/1.1 200 OK\\r\\nX-MCGS-Release-Manifest-SHA256: {wrong}\\r\\n\\r\\n",
            False,
            False,
            True,
        ),
        "missing_manifest_header": (
            "200",
            "HTTP/1.1 200 OK\\r\\nContent-Type: application/json\\r\\n\\r\\n",
            False,
            False,
            True,
        ),
        "empty_manifest_header": (
            "200",
            "HTTP/1.1 200 OK\\r\\nX-MCGS-Release-Manifest-SHA256:\\r\\n\\r\\n",
            False,
            False,
            True,
        ),
        "duplicate_manifest_header": (
            "200",
            "HTTP/1.1 200 OK\\r\\n"
            f"X-MCGS-Release-Manifest-SHA256: {expected}\\r\\n"
            f"X-MCGS-Release-Manifest-SHA256: {expected}\\r\\n\\r\\n",
            False,
            False,
            True,
        ),
        "comma_multivalue_manifest_header": (
            "200",
            f"HTTP/1.1 200 OK\\r\\nX-MCGS-Release-Manifest-SHA256: {expected},{expected}\\r\\n\\r\\n",
            False,
            False,
            True,
        ),
        "uppercase_digest": (
            "200",
            f"HTTP/1.1 200 OK\\r\\nX-MCGS-Release-Manifest-SHA256: {expected.upper()}\\r\\n\\r\\n",
            False,
            False,
            True,
        ),
        "status_301_with_identity": (
            "301",
            exact_headers.replace("200 OK", "301 Moved Permanently"),
            False,
            False,
            False,
        ),
        "status_302_with_identity": (
            "302",
            exact_headers.replace("200 OK", "302 Found"),
            False,
            False,
            False,
        ),
        "status_204_with_identity": (
            "204",
            exact_headers.replace("200 OK", "204 No Content"),
            False,
            False,
            False,
        ),
        "redirect_chain_302_then_200": (
            "200",
            "HTTP/1.1 302 Found\\r\\nLocation: /other\\r\\n\\r\\n" + exact_headers,
            False,
            False,
            False,
        ),
        "duplicate_200_responses": (
            "200",
            "HTTP/1.1 200 OK\\r\\nContent-Length: 0\\r\\n\\r\\n" + exact_headers,
            False,
            False,
            False,
        ),
        "writeout_header_status_mismatch": ("302", exact_headers, False, False, False),
        "missing_http_status_line": (
            "200",
            f"X-MCGS-Release-Manifest-SHA256: {expected}\\r\\n\\r\\n",
            False,
            False,
            False,
        ),
        "curl_failure": ("200", exact_headers, True, False, False),
    }

    completed_cases = 0
    for script_label, content in parser_sources.items():
        harness = temporary_root / f"health-response-{script_label}.sh"
        harness.write_text(
            "#!/usr/bin/env bash\nset -Eeuo pipefail\n"
            r'''curl() {
  printf '%b' "${MOCK_HEADERS-}"
  printf '\n__MCGS_HTTP_STATUS__%s' "${MOCK_STATUS-000}"
  [[ "${MOCK_CURL_FAIL-false}" != "true" ]]
}
'''
            + simple_function_definition(content, "validate_single_http_response_status")
            + "\n"
            + simple_function_definition(content, "validate_health_manifest_header")
            + "\n"
            + simple_function_definition(content, "manifest_bound_health")
            + "\n"
            + simple_function_definition(content, "availability_health")
            + r'''
case "$1" in
  manifest) manifest_bound_health "$2" 'https://health.invalid/api/health' 15 ;;
  availability) availability_health 'https://health.invalid/api/health' 15 ;;
  *) exit 64 ;;
esac
''',
            encoding="utf-8",
            newline="\n",
        )
        harness.chmod(0o755)
        for case_name, (
            status,
            headers,
            curl_failure,
            manifest_should_pass,
            availability_should_pass,
        ) in cases.items():
            environment = {
                **os.environ,
                "MOCK_STATUS": status,
                "MOCK_HEADERS": headers,
                "MOCK_CURL_FAIL": "true" if curl_failure else "false",
            }
            for mode, should_pass in (
                ("manifest", manifest_should_pass),
                ("availability", availability_should_pass),
            ):
                result = subprocess.run(
                    [bash, str(harness), mode, expected],
                    cwd=temporary_root,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                if (result.returncode == 0) != should_pass:
                    raise AssertionError(
                        f"{script_label} {mode} health case {case_name!r} failed: "
                        f"exit={result.returncode} stdout={result.stdout!r} "
                        f"stderr={result.stderr!r}"
                    )
                completed_cases += 1
    return {
        "script_count": len(parser_sources),
        "cases_per_script": len(cases),
        "modes_per_case": 2,
        "completed_cases": completed_cases,
    }


def assert_login_redirect_parser(
    bash: str,
    contents: dict[str, str],
    check_production: str,
    temporary_root: Path,
) -> dict[str, object]:
    parser_sources = {**contents, CHECK_PRODUCTION_SCRIPT.name: check_production}
    cases = {
        "exact_302": ("302", "HTTP/1.1 302 Found\r\nLocation: /login\r\n\r\n", True, False),
        "exact_303": ("303", "HTTP/2 303\r\nlocation: /login\r\n\r\n", True, False),
        "ows_after_colon": ("302", "HTTP/1.1 302 Found\r\nLocation:\t/login\r\n\r\n", True, False),
        "status_301": ("301", "HTTP/1.1 301 Moved\r\nLocation: /login\r\n\r\n", False, False),
        "status_307": ("307", "HTTP/1.1 307 Redirect\r\nLocation: /login\r\n\r\n", False, False),
        "status_200": ("200", "HTTP/1.1 200 OK\r\nLocation: /login\r\n\r\n", False, False),
        "missing": ("302", "HTTP/1.1 302 Found\r\nX-Location: /login\r\n\r\n", False, False),
        "empty": ("302", "HTTP/1.1 302 Found\r\nLocation:\r\n\r\n", False, False),
        "duplicate": (
            "302",
            "HTTP/1.1 302 Found\r\nLocation: /login\r\nLocation: /login\r\n\r\n",
            False,
            False,
        ),
        "comma_multi_value": (
            "302",
            "HTTP/1.1 302 Found\r\nLocation: /login, https://evil.invalid/login\r\n\r\n",
            False,
            False,
        ),
        "external_origin": (
            "302",
            "HTTP/1.1 302 Found\r\nLocation: https://evil.invalid/login\r\n\r\n",
            False,
            False,
        ),
        "same_origin_absolute": (
            "302",
            "HTTP/1.1 302 Found\r\nLocation: https://protocol.feian.online/login\r\n\r\n",
            False,
            False,
        ),
        "subpath": ("302", "HTTP/1.1 302 Found\r\nLocation: /foo/login\r\n\r\n", False, False),
        "query": ("302", "HTTP/1.1 302 Found\r\nLocation: /login?next=/\r\n\r\n", False, False),
        "fragment": ("302", "HTTP/1.1 302 Found\r\nLocation: /login#x\r\n\r\n", False, False),
        "path_case": ("302", "HTTP/1.1 302 Found\r\nLocation: /LOGIN\r\n\r\n", False, False),
        "field_name_whitespace": (
            "302",
            "HTTP/1.1 302 Found\r\nLocation : /login\r\n\r\n",
            False,
            False,
        ),
        "multiple_responses": (
            "302",
            "HTTP/1.1 301 Moved Permanently\r\nLocation: /old\r\n\r\n"
            "HTTP/1.1 302 Found\r\nLocation: /login\r\n\r\n",
            False,
            False,
        ),
        "writeout_header_status_mismatch": (
            "303",
            "HTTP/1.1 302 Found\r\nLocation: /login\r\n\r\n",
            False,
            False,
        ),
        "missing_http_status_line": ("302", "Location: /login\r\n\r\n", False, False),
        "curl_failure": ("302", "HTTP/1.1 302 Found\r\nLocation: /login\r\n\r\n", False, True),
    }
    completed_cases = 0
    for script_label, content in parser_sources.items():
        harness = temporary_root / f"login-redirect-{script_label}.sh"
        harness.write_text(
            "#!/usr/bin/env bash\nset -Eeuo pipefail\n"
            r'''curl() {
  [[ "${1-}" == "--disable" ]] || return 90
  local previous=""
  local noproxy_all="false"
  local dump_headers="false"
  local write_status="false"
  local argument
  for argument in "$@"; do
    if [[ "$previous" == "--noproxy" && "$argument" == "*" ]]; then
      noproxy_all="true"
    fi
    [[ "$argument" == "--dump-header" ]] && dump_headers="true"
    [[ "$argument" == *"__MCGS_HTTP_STATUS__%{http_code}"* ]] && write_status="true"
    previous="$argument"
  done
  [[ "$noproxy_all" == "true" && "$dump_headers" == "true" && "$write_status" == "true" ]] || return 91
  [[ "${MOCK_CURL_FAIL-false}" != "true" ]] || return 22
  printf '%s' "$MOCK_HEADERS"
  printf '\n__MCGS_HTTP_STATUS__%s' "$MOCK_STATUS"
}
'''
            + simple_function_definition(content, "validate_single_http_response_status")
            + "\n"
            + simple_function_definition(content, "validate_login_redirect_headers")
            + "\n"
            + simple_function_definition(content, "strict_login_redirect")
            + "\nstrict_login_redirect 'https://protocol.feian.online/' 15\n",
            encoding="utf-8",
            newline="\n",
        )
        harness.chmod(0o755)
        for case_name, (status, headers, expected_pass, curl_failure) in cases.items():
            environment = {
                **os.environ,
                "MOCK_STATUS": status,
                "MOCK_HEADERS": headers,
                "MOCK_CURL_FAIL": "true" if curl_failure else "false",
            }
            completed = subprocess.run(
                [bash, os.fspath(harness)],
                cwd=temporary_root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if (completed.returncode == 0) != expected_pass:
                raise AssertionError(
                    f"{script_label} strict login redirect case {case_name!r} failed: "
                    f"exit={completed.returncode} stdout={completed.stdout!r} stderr={completed.stderr!r}"
                )
            completed_cases += 1
    return {
        "script_count": len(parser_sources),
        "cases_per_script": len(cases),
        "completed_cases": completed_cases,
    }


def assert_check_production_identity(
    bash: str,
    content: str,
    temporary_root: Path,
) -> dict[str, bool]:
    require_fragments(
        content,
        [
            'APP_ROOT="${PROTOCOL_STUDIO_DEPLOY_ROOT-/srv/apps/protocol-studio}"',
            "PROTOCOL_STUDIO_DEPLOY_ROOT must be a canonical absolute path",
            '[[ -d "$APP_ROOT" && ! -L "$APP_ROOT" ]]',
            'resolved_app_root="$(/usr/bin/realpath -e -- "$APP_ROOT")"',
            '"$APP_ROOT/runtime-guard/runtime_fingerprint.py"',
            '--verify-current "$APP_ROOT/current"',
            '--releases-root "$APP_ROOT/releases"',
            '--baseline-directory "$APP_ROOT/runtime-guard/baselines"',
        ],
        "check-production-parameterized-installed-runtime-root",
    )
    harness = temporary_root / "check-production-identity-harness.sh"
    mocked_content, replacement_count = re.subn(
        r"(?ms)^verify_installed_runtime\(\) \{\n.*?^\}",
        'verify_installed_runtime() { [[ "${MOCK_RUNTIME_OK-false}" == "true" ]]; }',
        content,
        count=1,
    )
    if replacement_count != 1:
        raise AssertionError("check-production installed runtime verifier is missing")
    mock_curl = r'''curl() {
  [[ "${1-}" == "--disable" ]] || return 90
  local dump_headers="false"
  local noproxy_all="false"
  local previous=""
  local url=""
  local write_status="false"
  local argument
  for argument in "$@"; do
    if [[ "$previous" == "--noproxy" && "$argument" == "*" ]]; then
      noproxy_all="true"
    fi
    [[ "$argument" == "--dump-header" ]] && dump_headers="true"
    [[ "$argument" == *"__MCGS_HTTP_STATUS__%{http_code}"* ]] && write_status="true"
    [[ "$argument" == http://* || "$argument" == https://* ]] && url="$argument"
    previous="$argument"
  done
  [[ "$noproxy_all" == "true" ]] || return 91
  if [[ "$url" == */api/health ]]; then
    if [[ "$dump_headers" == "true" && "$write_status" == "true" ]]; then
      local digest="$MOCK_PUBLIC_DIGEST"
      [[ "$url" == http://127.0.0.1:* ]] && digest="$MOCK_LOCAL_DIGEST"
      printf 'HTTP/1.1 200 OK\r\nX-MCGS-Release-Manifest-SHA256: %s\r\n\r\n' "$digest"
      printf '\n__MCGS_HTTP_STATUS__200'
    else
      return 92
    fi
    return 0
  fi
  printf 'HTTP/1.1 303 See Other\r\nLocation: /login\r\n\r\n'
  printf '\n__MCGS_HTTP_STATUS__303'
}
'''
    harness.write_text(
        "#!/usr/bin/env bash\n" + mock_curl + mocked_content,
        encoding="utf-8",
        newline="\n",
    )
    harness.chmod(0o755)
    expected = "a" * 64
    wrong = "b" * 64

    def run_case(
        expected_value: str | None,
        public_digest: str,
        allow_availability_only: str | None = None,
        public_origin: str | None = None,
        local_origin: str | None = None,
        runtime_ok: bool = True,
        deploy_root: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            **os.environ,
            "MOCK_LOCAL_DIGEST": expected,
            "MOCK_PUBLIC_DIGEST": public_digest,
            "MOCK_RUNTIME_OK": "true" if runtime_ok else "false",
        }
        environment.pop("PROTOCOL_STUDIO_PUBLIC_ORIGIN", None)
        environment.pop("PROTOCOL_STUDIO_LOCAL_ORIGIN", None)
        environment.pop("PROTOCOL_STUDIO_ALLOW_AVAILABILITY_ONLY", None)
        environment.pop("PROTOCOL_STUDIO_DEPLOY_ROOT", None)
        if expected_value is None:
            environment.pop("PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256", None)
        else:
            environment["PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256"] = expected_value
        if allow_availability_only is not None:
            environment["PROTOCOL_STUDIO_ALLOW_AVAILABILITY_ONLY"] = allow_availability_only
        if public_origin is not None:
            environment["PROTOCOL_STUDIO_PUBLIC_ORIGIN"] = public_origin
        if local_origin is not None:
            environment["PROTOCOL_STUDIO_LOCAL_ORIGIN"] = local_origin
        if deploy_root is not None:
            environment["PROTOCOL_STUDIO_DEPLOY_ROOT"] = deploy_root
        return subprocess.run(
            [bash, "-p", str(harness)],
            cwd=temporary_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    exact = run_case(expected, expected)
    if (
        exact.returncode != 0
        or "installed_runtime_identity=passed" not in exact.stdout
        or "release_identity=passed" not in exact.stdout
    ):
        raise AssertionError(f"exact check-production identity failed: {exact}")
    helper_only_drift = run_case(expected, expected, runtime_ok=False)
    if (
        helper_only_drift.returncode == 0
        or "local_health=passed" not in helper_only_drift.stdout
        or "public_health=passed" not in helper_only_drift.stdout
        or "installed_runtime_identity=failed" not in helper_only_drift.stdout
        or "release_identity=failed" not in helper_only_drift.stdout
    ):
        raise AssertionError(
            "helper-only drift did not propagate through the installed-runtime gate: "
            f"{helper_only_drift}"
        )
    wrong_public = run_case(expected, wrong)
    if (
        wrong_public.returncode == 0
        or "local_health=passed" not in wrong_public.stdout
        or "public_health=failed" not in wrong_public.stdout
        or "release_identity=failed" not in wrong_public.stdout
    ):
        raise AssertionError(f"wrong public instance was accepted: {wrong_public}")
    missing_digest = run_case(None, wrong)
    if (
        missing_digest.returncode == 0
        or "required unless explicit availability-only mode is enabled" not in missing_digest.stderr
    ):
        raise AssertionError(f"missing expected digest was not rejected by default: {missing_digest}")
    availability_only = run_case(None, wrong, "true")
    if (
        availability_only.returncode != 0
        or "installed_runtime_identity=not_requested" not in availability_only.stdout
        or "release_identity=not_requested" not in availability_only.stdout
    ):
        raise AssertionError(f"explicit availability-only mode failed: {availability_only}")
    conflicting_mode = run_case(expected, expected, "true")
    if (
        conflicting_mode.returncode == 0
        or "must not be enabled when an expected Manifest digest is configured"
        not in conflicting_mode.stderr
    ):
        raise AssertionError(f"digest plus availability-only conflict was accepted: {conflicting_mode}")
    uppercase = run_case(expected.upper(), expected)
    if uppercase.returncode == 0:
        raise AssertionError("uppercase expected manifest digest was accepted")
    invalid_endpoint_cases = {
        "local-replaced-by-public": (
            "https://protocol.feian.online",
            "https://protocol.feian.online",
        ),
        "same-endpoint": ("https://example.test", "https://example.test"),
        "local-non-loopback": (None, "http://0.0.0.0:18771"),
        "local-port-zero": (None, "http://127.0.0.1:0"),
        "local-port-65536": (None, "http://127.0.0.1:65536"),
        "local-missing-port": (None, "http://127.0.0.1"),
        "local-path": (None, "http://127.0.0.1:18771/path"),
        "local-query": (None, "http://127.0.0.1:18771?query=1"),
        "local-fragment": (None, "http://127.0.0.1:18771#fragment"),
        "public-ip": ("https://127.0.0.1", None),
        "public-port": ("https://protocol.feian.online:443", None),
        "public-path": ("https://protocol.feian.online/path", None),
        "public-query": ("https://protocol.feian.online?query=1", None),
        "public-fragment": ("https://protocol.feian.online#fragment", None),
        "public-credentials": ("https://user@protocol.feian.online", None),
        "public-uppercase": ("https://Protocol.feian.online", None),
        "public-trailing-slash": ("https://protocol.feian.online/", None),
    }
    for label, (public_origin, local_origin) in invalid_endpoint_cases.items():
        invalid_endpoint = run_case(
            expected,
            expected,
            public_origin=public_origin,
            local_origin=local_origin,
        )
        if invalid_endpoint.returncode == 0:
            raise AssertionError(f"invalid production endpoint was accepted: {label}")
    staging_root = run_case(
        expected,
        expected,
        deploy_root="/srv/apps/protocol-studio-staging",
    )
    if staging_root.returncode != 0:
        raise AssertionError(f"canonical staging deploy root was rejected: {staging_root}")
    invalid_root_cases = (
        "relative/root",
        "/srv/apps/protocol-studio-staging/",
        "/srv/apps/../protocol-studio-staging",
        "/srv/apps//protocol-studio-staging",
        "/srv/apps/.hidden",
    )
    for deploy_root in invalid_root_cases:
        invalid_root = run_case(expected, expected, deploy_root=deploy_root)
        if invalid_root.returncode == 0:
            raise AssertionError(f"invalid deploy root was accepted: {deploy_root}")
    return {
        "exact_local_and_public": True,
        "installed_runtime_drift_rejected": True,
        "helper_only_drift_propagates_nonzero": True,
        "wrong_public_instance_rejected": True,
        "missing_digest_rejected_by_default": True,
        "explicit_availability_only_mode": True,
        "digest_and_availability_only_conflict_rejected": True,
        "uppercase_expected_digest_rejected": True,
        "invalid_endpoint_cases_rejected": len(invalid_endpoint_cases),
        "canonical_staging_root_accepted": True,
        "invalid_deploy_root_cases_rejected": len(invalid_root_cases),
    }


def assert_candidate_cleanup_behavior(
    bash: str,
    content: str,
    temporary_root: Path,
) -> dict[str, bool]:
    harness = temporary_root / "candidate-cleanup-harness.sh"
    harness.write_text(
        "#!/usr/bin/env bash\nset -Eeuo pipefail\n"
        "fsync_directory() { :; }\n"
        + simple_function_definition(content, "cleanup_candidate")
        + r'''
mode="$1"
root="$2"
APP_ROOT="$root"
RELEASES_DIR="$root/releases"
CONTROL_DIR="$root/control"
DEPLOYMENT_DIR="$root/deployments"
RELEASE_ID="synthetic-release"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"
CURRENT_LINK="$root/current"
INCOMING_DIR="$RELEASES_DIR/.incoming-synthetic"
RUNTIME_BASELINE_DIR="$root/runtime-baselines"
RUNTIME_BASELINE_TEMP="$RUNTIME_BASELINE_DIR/.pending-$RELEASE_ID.json"
TRANSACTION_TEMP="$root/.deploy-transaction-$RELEASE_ID.tmp"
CANDIDATE_CLEANUP_ACTIVE="true"
mkdir -p -- "$RELEASES_DIR" "$CONTROL_DIR" "$DEPLOYMENT_DIR" "$RUNTIME_BASELINE_DIR"
stat() {
  local target="${!#}"
  case "$target" in
    "$RUNTIME_BASELINE_TEMP") printf '0:0:444\n' ;;
    "$TRANSACTION_TEMP") printf '0:0:600\n' ;;
    *) command stat "$@" ;;
  esac
}

case "$mode" in
  promoted)
    RELEASE_PROMOTED="true"
    mkdir -p -- "$RELEASE_DIR" "$INCOMING_DIR"
    printf 'durable evidence\n' >"$RELEASE_DIR/sentinel"
    printf 'unexpected incoming state\n' >"$INCOMING_DIR/sentinel"
    cleanup_candidate
    [[ -f "$RELEASE_DIR/sentinel" ]]
    [[ -f "$INCOMING_DIR/sentinel" ]]
    [[ ! -e "$CONTROL_DIR/failed-preparations" && ! -L "$CONTROL_DIR/failed-preparations" ]]
    ;;
  incoming)
    RELEASE_PROMOTED="false"
    mkdir -p -- "$INCOMING_DIR/payload"
    printf 'ephemeral candidate\n' >"$INCOMING_DIR/payload/sentinel"
    printf '{}\n' >"$RUNTIME_BASELINE_TEMP"
    chmod 0444 "$RUNTIME_BASELINE_TEMP"
    printf '{}\n' >"$TRANSACTION_TEMP"
    chmod 0600 "$TRANSACTION_TEMP"
    cleanup_candidate
    [[ ! -e "$INCOMING_DIR" && ! -L "$INCOMING_DIR" ]]
    [[ ! -e "$RUNTIME_BASELINE_TEMP" && ! -L "$RUNTIME_BASELINE_TEMP" ]]
    [[ ! -e "$TRANSACTION_TEMP" && ! -L "$TRANSACTION_TEMP" ]]
    ;;
  *)
    exit 64
    ;;
esac
''',
        encoding="utf-8",
        newline="\n",
    )
    harness.chmod(0o755)

    results: dict[str, bool] = {}
    for mode in ("promoted", "incoming"):
        case_root = temporary_root / f"candidate-cleanup-{mode}"
        completed = subprocess.run(
            [bash, str(harness), mode, os.fspath(case_root)],
            cwd=temporary_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"candidate cleanup case {mode!r} failed: exit={completed.returncode} "
                f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
            )
        results[mode] = True
    return results


def assert_trusted_path_acl_contract(content: str, label: str) -> None:
    acl_predicate_body = function_body(content, "acl_is_minimal")
    require_fragments(
        acl_predicate_body,
        [
            '"$TRUST_GETFACL_BIN" -c -p -- "$path" 2>/dev/null',
            '"$TRUST_GREP_BIN" -Eq',
            "'^(default:|user:[^:]|group:[^:]|mask::)'",
            'acl_status=("${PIPESTATUS[@]}")',
            '[[ "${acl_status[0]}" == "0" && "${acl_status[1]}" == "1" ]]',
            "return 1",
            "return 2",
        ],
        f"{label}-acl-parser-fail-closed",
    )
    acl_assertion_body = function_body(content, "assert_no_extended_acl")
    require_fragments(
        acl_assertion_body,
        [
            'if acl_is_minimal "$path"; then',
            '[[ "$acl_status" == "1" ]]',
            "contains an extended or default ACL",
            "cannot verify $label ACLs",
        ],
        f"{label}-acl-assertion-status-dispatch",
    )

    directory_body = function_body(content, "assert_trusted_root_directory_path")
    require_in_order(
        directory_body,
        [
            'current="$directory"',
            'assert_no_extended_acl "$current" "$label path component"',
            '[[ "$current" == "/" ]] && break',
            'current="$("$TRUST_DIRNAME_BIN" -- "$current")"',
        ],
        f"{label}-trusted-directory-acl-parent-chain",
    )

    file_body = function_body(content, "assert_trusted_root_file_path")
    require_fragments(
        file_body,
        ['assert_no_extended_acl "$file" "$label"'],
        f"{label}-trusted-file-acl",
    )
    if (
        '"$("$TRUST_DIRNAME_BIN" -- "$file")" "$label parent directory"' not in file_body
        and 'assert_no_extended_acl "$current" "$label parent path component"' not in file_body
    ):
        raise AssertionError(f"{label}: trusted file parent ACL chain is missing")

    code_body = function_body(content, "assert_trusted_code_file")
    require_in_order(
        code_body,
        [
            'assert_no_extended_acl "$file" "$label"',
            '"$("$TRUST_DIRNAME_BIN" -- "$file")" "$label parent directory"',
        ],
        f"{label}-trusted-code-file-and-parent-acl",
    )
    record_body = function_body(content, "assert_trusted_record_file")
    require_fragments(
        record_body,
        [
            '== "0:0:640"',
            'assert_no_extended_acl "$file" "$label"',
            '"$("$TRUST_DIRNAME_BIN" -- "$file")" "$label parent directory"',
        ],
        f"{label}-trusted-record-file-and-parent-acl",
    )
    systemd_directory_body = function_body(content, "assert_secure_systemd_directory")
    require_fragments(
        systemd_directory_body,
        ['assert_trusted_root_directory_path "$directory" "$label path"'],
        f"{label}-systemd-directory-acl-parent-chain",
    )
    systemd_file_body = function_body(content, "assert_secure_systemd_file")
    require_in_order(
        systemd_file_body,
        [
            '"$TRUST_REALPATH_BIN" -e -- "$file" 2>/dev/null',
            'assert_no_extended_acl "$file" "$label"',
            '"$("$TRUST_DIRNAME_BIN" -- "$file")" "$label parent directory"',
        ],
        f"{label}-systemd-file-acl-parent-chain",
    )
    required_calls = [
        'assert_trusted_code_file "$trusted_bootstrap"',
        'assert_trusted_code_file "$trusted_helper"',
        'assert_trusted_root_directory_path "$APP_ROOT"',
        'assert_trusted_root_directory_path "$CONTROL_DIR"',
        'assert_trusted_root_file_path "$ENV_FILE"',
    ]
    if label == DEPLOY_SCRIPT.name:
        required_calls.append('assert_trusted_root_directory_path "$WHEELHOUSE"')
    require_fragments(content, required_calls, f"{label}-trusted-path-call-sites")


def assert_trusted_command_contract(content: str, label: str) -> None:
    require_fragments(
        content,
        [
            "#!/usr/bin/bash -p",
            "if [[ ! -o privileged ]]; then",
            "PATH=/usr/sbin:/usr/bin",
            "builtin export PATH",
            "builtin readonly PATH",
            "builtin readonly TRUST_REALPATH_BIN=/usr/bin/realpath",
            "builtin readonly TRUST_STAT_BIN=/usr/bin/stat",
            "builtin readonly TRUST_DIRNAME_BIN=/usr/bin/dirname",
            "builtin readonly TRUST_GETFACL_BIN=/usr/bin/getfacl",
            "builtin readonly TRUST_GREP_BIN=/usr/bin/grep",
            '[[ "$EUID" == "0" ]]',
            'SCRIPT_SOURCE="${BASH_SOURCE[0]}"',
            'SCRIPT_PARENT="${SCRIPT_SOURCE%/*}"',
            'SCRIPT_DIR="$(builtin cd -- "$SCRIPT_PARENT" && builtin pwd -P)"',
            "resolve_and_pin_trusted_command python3 PYTHON_BIN",
            "resolve_and_pin_trusted_command find FIND_BIN",
            "resolve_and_pin_trusted_command sh SH_BIN",
            "resolve_and_pin_trusted_command test TEST_BIN",
            "builtin readonly PYTHON_BIN FIND_BIN SH_BIN TEST_BIN",
            'runuser -u "$service_user" --',
            '"$SH_BIN" -c',
        ],
        f"{label}-trusted-command-bootstrap-and-use",
    )
    service_test_fragment = (
        'runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN"'
        if label == RECOVERY_SCRIPT.name
        else 'runuser -u "$SERVICE_USER" -- "$TEST_BIN"'
    )
    require_fragments(
        content,
        [service_test_fragment],
        f"{label}-trusted-external-test-command",
    )
    resolver_body = function_body(content, "resolve_and_pin_trusted_command")
    require_in_order(
        resolver_body,
        [
            'builtin unset -f "$name"',
            'candidate="$(builtin type -P -- "$name")"',
            'resolved="$("$TRUST_REALPATH_BIN" -e -- "$candidate" 2>/dev/null)"',
            "/usr/bin/*|/usr/sbin/*)",
            'assert_trusted_code_file "$resolved" "system command $name"',
            'builtin hash -p "$resolved" "$name"',
        ],
        f"{label}-trusted-command-resolver",
    )
    forbidden = [
        "/usr/local/",
        "command -v",
        '$(id -u)',
        "#!/usr/bin/env bash",
        "-- test ",
        "-- /bin/sh -c",
    ]
    present = [fragment for fragment in forbidden if fragment in content]
    if present:
        raise AssertionError(f"{label}: untrusted command-resolution fragments remain: {present}")

    expected_commands = {
        DEPLOY_SCRIPT.name: {
            "awk", "basename", "cat", "chmod", "chown", "cmp", "cp", "curl",
            "date", "dirname", "flock", "getfacl", "grep", "id", "install",
            "journalctl", "ln", "mv", "readlink", "realpath", "rm", "rmdir",
            "runuser", "sed", "seq", "sha256sum", "sleep", "stat", "sync",
            "systemctl", "systemd-run",
        },
        ROLLBACK_SCRIPT.name: {
            "awk", "basename", "cat", "chmod", "chown", "cmp", "cp", "curl",
            "date", "dirname", "flock", "getfacl", "grep", "id", "install",
            "journalctl", "ln", "mv", "readlink", "realpath", "rm", "runuser",
            "sed", "seq", "sha256sum", "sleep", "stat", "sync", "systemctl",
            "systemd-run",
        },
        RECOVERY_SCRIPT.name: {
            "awk", "basename", "cat", "chmod", "chown", "cmp", "cp", "curl", "dirname",
            "flock", "getfacl", "grep", "id", "install", "journalctl", "ln", "mv",
            "readlink", "realpath", "rm", "runuser", "sed", "seq", "sha256sum",
            "sleep", "stat", "sync", "systemctl", "systemd-run",
        },
    }[label]
    match = re.search(
        r"(?ms)^for trusted_command in \\\n(?P<body>.*?)\; do$",
        content,
    )
    if not match:
        raise AssertionError(f"{label}: trusted command loop is missing")
    actual_commands = set(re.findall(r"[A-Za-z][A-Za-z0-9-]*", match.group("body")))
    if actual_commands != expected_commands:
        raise AssertionError(
            f"{label}: trusted command set mismatch: "
            f"missing={sorted(expected_commands - actual_commands)} "
            f"extra={sorted(actual_commands - expected_commands)}"
        )


def assert_control_state_acl_contract(content: str, label: str) -> None:
    transition_body = function_body(content, "transition_transaction_status")
    require_in_order(
        transition_body,
        [
            'assert_trusted_root_file_path "$TRANSACTION_FILE" "active transaction marker"',
            '"$PYTHON_BIN" -I - "$TRANSACTION_FILE" "$temporary"',
            'assert_trusted_root_file_path "$TRANSACTION_FILE" "transitioned transaction marker"',
        ],
        f"{label}-transaction-marker-acl-before-and-after-transition",
    )
    backup_body = function_body(content, "verify_database_backup_evidence")
    require_in_order(
        backup_body,
        [
            'assert_trusted_root_directory_path "$BACKUP_DIR"',
            'assert_no_extended_acl "$backup_path" "database backup evidence"',
            'inspect --source "$backup_path"',
        ],
        f"{label}-database-backup-acl-before-inspect",
    )
    publish_body = function_body(content, "publish_committed_record")
    require_in_order(
        publish_body,
        [
            'assert_trusted_record_file "$temporary"',
            'ln -T -- "$temporary" "$final"',
            'assert_trusted_record_file "$final"',
        ],
        f"{label}-pending-and-final-record-acl",
    )
    require_fragments(
        content,
        [
            'assert_trusted_root_file_path "$LOCK_FILE" "deployment lock"',
            'assert_no_extended_acl "$LEGACY_LOCK_FILE" "legacy deployment lock"',
            '&& acl_is_minimal "$TRANSACTION_FILE"; then',
        ],
        f"{label}-lock-and-failure-marker-acl",
    )

    if label == DEPLOY_SCRIPT.name:
        wheel_loop = re.search(
            r'(?ms)^for wheel_entry in "\$\{WHEELHOUSE_ENTRIES\[@\]\}"; do\n(?P<body>.*?)^done$',
            content,
        )
        if not wheel_loop:
            raise AssertionError("deploy wheel loop is missing")
        require_fragments(
            wheel_loop.group("body"),
            ['assert_no_extended_acl "$wheel_entry" "offline wheel file"'],
            "deploy-wheel-file-acl",
        )
        require_fragments(
            content,
            [
                'assert_trusted_root_file_path "$TRUSTED_ARCHIVE"',
                'assert_trusted_root_file_path "$UNIT_BACKUP"',
                'assert_trusted_root_file_path "$DROPIN_BACKUP"',
                'assert_trusted_record_file "$PREVIOUS_DEPLOYMENT_RECORD"',
                'assert_trusted_root_file_path "$LEGACY_BASELINE_RECORD"',
                'assert_trusted_root_file_path "$TRANSACTION_FILE" "active deployment transaction marker"',
                'assert_trusted_record_file "$DEPLOYMENT_RECORD_TEMP"',
                'assert_trusted_root_file_path "$COMMITTED_TRANSACTION_RECORD"',
            ],
            "deploy-control-state-acl-call-sites",
        )
    elif label == ROLLBACK_SCRIPT.name:
        require_fragments(
            content,
            [
                'assert_trusted_record_file "$record" "release $release_id passed deployment record"',
                'assert_trusted_root_file_path "$record" "registered legacy baseline record"',
                'assert_trusted_root_file_path "$UNIT_BACKUP"',
                'assert_trusted_root_file_path "$DROPIN_BACKUP"',
                'assert_trusted_root_file_path "$TRANSACTION_FILE" "active rollback transaction marker"',
                'assert_trusted_record_file "$ROLLBACK_RECORD_TEMP"',
                'assert_trusted_root_file_path "$COMMITTED_TRANSACTION_RECORD"',
            ],
            "rollback-control-state-acl-call-sites",
        )
    else:
        reconcile_body = function_body(content, "reconcile_or_publish_committed_record")
        require_fragments(
            reconcile_body,
            [
                'assert_trusted_record_file "$pending"',
                'assert_trusted_record_file "$final"',
                'publish_committed_record "$pending" "$final"',
            ],
            "recovery-record-reconciliation-acl",
        )
        require_fragments(
            content,
            [
                'assert_trusted_root_file_path "$TRANSACTION_FILE" "active interrupted-transaction marker"',
                'assert_trusted_root_file_path "$TRANSACTION_FILE"',
                'assert_trusted_root_file_path "$FRAGMENT_BACKUP"',
                'assert_trusted_root_file_path "$DROPIN_BACKUP"',
                'assert_trusted_record_file "$record" "recorded previous release passed record"',
                'assert_trusted_root_file_path "$record" "registered legacy baseline record"',
                'assert_trusted_record_file "$PENDING_RECOVERY_RECORD"',
                'assert_trusted_record_file "$record_path" "rollback evidence record"',
                'assert_trusted_root_file_path "$ARCHIVED_TRANSACTION_RECORD"',
            ],
            "recovery-control-state-acl-call-sites",
        )


def assert_trusted_path_acl_behavior(
    bash: str,
    contents: dict[str, str],
    temporary_root: Path,
) -> dict[str, object]:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        return {
            "status": "not_run",
            "reason": "requires Linux POSIX ACL semantics",
            "helper_cases": 0,
            "root_trusted_path_cases": 0,
            "fake_path_command_rejections": 0,
        }

    getfacl = shutil.which("getfacl")
    setfacl = shutil.which("setfacl")
    if not getfacl or not setfacl:
        return {
            "status": "not_run",
            "reason": "requires getfacl and setfacl for deterministic ACL injection",
            "helper_cases": 0,
            "root_trusted_path_cases": 0,
            "fake_path_command_rejections": 0,
        }

    behavior_root = temporary_root / "trusted-path-acl-behavior"
    behavior_root.mkdir(mode=0o700)
    minimal_directory = behavior_root / "minimal-directory"
    control_directory = behavior_root / "control-directory"
    wheelhouse_directory = behavior_root / "wheelhouse-directory"
    for directory in (minimal_directory, control_directory, wheelhouse_directory):
        directory.mkdir(mode=0o750)
    minimal_file = behavior_root / "minimal-file"
    environment_file = behavior_root / "service.env"
    mask_file = behavior_root / "mask-only-file"
    wheel_file = behavior_root / "synthetic.whl"
    for file in (minimal_file, environment_file, mask_file, wheel_file):
        file.write_text("fixture\n", encoding="utf-8", newline="\n")
        file.chmod(0o600)

    def mutate_acl(arguments: list[str], path: Path) -> None:
        completed = subprocess.run(
            [setfacl, *arguments, os.fspath(path)],
            cwd=behavior_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"setfacl injection failed: arguments={arguments!r} "
                f"exit={completed.returncode} stderr={completed.stderr!r}"
            )

    for path in (minimal_directory, control_directory, wheelhouse_directory):
        mutate_acl(["-b"], path)
        mutate_acl(["-k"], path)
    for path in (minimal_file, environment_file, mask_file):
        mutate_acl(["-b"], path)

    mutate_acl(["-m", "u:12345:r-x"], control_directory)
    mutate_acl(["-m", "g:12345:---"], environment_file)
    mutate_acl(["-m", "d:u:12345:r-x"], wheelhouse_directory)
    mutate_acl(["-m", "m::---"], mask_file)
    mutate_acl(["-m", "u:12345:r--"], wheel_file)

    cases = (
        ("minimal-directory", minimal_directory, True),
        ("minimal-file", minimal_file, True),
        ("control-directory-named-user", control_directory, False),
        ("environment-file-named-group", environment_file, False),
        ("wheelhouse-default-acl", wheelhouse_directory, False),
        ("mask-entry", mask_file, False),
        ("wheel-file-named-user", wheel_file, False),
    )

    def run_case(
        harness: Path,
        arguments: list[str],
        expected_pass: bool,
        sensitive_path: Path,
        case_label: str,
    ) -> None:
        completed = subprocess.run(
            [bash, os.fspath(harness), *arguments],
            cwd=behavior_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        passed = completed.returncode == 0
        if passed != expected_pass:
            raise AssertionError(
                f"trusted ACL behavior case {case_label!r} returned {completed.returncode}; "
                f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
            )
        combined = completed.stdout + completed.stderr
        if os.fspath(sensitive_path) in combined:
            raise AssertionError(f"trusted ACL behavior case {case_label!r} leaked its path")
        if not expected_pass and "contains an extended or default ACL" not in completed.stderr:
            raise AssertionError(
                f"trusted ACL behavior case {case_label!r} did not fail at the ACL gate"
            )

    helper_case_count = 0
    for script_label, content in contents.items():
        harness = behavior_root / f"acl-helper-{script_label}.sh"
        harness.write_text(
            "#!/usr/bin/env bash\nset -Eeuo pipefail\n"
            "TRUST_GETFACL_BIN=/usr/bin/getfacl\n"
            "TRUST_GREP_BIN=/usr/bin/grep\n"
            "fail() { printf 'ERROR: %s\\n' \"$*\" >&2; exit 97; }\n"
            + function_definition(content, "acl_is_minimal")
            + "\n"
            + function_definition(content, "assert_no_extended_acl")
            + "\nassert_no_extended_acl \"$1\" \"$2\"\n",
            encoding="utf-8",
            newline="\n",
        )
        harness.chmod(0o755)
        for case_name, path, expected_pass in cases:
            run_case(
                harness,
                [os.fspath(path), f"synthetic-{case_name}"],
                expected_pass,
                path,
                f"{script_label}:{case_name}",
            )
            helper_case_count += 1

    root_case_count = 0
    root_case_status = "not_run_non_root"
    if hasattr(os, "geteuid") and os.geteuid() == 0 and Path("/root").is_dir():
        root_case_status = "passed"
        with tempfile.TemporaryDirectory(prefix="mcgs-trusted-acl-", dir="/root") as root_temp:
            trusted_root = Path(root_temp)
            trusted_root.chmod(0o700)
            for script_label, content in contents.items():
                script_root = trusted_root / script_label
                app_root = script_root / "app"
                control = app_root / ".deploy-state"
                wheelhouse = app_root / "wheelhouse"
                script_root.mkdir(mode=0o755)
                script_root.chmod(0o755)
                app_root.mkdir(mode=0o755)
                app_root.chmod(0o755)
                control.mkdir(mode=0o750)
                control.chmod(0o750)
                wheelhouse.mkdir(mode=0o755)
                wheelhouse.chmod(0o755)
                env_file = app_root / "service.env"
                env_file.write_text("fixture\n", encoding="utf-8", newline="\n")
                env_file.chmod(0o600)
                marker_file = app_root / ".deploy-transaction.json"
                backup_file = control / "backup.sqlite3"
                record_file = control / "passed.json"
                code_parent = script_root / "trusted-bin"
                code_parent.mkdir(mode=0o755)
                code_file = code_parent / "helper"
                for path in (marker_file, backup_file, record_file, code_file):
                    path.write_text("fixture\n", encoding="utf-8", newline="\n")
                marker_file.chmod(0o600)
                backup_file.chmod(0o600)
                record_file.chmod(0o640)
                code_file.chmod(0o755)

                harness = behavior_root / f"trusted-path-{script_label}.sh"
                harness.write_text(
                    "#!/usr/bin/env bash\nset -Eeuo pipefail\n"
                    "TRUST_REALPATH_BIN=/usr/bin/realpath\n"
                    "TRUST_STAT_BIN=/usr/bin/stat\n"
                    "TRUST_DIRNAME_BIN=/usr/bin/dirname\n"
                    "TRUST_GETFACL_BIN=/usr/bin/getfacl\n"
                    "TRUST_GREP_BIN=/usr/bin/grep\n"
                    "fail() { printf 'ERROR: %s\\n' \"$*\" >&2; exit 97; }\n"
                    + function_definition(content, "acl_is_minimal")
                    + "\n"
                    + function_definition(content, "assert_no_extended_acl")
                    + "\n"
                    + function_definition(content, "assert_trusted_root_directory_path")
                    + "\n"
                    + function_definition(content, "assert_trusted_root_file_path")
                    + "\n"
                    + function_definition(content, "assert_trusted_code_file")
                    + "\n"
                    + function_definition(content, "assert_trusted_record_file")
                    + "\ncase \"$1\" in\n"
                    "  directory) assert_trusted_root_directory_path \"$2\" \"$3\" ;;\n"
                    "  file) assert_trusted_root_file_path \"$2\" \"$3\" ;;\n"
                    "  code) assert_trusted_code_file \"$2\" \"$3\" ;;\n"
                    "  record) assert_trusted_record_file \"$2\" \"$3\" ;;\n"
                    "  *) exit 64 ;;\n"
                    "esac\n",
                    encoding="utf-8",
                    newline="\n",
                )
                harness.chmod(0o755)

                full_cases = (
                    ("control-baseline", "directory", control, True),
                    ("environment-baseline", "file", env_file, True),
                    ("wheelhouse-baseline", "directory", wheelhouse, True),
                    ("marker-baseline", "file", marker_file, True),
                    ("backup-baseline", "file", backup_file, True),
                    ("record-baseline", "record", record_file, True),
                    ("code-baseline", "code", code_file, True),
                )
                for case_name, path_type, path, expected_pass in full_cases:
                    run_case(
                        harness,
                        [path_type, os.fspath(path), f"synthetic-{case_name}"],
                        expected_pass,
                        path,
                        f"{script_label}:{case_name}",
                    )
                    root_case_count += 1

                mutate_root_cases = (
                    ("backup-mask", "file", backup_file, ["-m", "m::---"]),
                    ("record-extended", "record", record_file, ["-m", "g:12345:---"]),
                    ("code-extended", "code", code_file, ["-m", "u:12345:r-x"]),
                    ("marker-extended", "file", marker_file, ["-m", "u:12345:r--"]),
                    ("environment-extended", "file", env_file, ["-m", "g:12345:---"]),
                    ("wheelhouse-default", "directory", wheelhouse, ["-m", "d:u:12345:r-x"]),
                    ("control-extended", "directory", control, ["-m", "u:12345:r-x"]),
                )
                for case_name, path_type, path, acl_arguments in mutate_root_cases:
                    completed = subprocess.run(
                        [setfacl, *acl_arguments, os.fspath(path)],
                        cwd=trusted_root,
                        check=False,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                    )
                    if completed.returncode != 0:
                        raise AssertionError(
                            f"root trusted ACL injection failed: case={case_name!r} "
                            f"exit={completed.returncode} stderr={completed.stderr!r}"
                        )
                    run_case(
                        harness,
                        [path_type, os.fspath(path), f"synthetic-{case_name}"],
                        False,
                        path,
                        f"{script_label}:{case_name}",
                    )
                    root_case_count += 1

    fake_path_case_count = 0
    fake_bin = behavior_root / "fake-bin"
    fake_bin.mkdir(mode=0o700)
    fake_curl = fake_bin / "curl"
    fake_curl.write_text("#!/usr/bin/bash\nexit 0\n", encoding="utf-8", newline="\n")
    fake_curl.chmod(0o755)
    for script_label, content in contents.items():
        resolver_harness = behavior_root / f"trusted-command-{script_label}.sh"
        resolver_harness.write_text(
            "#!/usr/bin/bash\nset -Eeuo pipefail\n"
            "TRUST_REALPATH_BIN=/usr/bin/realpath\n"
            "fail() { printf 'ERROR: %s\\n' \"$*\" >&2; exit 97; }\n"
            + function_definition(content, "resolve_and_pin_trusted_command")
            + "\nPATH=\"$1:/usr/sbin:/usr/bin\"\nexport PATH\n"
            "resolve_and_pin_trusted_command curl PINNED_CURL\n",
            encoding="utf-8",
            newline="\n",
        )
        resolver_harness.chmod(0o755)
        completed = subprocess.run(
            [bash, os.fspath(resolver_harness), os.fspath(fake_bin)],
            cwd=behavior_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 97:
            raise AssertionError(
                f"{script_label} fake PATH command was not rejected: "
                f"exit={completed.returncode} stdout={completed.stdout!r} stderr={completed.stderr!r}"
            )
        if os.fspath(fake_bin) in completed.stdout + completed.stderr:
            raise AssertionError(f"{script_label} fake PATH rejection leaked its path")
        fake_path_case_count += 1

    return {
        "status": "passed",
        "helper_cases": helper_case_count,
        "root_trusted_path_status": root_case_status,
        "root_trusted_path_cases": root_case_count,
        "fake_path_command_rejections": fake_path_case_count,
        "sensitive_path_output": False,
    }


def assert_dropin_contract(content: str, label: str) -> None:
    canonical_source = simple_function_definition(content, "canonical_managed_dropin_content")
    match = re.search(
        r'cat <<EOF\n(?P<body>.*?)\nEOF',
        canonical_source,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError(f"{label}: canonical managed drop-in here-document is missing")
    lines = match.group("body").splitlines()
    expected_exec = [
        "ExecStart=",
        "ExecStart=$CURRENT_LINK/.venv/bin/python -I -B -u -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $LOCAL_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1",
    ]
    if [line for line in lines if line.startswith("ExecStart=")] != expected_exec:
        raise AssertionError(f"{label}: managed drop-in must reset and replace ExecStart exactly")
    expected_exec_start_pre = [
        "ExecStartPre=",
        "ExecStartPre=/usr/bin/python3 -I -B -u $RUNTIME_GUARD_HELPER --verify-current $CURRENT_LINK --releases-root $RELEASES_DIR --baseline-directory $RUNTIME_BASELINE_DIR --require-root-owned-immutable",
        "ExecStartPre=$CURRENT_LINK/.venv/bin/python -I -B -u $CURRENT_LINK/deploy/validate_production_env.py --shared-runs $RUNS_DIR --security-db $SECURITY_DB --public-origin $PUBLIC_ORIGIN --public-host $PUBLIC_HOST",
    ]
    if [line for line in lines if line.startswith("ExecStartPre=")] != expected_exec_start_pre:
        raise AssertionError(
            f"{label}: managed drop-in must verify the external runtime baseline before the release environment"
        )
    if [line for line in lines if line.startswith("ReadWritePaths=")] != [
        "ReadWritePaths=",
        "ReadWritePaths=$SHARED_DIR",
    ]:
        raise AssertionError(
            f"{label}: managed drop-in must reset and replace ReadWritePaths exactly"
        )
    if "WorkingDirectory=$CURRENT_LINK" not in lines:
        raise AssertionError(f"{label}: managed drop-in does not pin WorkingDirectory")
    if [line for line in lines if line.startswith("Environment=")] != [
        "Environment=",
        "Environment=PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1",
    ]:
        raise AssertionError(
            f"{label}: managed drop-in must reset inherited Environment entries before the exact allowlist"
        )
    unset_lines = [line for line in lines if line.startswith("UnsetEnvironment=")]
    if unset_lines != ["UnsetEnvironment=$REQUIRED_UNSET_ENVIRONMENT"]:
        raise AssertionError(
            f"{label}: managed drop-in must define UnsetEnvironment exactly once"
        )
    if any("*" in name for name in EXPECTED_UNSET_ENVIRONMENT):
        raise AssertionError(
            f"{label}: UnsetEnvironment contains a pseudo-wildcard that systemd will not expand"
        )
    required_hardening = {
        "StartLimitIntervalSec=60s",
        "StartLimitBurst=3",
        "Environment=",
        "Environment=PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1",
        "UnsetEnvironment=$REQUIRED_UNSET_ENVIRONMENT",
        "UMask=0077",
        "NoNewPrivileges=true",
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
        "PrivateTmp=true",
        "PrivateDevices=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "ProtectControlGroups=true",
        "ProtectKernelModules=true",
        "ProtectKernelTunables=true",
        "ProtectKernelLogs=true",
        "ProtectClock=true",
        "RestrictSUIDSGID=true",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "RestrictNamespaces=true",
        "LockPersonality=true",
        "ReadWritePaths=$SHARED_DIR",
    }
    missing = sorted(required_hardening - set(lines))
    if missing:
        raise AssertionError(f"{label}: managed drop-in hardening is incomplete: {missing}")
    matcher_source = simple_function_definition(
        content, "managed_dropin_matches_canonical_content"
    )
    require_in_order(
        matcher_source,
        [
            '[[ -f "$MANAGED_DROPIN" && ! -L "$MANAGED_DROPIN" ]]',
            'cmp -s "$MANAGED_DROPIN" <(canonical_managed_dropin_content)',
        ],
        f"{label}-canonical-managed-dropin-byte-comparison",
    )
    unset_matcher_source = simple_function_definition(
        content, "unset_environment_matches"
    )
    require_fragments(
        unset_matcher_source,
        [
            'read -r -a expected_names <<<"$REQUIRED_UNSET_ENVIRONMENT"',
            'read -r -a actual_names <<<"$actual_text"',
            '[[ "${#expected_names[@]}" == "${#actual_names[@]}" ]]',
            '[[ -z "${expected_seen[$name]+configured}" ]]',
            '[[ -z "${actual_seen[$name]+configured}" ]]',
            '[[ -n "${actual_seen[$name]+configured}" ]]',
        ],
        f"{label}-unset-environment-exact-set-matcher",
    )
    readback_source = simple_function_definition(
        content, "effective_unset_environment_matches"
    )
    require_fragments(
        readback_source,
        [
            '--property=UnsetEnvironment --value',
            'unset_environment_matches "$actual"',
        ],
        f"{label}-unset-environment-manager-readback",
    )
    environment_matcher_source = simple_function_definition(
        content, "environment_assignments_match"
    )
    require_fragments(
        environment_matcher_source,
        [
            'read -r -a expected_assignments <<<"$REQUIRED_SERVICE_ENVIRONMENT"',
            'read -r -a actual_assignments <<<"$actual_text"',
            '[[ "${#expected_assignments[@]}" == "${#actual_assignments[@]}" ]]',
            '[[ -z "${expected_seen[$assignment]+configured}" ]]',
            '[[ -z "${actual_seen[$assignment]+configured}" ]]',
            '[[ -n "${actual_seen[$assignment]+configured}" ]]',
        ],
        f"{label}-explicit-environment-exact-set-matcher",
    )
    environment_readback_source = simple_function_definition(
        content, "effective_environment_matches"
    )
    require_fragments(
        environment_readback_source,
        [
            '--property=Environment --value',
            'environment_assignments_match "$actual"',
        ],
        f"{label}-explicit-environment-manager-readback",
    )
    restart_limit_source = simple_function_definition(
        content, "effective_restart_limit_matches"
    )
    require_fragments(
        restart_limit_source,
        [
            '--property=StartLimitIntervalUSec --value',
            '== "1min"',
            '--property=StartLimitBurst --value',
            '== "3"',
        ],
        f"{label}-bounded-integrity-restart-manager-readback",
    )
    process_environment_source = simple_function_definition(
        content, "process_environment_matches"
    )
    require_fragments(
        process_environment_source,
        [
            'Path(f"/proc/{pid}/environ").read_bytes()',
            'module.load_environment(Path(env_path))',
            'expected.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})',
            'if any(actual.get(key) != value for key, value in expected.items())',
            'module.is_privileged_loader_key(key)',
        ],
        f"{label}-process-environment-provenance",
    )


def assert_reference_service_unit_contract(content: str) -> None:
    lines = content.splitlines()
    expected_exec = (
        "ExecStart=/srv/apps/protocol-studio/current/.venv/bin/python -I -B -u -m uvicorn "
        "protocol_studio.app:app --host 127.0.0.1 --port 18771 --proxy-headers "
        "--forwarded-allow-ips 127.0.0.1"
    )
    if [line for line in lines if line.startswith("ExecStart=")] != [expected_exec]:
        raise AssertionError("reference service main Python is not isolated")
    expected_integrity_pre = (
        "ExecStartPre=/usr/bin/python3 -I -B -u "
        "/srv/apps/protocol-studio/runtime-guard/runtime_fingerprint.py "
        "--verify-current /srv/apps/protocol-studio/current --releases-root "
        "/srv/apps/protocol-studio/releases --baseline-directory "
        "/srv/apps/protocol-studio/runtime-guard/baselines "
        "--require-root-owned-immutable"
    )
    expected_environment_pre = (
        "ExecStartPre=/srv/apps/protocol-studio/current/.venv/bin/python -I -B -u "
        "/srv/apps/protocol-studio/current/deploy/validate_production_env.py "
        "--shared-runs /srv/apps/protocol-studio/shared/runs --security-db "
        "/srv/apps/protocol-studio/shared/security.sqlite3 --public-origin "
        "https://protocol.feian.online --public-host protocol.feian.online"
    )
    if [line for line in lines if line.startswith("ExecStartPre=")] != [
        "ExecStartPre=",
        expected_integrity_pre,
        expected_environment_pre,
    ]:
        raise AssertionError("reference service runtime guard order or Python flags drifted")
    unset_lines = [line for line in lines if line.startswith("UnsetEnvironment=")]
    if len(unset_lines) != 1:
        raise AssertionError("reference service must define UnsetEnvironment exactly once")
    names = tuple(unset_lines[0].removeprefix("UnsetEnvironment=").split())
    if names != EXPECTED_UNSET_ENVIRONMENT or any("*" in name for name in names):
        raise AssertionError("reference service environment sanitization set drifted")
    required = {
        "WorkingDirectory=/srv/apps/protocol-studio/current",
        "EnvironmentFile=/etc/protocol-studio/protocol-studio.env",
        "StartLimitIntervalSec=60s",
        "StartLimitBurst=3",
        "Environment=",
        "Environment=PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1",
    }
    missing = sorted(required - set(lines))
    if missing:
        raise AssertionError(f"reference service runtime contract is incomplete: {missing}")


def assert_isolated_uvicorn_cwd_import(temporary_root: Path) -> dict[str, object]:
    """Prove Uvicorn 0.38 can import the real app under Python isolated mode."""

    flag_probe = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-u",
            "-c",
            (
                "import json,sys; print(json.dumps({"
                "'dont_write_bytecode':sys.dont_write_bytecode,"
                "'stdout_write_through':sys.stdout.write_through,"
                "'isolated':bool(sys.flags.isolated),"
                "'ignore_environment':bool(sys.flags.ignore_environment)}))"
            ),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if flag_probe.returncode != 0:
        raise AssertionError(f"isolated Python flag probe failed: {flag_probe.stderr!r}")
    flag_report = json.loads(flag_probe.stdout)
    if flag_report != {
        "dont_write_bytecode": True,
        "stdout_write_through": True,
        "isolated": True,
        "ignore_environment": True,
    }:
        raise AssertionError(f"isolated Python runtime flags are ineffective: {flag_report}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    runs = temporary_root / "isolated-uvicorn-runs"
    database = temporary_root / "isolated-uvicorn-security.sqlite3"
    environment = {
        "MCGS_FULL_CHAIN_RUNS_ROOT": str(runs),
        "PROTOCOL_STUDIO_RUNS_ROOT": str(runs),
        "PROTOCOL_STUDIO_SECURITY_DB": str(database),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    if os.name == "nt":
        for name in ("SystemRoot", "WINDIR"):
            if os.environ.get(name):
                environment[name] = os.environ[name]
    command = [
        sys.executable,
        "-I",
        "-B",
        "-u",
        "-m",
        "uvicorn",
        "protocol_studio.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--proxy-headers",
        "--forwarded-allow-ips",
        "127.0.0.1",
    ]
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    listening = False
    try:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    listening = True
                    break
            except OSError:
                time.sleep(0.05)
        if not listening:
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            raise AssertionError(
                "python -I -B -u -m uvicorn could not import and start the real app from its "
                f"WorkingDirectory: exit={process.returncode} stdout={stdout!r} stderr={stderr!r}"
            )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
    if process.returncode not in {0, 1, 15, -15}:
        raise AssertionError(
            f"isolated Uvicorn smoke had an unexpected termination code: {process.returncode}"
        )
    return {
        "executed": True,
        "python_isolated": True,
        "bytecode_disabled_by_flag": True,
        "stdio_unbuffered_by_flag": True,
        "real_app_imported_before_listen": True,
        "working_directory": str(REPO_ROOT),
    }


def assert_uvicorn_app_dir_hijack_blocked(temporary_root: Path) -> dict[str, object]:
    """Exercise the real Uvicorn Click env path, then prove both gates reject it."""

    hostile_root = temporary_root / "hostile-uvicorn-app-dir"
    hostile_package = hostile_root / "protocol_studio"
    hostile_package.mkdir(parents=True)
    (hostile_package / "__init__.py").write_text("", encoding="utf-8")
    sentinel = temporary_root / "hostile-import-sentinel"
    (hostile_package / "app.py").write_text(
        "from pathlib import Path\n"
        "import os\n"
        "Path(os.environ['MCGS_UVICORN_HIJACK_SENTINEL']).write_text('imported\\n', encoding='utf-8')\n"
        "async def app(scope, receive, send):\n"
        "    await send({'type': 'http.response.start', 'status': 200, 'headers': []})\n"
        "    await send({'type': 'http.response.body', 'body': b'ok'})\n",
        encoding="utf-8",
    )
    raw_environment = {
        "MCGS_UVICORN_HIJACK_SENTINEL": str(sentinel),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "UVICORN_APP_DIR": str(hostile_root),
    }
    if os.name == "nt":
        for name in ("SystemRoot", "WINDIR"):
            if os.environ.get(name):
                raw_environment[name] = os.environ[name]
    raw_command = [
        sys.executable,
        "-I",
        "-B",
        "-u",
        "-m",
        "uvicorn",
        "protocol_studio.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "0",
        "--proxy-headers",
        "--forwarded-allow-ips",
        "127.0.0.1",
    ]
    vulnerable_probe = subprocess.Popen(
        raw_command,
        cwd=REPO_ROOT,
        env=raw_environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and not sentinel.is_file():
            if vulnerable_probe.poll() is not None:
                break
            time.sleep(0.05)
        if not sentinel.is_file() or sentinel.read_text(encoding="utf-8") != "imported\n":
            vulnerable_probe.terminate()
            stdout, stderr = vulnerable_probe.communicate(timeout=5)
            raise AssertionError(
                "Uvicorn 0.38 UVICORN_APP_DIR threat probe did not exercise the real "
                f"import path: exit={vulnerable_probe.returncode} "
                f"stdout={stdout!r} stderr={stderr!r}"
            )
    finally:
        if vulnerable_probe.poll() is None:
            vulnerable_probe.terminate()
            try:
                vulnerable_probe.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                vulnerable_probe.kill()
                vulnerable_probe.communicate(timeout=5)

    sentinel.unlink()
    hostile_environment_file = temporary_root / "hostile-uvicorn.env"
    hostile_environment_file.write_text(
        f"UVICORN_APP_DIR={hostile_root.as_posix()}\nWEB_CONCURRENCY=9\n",
        encoding="utf-8",
    )
    blocked_environment = {}
    if os.name == "nt":
        for name in ("SystemRoot", "WINDIR"):
            if os.environ.get(name):
                blocked_environment[name] = os.environ[name]
    blocked = subprocess.run(
        [
            sys.executable,
            str(ENV_RUNNER),
            "--env-file",
            str(hostile_environment_file),
            "--",
            sys.executable,
            "-c",
            (
                "from pathlib import Path; import sys; "
                "Path(sys.argv[1]).write_text('bypassed', encoding='utf-8')"
            ),
            str(sentinel),
        ],
        cwd=REPO_ROOT,
        env=blocked_environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if (
        blocked.returncode == 0
        or sentinel.exists()
        or "UVICORN_APP_DIR" not in blocked.stderr
        or "WEB_CONCURRENCY" not in blocked.stderr
        or hostile_root.as_posix() in blocked.stdout + blocked.stderr
    ):
        raise AssertionError(
            "environment runner did not block Uvicorn Click import controls before exec: "
            f"exit={blocked.returncode} stdout={blocked.stdout!r} stderr={blocked.stderr!r}"
        )
    return {
        "real_uvicorn_click_app_dir_exercised": True,
        "environment_runner_rejected_before_exec": True,
        "sentinel_absent_after_rejection": True,
    }


def assert_uvicorn_cli_environment_coverage() -> dict[str, object]:
    uvicorn = importlib.import_module("uvicorn")
    uvicorn_main = importlib.import_module("uvicorn.main")
    option_environment_names = {
        f"UVICORN_{parameter.name.upper()}" for parameter in uvicorn_main.main.params
    }
    configured = set(EXPECTED_UNSET_ENVIRONMENT)
    missing = sorted(option_environment_names - configured)
    if missing:
        raise AssertionError(
            f"systemd environment sanitization misses Uvicorn CLI options: {missing}"
        )
    for required in (
        "UVICORN_APP_DIR",
        "UVICORN_ENV_FILE",
        "UVICORN_FACTORY",
        "UVICORN_RELOAD",
        "UVICORN_WORKERS",
        "WEB_CONCURRENCY",
        "FORWARDED_ALLOW_IPS",
    ):
        if required not in configured:
            raise AssertionError(f"Uvicorn startup control is not sanitized: {required}")
    return {
        "uvicorn_version": str(uvicorn.__version__),
        "click_option_environment_names": len(option_environment_names),
        "missing": [],
    }


def assert_final_publication_gate_contract(
    content: str,
    label: str,
    publication_fragments: list[str],
) -> int:
    gate_body = function_body(content, "validate_final_publication_configuration")
    require_fragments(
        gate_body,
        [
            'sha256sum "$ENV_FILE"',
            'sha256sum "$FRAGMENT_PATH"',
            'cmp -s "$FRAGMENT_PATH"',
            'assert_trusted_root_file_path "$ENV_FILE"',
            'assert_secure_systemd_file "$FRAGMENT_PATH"',
            '--property=NeedDaemonReload --value',
            '--property=EnvironmentFiles --value',
            'managed_dropin_matches_canonical_content',
            'effective_exec_start_pre_argvs',
            'effective_unset_environment_matches',
            'effective_environment_matches',
            'effective_restart_limit_matches',
            '--property=DropInPaths --value',
            'assert_dropin_paths_exact',
        ],
        f"{label}-final-publication-config-hash-content-and-manager-binding",
    )
    if label == DEPLOY_SCRIPT.name:
        require_fragments(
            gate_body,
            [
                '== "$UNIT_FRAGMENT_SHA256"',
                '"$UNIT_BACKUP"',
                'sha256sum "$MANAGED_DROPIN"',
                '== "$MANAGED_DROPIN_SHA256"',
                '== "$MODERN_EXEC_START_PRE_ARGVS_JSON"',
            ],
            f"{label}-final-publication-modern-runtime-binding",
        )
    elif label == ROLLBACK_SCRIPT.name:
        require_fragments(
            gate_body,
            [
                '== "$UNIT_FRAGMENT_SHA256"',
                '"$UNIT_BACKUP"',
                'if [[ "$TARGET_MODE" == "release" ]]',
                '== "$TARGET_MANAGED_DROPIN_SHA256"',
                '== "$MODERN_EXEC_START_PRE_ARGVS_JSON"',
                '[[ ! -e "$MANAGED_DROPIN" && ! -L "$MANAGED_DROPIN"',
            ],
            f"{label}-final-publication-release-and-legacy-binding",
        )
    else:
        require_fragments(
            gate_body,
            [
                '== "$FRAGMENT_SHA256"',
                '"$FRAGMENT_BACKUP"',
                'if [[ "$ACTIVATION_MODE" == "release" ]]',
                'expected_managed_dropin_sha256="$(canonical_managed_dropin_content | sha256sum',
                'sha256sum "$MANAGED_DROPIN"',
                '== "$expected_managed_dropin_sha256"',
                '== "$EXPECTED_EXEC_START_PRE_ARGVS_JSON"',
                '[[ ! -e "$MANAGED_DROPIN" && ! -L "$MANAGED_DROPIN"',
            ],
            f"{label}-final-publication-recovery-mode-binding",
        )

    validated_publications = 0
    publication_offsets: dict[str, int] = {}
    for publication in publication_fragments:
        publication_position = content.find(
            publication, publication_offsets.get(publication, 0)
        )
        if publication_position < 0:
            raise AssertionError(f"{label}: publication call is missing: {publication}")
        publication_offsets[publication] = publication_position + len(publication)
        enable_position = content.rfind(
            'systemctl enable "$SERVICE"', 0, publication_position
        )
        prefix = content[:publication_position]
        gate_calls = list(
            re.finditer(
                r"(?m)^[ \t]*validate_final_publication_configuration \\$",
                prefix,
            )
        )
        validator_calls = list(
            re.finditer(
                r"(?m)^[ \t]*validate_production_environment \\$",
                prefix,
            )
        )
        gate_position = gate_calls[-1].start() if gate_calls else -1
        validator_position = validator_calls[-1].start() if validator_calls else -1
        if not (
            0 <= enable_position < gate_position < validator_position < publication_position
        ):
            raise AssertionError(
                f"{label}: enable/final-config/full-validator/publication order is invalid "
                f"for {publication}: enable={enable_position} gate={gate_position} "
                f"validator={validator_position} publication={publication_position}"
            )
        validated_publications += 1
    return validated_publications


def compile_python_heredocs(content: str, label: str) -> int:
    lines = content.splitlines()
    count = 0
    line_index = 0
    while line_index < len(lines):
        opener = lines[line_index]
        if "<<'PY'" not in opener:
            line_index += 1
            continue
        body_start = line_index + 1
        command_line = opener
        while command_line.rstrip().endswith("\\"):
            if body_start >= len(lines):
                raise AssertionError(f"{label}: unterminated heredoc command continuation")
            command_line = lines[body_start]
            body_start += 1
        try:
            closer = lines.index("PY", body_start)
        except ValueError as exc:
            raise AssertionError(f"{label}: Python heredoc terminator is missing") from exc
        count += 1
        compile(
            "\n".join(lines[body_start:closer]),
            f"{label}:python-heredoc:{count}",
            "exec",
        )
        line_index = closer + 1
    return count


def assert_atomic_probe_only(content: str, label: str) -> None:
    body = function_body(content, "verify_atomic_rename_boundary")
    require_fragments(
        body,
        [
            '"$APP_ROOT" "$DEPLOYMENT_DIR"',
            '"same_device"',
            '"inode_preserved"',
            '"source_removed"',
            '"target_removed"',
        ],
        f"{label}-atomic-marker-archive-same-device-probe",
    )
    modes = re.findall(r'\bhelper,\s*["\']([a-z][a-z0-9_-]*)["\']', body)
    if modes != ["probe"]:
        raise AssertionError(f"{label}: atomic helper modes must be exactly ['probe']: {modes}")
    if content.count('"$SCRIPT_DIR/atomic_rename.py"') != 2:
        raise AssertionError(
            f"{label}: atomic helper must appear only in the trust list and probe wrapper"
        )
    if content.count("verify_atomic_rename_boundary") != 2:
        raise AssertionError(f"{label}: atomic probe must be defined and called exactly once")
    call_positions = [
        match.start()
        for match in re.finditer(r"(?m)^verify_atomic_rename_boundary \\\n", content)
    ]
    marker_archive_position = content.find('mv -T -- "$TRANSACTION_FILE"')
    if (
        len(call_positions) != 1
        or marker_archive_position < 0
        or call_positions[0] > marker_archive_position
    ):
        raise AssertionError(f"{label}: same-device gate does not precede marker archival")
    direct_replace = re.search(
        r'atomic_rename\.py["\']?(?:\s*\\\r?\n\s*|\s+)["\']?replace\b',
        content,
    )
    if direct_replace or re.search(r'\bhelper,\s*["\']replace["\']', content):
        raise AssertionError(f"{label}: atomic helper replace mode is forbidden")


def assert_runtime_systemd_guard_contract(content: str, label: str) -> None:
    require_fragments(
        content,
        [
            'RUNTIME_SYSTEMD_DIR="/run/systemd/system"',
            'TRANSACTION_RUNTIME_GUARD_DIR="$RUNTIME_SYSTEMD_DIR/$SERVICE.d"',
            'TRANSACTION_RUNTIME_GUARD="$TRANSACTION_RUNTIME_GUARD_DIR/99-transaction-runtime-guard.conf"',
            "assert_transaction_runtime_guard_file()",
            "assert_transaction_runtime_guard_loaded()",
            "install_transaction_runtime_guard()",
            "ensure_transaction_runtime_guard_loaded()",
            "remove_transaction_runtime_guard()",
            "transition_transaction_status()",
            "payload = b\"[Service]\\nRestart=no\\nRuntimeMaxSec=300s\\n\"",
        ],
        f"{label}-runtime-systemd-guard-surface",
    )
    installed = function_body(content, "install_transaction_runtime_guard")
    require_in_order(
        installed,
        [
            '[[ ! -e "$TRANSACTION_RUNTIME_GUARD" && ! -L "$TRANSACTION_RUNTIME_GUARD" ]]',
            "os.O_EXCL",
            "os.fchmod(descriptor, 0o644)",
            "os.fchown(descriptor, 0, 0)",
            "os.fsync(handle.fileno())",
            "if os.path.lexists(final):",
            "os.rename(temporary, final)",
            "os.fsync(directory_fd)",
            "assert_transaction_runtime_guard_file",
            "systemctl daemon-reload",
            "assert_transaction_runtime_guard_loaded",
        ],
        f"{label}-runtime-systemd-guard-install",
    )
    loaded = function_body(content, "assert_transaction_runtime_guard_loaded")
    require_in_order(
        loaded,
        [
            "assert_transaction_runtime_guard_file",
            "--property=Restart --value",
            '== "no"',
            "--property=RuntimeMaxUSec --value",
            '== "5min"',
            "--property=NeedDaemonReload --value",
            "--property=DropInPaths --value",
            "assert_dropin_paths_exact",
        ],
        f"{label}-runtime-systemd-guard-loaded-readback",
    )
    removed = function_body(content, "remove_transaction_runtime_guard")
    require_in_order(
        removed,
        [
            "assert_transaction_runtime_guard_file",
            "rm " + '-f -- "$TRANSACTION_RUNTIME_GUARD"',
            '[[ ! -e "$TRANSACTION_RUNTIME_GUARD" && ! -L "$TRANSACTION_RUNTIME_GUARD" ]]',
            'fsync_directory "$TRANSACTION_RUNTIME_GUARD_DIR"',
            "systemctl daemon-reload",
            "--property=Restart --value",
            '== "on-failure"',
            "--property=RuntimeMaxUSec --value",
            '== "infinity"',
            "--property=NeedDaemonReload --value",
            "--property=DropInPaths --value",
            "assert_dropin_paths_exact",
        ],
        f"{label}-runtime-systemd-guard-removal-readback",
    )


def main() -> int:
    contents = {path.name: path.read_text(encoding="utf-8") for path in SHELL_SCRIPTS}
    deploy = contents[DEPLOY_SCRIPT.name]
    rollback = contents[ROLLBACK_SCRIPT.name]
    recovery = contents[RECOVERY_SCRIPT.name]
    check_production = CHECK_PRODUCTION_SCRIPT.read_text(encoding="utf-8")
    runner = ENV_RUNNER.read_text(encoding="utf-8")
    validator_source = ENV_VALIDATOR.read_text(encoding="utf-8")
    reference_service = REFERENCE_SERVICE_UNIT.read_text(encoding="utf-8")
    runtime_fingerprint_helper = RUNTIME_FINGERPRINT_HELPER.read_text(encoding="utf-8")
    (
        deploy_activation_audit_source,
        deploy_activation_gate_source,
        deploy_activation_entry_block,
        deploy_activation_side_effect_anchors,
    ) = assert_deploy_activation_schema_fail_fast_contract(deploy)
    assert_reference_service_unit_contract(reference_service)
    require_fragments(
        runtime_fingerprint_helper,
        [
            '"runtime_guard_helper_sha256"',
            'baseline["runtime_guard_helper_sha256"] != helper_sha256',
            'fail_verification("runtime guard helper digest mismatch")',
        ],
        "ordinary-restart-helper-content-binding",
    )
    uvicorn_cli_environment_coverage = assert_uvicorn_cli_environment_coverage()
    entry_contents = {
        **contents,
        CHECK_PRODUCTION_SCRIPT.name: check_production,
    }
    for label, content in entry_contents.items():
        assert_privileged_shell_entry_contract(content, label)
        assert_strict_health_status_contract(content, label)

    bash = shutil.which("bash")
    if not bash:
        raise AssertionError("bash is required to validate deployment script syntax")
    syntax_results: dict[str, int] = {}
    for path in ALL_SHELL_SCRIPTS:
        syntax = subprocess.run(
            [bash, "-n", str(path)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        syntax_results[path.name] = syntax.returncode
        if syntax.returncode != 0:
            raise AssertionError(
                json.dumps(
                    {
                        "bash_syntax_file": path.name,
                        "bash_syntax_exit": syntax.returncode,
                        "stderr": syntax.stderr,
                    },
                    ensure_ascii=False,
                )
            )

    heredoc_counts = {
        label: compile_python_heredocs(content, label) for label, content in contents.items()
    }

    for label, content in contents.items():
        constant_match = re.search(
            r"^builtin readonly REQUIRED_UNSET_ENVIRONMENT='([^']+)'$",
            content,
            flags=re.MULTILINE,
        )
        if (
            constant_match is None
            or tuple(constant_match.group(1).split()) != EXPECTED_UNSET_ENVIRONMENT
        ):
            raise AssertionError(f"{label}: environment sanitization constant drifted")
        service_environment_match = re.search(
            r"^builtin readonly REQUIRED_SERVICE_ENVIRONMENT='([^']+)'$",
            content,
            flags=re.MULTILINE,
        )
        if (
            service_environment_match is None
            or service_environment_match.group(1)
            != "PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1"
        ):
            raise AssertionError(f"{label}: explicit service environment allowlist drifted")
        require_fragments(
            content,
            [
                '--property=Environment=',
                '--property="Environment=PYTHONDONTWRITEBYTECODE=1"',
                '--property="Environment=PYTHONUNBUFFERED=1"',
                '--property="UnsetEnvironment=$REQUIRED_UNSET_ENVIRONMENT"',
                '--property=UnsetEnvironment --value',
                '--property=Environment --value',
                ' -I -B -u -m uvicorn protocol_studio.app:app',
                'transient canary environment sanitization does not match the managed service',
                'transient canary explicit environment does not match the managed service',
                'process_environment_matches "$PREFLIGHT_MAIN_PID"',
            ],
            f"{label}-transient-and-managed-environment-sanitization",
        )
        require_fragments(
            content,
            [
                "validate_health_manifest_header()",
                "manifest_bound_health()",
                "availability_health()",
                "runtime_health()",
                "validate_login_redirect_headers()",
                "strict_login_redirect()",
                "--dump-header - --output /dev/null",
                '[[ "${#manifest_values[@]}" == "1" ]]',
                '[[ "${manifest_values[0]}" =~ ^[0-9a-f]{64}$ ]]',
                '[[ "${manifest_values[0]}" == "$expected_sha256" ]]',
                "release|release-local-venv)",
                "legacy|legacy-shared-venv)",
            ],
            f"{label}-release-health-identity-surface",
        )
        for match in re.finditer(r"/api/health", content):
            prefix = content[max(0, match.start() - 220) : match.start()]
            if not re.search(r"(?:manifest_bound_health|runtime_health)[^\n]*\\?\n?[^\n]*$", prefix):
                raise AssertionError(
                    f"{label}: health call is not manifest-dispatched near offset {match.start()}"
                )

    require_fragments(
        check_production,
        [
            "PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256",
            "PROTOCOL_STUDIO_ALLOW_AVAILABILITY_ONLY",
            "EXPECTED_MANIFEST_CONFIGURED",
            'EXPECTED_MANIFEST_CONFIGURED" == "false" && "$ALLOW_AVAILABILITY_ONLY" != "true"',
            'EXPECTED_MANIFEST_CONFIGURED" == "true" && "$ALLOW_AVAILABILITY_ONLY" == "true"',
            "manifest_bound_health",
            '"$LOCAL_ORIGIN/api/health"',
            '"$PUBLIC_ORIGIN/api/health"',
            'printf \'release_identity=%s\\n\'',
        ],
        "check-production-release-identity-stop-condition",
    )
    curl_contract_contents = {
        **contents,
        CHECK_PRODUCTION_SCRIPT.name: check_production,
    }
    curl_command_counts = {
        label: assert_curl_isolation_contract(content, label)
        for label, content in curl_contract_contents.items()
    }

    for label, content in contents.items():
        require_fragments(
            content,
            [
                'CONTROL_DIR="$APP_ROOT/.deploy-state"',
                'LOCK_FILE="$CONTROL_DIR/deploy.lock"',
                'exec 9<>"$LOCK_FILE"',
                'exec 8<>"$LEGACY_LOCK_FILE"',
                'TRANSACTION_FILE="$APP_ROOT/.deploy-transaction.json"',
                'service_enable_state()',
                'fsync_file()',
                'fsync_directory()',
                'fsync_systemd_enablement_state()',
                'collect_service_enablement_links()',
                'SYSTEMD_CONFIG_DIR="/etc/systemd/system"',
                'assert_trusted_root_directory_path()',
                'assert_trusted_code_file()',
                'assert_release_tree_security()',
                'assert_secure_systemd_directory()',
                'effective_exec_argv()',
                'resolve_and_pin_trusted_command python3 PYTHON_BIN',
                '"$PYTHON_BIN" -I',
                '--release-root "$release_root"',
                '--require-root-owned-immutable',
                'PREVIOUS_UMASK=',
                '"previous_umask"',
                'type(record["runtime_fingerprint"].get("schema_version")) is not int',
                'verify_atomic_rename_boundary()',
                '[python, "-I", helper, "probe", "--source-dir", source_dir, "--target-dir", target_dir]',
                'type(report["schema_version"]) is not int',
                'type(report["error_number"]) is not int',
                'publish_committed_record()',
            ],
            f"{label}-shared-safety-boundary",
        )
        assert_atomic_probe_only(content, label)
        assert_runtime_systemd_guard_contract(content, label)
        assert_trusted_path_acl_contract(content, label)
        assert_trusted_command_contract(content, label)
        assert_control_state_acl_contract(content, label)

    require_fragments(
        deploy,
        [
            "--archive-sha256 SHA256",
            'EXPECTED_ARCHIVE_SHA256="${2,,}"',
            'TRUSTED_ARCHIVE="$CONTROL_DIR/.archive-$RELEASE_ID-$$.tar.gz"',
            "os.O_EXCL",
            "O_NOFOLLOW",
            'ARCHIVE_SHA256="$ARCHIVE_SHA256_FIXED"',
            'PROTOCOL_STUDIO_WHEELHOUSE is required for hash-locked offline installation',
            'requirements.production.lock.txt',
            "--no-index",
            "--only-binary=:all:",
            "--require-hashes",
            'assert_trusted_record_file "$PREVIOUS_DEPLOYMENT_RECORD"',
            '"prepared_release_durable": True',
            '"service_enabled_before_switch": True',
            '"service_disabled_during_switch": True',
            '"service_enabled_after_health": True',
            '"final_publication_configuration_gate": True',
            'systemd service user cannot persist shared runs or account database state',
            'process_exec_argv "$PREVIOUS_MAIN_PID"',
            'process_working_directory "$PREVIOUS_MAIN_PID"',
            'sys.version_info[:2] != (3, 11)',
            'from pip._vendor.packaging.tags import sys_tags',
            '"$CANDIDATE_PYTHON" -I -m pip check',
            'assert_release_tree_security "$CANDIDATE_DIR" "$SERVICE_USER"',
            '"release_tree_immutable": True',
            '"release_root_sha256"',
        ],
        "deploy-release-integrity",
    )
    cleanup_source = simple_function_definition(deploy, "cleanup_candidate")
    promoted_branch = re.search(
        r'(?ms)if \[\[ "\$RELEASE_PROMOTED" == "true" \]\]; then\n(?P<body>.*?)^  fi$',
        cleanup_source,
    )
    if not promoted_branch:
        raise AssertionError("promoted candidate cleanup guard is missing")
    promoted_cleanup_body = promoted_branch.group("body")
    if "return 0" not in promoted_cleanup_body:
        raise AssertionError("promoted release cleanup does not stop before automatic cleanup")
    promoted_mutations = [
        fragment
        for fragment in ("mv ", "rm ", "install ", "failed-preparations")
        if fragment in promoted_cleanup_body
    ]
    if promoted_mutations:
        raise AssertionError(
            f"promoted release cleanup still mutates durable evidence: {promoted_mutations}"
        )
    if "failed-preparations" in cleanup_source:
        raise AssertionError("cleanup trap still contains automatic promoted-release quarantine")
    incoming_cleanup = 'rm -rf -- "$INCOMING_DIR"'
    if (
        incoming_cleanup not in cleanup_source
        or cleanup_source.find(incoming_cleanup) < promoted_branch.end()
    ):
        raise AssertionError("unpromoted incoming candidate cleanup is missing or bypasses the guard")
    assert_dropin_contract(deploy, "deploy")
    deploy_switch = content_after(deploy, '"status": "switching"', "deploy-main")
    require_in_order(
        deploy_switch,
        [
            'fsync_file "$TRANSACTION_TEMP"',
            'mv -Tf -- "$TRANSACTION_TEMP" "$TRANSACTION_FILE"',
            'fsync_directory "$APP_ROOT"',
            'systemctl disable "$SERVICE"',
            'assert_service_persistently_disabled "$SERVICE_USER"',
            'fsync_systemd_enablement_state',
            'assert_service_persistently_disabled "$SERVICE_USER"',
            'install_transaction_runtime_guard "$SERVICE_USER"',
            "stop_service_and_verify",
            'atomic_link "$RELEASE_DIR"',
            'fsync_file "$DROPIN_TEMP"',
            'mv -Tf -- "$DROPIN_TEMP" "$MANAGED_DROPIN"',
            'fsync_directory "$MANAGED_DROPIN_DIR"',
            'systemctl daemon-reload',
            'systemctl --no-block start "$SERVICE"',
            '"$PUBLIC_ORIGIN/api/health"',
            'fsync_file "$DEPLOYMENT_RECORD_TEMP"',
            'transition_transaction_status "switching" "deploy_committed_pending_activation"',
            "stop_service_and_verify",
            'remove_transaction_runtime_guard "$SERVICE_USER"',
            'systemctl --no-block start "$SERVICE"',
            'systemctl enable "$SERVICE"',
            'assert_standard_enabled_topology "$SERVICE_USER"',
            'fsync_systemd_enablement_state',
            'assert_standard_enabled_topology "$SERVICE_USER"',
            'systemctl is-active --quiet "$SERVICE"',
            'process_exec_argv "$MAIN_PID"',
            'process_working_directory "$MAIN_PID"',
            'assert_release_tree_security "$RELEASE_DIR" "$SERVICE_USER"',
            'runtime_fingerprint "$RELEASE_DIR/.venv"',
            '"$PYTHON_BIN" -I "$SCRIPT_DIR/verify_installed_release.py"',
            'validate_final_publication_configuration',
            'validate_production_environment',
            'publish_committed_record "$DEPLOYMENT_RECORD_TEMP" "$DEPLOYMENT_RECORD"',
            'mv -T -- "$TRANSACTION_FILE" "$COMMITTED_TRANSACTION_RECORD"',
            'TRANSACTION_ACTIVE="false"',
            'fsync_file "$COMMITTED_TRANSACTION_RECORD"',
            'fsync_directory "$DEPLOYMENT_DIR"',
            'fsync_directory "$APP_ROOT"',
            'trap - EXIT INT TERM HUP',
        ],
        "deploy-pending-activation-enable-archive-publication-order",
    )
    deploy_restore = function_body(deploy, "rollback_to_previous")
    require_in_order(
        deploy_restore,
        [
            'systemctl disable "$SERVICE"',
            'fsync_systemd_enablement_state',
            '( trap - EXIT; stop_service_and_verify )',
            'systemctl reset-failed "$SERVICE"',
            "probe_service_enablement",
            "--property=ActiveState --value",
            "--property=SubState --value",
            "--property=MainPID --value",
            '"$marker_retained" == "true"',
            "assert_service_persistently_disabled",
            'if [[ "$fail_closed" == "true" ]]',
            "FAIL-CLOSED CONFIRMED:",
            "else",
            "CRITICAL: FAIL-CLOSED NOT CONFIRMED",
            "cleanup_candidate",
            "exit 1",
        ],
        "deploy-failure-retains-marker-and-reports-actual-disabled-state",
    )
    forbidden_restore_actions = [
        "atomic_link ",
        "restore_previous_dropin",
        'systemctl --no-block start "$SERVICE"',
        'systemctl enable "$SERVICE"',
    ]
    unexpected_restore_actions = [
        fragment for fragment in forbidden_restore_actions if fragment in deploy_restore
    ]
    if unexpected_restore_actions:
        raise AssertionError(
            "deploy failure handler must leave restoration to recover-transaction.sh: "
            f"{unexpected_restore_actions}"
        )

    require_fragments(
        rollback,
        [
            'validate_passed_release_record "$TARGET_DEPLOYMENT_RECORD" "$RELEASE_ID" "$TARGET"',
            'validate_legacy_baseline "$TARGET"',
            'validate_passed_release_record "$DEPLOYMENT_DIR/$PREVIOUS_ID.json" "$PREVIOUS_ID" "$PREVIOUS_TARGET"',
            '"prepared_release_durable": True',
            '"service_enabled_before_switch": True',
            '"service_disabled_during_switch": True',
            '"service_enabled_after_health": True',
            '"final_publication_configuration_gate": True',
            'assert_release_tree_security "$target" "$SERVICE_USER"',
            '"$target/requirements.production.lock.txt" "$target"',
        ],
        "rollback-known-good-only",
    )
    require_fragments(
        rollback,
        [
            'PREFLIGHT_LOG="$LOG_DIR/$RELEASE_ID-rollback-preflight-$$.log"',
            'systemd-run --quiet --collect --unit="$PREFLIGHT_UNIT"',
            '--property="BindPaths=$PREFLIGHT_SHARED:$SHARED_DIR"',
            '--property="RuntimeMaxSec=${CANARY_RUNTIME_MAX_SECONDS}s"',
            'systemctl kill --kill-who=all --signal=KILL "$PREFLIGHT_UNIT"',
        ],
        "rollback-transient-systemd-canary-is-bounded-and-private",
    )
    assert_dropin_contract(rollback, "rollback")
    rollback_switch = content_after(rollback, '"status": "rolling_back"', "rollback-main")
    require_in_order(
        rollback_switch,
        [
            'fsync_file "$TRANSACTION_TEMP"',
            'mv -Tf -- "$TRANSACTION_TEMP" "$TRANSACTION_FILE"',
            'fsync_directory "$APP_ROOT"',
            'systemctl disable "$SERVICE"',
            'assert_service_persistently_disabled "$SERVICE_USER"',
            'fsync_systemd_enablement_state',
            'assert_service_persistently_disabled "$SERVICE_USER"',
            'install_transaction_runtime_guard "$SERVICE_USER"',
            "stop_service_and_verify",
            'atomic_link "$TARGET"',
            'systemctl daemon-reload',
            'systemctl --no-block start "$SERVICE"',
            '"$PUBLIC_ORIGIN/api/health"',
            'fsync_file "$ROLLBACK_RECORD_TEMP"',
            'transition_transaction_status "rolling_back" "rollback_committed_pending_activation"',
            "stop_service_and_verify",
            'remove_transaction_runtime_guard "$SERVICE_USER"',
            'systemctl --no-block start "$SERVICE"',
            'systemctl enable "$SERVICE"',
            'assert_standard_enabled_topology "$SERVICE_USER"',
            'fsync_systemd_enablement_state',
            'assert_standard_enabled_topology "$SERVICE_USER"',
            'systemctl is-active --quiet "$SERVICE"',
            'process_exec_argv "$MAIN_PID"',
            'process_working_directory "$MAIN_PID"',
            'validate_runtime_provenance "$TARGET_MODE" "$RELEASE_ID" "$TARGET"',
            'validate_final_publication_configuration',
            'validate_production_environment',
            'publish_committed_record "$ROLLBACK_RECORD_TEMP" "$ROLLBACK_RECORD"',
            'mv -T -- "$TRANSACTION_FILE" "$COMMITTED_TRANSACTION_RECORD"',
            'TRANSACTION_ACTIVE="false"',
            'fsync_file "$COMMITTED_TRANSACTION_RECORD"',
            'fsync_directory "$DEPLOYMENT_DIR"',
            'fsync_directory "$APP_ROOT"',
            'trap - EXIT INT TERM HUP',
        ],
        "rollback-pending-activation-enable-archive-publication-order",
    )

    assert_dropin_contract(recovery, "recovery")
    require_fragments(
        recovery,
        [
            'record.get("prepared_release_durable") is not True',
            'record.get("service_enabled_before_switch") is not True',
            'record.get("known_good_health_before_switch") is not True',
            "probe_service_enablement",
            'INITIAL_ENABLE_STATE="$SERVICE_ENABLE_STDOUT"',
            'INITIAL_ENABLE_EXIT="$SERVICE_ENABLE_EXIT"',
            'validate_passed_release_record',
            'validate_legacy_baseline',
            '"service_disabled_during_recovery": True',
            '"service_enabled_after_health": True',
            '"final_publication_configuration_gate": True',
            '"database_backup", "prepared_release_durable", "service_enabled_before_switch"',
            'type(record.get("schema_version")) is not int',
            'type(database_backup[key]) is not int',
            '[[ "${#TX_FIELDS[@]}" == "26" ]]',
            'PREVIOUS_UMASK="${TX_FIELDS[16]}"',
            'MARKER_PUBLIC_ORIGIN="${TX_FIELDS[18]}"',
            'MARKER_PUBLIC_HOST="${TX_FIELDS[19]}"',
            'DATABASE_BACKUP_BASENAME="${TX_FIELDS[20]}"',
            'DATABASE_BACKUP_METADATA_JSON="${TX_FIELDS[21]}"',
            'TX_OPERATION="${TX_FIELDS[22]}"',
            'TX_TARGET_ID="${TX_FIELDS[23]}"',
            'TX_TARGET_MODE="${TX_FIELDS[24]}"',
            'TX_STARTED_AT="${TX_FIELDS[25]}"',
            'CALLER_PUBLIC_ORIGIN" == "$MARKER_PUBLIC_ORIGIN',
            'CALLER_PUBLIC_HOST" == "$MARKER_PUBLIC_HOST',
            'TX_STAMP="${TX_STARTED_AT//[-:]/}"',
            'assert_release_tree_security "$PREVIOUS_TARGET" "$PREVIOUS_SERVICE_USER"',
        ],
        "recovery-authenticated-marker",
    )
    require_fragments(
        recovery,
        [
            'PREFLIGHT_LOG="$LOG_DIR/$ACTIVATION_ID-recovery-preflight-$$.log"',
            'systemd-run --quiet --collect --unit="$PREFLIGHT_UNIT"',
            '--property="BindPaths=$PREFLIGHT_SHARED:$SHARED_DIR"',
            '--property="RuntimeMaxSec=${CANARY_RUNTIME_MAX_SECONDS}s"',
            'systemctl kill --kill-who=all --signal=KILL "$PREFLIGHT_UNIT"',
        ],
        "recovery-transient-systemd-canary-is-bounded-and-private",
    )
    recovery_main = content_after(recovery, 'RECOVERY_ACTIVE="true"', "recovery-main")
    require_in_order(
        recovery_main,
        [
            'trap recovery_exit_guard EXIT',
            'systemctl disable "$SERVICE"',
            'assert_service_persistently_disabled "$PREVIOUS_SERVICE_USER"',
            'fsync_systemd_enablement_state',
            'assert_service_persistently_disabled "$PREVIOUS_SERVICE_USER"',
            'ensure_transaction_runtime_guard_loaded "$PREVIOUS_SERVICE_USER"',
            "stop_service_and_verify",
            'atomic_link "$ACTIVATION_TARGET"',
            "restore_marker_dropin",
            'systemctl daemon-reload',
            'systemctl --no-block start "$SERVICE"',
            '"$PUBLIC_ORIGIN/api/health"',
            'fsync_file "$PENDING_RECOVERY_RECORD"',
            'transition_transaction_status "$TX_STATUS" "recovery_committed_pending_activation"',
            "stop_service_and_verify",
            'remove_transaction_runtime_guard "$PREVIOUS_SERVICE_USER"',
            'systemctl --no-block start "$SERVICE"',
            'systemctl enable "$SERVICE"',
            'assert_standard_enabled_topology "$PREVIOUS_SERVICE_USER"',
            'fsync_systemd_enablement_state',
            'assert_standard_enabled_topology "$PREVIOUS_SERVICE_USER"',
            'systemctl is-active --quiet "$SERVICE"',
            'process_exec_argv "$FINAL_MAIN_PID"',
            'process_working_directory "$FINAL_MAIN_PID"',
            "validate_previous_runtime_provenance",
            'validate_final_publication_configuration',
            'validate_production_environment',
            'reconcile_or_publish_committed_record "$PENDING_RECOVERY_RECORD" "$RECOVERY_RECORD"',
            'mv -T -- "$TRANSACTION_FILE" "$ARCHIVED_TRANSACTION_RECORD"',
            'RECOVERY_ACTIVE="false"',
            'fsync_file "$ARCHIVED_TRANSACTION_RECORD"',
            'fsync_directory "$DEPLOYMENT_DIR"',
            'fsync_directory "$APP_ROOT"',
            'trap - EXIT INT TERM HUP',
        ],
        "recovery-pending-activation-enable-archive-publication-order",
    )

    final_publication_gate_cases = {
        DEPLOY_SCRIPT.name: assert_final_publication_gate_contract(
            deploy,
            DEPLOY_SCRIPT.name,
            ['publish_committed_record "$DEPLOYMENT_RECORD_TEMP" "$DEPLOYMENT_RECORD"'],
        ),
        ROLLBACK_SCRIPT.name: assert_final_publication_gate_contract(
            rollback,
            ROLLBACK_SCRIPT.name,
            ['publish_committed_record "$ROLLBACK_RECORD_TEMP" "$ROLLBACK_RECORD"'],
        ),
        RECOVERY_SCRIPT.name: assert_final_publication_gate_contract(
            recovery,
            RECOVERY_SCRIPT.name,
            [
                'reconcile_or_publish_committed_record "$ORIGINAL_PENDING_RECORD" "$ORIGINAL_FINAL_RECORD"',
                'reconcile_or_publish_committed_record "$ORIGINAL_PENDING_RECORD" "$ORIGINAL_FINAL_RECORD"',
                'reconcile_or_publish_committed_record "$PENDING_RECOVERY_RECORD" "$RECOVERY_RECORD"',
            ],
        ),
    }

    require_fragments(
        runner,
        [
            "def is_privileged_loader_key",
            '"BASHOPTS"',
            '("BASH_FUNC_", "LD_", "DYLD_", "PYTHON", "UVICORN_", "_UVICORN_")',
            '"GLIBC_TUNABLES"',
            '"OPENSSL_CONF"',
            '"OPENSSL_MODULES"',
            '"PATH": "/usr/sbin:/usr/bin"',
            "forbidden = sorted(key for key in loaded if is_privileged_loader_key(key))",
            "environment = dict(SAFE_BASE_ENVIRONMENT)",
            'if os.name == "nt":',
            "return subprocess.run(command, env=environment, check=False).returncode",
        ],
        "environment-runner-loader-safety",
    )
    require_fragments(
        validator_source,
        [
            "def privileged_loader_environment_names",
            '"UVICORN_",',
            '"_UVICORN_",',
            '"WEB_CONCURRENCY"',
            '"GLIBC_TUNABLES"',
            '"OPENSSL_CONF"',
            '"OPENSSL_MODULES"',
            '"privileged_loader_environment_safe": not privileged_loader_names',
        ],
        "ordinary-restart-runtime-loader-validator",
    )
    if "/usr/local/" in runner:
        raise AssertionError("environment runner retains an untrusted /usr/local search path")

    absolute_env_contract = {
        DEPLOY_SCRIPT.name: 0,
        ROLLBACK_SCRIPT.name: 0,
        RECOVERY_SCRIPT.name: 0,
    }
    for label, expected_count in absolute_env_contract.items():
        content = contents[label]
        actual_count = len(re.findall(r"(?m)^    /usr/bin/env \\$", content))
        if actual_count != expected_count:
            raise AssertionError(
                f"{label}: expected {expected_count} absolute /usr/bin/env launchers, "
                f"found {actual_count}"
            )
        if re.search(r"(?m)^    env \\$", content):
            raise AssertionError(f"{label}: PATH-resolved env launcher remains")

    forbidden = [
        'systemctl restart "$SERVICE"',
        "rm " + '-rf -- "$MANAGED_DROPIN_DIR"',
        'SERVICE_USER="root"',
        'LOG_DIR="$SHARED_DIR/deploy-logs"',
        'BACKUP_DIR="$SHARED_DIR/backups"',
        'DEPLOYMENT_DIR="$SHARED_DIR/deployments"',
    ]
    unsafe = {
        label: [fragment for fragment in forbidden if fragment in content]
        for label, content in contents.items()
    }
    unsafe = {label: values for label, values in unsafe.items() if values}
    if unsafe:
        raise AssertionError(json.dumps({"unsafe": unsafe}, ensure_ascii=False))

    for label, content in contents.items():
        direct_python = [
            fragment
            for fragment in ('python3 "', "exec setsid python3")
            if fragment in content
        ]
        direct_python.extend(
            line.strip()
            for line in content.splitlines()
            if "/usr/bin/python3 " in line and "/usr/bin/python3 -I -B -u " not in line
        )
        if direct_python:
            raise AssertionError(
                json.dumps(
                    {"label": label, "noncanonical_python_calls": direct_python},
                    ensure_ascii=False,
                )
            )
    if "shared_runtime_sha256" in rollback:
        raise AssertionError("obsolete legacy schema-v1 runtime validation remains in rollback")
    require_in_order(
        recovery,
        [
            'assert_trusted_code_file "$trusted_bootstrap"',
            'resolve_and_pin_trusted_command python3 PYTHON_BIN',
            'assert_trusted_code_file "$trusted_helper"',
        ],
        "recovery-command-trust-anchor-order",
    )
    if deploy.count('assert_release_tree_security "') < 4:
        raise AssertionError("deploy does not recheck immutable release security at each gate")

    with tempfile.TemporaryDirectory(prefix="deploy-contract-") as temporary:
        temporary_root = Path(temporary)
        uvicorn_environment_hijack = assert_uvicorn_app_dir_hijack_blocked(
            temporary_root
        )
        isolated_uvicorn_smoke = assert_isolated_uvicorn_cwd_import(temporary_root)
        privileged_entry_cases = assert_privileged_shell_entry_behavior(temporary_root)
        health_response_cases = assert_health_response_parser(
            bash, contents, check_production, temporary_root
        )
        login_redirect_cases = assert_login_redirect_parser(
            bash, contents, check_production, temporary_root
        )
        check_production_identity_cases = assert_check_production_identity(
            bash, check_production, temporary_root
        )
        candidate_cleanup_cases = assert_candidate_cleanup_behavior(
            bash, deploy, temporary_root
        )
        deploy_activation_fail_fast_cases = (
            assert_deploy_activation_schema_fail_fast_behavior(
                bash,
                deploy_activation_audit_source,
                deploy_activation_gate_source,
                deploy_activation_entry_block,
                temporary_root,
            )
        )
        release_tree_cwd_cases = assert_release_tree_cwd_behavior(
            bash, contents, temporary_root
        )
        trusted_path_acl_cases = assert_trusted_path_acl_behavior(
            bash, contents, temporary_root
        )
        env_file = temporary_root / "service.env"
        env_file.write_text("PROTOCOL_STUDIO_AUTH_ENABLED=true\n", encoding="utf-8")
        ambient = dict(os.environ)
        ambient["CODEX_DEPLOY_CONTRACT_SENTINEL"] = "must-not-leak"
        ambient["BASH_ENV"] = "must-not-leak"
        ambient["ENV"] = "must-not-leak"
        ambient["SHELLOPTS"] = "must-not-leak"
        ambient["BASHOPTS"] = "must-not-leak"
        ambient["BASH_FUNC_contract_probe%%"] = "() { :; }"
        child = subprocess.run(
            [
                sys.executable,
                str(ENV_RUNNER),
                "--env-file",
                str(env_file),
                "--",
                sys.executable,
                "-c",
                (
                    "import json,os; print(json.dumps({"
                    "'sentinel': 'CODEX_DEPLOY_CONTRACT_SENTINEL' in os.environ,"
                    "'path': os.environ.get('PATH'),"
                    "'auth': os.environ.get('PROTOCOL_STUDIO_AUTH_ENABLED'),"
                    "'startup_hooks': [name for name in ("
                    "'BASH_ENV','ENV','SHELLOPTS','BASHOPTS','BASH_FUNC_contract_probe%%') "
                    "if name in os.environ]}))"
                ),
            ],
            cwd=REPO_ROOT,
            env=ambient,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if child.returncode != 0:
            raise AssertionError(
                f"clean environment runner failed: exit={child.returncode} "
                f"stdout={child.stdout!r} stderr={child.stderr!r}"
            )
        child_env = json.loads(child.stdout)
        if child_env != {
            "sentinel": False,
            "path": "/usr/sbin:/usr/bin",
            "auth": "true",
            "startup_hooks": [],
        }:
            raise AssertionError(f"clean environment contract failed: {child_env}")

        runs = temporary_root / "runs"
        runs.mkdir()
        database = temporary_root / "security.sqlite3"
        database.write_bytes(b"fixture")
        validator_env = {
            "PATH": "/usr/sbin:/usr/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PROTOCOL_STUDIO_AUTH_ENABLED": "true",
            "PROTOCOL_STUDIO_COOKIE_SECURE": "true",
            "PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH": (
                "scrypt$n=16384,r=8,p=1,dk=32$"
                "AAECAwQFBgcICQoLDA0ODw$"
                "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
            ),
            "PROTOCOL_STUDIO_RUNS_ROOT": str(runs),
            "PROTOCOL_STUDIO_SECURITY_DB": str(database),
            "PROTOCOL_STUDIO_EXTERNAL_ORIGIN": "https://example.test",
            "PROTOCOL_STUDIO_ALLOWED_HOSTS": "example.test,127.0.0.1",
        }
        if os.name == "nt":
            for name in ("SystemRoot", "WINDIR"):
                if os.environ.get(name):
                    validator_env[name] = os.environ[name]
        validator_command = [
            sys.executable,
            "-I",
            "-B",
            "-u",
            str(ENV_VALIDATOR),
            "--shared-runs",
            str(runs),
            "--security-db",
            str(database),
            "--public-origin",
            "https://example.test",
            "--public-host",
            "example.test",
        ]
        valid = subprocess.run(
            validator_command,
            env=validator_env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        valid_report = json.loads(valid.stdout)
        if valid.returncode != 0 or valid_report["status"] != "passed" or valid_report["errors"] != []:
            raise AssertionError(f"valid production environment was rejected: {valid_report}")
        wildcard_env = {**validator_env, "PROTOCOL_STUDIO_ALLOWED_HOSTS": "example.test,127.0.0.1,*"}
        wildcard = subprocess.run(
            validator_command,
            env=wildcard_env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if wildcard.returncode == 0 or json.loads(wildcard.stdout)["status"] != "failed":
            raise AssertionError("wildcard allowed-host entry was not rejected")
        override_env = {
            **validator_env,
            "MCGS_FULL_CHAIN_RUNS_ROOT": str(temporary_root / "wrong-runs"),
        }
        override = subprocess.run(
            validator_command,
            env=override_env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if override.returncode == 0 or json.loads(override.stdout)["status"] != "failed":
            raise AssertionError("higher-priority MCGS runs override was not rejected")

    report = {
        "status": "passed",
        "suite": "deploy_text_contract",
        "scope": "shell syntax, embedded Python syntax, static contracts, and isolated behavior probes",
        "not_proven": [
            "real systemd transaction behavior",
            "power-loss persistence",
            "fault-injection recovery",
            "production deployment",
        ],
        "checks": {
            "bash_syntax": syntax_results,
            "python_heredoc_syntax": heredoc_counts,
            "shared_root_only_control_plane": True,
            "hash_locked_offline_dependencies": True,
            "durable_transaction_marker_text_contract": True,
            "disable_stop_switch_start_health_enable_order": True,
            "known_good_rollback_target_text_contract": True,
            "recovery_script_included": True,
            "marker_commit_order_text_contract": True,
            "three_shell_atomic_probe_only": True,
            "atomic_helper_replace_calls": 0,
            "three_shell_runtime_systemd_guard_contract": True,
            "ordinary_restart_helper_content_binding": True,
            "recovery_parser_internal_field_count": 26,
            "pending_activation_marker_retained_through_enable": True,
            "passed_record_publication_after_enablement": True,
            "final_publication_configuration_gate": final_publication_gate_cases,
            "marker_archive_after_passed_record_publication": True,
            "privileged_loader_rejection": True,
            "ambient_root_environment_isolation": True,
            "production_environment_negative_matrix": True,
            "private_umask_and_writable_path_reset": True,
            "canonical_isolated_control_python": True,
            "release_source_metadata_and_acl_boundary": True,
            "trusted_root_path_acl_static_contract": True,
            "trusted_root_path_acl_behavior": trusted_path_acl_cases,
            "trusted_command_source_contract": True,
            "control_state_acl_contract": True,
            "privileged_shell_entry_contract": privileged_entry_cases,
            "absolute_env_launcher_contract": absolute_env_contract,
            "strict_login_redirect_matrix": login_redirect_cases,
            "final_process_cwd_and_runtime_provenance_before_publication": True,
            "strict_health_response_matrix": health_response_cases,
            "check_production_identity_matrix": check_production_identity_cases,
            "candidate_cleanup_matrix": candidate_cleanup_cases,
            "deploy_activation_schema_fail_fast": {
                **deploy_activation_fail_fast_cases,
                "ordered_side_effect_anchors": deploy_activation_side_effect_anchors,
            },
            "curl_isolation_command_counts": curl_command_counts,
            "release_tree_service_user_cwd_matrix": release_tree_cwd_cases,
            "isolated_uvicorn_cwd_import_smoke": isolated_uvicorn_smoke,
            "uvicorn_environment_hijack_negative": uvicorn_environment_hijack,
            "uvicorn_cli_environment_coverage": uvicorn_cli_environment_coverage,
        },
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
