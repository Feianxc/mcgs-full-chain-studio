#!/usr/bin/env python3
"""Verify the fail-closed systemd EnvironmentFile subset used by deployment."""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_RUNNER = REPO_ROOT / "deploy" / "run_with_env.py"
ENV_VALIDATOR = REPO_ROOT / "deploy" / "validate_production_env.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from protocol_studio.security import (  # noqa: E402
    PASSWORD_DKLEN,
    PASSWORD_N,
    PASSWORD_P,
    PASSWORD_R,
    SecuritySettings,
    hash_password,
    verify_password,
)


def load_runner_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("deployment_environment_runner", ENV_RUNNER)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load deployment environment runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_validator_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "production_environment_validator",
        ENV_VALIDATOR,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load production environment validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def minimal_child_environment() -> dict[str, str]:
    environment = {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if os.name == "nt":
        for name in ("SystemRoot", "WINDIR"):
            if os.environ.get(name):
                environment[name] = os.environ[name]
    return environment


def run_validate_only(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ENV_RUNNER),
            "--env-file",
            str(path),
            "--validate-only",
            "--reject-privileged-loader-variables",
        ],
        cwd=REPO_ROOT,
        env=minimal_child_environment(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def assert_json_contract(report: object) -> dict[str, object]:
    if not isinstance(report, dict):
        raise AssertionError("validator report must be a JSON object")
    if type(report.get("schema_version")) is not int:
        raise AssertionError("validator schema_version must be an integer")
    if not isinstance(report.get("status"), str):
        raise AssertionError("validator status must be a string")
    if not isinstance(report.get("errors"), list):
        raise AssertionError("validator errors must always be an array")
    checks = report.get("checks")
    if not isinstance(checks, dict) or any(type(value) is not bool for value in checks.values()):
        raise AssertionError("validator checks must be a JSON object of booleans")
    return report


def run_library_overlay(
    project_root: Path,
    configured_resources: str | None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    environment = minimal_child_environment()
    if configured_resources is not None:
        environment["PROTOCOL_STUDIO_RESOURCES_ROOT"] = configured_resources
    child_code = """\
import json

payload = {
    "schema_version": 1,
    "status": "failed",
    "resources_root": None,
    "error_type": None,
    "error": None,
}
try:
    from mvp_generator.library import PROTOCOL_RESOURCES_ROOT
except Exception as exc:
    payload["error_type"] = type(exc).__name__
    payload["error"] = str(exc)
else:
    payload["status"] = "passed"
    payload["resources_root"] = str(PROTOCOL_RESOURCES_ROOT)
print(json.dumps(payload, sort_keys=True))
raise SystemExit(0 if payload["status"] == "passed" else 17)
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            child_code,
        ],
        cwd=project_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.stderr:
        raise AssertionError(
            "release overlay import wrote unexpected stderr: "
            f"exit={completed.returncode} stderr={completed.stderr!r}"
        )
    report = json.loads(completed.stdout)
    required_types = {
        "schema_version": int,
        "status": str,
    }
    if not isinstance(report, dict) or any(
        type(report.get(name)) is not expected
        for name, expected in required_types.items()
    ):
        raise AssertionError(f"release overlay report types are invalid: {report}")
    for name in ("resources_root", "error_type", "error"):
        if report.get(name) is not None and not isinstance(report.get(name), str):
            raise AssertionError(f"release overlay field {name} has an invalid type")
    return completed, report


def assert_fd_isolation_failure_is_redacted(runner: ModuleType) -> None:
    original_snapshot = runner._open_file_descriptors_from_proc
    original_close = runner.os.close
    secret_marker = "/root/private-lock-secret"

    def fail_close(_descriptor: int) -> None:
        raise OSError(1, "close denied", secret_marker)

    try:
        runner._open_file_descriptors_from_proc = lambda: {91}
        runner.os.close = fail_close
        try:
            runner.close_inherited_file_descriptors()
        except runner.FileDescriptorIsolationError as exc:
            diagnostic = str(exc)
            if diagnostic != runner.FD_ISOLATION_ERROR or secret_marker in diagnostic:
                raise AssertionError(
                    f"descriptor isolation failure was not redacted: {diagnostic!r}"
                ) from exc
        else:
            raise AssertionError("descriptor isolation close failure did not fail closed")
    finally:
        runner._open_file_descriptors_from_proc = original_snapshot
        runner.os.close = original_close


def run_linux_fd_isolation_contract(root: Path, environment_file: Path) -> dict[str, object]:
    if not sys.platform.startswith("linux"):
        return {
            "status": "not_run",
            "executed": False,
            "sentinel_fd": None,
            "proc_fd_verified": None,
            "lock_reacquired": None,
        }

    sentinel_fd = 9
    sentinel = root / "sentinel.lock"
    child_stdin = root / "fd-child.stdin"
    child_stdout = root / "fd-child.stdout"
    child_stderr = root / "fd-child.stderr"
    launcher_report = root / "fd-launcher.json"
    release_child = root / "fd-child.release"
    child_done = root / "fd-child.done"
    child_stdin.write_text("", encoding="utf-8")

    child_code = r"""
import json
import os
import sys
import time
from pathlib import Path

expected_fd = int(sys.argv[1])
expected_identity = (int(sys.argv[2]), int(sys.argv[3]))
release_path = Path(sys.argv[4])
done_path = Path(sys.argv[5])

try:
    os.fstat(expected_fd)
except OSError:
    expected_fd_open = False
else:
    expected_fd_open = True

matching_descriptors = []
open_descriptors = []
for entry in os.listdir("/proc/self/fd"):
    if not entry.isascii() or not entry.isdecimal():
        continue
    descriptor = int(entry)
    if descriptor <= 2:
        continue
    try:
        identity = os.fstat(descriptor)
    except OSError:
        continue
    open_descriptors.append(descriptor)
    if (identity.st_dev, identity.st_ino) == expected_identity:
        matching_descriptors.append(descriptor)

stdio_open = []
for descriptor in (0, 1, 2):
    try:
        os.fstat(descriptor)
    except OSError:
        stdio_open.append(False)
    else:
        stdio_open.append(True)

print(json.dumps({
    "expected_fd_open": expected_fd_open,
    "matching_sentinel_descriptors": matching_descriptors,
    "open_descriptors_above_stderr": open_descriptors,
    "stdio_open": stdio_open,
}, sort_keys=True), flush=True)

deadline = time.monotonic() + 10.0
while not release_path.exists() and time.monotonic() < deadline:
    time.sleep(0.02)
if not release_path.exists():
    raise SystemExit(92)
done_path.write_text("done\n", encoding="utf-8")
"""

    launcher_code = r"""
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

(
    runner,
    environment_file,
    sentinel_path,
    stdin_path,
    stdout_path,
    stderr_path,
    report_path,
    release_path,
    done_path,
    child_code,
) = sys.argv[1:]

sentinel_fd = 9
source_fd = os.open(sentinel_path, os.O_RDWR | os.O_CREAT, 0o600)
if source_fd != sentinel_fd:
    os.dup2(source_fd, sentinel_fd, inheritable=True)
    os.close(source_fd)
else:
    os.set_inheritable(sentinel_fd, True)
fcntl.flock(sentinel_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
identity = os.fstat(sentinel_fd)
inheritable = os.get_inheritable(sentinel_fd)
with (
    open(stdin_path, "rb") as child_stdin,
    open(stdout_path, "wb") as child_stdout,
    open(stderr_path, "wb") as child_stderr,
):
    child = subprocess.Popen(
        [
            sys.executable,
            runner,
            "--env-file",
            environment_file,
            "--",
            sys.executable,
            "-c",
            child_code,
            str(sentinel_fd),
            str(identity.st_dev),
            str(identity.st_ino),
            release_path,
            done_path,
        ],
        stdin=child_stdin,
        stdout=child_stdout,
        stderr=child_stderr,
        close_fds=True,
        pass_fds=(sentinel_fd,),
        start_new_session=True,
    )
payload = {
    "schema_version": 1,
    "child_pid": child.pid,
    "sentinel_fd": sentinel_fd,
    "sentinel_dev": identity.st_dev,
    "sentinel_ino": identity.st_ino,
    "inheritable": inheritable,
}
Path(report_path).write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
"""

    launcher = subprocess.run(
        [
            sys.executable,
            "-c",
            launcher_code,
            str(ENV_RUNNER),
            str(environment_file),
            str(sentinel),
            str(child_stdin),
            str(child_stdout),
            str(child_stderr),
            str(launcher_report),
            str(release_child),
            str(child_done),
            child_code,
        ],
        cwd=REPO_ROOT,
        env=minimal_child_environment(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if launcher.returncode != 0:
        raise AssertionError(
            f"fd launcher failed: exit={launcher.returncode} "
            f"stdout={launcher.stdout!r} stderr={launcher.stderr!r}"
        )

    launcher_payload = json.loads(launcher_report.read_text(encoding="utf-8"))
    required_launcher_types = {
        "schema_version": int,
        "child_pid": int,
        "sentinel_fd": int,
        "sentinel_dev": int,
        "sentinel_ino": int,
        "inheritable": bool,
    }
    if any(type(launcher_payload.get(key)) is not expected for key, expected in required_launcher_types.items()):
        raise AssertionError(f"fd launcher report types are invalid: {launcher_payload}")
    if launcher_payload["sentinel_fd"] != sentinel_fd or launcher_payload["inheritable"] is not True:
        raise AssertionError(f"fd launcher did not create inheritable fd 9: {launcher_payload}")

    child_pid = launcher_payload["child_pid"]
    try:
        deadline = time.monotonic() + 10.0
        ready_line = ""
        while time.monotonic() < deadline:
            if child_stdout.exists():
                output = child_stdout.read_text(encoding="utf-8")
                if "\n" in output:
                    ready_line = output.splitlines()[0]
                    break
            time.sleep(0.02)
        if not ready_line:
            stderr = child_stderr.read_text(encoding="utf-8") if child_stderr.exists() else ""
            raise AssertionError(f"fd child did not report readiness: stderr={stderr!r}")

        child_payload = json.loads(ready_line)
        if child_payload != {
            "expected_fd_open": False,
            "matching_sentinel_descriptors": [],
            "open_descriptors_above_stderr": [],
            "stdio_open": [True, True, True],
        }:
            raise AssertionError(f"inherited descriptors reached exec child: {child_payload}")

        os.kill(child_pid, 0)
        lock_probe = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import fcntl,os,sys; "
                    "fd=os.open(sys.argv[1],os.O_RDWR); "
                    "fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)"
                ),
                str(sentinel),
            ],
            cwd=REPO_ROOT,
            env=minimal_child_environment(),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if lock_probe.returncode != 0:
            raise AssertionError(
                "sentinel lock remained held after the launcher parent exited: "
                f"exit={lock_probe.returncode} stderr={lock_probe.stderr!r}"
            )
    finally:
        release_child.write_text("release\n", encoding="utf-8")

    deadline = time.monotonic() + 10.0
    while not child_done.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not child_done.is_file() or child_done.read_text(encoding="utf-8") != "done\n":
        raise AssertionError("fd inspection child did not exit its hold loop")

    return {
        "status": "passed",
        "executed": True,
        "sentinel_fd": sentinel_fd,
        "proc_fd_verified": True,
        "lock_reacquired": True,
    }


def main() -> int:
    runner = load_runner_module()
    validator = load_validator_module()
    expected_password_parameters = {
        "n": PASSWORD_N,
        "r": PASSWORD_R,
        "p": PASSWORD_P,
        "dk": PASSWORD_DKLEN,
    }
    actual_validator_parameters = {
        "n": validator.PASSWORD_N,
        "r": validator.PASSWORD_R,
        "p": validator.PASSWORD_P,
        "dk": validator.PASSWORD_DKLEN,
    }
    if actual_validator_parameters != expected_password_parameters:
        raise AssertionError(
            "production validator scrypt parameters drifted from security.hash_password"
        )
    for invalid_hash_type in (None, True, False, 1, 1.0, [], {}):
        if validator.valid_scrypt_password_hash(invalid_hash_type):
            raise AssertionError("non-string password hash passed validator")
    assert_fd_isolation_failure_is_redacted(runner)
    if runner.SAFE_BASE_ENVIRONMENT.get("PATH") != "/usr/sbin:/usr/bin":
        raise AssertionError("environment runner PATH is not restricted to trusted system roots")
    for key in ("BASHOPTS", "BASH_ENV", "ENV", "SHELLOPTS"):
        if not runner.is_privileged_loader_key(key):
            raise AssertionError(f"startup-control variable is not rejected: {key}")
    if not runner.is_privileged_loader_key("BASH_FUNC_contract_probe"):
        raise AssertionError("exported Bash function prefix is not rejected")
    for key in (
        "UVICORN_APP_DIR",
        "UVICORN_CONTRACT_SENTINEL",
        "_UVICORN_COMPLETE",
        "WEB_CONCURRENCY",
        "FORWARDED_ALLOW_IPS",
        "PYTHON_CONTRACT_SENTINEL",
    ):
        if not runner.is_privileged_loader_key(key):
            raise AssertionError(f"runtime startup-control variable is not rejected: {key}")
    positive_text = (
        """\
# hash comment
  ; semicolon comment
EMPTY=
BOOL=true
UNICODE=飞安
PLAIN_DOLLAR=$HOME
PASSWORD_HASH=scrypt$n=32768,r=8,p=1$salt$derived
SINGLE='two words'
DOUBLE="three words"
"""
        + "PADDED=   trimmed   \n"
        + """\
INLINE_HASH=value#literal
DUPLICATE=first
DUPLICATE=second
"""
    )
    expected_values = {
        "EMPTY": "",
        "BOOL": "true",
        "UNICODE": "飞安",
        "PLAIN_DOLLAR": "$HOME",
        "PASSWORD_HASH": "scrypt$n=32768,r=8,p=1$salt$derived",
        "SINGLE": "two words",
        "DOUBLE": "three words",
        "PADDED": "trimmed",
        "INLINE_HASH": "value#literal",
        "DUPLICATE": "second",
    }
    physical_line_continuation = "VALUE=first" + chr(92) + "\nsecond\n"
    negative_cases = {
        "export-prefix": ("export VALUE=secret-marker\n", "export prefixes"),
        "indented-export-prefix": ("  export\tVALUE=secret-marker\n", "export prefixes"),
        "line-continuation": (physical_line_continuation, "backslash escapes"),
        "backslash-escape": ("VALUE=first\\ second\n", "backslash escapes"),
        "unterminated-single-quote": ("VALUE='open\n", "unterminated quoting"),
        "unterminated-double-quote": ('VALUE="open\n', "unterminated quoting"),
        "quoted-tail": ('VALUE="closed"tail\n', "partial or unterminated quoting"),
        "embedded-partial-quote": ('VALUE=pre"mid"\n', "partial quoting"),
        "unquoted-whitespace": ("VALUE=two words\n", "unquoted whitespace"),
        "command-substitution": ("VALUE=$(id)\n", "shell syntax"),
        "parameter-expansion": ("VALUE=${HOME}\n", "shell syntax"),
        "backtick-substitution": ("VALUE=`id`\n", "shell syntax"),
        "command-chain": ("VALUE=first&&second\n", "shell syntax"),
        "pipe": ("VALUE=first|second\n", "shell syntax"),
        "redirect": ("VALUE=>output\n", "shell syntax"),
        "statement-separator": ("VALUE=first;second\n", "shell syntax"),
        "background-operator": ("VALUE=first&\n", "shell syntax"),
        "key-whitespace": ("VALUE =data\n", "whitespace around environment keys"),
        "non-assignment-statement": ("source other.env\n", "expected KEY=VALUE"),
        "control-character": ("VALUE=bad\x01value\n", "control characters"),
        "nul": ("VALUE=bad\x00value\n", "invalid Unicode character"),
        "bom": ("\ufeffVALUE=data\n", "invalid Unicode character"),
        "unicode-noncharacter": ("VALUE=bad\ufdd0value\n", "invalid Unicode character"),
    }

    with tempfile.TemporaryDirectory(prefix="environment-file-contract-") as temporary:
        root = Path(temporary)
        positive_file = root / "positive.env"
        positive_file.write_bytes(positive_text.encode("utf-8"))
        loaded = runner.load_environment(positive_file)
        if loaded != expected_values:
            raise AssertionError(
                json.dumps(
                    {"expected": expected_values, "actual": loaded},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        positive_cli = run_validate_only(positive_file)
        if positive_cli.returncode != 0 or positive_cli.stdout or positive_cli.stderr:
            raise AssertionError(
                f"valid EnvironmentFile rejected: exit={positive_cli.returncode} "
                f"stdout={positive_cli.stdout!r} stderr={positive_cli.stderr!r}"
            )

        for label, (content, expected_error) in negative_cases.items():
            path = root / f"negative-{label}.env"
            path.write_bytes(content.encode("utf-8"))
            try:
                runner.load_environment(path)
            except ValueError as exc:
                if expected_error not in str(exc):
                    raise AssertionError(
                        f"{label}: unexpected parser error {exc!s}; expected {expected_error!r}"
                    ) from exc
            else:
                raise AssertionError(f"{label}: invalid EnvironmentFile was accepted")
            completed = run_validate_only(path)
            if completed.returncode == 0 or expected_error not in completed.stderr:
                raise AssertionError(
                    f"{label}: CLI did not fail closed: exit={completed.returncode} "
                    f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
                )
            if "secret-marker" in completed.stdout or "secret-marker" in completed.stderr:
                raise AssertionError(f"{label}: rejected value leaked into diagnostics")

        invalid_utf8 = root / "negative-invalid-utf8.env"
        invalid_utf8.write_bytes(b"VALUE=\xff\n")
        invalid_utf8_result = run_validate_only(invalid_utf8)
        if invalid_utf8_result.returncode == 0:
            raise AssertionError("invalid UTF-8 EnvironmentFile was accepted")

        privileged_loader_cases = {
            "path": "PATH=/tmp\n",
            "bash-env": "BASH_ENV=/tmp/startup-hook\n",
            "env": "ENV=/tmp/startup-hook\n",
            "cdpath": "CDPATH=/tmp\n",
            "globignore": "GLOBIGNORE=payload\n",
            "shellopts": "SHELLOPTS=xtrace\n",
            "bashopts": "BASHOPTS=extdebug\n",
            "bash-function-prefix": "BASH_FUNC_contract_probe=payload\n",
            "pythonpath": "PYTHONPATH=/tmp\n",
            "pythonhome": "PYTHONHOME=/tmp\n",
            "pythoninspect": "PYTHONINSPECT=1\n",
            "pythonstartup": "PYTHONSTARTUP=/tmp/hook.py\n",
            "python-prefix": "PYTHON_CONTRACT_SENTINEL=payload\n",
            "ld-preload": "LD_PRELOAD=/tmp/payload.so\n",
            "ld-library-path": "LD_LIBRARY_PATH=/tmp\n",
            "ld-audit": "LD_AUDIT=/tmp/audit.so\n",
            "ld-prefix": "LD_CONTRACT_SENTINEL=payload\n",
            "dyld-prefix": "DYLD_CONTRACT_SENTINEL=payload\n",
            "gconv-path": "GCONV_PATH=/tmp\n",
            "glibc-tunables": "GLIBC_TUNABLES=glibc.malloc.check=3\n",
            "openssl-conf": "OPENSSL_CONF=/tmp/openssl.cnf\n",
            "openssl-modules": "OPENSSL_MODULES=/tmp/modules\n",
            "uvicorn-app-dir": "UVICORN_APP_DIR=/tmp/external-app\n",
            "uvicorn-env-file": "UVICORN_ENV_FILE=/tmp/uvicorn.env\n",
            "uvicorn-reload": "UVICORN_RELOAD=true\n",
            "uvicorn-factory": "UVICORN_FACTORY=true\n",
            "uvicorn-workers": "UVICORN_WORKERS=9\n",
            "uvicorn-prefix": "UVICORN_CONTRACT_SENTINEL=payload\n",
            "uvicorn-completion": "_UVICORN_COMPLETE=bash_source\n",
            "web-concurrency": "WEB_CONCURRENCY=9\n",
            "forwarded-allow-ips": "FORWARDED_ALLOW_IPS=*\n",
        }
        for label, content in privileged_loader_cases.items():
            privileged = root / f"negative-loader-{label}.env"
            privileged.write_text(content, encoding="utf-8")
            privileged_result = run_validate_only(privileged)
            if (
                privileged_result.returncode == 0
                or "privileged loader variables" not in privileged_result.stderr
            ):
                raise AssertionError(f"privileged loader variable was accepted: {label}")

        clean_environment_file = root / "clean.env"
        clean_environment_file.write_text(
            "PROTOCOL_STUDIO_AUTH_ENABLED=true\nLITERAL_DOLLAR=$HOME\n",
            encoding="utf-8",
        )
        ambient = dict(os.environ)
        ambient["CODEX_ENVIRONMENT_CONTRACT_SENTINEL"] = "must-not-leak"
        ambient["BASH_ENV"] = "must-not-leak"
        ambient["ENV"] = "must-not-leak"
        ambient["SHELLOPTS"] = "must-not-leak"
        ambient["BASHOPTS"] = "must-not-leak"
        ambient["BASH_FUNC_contract_probe%%"] = "() { :; }"
        clean_child = subprocess.run(
            [
                sys.executable,
                str(ENV_RUNNER),
                "--env-file",
                str(clean_environment_file),
                "--",
                sys.executable,
                "-c",
                (
                    "import json,os; print(json.dumps({"
                    "'sentinel': 'CODEX_ENVIRONMENT_CONTRACT_SENTINEL' in os.environ,"
                    "'path': os.environ.get('PATH'),"
                    "'literal_dollar': os.environ.get('LITERAL_DOLLAR'),"
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
        if clean_child.returncode != 0:
            raise AssertionError(
                f"clean environment launch failed: exit={clean_child.returncode} "
                f"stdout={clean_child.stdout!r} stderr={clean_child.stderr!r}"
            )
        clean_report = json.loads(clean_child.stdout)
        if clean_report != {
            "sentinel": False,
            "path": "/usr/sbin:/usr/bin",
            "literal_dollar": "$HOME",
            "startup_hooks": [],
        }:
            raise AssertionError(f"clean environment contract failed: {clean_report}")

        linux_fd_isolation = run_linux_fd_isolation_contract(root, clean_environment_file)

        nonzero_child = subprocess.run(
            [
                sys.executable,
                str(ENV_RUNNER),
                "--env-file",
                str(clean_environment_file),
                "--",
                sys.executable,
                "-c",
                (
                    "import sys; "
                    "payload=sys.stdin.readline().rstrip('\\n'); "
                    "print('stdout:' + payload, flush=True); "
                    "print('stderr:preserved', file=sys.stderr, flush=True); "
                    "raise SystemExit(7)"
                ),
            ],
            cwd=REPO_ROOT,
            env=minimal_child_environment(),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            input="stdio-payload\n",
        )
        if (
            nonzero_child.returncode != 7
            or nonzero_child.stdout != "stdout:stdio-payload\n"
            or nonzero_child.stderr != "stderr:preserved\n"
        ):
            raise AssertionError(
                "child stdio or exit code was not propagated: "
                f"exit={nonzero_child.returncode} stdout={nonzero_child.stdout!r} "
                f"stderr={nonzero_child.stderr!r}"
            )

        runs = root / "runs"
        runs.mkdir()
        database = root / "security.sqlite3"
        database.write_bytes(b"fixture")
        fixture_password = secrets.token_urlsafe(32)
        fixture_password_hash = hash_password(
            fixture_password,
            salt=bytes(range(16)),
        )
        if not verify_password(fixture_password, fixture_password_hash):
            raise AssertionError("real password verifier rejected the synthetic fixture hash")
        if not validator.valid_scrypt_password_hash(fixture_password_hash):
            raise AssertionError("production validator rejected hash_password output")
        legacy_false_positive_hash = "scrypt$n=32768,r=8,p=1$salt$derived"
        if verify_password(fixture_password, legacy_false_positive_hash):
            raise AssertionError("legacy malformed fixture unexpectedly verified")
        validator_values = {
            "PROTOCOL_STUDIO_AUTH_ENABLED": "true",
            "PROTOCOL_STUDIO_COOKIE_SECURE": "true",
            "PROTOCOL_STUDIO_ADMIN_USERNAME": "FIXTURE.ADMIN",
            "PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH": fixture_password_hash,
            "PROTOCOL_STUDIO_ADMIN_FORCE_PASSWORD_CHANGE": "true",
            "PROTOCOL_STUDIO_RUNS_ROOT": runs.as_posix(),
            "PROTOCOL_STUDIO_SECURITY_DB": database.as_posix(),
            "PROTOCOL_STUDIO_EXTERNAL_ORIGIN": "https://example.test",
            "PROTOCOL_STUDIO_ALLOWED_HOSTS": "example.test,127.0.0.1",
            "PROTOCOL_STUDIO_SESSION_IDLE_SECONDS": "43200",
            "PROTOCOL_STUDIO_SESSION_ABSOLUTE_SECONDS": "604800",
        }
        production_file = root / "production.env"
        production_file.write_text(
            "".join(f"{name}={value}\n" for name, value in validator_values.items()),
            encoding="utf-8",
        )
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

        def run_production_validator(
            values: dict[str, str],
            *,
            expected_runs: str | None = None,
            expected_database: str | None = None,
            public_origin: str = "https://example.test",
            public_host: str = "example.test",
            label: str,
        ) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
            case_file = root / f"validator-{label}.env"
            case_file.write_text(
                "".join(f"{name}={value}\n" for name, value in values.items()),
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(ENV_RUNNER),
                "--env-file",
                str(case_file),
                "--",
                sys.executable,
                "-I",
                "-B",
                "-u",
                str(ENV_VALIDATOR),
                "--shared-runs",
                expected_runs if expected_runs is not None else str(runs),
                "--security-db",
                expected_database if expected_database is not None else str(database),
                "--public-origin",
                public_origin,
                "--public-host",
                public_host,
            ]
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=minimal_child_environment(),
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if not completed.stdout:
                raise AssertionError(
                    f"{label}: production validator emitted no JSON: "
                    f"exit={completed.returncode} stderr={completed.stderr!r}"
                )
            return completed, assert_json_contract(json.loads(completed.stdout))

        integrated_validator = subprocess.run(
            [
                sys.executable,
                str(ENV_RUNNER),
                "--env-file",
                str(production_file),
                "--",
                *validator_command,
            ],
            cwd=REPO_ROOT,
            env=minimal_child_environment(),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if integrated_validator.returncode != 0:
            raise AssertionError(
                f"valid production environment rejected: exit={integrated_validator.returncode} "
                f"stdout={integrated_validator.stdout!r} stderr={integrated_validator.stderr!r}"
            )
        valid_report = assert_json_contract(json.loads(integrated_validator.stdout))
        if valid_report["status"] != "passed" or valid_report["errors"] != []:
            raise AssertionError(f"unexpected valid production report: {valid_report}")
        valid_checks = valid_report["checks"]
        if (
            not isinstance(valid_checks, dict)
            or valid_checks.get("environment_values_safe") is not True
            or valid_checks.get("packaged_protocol_resources_enforced") is not True
            or valid_checks.get("privileged_loader_environment_safe") is not True
            or valid_checks.get("admin_username_valid") is not True
            or valid_checks.get("password_hash_valid") is not True
            or valid_checks.get("force_password_change_valid") is not True
            or valid_checks.get("session_idle_seconds_valid") is not True
            or valid_checks.get("session_absolute_seconds_valid") is not True
            or valid_checks.get("session_lifetime_order_valid") is not True
        ):
            raise AssertionError("valid production environment checks were not reported")

        with patch.dict(os.environ, validator_values, clear=True):
            security_settings = SecuritySettings.from_env(REPO_ROOT)
        expected_security_settings = {
            "enabled": True,
            "database_path": database.resolve(),
            "admin_username": "FIXTURE.ADMIN",
            "bootstrap_password_hash": fixture_password_hash,
            "force_password_change": True,
            "cookie_secure": True,
            "session_idle_seconds": 43200,
            "session_absolute_seconds": 604800,
            "allowed_hosts": ("example.test", "127.0.0.1"),
            "external_origin": "https://example.test",
        }
        actual_security_settings = {
            name: getattr(security_settings, name)
            for name in expected_security_settings
        }
        if actual_security_settings != expected_security_settings:
            raise AssertionError(
                "validator-positive fixture does not construct the expected SecuritySettings"
            )

        force_false_values = {
            **validator_values,
            "PROTOCOL_STUDIO_ADMIN_FORCE_PASSWORD_CHANGE": "false",
        }
        force_false, force_false_report = run_production_validator(
            force_false_values,
            label="force-password-change-false",
        )
        if (
            force_false.returncode != 0
            or force_false_report["status"] != "passed"
            or force_false_report["checks"].get("force_password_change_valid")
            is not True
        ):
            raise AssertionError(
                f"valid false force-password-change flag was rejected: {force_false_report}"
            )
        with patch.dict(os.environ, force_false_values, clear=True):
            if SecuritySettings.from_env(REPO_ROOT).force_password_change is not False:
                raise AssertionError("SecuritySettings did not consume false force-change flag")

        scheme, params_text, salt_text, digest_text = fixture_password_hash.split("$")
        if scheme != "scrypt":
            raise AssertionError("synthetic fixture hash has the wrong scheme")

        def replace_hash_parameter(name: str, value: str) -> str:
            replaced = []
            for item in params_text.split(","):
                key, _current = item.split("=", 1)
                replaced.append(f"{key}={value}" if key == name else item)
            return ",".join(replaced)

        def encode_fixture_bytes(value: bytes) -> str:
            return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

        password_hash_cases = {
            "empty": "",
            "legacy-false-positive": legacy_false_positive_hash,
            "wrong-scheme": f"pbkdf2${params_text}${salt_text}${digest_text}",
            "missing-dk": (
                f"scrypt$n={PASSWORD_N},r={PASSWORD_R},p={PASSWORD_P}"
                f"${salt_text}${digest_text}"
            ),
            "duplicate-dk": (
                f"scrypt${params_text},dk={PASSWORD_DKLEN}${salt_text}${digest_text}"
            ),
            "unknown-parameter": (
                f"scrypt$n={PASSWORD_N},r={PASSWORD_R},p={PASSWORD_P},x={PASSWORD_DKLEN}"
                f"${salt_text}${digest_text}"
            ),
            "noninteger-n": (
                f"scrypt${replace_hash_parameter('n', 'true')}${salt_text}${digest_text}"
            ),
            "float-r": (
                f"scrypt${replace_hash_parameter('r', '8.0')}${salt_text}${digest_text}"
            ),
            "negative-p": (
                f"scrypt${replace_hash_parameter('p', '-1')}${salt_text}${digest_text}"
            ),
            "noncanonical-n": (
                f"scrypt${replace_hash_parameter('n', '016384')}${salt_text}${digest_text}"
            ),
            "wrong-n": (
                f"scrypt${replace_hash_parameter('n', str(PASSWORD_N * 2))}"
                f"${salt_text}${digest_text}"
            ),
            "wrong-r": (
                f"scrypt${replace_hash_parameter('r', str(PASSWORD_R + 1))}"
                f"${salt_text}${digest_text}"
            ),
            "wrong-p": (
                f"scrypt${replace_hash_parameter('p', str(PASSWORD_P + 1))}"
                f"${salt_text}${digest_text}"
            ),
            "wrong-dk": (
                f"scrypt${replace_hash_parameter('dk', str(PASSWORD_DKLEN - 1))}"
                f"${salt_text}${digest_text}"
            ),
            "huge-n": (
                f"scrypt${replace_hash_parameter('n', str(2**63))}"
                f"${salt_text}${digest_text}"
            ),
            "salt-decode-failure": f"scrypt${params_text}$***${digest_text}",
            "salt-length": (
                f"scrypt${params_text}${encode_fixture_bytes(bytes(15))}${digest_text}"
            ),
            "digest-decode-failure": f"scrypt${params_text}${salt_text}$***",
            "digest-length": (
                f"scrypt${params_text}${salt_text}${encode_fixture_bytes(bytes(31))}"
            ),
            "padded-digest": f"scrypt${params_text}${salt_text}${digest_text}=",
            "extra-component": f"{fixture_password_hash}$extra",
        }
        for label, malformed_hash in password_hash_cases.items():
            if validator.valid_scrypt_password_hash(malformed_hash):
                raise AssertionError(f"malformed hash passed direct validator: {label}")
            malformed_values = {
                **validator_values,
                "PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH": malformed_hash,
            }
            rejected_hash, hash_report = run_production_validator(
                malformed_values,
                label=f"password-hash-{label}",
            )
            if (
                rejected_hash.returncode == 0
                or hash_report["status"] != "failed"
                or hash_report["checks"].get("password_hash_present") is not False
                or hash_report["checks"].get("password_hash_valid") is not False
                or "bootstrap password hash is missing or invalid"
                not in hash_report["errors"]
            ):
                raise AssertionError(
                    f"malformed bootstrap hash was accepted: {label}: {hash_report}"
                )
            serialized_hash_report = json.dumps(hash_report, ensure_ascii=False)
            if (
                fixture_password in serialized_hash_report
                or (malformed_hash and malformed_hash in serialized_hash_report)
            ):
                raise AssertionError(
                    f"password material leaked into validator diagnostics: {label}"
                )

        security_settings_cases = {
            "auth-boolean": (
                {"PROTOCOL_STUDIO_AUTH_ENABLED": "truthy"},
                "authentication flag is invalid",
                "authentication_flag_valid",
            ),
            "cookie-boolean": (
                {"PROTOCOL_STUDIO_COOKIE_SECURE": "2"},
                "secure-cookie flag is invalid",
                "secure_cookie_flag_valid",
            ),
            "force-change-boolean": (
                {"PROTOCOL_STUDIO_ADMIN_FORCE_PASSWORD_CHANGE": "sometimes"},
                "administrator force-password-change flag is invalid",
                "force_password_change_valid",
            ),
            "force-change-empty": (
                {"PROTOCOL_STUDIO_ADMIN_FORCE_PASSWORD_CHANGE": ""},
                "administrator force-password-change flag is invalid",
                "force_password_change_valid",
            ),
            "username-short": (
                {"PROTOCOL_STUDIO_ADMIN_USERNAME": "A"},
                "administrator username is missing or invalid",
                "admin_username_valid",
            ),
            "username-character": (
                {"PROTOCOL_STUDIO_ADMIN_USERNAME": "ADMIN/ROOT"},
                "administrator username is missing or invalid",
                "admin_username_valid",
            ),
            "username-long": (
                {"PROTOCOL_STUDIO_ADMIN_USERNAME": "A" * 65},
                "administrator username is missing or invalid",
                "admin_username_valid",
            ),
            "idle-noninteger": (
                {"PROTOCOL_STUDIO_SESSION_IDLE_SECONDS": "not-an-integer"},
                "session idle seconds is missing, noncanonical or out of range",
                "session_idle_seconds_valid",
            ),
            "idle-boolean": (
                {"PROTOCOL_STUDIO_SESSION_IDLE_SECONDS": "true"},
                "session idle seconds is missing, noncanonical or out of range",
                "session_idle_seconds_valid",
            ),
            "idle-float": (
                {"PROTOCOL_STUDIO_SESSION_IDLE_SECONDS": "900.0"},
                "session idle seconds is missing, noncanonical or out of range",
                "session_idle_seconds_valid",
            ),
            "idle-below-minimum": (
                {"PROTOCOL_STUDIO_SESSION_IDLE_SECONDS": "899"},
                "session idle seconds is missing, noncanonical or out of range",
                "session_idle_seconds_valid",
            ),
            "idle-leading-zero": (
                {"PROTOCOL_STUDIO_SESSION_IDLE_SECONDS": "0900"},
                "session idle seconds is missing, noncanonical or out of range",
                "session_idle_seconds_valid",
            ),
            "idle-overflow": (
                {
                    "PROTOCOL_STUDIO_SESSION_IDLE_SECONDS": str(
                        validator.SESSION_MAX_SECONDS + 1
                    )
                },
                "session idle seconds is missing, noncanonical or out of range",
                "session_idle_seconds_valid",
            ),
            "idle-python-digit-limit": (
                {"PROTOCOL_STUDIO_SESSION_IDLE_SECONDS": "9" * 5000},
                "session idle seconds is missing, noncanonical or out of range",
                "session_idle_seconds_valid",
            ),
            "absolute-noninteger": (
                {"PROTOCOL_STUDIO_SESSION_ABSOLUTE_SECONDS": "not-an-integer"},
                "session absolute seconds is missing, noncanonical or out of range",
                "session_absolute_seconds_valid",
            ),
            "absolute-below-minimum": (
                {"PROTOCOL_STUDIO_SESSION_ABSOLUTE_SECONDS": "3599"},
                "session absolute seconds is missing, noncanonical or out of range",
                "session_absolute_seconds_valid",
            ),
            "absolute-overflow": (
                {
                    "PROTOCOL_STUDIO_SESSION_ABSOLUTE_SECONDS": str(
                        validator.SESSION_MAX_SECONDS + 1
                    )
                },
                "session absolute seconds is missing, noncanonical or out of range",
                "session_absolute_seconds_valid",
            ),
            "session-order": (
                {
                    "PROTOCOL_STUDIO_SESSION_IDLE_SECONDS": "7200",
                    "PROTOCOL_STUDIO_SESSION_ABSOLUTE_SECONDS": "3600",
                },
                "session idle seconds must not exceed session absolute seconds",
                "session_lifetime_order_valid",
            ),
        }
        for label, (updates, expected_error, expected_false_check) in (
            security_settings_cases.items()
        ):
            invalid_settings_values = {**validator_values, **updates}
            rejected_settings, settings_report = run_production_validator(
                invalid_settings_values,
                label=f"security-settings-{label}",
            )
            if (
                rejected_settings.returncode == 0
                or settings_report["status"] != "failed"
                or expected_error not in settings_report["errors"]
                or settings_report["checks"].get(expected_false_check) is not False
            ):
                raise AssertionError(
                    f"invalid security setting was accepted: {label}: {settings_report}"
                )
            serialized_settings_report = json.dumps(
                settings_report,
                ensure_ascii=False,
            )
            if (
                fixture_password in serialized_settings_report
                or fixture_password_hash in serialized_settings_report
            ):
                raise AssertionError(
                    f"invalid security setting leaked into diagnostics: {label}"
                )

        with patch.dict(
            os.environ,
            {
                **validator_values,
                "PROTOCOL_STUDIO_SESSION_IDLE_SECONDS": "not-an-integer",
            },
            clear=True,
        ):
            try:
                SecuritySettings.from_env(REPO_ROOT)
            except ValueError:
                pass
            else:
                raise AssertionError(
                    "SecuritySettings unexpectedly accepted a non-integer session value"
                )

        direct_validator_base = {
            "PATH": "/usr/sbin:/usr/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            **validator_values,
        }
        if os.name == "nt":
            for name in ("SystemRoot", "WINDIR"):
                if os.environ.get(name):
                    direct_validator_base[name] = os.environ[name]
        runtime_loader_names = (
            "PATH",
            "PYTHONPATH",
            "PYTHONHOME",
            "PYTHONINSPECT",
            "PYTHONSTARTUP",
            "PYTHON_CONTRACT_SENTINEL",
            "BASH_ENV",
            "ENV",
            "BASHOPTS",
            "SHELLOPTS",
            "CDPATH",
            "GLOBIGNORE",
            "BASH_FUNC_contract_probe",
            "LD_PRELOAD",
            "LD_LIBRARY_PATH",
            "LD_AUDIT",
            "LD_CONTRACT_SENTINEL",
            "DYLD_CONTRACT_SENTINEL",
            "GCONV_PATH",
            "GLIBC_TUNABLES",
            "OPENSSL_CONF",
            "OPENSSL_MODULES",
            "UVICORN_APP_DIR",
            "UVICORN_ENV_FILE",
            "UVICORN_RELOAD",
            "UVICORN_FACTORY",
            "UVICORN_WORKERS",
            "UVICORN_CONTRACT_SENTINEL",
            "_UVICORN_COMPLETE",
            "WEB_CONCURRENCY",
            "FORWARDED_ALLOW_IPS",
        )
        for loader_name in runtime_loader_names:
            loader_environment = dict(direct_validator_base)
            loader_environment[loader_name] = ""
            rejected_loader = subprocess.run(
                validator_command,
                cwd=REPO_ROOT,
                env=loader_environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            rejected_report = assert_json_contract(json.loads(rejected_loader.stdout))
            if (
                rejected_loader.returncode == 0
                or rejected_report["status"] != "failed"
                or rejected_report["checks"].get(
                    "privileged_loader_environment_safe"
                )
                is not False
                or loader_name.casefold()
                not in str(rejected_report["errors"][0]).casefold()
            ):
                raise AssertionError(
                    f"runtime loader variable was not rejected by key presence: "
                    f"{loader_name}: {rejected_report}"
                )
            serialized_loader_report = json.dumps(
                rejected_report, ensure_ascii=False
            )
            if "secret-loader-value" in serialized_loader_report:
                raise AssertionError("runtime loader diagnostic disclosed a value")

        for safe_name in ("PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"):
            wrong_safe_environment = dict(direct_validator_base)
            wrong_safe_environment[safe_name] = "wrong"
            wrong_safe = subprocess.run(
                validator_command,
                cwd=REPO_ROOT,
                env=wrong_safe_environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            wrong_safe_report = assert_json_contract(json.loads(wrong_safe.stdout))
            if (
                wrong_safe.returncode == 0
                or wrong_safe_report["checks"].get(
                    "privileged_loader_environment_safe"
                )
                is not False
            ):
                raise AssertionError(
                    f"safe runtime variable accepted a noncanonical value: {safe_name}"
                )

        public_origin_cases = {
            "ip": ("https://127.0.0.1", "127.0.0.1", "https://127.0.0.1"),
            "explicit-port": (
                "https://example.test:443",
                "example.test",
                "https://example.test:443",
            ),
            "path": (
                "https://example.test/path",
                "example.test",
                "https://example.test/path",
            ),
            "query": (
                "https://example.test?query=1",
                "example.test",
                "https://example.test?query=1",
            ),
            "fragment": (
                "https://example.test#fragment",
                "example.test",
                "https://example.test#fragment",
            ),
            "credentials": (
                "https://user@example.test",
                "example.test",
                "https://user@example.test",
            ),
            "uppercase": (
                "https://Example.test",
                "Example.test",
                "https://Example.test",
            ),
            "trailing-slash": (
                "https://example.test/",
                "example.test",
                "https://example.test/",
            ),
            "external-origin-mismatch": (
                "https://example.test",
                "example.test",
                "https://mismatch.test",
            ),
        }
        for label, (origin, host, external_origin) in public_origin_cases.items():
            origin_values = {
                **validator_values,
                "PROTOCOL_STUDIO_EXTERNAL_ORIGIN": external_origin,
                "PROTOCOL_STUDIO_ALLOWED_HOSTS": f"{host},127.0.0.1",
            }
            rejected_origin, origin_report = run_production_validator(
                origin_values,
                public_origin=origin,
                public_host=host,
                label=f"origin-{label}",
            )
            if rejected_origin.returncode == 0 or origin_report["status"] != "failed":
                raise AssertionError(
                    f"invalid public origin was accepted: {label}: {origin_report}"
                )
            if label == "external-origin-mismatch":
                expected_error = "external origin does not match the production origin"
            else:
                expected_error = (
                    "public origin must be a canonical lowercase HTTPS DNS origin "
                    "for the public host"
                )
            if expected_error not in origin_report["errors"]:
                raise AssertionError(
                    f"invalid public origin had the wrong failure: {label}: {origin_report}"
                )

        real_runs_target = root / "real-runs-target"
        real_runs_target.mkdir()
        runs_target_link = root / "runs-target-link"
        real_database_target = root / "real-database-target.sqlite3"
        real_database_target.write_bytes(b"fixture")
        database_target_link = root / "database-target-link.sqlite3"
        real_runs_ancestor = root / "real-runs-ancestor"
        (real_runs_ancestor / "runs").mkdir(parents=True)
        runs_ancestor_link = root / "runs-ancestor-link"
        real_database_ancestor = root / "real-database-ancestor"
        real_database_ancestor.mkdir()
        (real_database_ancestor / "security.sqlite3").write_bytes(b"fixture")
        database_ancestor_link = root / "database-ancestor-link"
        try:
            runs_target_link.symlink_to(real_runs_target, target_is_directory=True)
            database_target_link.symlink_to(real_database_target)
            runs_ancestor_link.symlink_to(real_runs_ancestor, target_is_directory=True)
            database_ancestor_link.symlink_to(
                real_database_ancestor, target_is_directory=True
            )
        except OSError as exc:
            raise AssertionError(
                "filesystem symlink capability is required for production path identity tests"
            ) from exc

        path_identity_cases = {
            "runs-target-symlink": (
                runs_target_link.as_posix(),
                database.as_posix(),
                "shared runs path must be an existing non-symlink directory with no symlink ancestors",
            ),
            "database-target-symlink": (
                runs.as_posix(),
                database_target_link.as_posix(),
                "shared security database must be an existing non-symlink regular file with no symlink ancestors",
            ),
            "runs-ancestor-symlink": (
                (runs_ancestor_link / "runs").as_posix(),
                database.as_posix(),
                "shared runs path must be an existing non-symlink directory with no symlink ancestors",
            ),
            "database-ancestor-symlink": (
                runs.as_posix(),
                (database_ancestor_link / "security.sqlite3").as_posix(),
                "shared security database must be an existing non-symlink regular file with no symlink ancestors",
            ),
            "runs-lexical-noncanonical": (
                f"{runs.as_posix()}/../{runs.name}",
                database.as_posix(),
                "expected shared paths must be canonical absolute paths",
            ),
            "database-lexical-noncanonical": (
                runs.as_posix(),
                f"{database.parent.as_posix()}/nested/../{database.name}",
                "expected shared paths must be canonical absolute paths",
            ),
        }
        for label, (runs_value, database_value, expected_error) in path_identity_cases.items():
            path_values = {
                **validator_values,
                "PROTOCOL_STUDIO_RUNS_ROOT": runs_value,
                "PROTOCOL_STUDIO_SECURITY_DB": database_value,
            }
            rejected_path, path_report = run_production_validator(
                path_values,
                expected_runs=runs_value,
                expected_database=database_value,
                label=f"path-{label}",
            )
            if (
                rejected_path.returncode == 0
                or path_report["status"] != "failed"
                or expected_error not in path_report["errors"]
            ):
                raise AssertionError(
                    f"unsafe shared path was accepted: {label}: {path_report}"
                )
            serialized_path_report = json.dumps(path_report, ensure_ascii=False)
            if runs_value in serialized_path_report or database_value in serialized_path_report:
                raise AssertionError(f"unsafe shared path leaked into diagnostics: {label}")

        release_root = root / "release-0.1.1"
        packaged_resources = release_root / "resources" / "protocol"
        packaged_resources.mkdir(parents=True)
        shared_resources = root / "shared" / "protocol"
        shared_resources.mkdir(parents=True)
        wrong_release_resources = root / "release-0.1.0" / "resources" / "protocol"
        wrong_release_resources.mkdir(parents=True)
        symlink_resources = release_root / "protocol-resources-link"
        symlink_fixture_created = False
        try:
            symlink_resources.symlink_to(shared_resources, target_is_directory=True)
        except OSError:
            # The production policy rejects the override by key presence before
            # trusting or inspecting its value.  Windows without symlink
            # privileges can therefore still exercise the same fail-closed
            # contract using the would-be link path.
            pass
        else:
            symlink_fixture_created = symlink_resources.is_symlink()

        resources_override_cases = {
            "empty": "",
            "correct-release-path": packaged_resources.as_posix(),
            "shared-path": shared_resources.as_posix(),
            "symlink-path": symlink_resources.as_posix(),
            "path-traversal": (
                f"{packaged_resources.as_posix()}/../../../shared/protocol"
            ),
            "wrong-target": wrong_release_resources.as_posix(),
        }
        for label, configured_resources in resources_override_cases.items():
            override_file = root / f"production-resources-{label}.env"
            override_values = {
                **validator_values,
                "PROTOCOL_STUDIO_RESOURCES_ROOT": configured_resources,
            }
            override_file.write_text(
                "".join(f"{name}={value}\n" for name, value in override_values.items()),
                encoding="utf-8",
            )
            rejected_override = subprocess.run(
                [
                    sys.executable,
                    str(ENV_RUNNER),
                    "--env-file",
                    str(override_file),
                    "--",
                    *validator_command,
                ],
                cwd=REPO_ROOT,
                env=minimal_child_environment(),
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            rejected_report = assert_json_contract(json.loads(rejected_override.stdout))
            if (
                rejected_override.returncode == 0
                or rejected_report["status"] != "failed"
                or rejected_report["checks"].get(
                    "packaged_protocol_resources_enforced"
                )
                is not False
                or "production environment must use packaged protocol resources"
                not in rejected_report["errors"]
            ):
                raise AssertionError(
                    f"{label}: production resources override was not rejected: "
                    f"{rejected_report}"
                )
            if configured_resources and configured_resources in json.dumps(
                rejected_report, ensure_ascii=False
            ):
                raise AssertionError(
                    f"{label}: rejected resources path leaked into diagnostics"
                )

        development_resources = root / "development-protocol-resources"
        development_resources.mkdir()
        development_override = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json; "
                    "from mvp_generator.library import PROTOCOL_RESOURCES_ROOT; "
                    "print(json.dumps({'resolved': str(PROTOCOL_RESOURCES_ROOT)}))"
                ),
            ],
            cwd=REPO_ROOT,
            env={
                **minimal_child_environment(),
                "PROTOCOL_STUDIO_RESOURCES_ROOT": development_resources.as_posix(),
            },
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if development_override.returncode != 0:
            raise AssertionError(
                "development resources override failed outside the production validator: "
                f"exit={development_override.returncode} "
                f"stdout={development_override.stdout!r} "
                f"stderr={development_override.stderr!r}"
            )
        development_report = json.loads(development_override.stdout)
        if (
            not isinstance(development_report, dict)
            or not isinstance(development_report.get("resolved"), str)
            or Path(development_report["resolved"]) != development_resources.resolve()
        ):
            raise AssertionError(
                f"development resources override contract failed: {development_report}"
            )

        release_overlay = root / "release-overlay"
        shutil.copytree(
            REPO_ROOT / "mvp_generator",
            release_overlay / "mvp_generator",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(
            REPO_ROOT / "resources" / "protocol",
            release_overlay / "resources" / "protocol",
        )
        release_manifest = release_overlay / "release-manifest.json"
        release_manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "project": "mcgs-full-chain-studio",
                    "version": "0.1.1",
                    "created_at": "2026-01-01T00:00:00Z",
                    "source_date_epoch": 1767225600,
                    "files": [],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        packaged_overlay_resources = release_overlay / "resources" / "protocol"
        overlay_positive, overlay_positive_report = run_library_overlay(
            release_overlay,
            None,
        )
        if (
            overlay_positive.returncode != 0
            or overlay_positive_report["status"] != "passed"
            or overlay_positive_report["resources_root"]
            != str(packaged_overlay_resources.resolve())
            or overlay_positive_report["error_type"] is not None
            or overlay_positive_report["error"] is not None
        ):
            raise AssertionError(
                "modern release did not use its packaged resources: "
                f"{overlay_positive_report}"
            )

        release_override_error = "release builds must use packaged protocol resources"
        runtime_override_cases = {
            "empty": "",
            "packaged-path": packaged_overlay_resources.as_posix(),
            "external-path": shared_resources.as_posix(),
        }
        for label, configured_resources in runtime_override_cases.items():
            override_result, override_report = run_library_overlay(
                release_overlay,
                configured_resources,
            )
            if (
                override_result.returncode != 17
                or override_report["status"] != "failed"
                or override_report["resources_root"] is not None
                or override_report["error_type"] != "RuntimeError"
                or override_report["error"] != release_override_error
            ):
                raise AssertionError(
                    f"{label}: modern release runtime override was not rejected: "
                    f"{override_report}"
                )
            if configured_resources and configured_resources in json.dumps(
                override_report, ensure_ascii=False
            ):
                raise AssertionError(
                    f"{label}: runtime override path leaked into diagnostics"
                )

        release_manifest_error = (
            "release-manifest.json must be a regular non-symlink file"
        )
        manifest_target = root / "manifest-target.json"
        manifest_target.write_text("{}\n", encoding="utf-8")
        release_manifest.unlink()
        release_manifest_symlink_tested = False
        try:
            release_manifest.symlink_to(manifest_target)
        except OSError:
            pass
        else:
            release_manifest_symlink_tested = release_manifest.is_symlink()
            symlink_result, symlink_report = run_library_overlay(
                release_overlay,
                None,
            )
            if (
                symlink_result.returncode != 17
                or symlink_report["status"] != "failed"
                or symlink_report["resources_root"] is not None
                or symlink_report["error_type"] != "RuntimeError"
                or symlink_report["error"] != release_manifest_error
            ):
                raise AssertionError(
                    f"release manifest symlink was not rejected: {symlink_report}"
                )
            if str(manifest_target) in json.dumps(symlink_report, ensure_ascii=False):
                raise AssertionError("release manifest symlink target leaked into diagnostics")
            release_manifest.unlink()

        release_manifest.mkdir()
        nonregular_result, nonregular_report = run_library_overlay(
            release_overlay,
            None,
        )
        if (
            nonregular_result.returncode != 17
            or nonregular_report["status"] != "failed"
            or nonregular_report["resources_root"] is not None
            or nonregular_report["error_type"] != "RuntimeError"
            or nonregular_report["error"] != release_manifest_error
        ):
            raise AssertionError(
                f"non-regular release manifest was not rejected: {nonregular_report}"
            )
        release_manifest.rmdir()

        overlay_development, overlay_development_report = run_library_overlay(
            release_overlay,
            development_resources.as_posix(),
        )
        if (
            overlay_development.returncode != 0
            or overlay_development_report["status"] != "passed"
            or overlay_development_report["resources_root"]
            != str(development_resources.resolve())
            or overlay_development_report["error_type"] is not None
            or overlay_development_report["error"] is not None
        ):
            raise AssertionError(
                "manifest-free development overlay rejected resources override: "
                f"{overlay_development_report}"
            )

        invalid_runtime_environment = {
            **minimal_child_environment(),
            **validator_values,
            "PROTOCOL_STUDIO_AUTH_ENABLED": "true\t",
        }
        invalid_runtime = subprocess.run(
            validator_command,
            cwd=REPO_ROOT,
            env=invalid_runtime_environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        invalid_runtime_report = assert_json_contract(json.loads(invalid_runtime.stdout))
        if (
            invalid_runtime.returncode == 0
            or invalid_runtime_report["status"] != "failed"
            or invalid_runtime_report["checks"].get("environment_values_safe") is not False
        ):
            raise AssertionError(
                f"runtime control character was not rejected: {invalid_runtime_report}"
            )
        serialized_report = json.dumps(invalid_runtime_report, ensure_ascii=False)
        if validator_values["PROTOCOL_STUDIO_ADMIN_PASSWORD_HASH"] in serialized_report:
            raise AssertionError("validator disclosed a password hash")

    report = {
        "schema_version": 1,
        "status": "passed",
        "suite": "environment_file_contract",
        "checks": {
            "positive_assignment_count": len(expected_values),
            "negative_syntax_count": len(negative_cases) + 2,
            "strict_systemd_subset": True,
            "plain_dollar_is_literal": True,
            "trusted_system_path_only": True,
            "privileged_loader_cases_rejected": len(privileged_loader_cases),
            "ambient_environment_isolated": True,
            "child_exit_code_propagated": True,
            "child_stdio_preserved": True,
            "fd_isolation_failure_redacted": True,
            "linux_fd_isolation_executed": linux_fd_isolation["executed"],
            "linux_fd_isolation_passed": (
                linux_fd_isolation["status"] == "passed"
                if linux_fd_isolation["executed"]
                else None
            ),
            "production_validator_integrated": True,
            "production_password_hash_negative_cases": len(password_hash_cases),
            "production_security_settings_negative_cases": len(
                security_settings_cases
            ),
            "production_security_settings_real_constructor_passed": True,
            "production_password_hash_real_verifier_passed": True,
            "runtime_loader_names_rejected_by_presence": len(runtime_loader_names),
            "runtime_safe_values_enforced": 3,
            "public_origin_negative_cases": len(public_origin_cases),
            "shared_path_identity_negative_cases": len(path_identity_cases),
            "production_resources_override_cases_rejected": len(
                resources_override_cases
            ),
            "production_resources_symlink_fixture_created": symlink_fixture_created,
            "development_resources_override_preserved": True,
            "modern_release_overlay_default_resources_passed": True,
            "modern_release_overlay_override_cases_rejected": len(
                runtime_override_cases
            ),
            "modern_release_manifest_symlink_tested": (
                release_manifest_symlink_tested
            ),
            "modern_release_nonregular_manifest_rejected": True,
            "manifest_free_overlay_development_override_preserved": True,
            "runtime_control_characters_rejected": True,
        },
        "platform": os.name,
        "sys_platform": sys.platform,
        "linux_fd_isolation": linux_fd_isolation,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
