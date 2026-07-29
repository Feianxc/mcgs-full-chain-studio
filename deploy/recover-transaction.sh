#!/usr/bin/bash -p
if [[ ! -o privileged ]]; then
  builtin printf 'ERROR: privileged Bash mode is required; execute this script directly or with /usr/bin/bash -p\n' >&2
  builtin exit 1
fi
builtin set -Eeuo pipefail
builtin umask 027
PATH=/usr/sbin:/usr/bin
builtin export PATH
builtin readonly PATH
builtin readonly TRUST_REALPATH_BIN=/usr/bin/realpath
builtin readonly TRUST_STAT_BIN=/usr/bin/stat
builtin readonly TRUST_DIRNAME_BIN=/usr/bin/dirname
builtin readonly TRUST_GETFACL_BIN=/usr/bin/getfacl
builtin readonly TRUST_GREP_BIN=/usr/bin/grep
builtin readonly REQUIRED_UNSET_ENVIRONMENT='BASHOPTS BASH_ENV CDPATH ENV GCONV_PATH GLIBC_TUNABLES GLOBIGNORE LD_ASSUME_KERNEL LD_AUDIT LD_BIND_NOT LD_BIND_NOW LD_DEBUG LD_DEBUG_OUTPUT LD_DYNAMIC_WEAK LD_HWCAP_MASK LD_LIBRARY_PATH LD_ORIGIN_PATH LD_POINTER_GUARD LD_PREFER_MAP_32BIT_EXEC LD_PRELOAD LD_PROFILE LD_PROFILE_OUTPUT LD_SHOW_AUXV LD_TRACE_LOADED_OBJECTS LD_TRACE_PRELINKING LD_USE_LOAD_BIAS LD_VERBOSE LD_WARN LOCPATH OPENSSL_CONF OPENSSL_CONF_INCLUDE OPENSSL_ENGINES OPENSSL_MODULES PATH PYTHONHOME PYTHONINSPECT PYTHONPATH PYTHONSTARTUP SHELLOPTS _UVICORN_COMPLETE FORWARDED_ALLOW_IPS UVICORN_ACCESS_LOG UVICORN_APP UVICORN_APP_DIR UVICORN_BACKLOG UVICORN_DATE_HEADER UVICORN_ENV_FILE UVICORN_FACTORY UVICORN_FD UVICORN_FORWARDED_ALLOW_IPS UVICORN_H11_MAX_INCOMPLETE_EVENT_SIZE UVICORN_HEADERS UVICORN_HOST UVICORN_HTTP UVICORN_INTERFACE UVICORN_LIFESPAN UVICORN_LIMIT_CONCURRENCY UVICORN_LIMIT_MAX_REQUESTS UVICORN_LOG_CONFIG UVICORN_LOG_LEVEL UVICORN_LOOP UVICORN_PORT UVICORN_PROXY_HEADERS UVICORN_RELOAD UVICORN_RELOAD_DELAY UVICORN_RELOAD_DIRS UVICORN_RELOAD_EXCLUDES UVICORN_RELOAD_INCLUDES UVICORN_ROOT_PATH UVICORN_SERVER_HEADER UVICORN_SSL_CA_CERTS UVICORN_SSL_CERTFILE UVICORN_SSL_CERT_REQS UVICORN_SSL_CIPHERS UVICORN_SSL_KEYFILE UVICORN_SSL_KEYFILE_PASSWORD UVICORN_SSL_VERSION UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN UVICORN_TIMEOUT_KEEP_ALIVE UVICORN_TIMEOUT_WORKER_HEALTHCHECK UVICORN_UDS UVICORN_USE_COLORS UVICORN_VERSION UVICORN_WORKERS UVICORN_WS UVICORN_WS_MAX_QUEUE UVICORN_WS_MAX_SIZE UVICORN_WS_PER_MESSAGE_DEFLATE UVICORN_WS_PING_INTERVAL UVICORN_WS_PING_TIMEOUT WEB_CONCURRENCY'
builtin readonly REQUIRED_SERVICE_ENVIRONMENT='PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1'
builtin unset BASH_ENV ENV CDPATH
builtin unset CURL_HOME ALL_PROXY HTTPS_PROXY HTTP_PROXY NO_PROXY \
  all_proxy https_proxy http_proxy no_proxy

fail() {
  builtin printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

validate_single_http_response_status() {
  local expected_status="$1"
  local header_dump="$2"
  local -a response_statuses=()
  [[ "$expected_status" =~ ^[0-9]{3}$ ]] || return 1
  mapfile -t response_statuses < <(
    printf '%s\n' "$header_dump" | awk '
      {
        sub(/\r$/, "")
        if ($0 ~ /^HTTP\/[0-9]+([.][0-9]+)?[ \t]+[0-9][0-9][0-9]([ \t]|$)/) {
          split($0, fields, /[ \t]+/)
          print fields[2]
        }
      }
    '
  )
  [[ "${#response_statuses[@]}" == "1" ]] || return 1
  [[ "${response_statuses[0]}" == "$expected_status" ]]
}

validate_health_manifest_header() {
  local expected_sha256="$1"
  local header_dump="$2"
  local -a manifest_values=()
  [[ "$expected_sha256" =~ ^[0-9a-f]{64}$ ]] || return 1
  mapfile -t manifest_values < <(
    printf '%s\n' "$header_dump" | awk '
      {
        sub(/\r$/, "")
        colon = index($0, ":")
        if (colon == 0) next
        name = substr($0, 1, colon - 1)
        if (tolower(name) != "x-mcgs-release-manifest-sha256") next
        value = substr($0, colon + 1)
        sub(/^[ \t]+/, "", value)
        sub(/[ \t]+$/, "", value)
        print value
      }
    '
  )
  [[ "${#manifest_values[@]}" == "1" ]] || return 1
  [[ "${manifest_values[0]}" =~ ^[0-9a-f]{64}$ ]] || return 1
  [[ "${manifest_values[0]}" == "$expected_sha256" ]]
}

manifest_bound_health() {
  local expected_sha256="$1"
  local url="$2"
  local max_time="$3"
  local host_header="${4:-}"
  local response
  local status_line
  local http_status
  local header_dump
  local -a curl_args=(
    --disable --noproxy '*' --silent --show-error --fail --max-time "$max_time"
    --dump-header - --output /dev/null
    --write-out $'\n__MCGS_HTTP_STATUS__%{http_code}'
  )
  if [[ -n "$host_header" ]]; then
    curl_args+=(--header "Host: $host_header")
  fi
  response="$(curl "${curl_args[@]}" "$url")" || return 1
  status_line="${response##*$'\n'}"
  [[ "$status_line" =~ ^__MCGS_HTTP_STATUS__([0-9]{3})$ ]] || return 1
  http_status="${BASH_REMATCH[1]}"
  [[ "$http_status" == "200" ]] || return 1
  header_dump="${response%$'\n'*}"
  validate_single_http_response_status "$http_status" "$header_dump" || return 1
  validate_health_manifest_header "$expected_sha256" "$header_dump"
}

availability_health() {
  local url="$1"
  local max_time="$2"
  local host_header="${3:-}"
  local response
  local status_line
  local http_status
  local header_dump
  local -a curl_args=(
    --disable --noproxy '*' --silent --show-error --fail --max-time "$max_time"
    --dump-header - --output /dev/null
    --write-out $'\n__MCGS_HTTP_STATUS__%{http_code}'
  )
  if [[ -n "$host_header" ]]; then
    curl_args+=(--header "Host: $host_header")
  fi
  response="$(curl "${curl_args[@]}" "$url")" || return 1
  status_line="${response##*$'\n'}"
  [[ "$status_line" =~ ^__MCGS_HTTP_STATUS__([0-9]{3})$ ]] || return 1
  http_status="${BASH_REMATCH[1]}"
  [[ "$http_status" == "200" ]] || return 1
  header_dump="${response%$'\n'*}"
  validate_single_http_response_status "$http_status" "$header_dump"
}

validate_login_redirect_headers() {
  local http_status="$1"
  local header_dump="$2"
  local -a location_values=()
  [[ "$http_status" == "302" || "$http_status" == "303" ]] || return 1
  validate_single_http_response_status "$http_status" "$header_dump" || return 1
  mapfile -t location_values < <(
    printf '%s\n' "$header_dump" | awk '
      {
        sub(/\r$/, "")
        colon = index($0, ":")
        if (colon == 0) next
        name = substr($0, 1, colon - 1)
        if (tolower(name) != "location") next
        value = substr($0, colon + 1)
        sub(/^[ \t]+/, "", value)
        sub(/[ \t]+$/, "", value)
        print value
      }
    '
  )
  [[ "${#location_values[@]}" == "1" ]] || return 1
  [[ "${location_values[0]}" == "/login" ]]
}

strict_login_redirect() {
  local url="$1"
  local max_time="$2"
  local host_header="${3:-}"
  local response
  local status_line
  local http_status
  local header_dump
  local -a curl_args=(
    --disable --noproxy '*' --silent --show-error --max-time "$max_time"
    --max-redirs 0 --dump-header - --output /dev/null
    --write-out $'\n__MCGS_HTTP_STATUS__%{http_code}'
  )
  if [[ -n "$host_header" ]]; then
    curl_args+=(--header "Host: $host_header")
  fi
  response="$(curl "${curl_args[@]}" "$url")" || return 1
  status_line="${response##*$'\n'}"
  [[ "$status_line" =~ ^__MCGS_HTTP_STATUS__([0-9]{3})$ ]] || return 1
  http_status="${BASH_REMATCH[1]}"
  header_dump="${response%$'\n'*}"
  validate_login_redirect_headers "$http_status" "$header_dump"
}

runtime_health() {
  local runtime_mode="$1"
  local expected_sha256="$2"
  local url="$3"
  local max_time="$4"
  local host_header="${5:-}"
  case "$runtime_mode" in
    release|release-local-venv)
      manifest_bound_health "$expected_sha256" "$url" "$max_time" "$host_header"
      ;;
    legacy|legacy-shared-venv)
      availability_health "$url" "$max_time" "$host_header"
      ;;
    *)
      return 1
      ;;
  esac
}

validate_production_environment() {
  "$PYTHON_BIN" -I "$SCRIPT_DIR/run_with_env.py" --env-file "$ENV_FILE" -- \
    "$PYTHON_BIN" -I -B -u "$SCRIPT_DIR/validate_production_env.py" \
    --shared-runs "$RUNS_DIR" \
    --security-db "$SECURITY_DB" \
    --public-origin "$PUBLIC_ORIGIN" \
    --public-host "$PUBLIC_HOST"
}

canonical_managed_dropin_content() {
  cat <<EOF
# Managed by mcgs-full-chain-studio deploy-release.sh.
[Unit]
StartLimitIntervalSec=60s
StartLimitBurst=3
[Service]
WorkingDirectory=$CURRENT_LINK
ExecStartPre=
ExecStartPre=/usr/bin/python3 -I -B -u $RUNTIME_GUARD_HELPER --verify-current $CURRENT_LINK --releases-root $RELEASES_DIR --baseline-directory $RUNTIME_BASELINE_DIR --require-root-owned-immutable
ExecStartPre=$CURRENT_LINK/.venv/bin/python -I -B -u $CURRENT_LINK/deploy/validate_production_env.py --shared-runs $RUNS_DIR --security-db $SECURITY_DB --public-origin $PUBLIC_ORIGIN --public-host $PUBLIC_HOST
ExecStart=
ExecStart=$CURRENT_LINK/.venv/bin/python -I -B -u -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $LOCAL_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1
Environment=
Environment=PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
UnsetEnvironment=$REQUIRED_UNSET_ENVIRONMENT
UMask=0077
NoNewPrivileges=true
CapabilityBoundingSet=
AmbientCapabilities=
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectControlGroups=true
ProtectKernelModules=true
ProtectKernelTunables=true
ProtectKernelLogs=true
ProtectClock=true
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=true
LockPersonality=true
ReadWritePaths=
ReadWritePaths=$SHARED_DIR
EOF
}

managed_dropin_matches_canonical_content() {
  [[ -f "$MANAGED_DROPIN" && ! -L "$MANAGED_DROPIN" ]] || return 1
  cmp -s "$MANAGED_DROPIN" <(canonical_managed_dropin_content)
}

validate_final_publication_configuration() {
  local expected_managed_dropin_sha256
  [[ "$(sha256sum "$ENV_FILE" | awk '{print $1}')" == "$ENV_FILE_SHA256" \
    && "$(sha256sum "$FRAGMENT_PATH" | awk '{print $1}')" == "$FRAGMENT_SHA256" ]] \
    || return 1
  cmp -s "$FRAGMENT_PATH" "$FRAGMENT_BACKUP" || return 1
  assert_trusted_root_file_path "$ENV_FILE" "production environment file" || return 1
  assert_secure_systemd_directory "/etc/systemd/system" \
    "systemd administrator unit directory" || return 1
  assert_secure_systemd_file "$FRAGMENT_PATH" "systemd base unit" || return 1
  [[ "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
    && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" ]] \
    || return 1
  if [[ "$ACTIVATION_MODE" == "release" ]]; then
    assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" \
      "managed systemd drop-in directory" || return 1
    assert_secure_systemd_file "$MANAGED_DROPIN" \
      "managed systemd runtime drop-in" || return 1
    expected_managed_dropin_sha256="$(canonical_managed_dropin_content | sha256sum | awk '{print $1}')" \
      || return 1
    [[ "$(sha256sum "$MANAGED_DROPIN" | awk '{print $1}')" == "$expected_managed_dropin_sha256" ]] \
      || return 1
    managed_dropin_matches_canonical_content || return 1
    [[ "$(effective_exec_start_pre_argvs)" == "$EXPECTED_EXEC_START_PRE_ARGVS_JSON" ]] \
      || return 1
    effective_unset_environment_matches || return 1
    effective_environment_matches || return 1
    effective_restart_limit_matches || return 1
    assert_dropin_paths_exact \
      "$(systemctl show "$SERVICE" --property=DropInPaths --value)" "$MANAGED_DROPIN" \
      || return 1
  else
    [[ ! -e "$MANAGED_DROPIN" && ! -L "$MANAGED_DROPIN" \
      && -z "$(systemctl show "$SERVICE" --property=ExecStartPre --value)" ]] \
      || return 1
    assert_dropin_paths_exact \
      "$(systemctl show "$SERVICE" --property=DropInPaths --value)" || return 1
  fi
}

service_enable_state() {
  systemctl is-enabled "$SERVICE" 2>/dev/null || true
}

effective_exec_argv() {
  systemctl show "$SERVICE" --property=ExecStart --value \
    | sed -n 's/^{ path=[^;]* ; argv\[\]=\(.*\) ; ignore_errors=.*/\1/p'
}

effective_exec_start_pre_argvs() {
  local value
  value="$(systemctl show "$SERVICE" --property=ExecStartPre --value)" || return 1
  "$PYTHON_BIN" -I - "$value" <<'PY'
import re
import json
import sys

matches = re.findall(
    r"\{ path=[^;]* ; argv\[\]=(.*?) ; ignore_errors=",
    sys.argv[1],
)
if any(not value for value in matches):
    raise SystemExit(1)
print(json.dumps(matches, ensure_ascii=False, separators=(",", ":")))
PY
}

unset_environment_matches() {
  local actual_text="$1"
  local name
  local -a expected_names=()
  local -a actual_names=()
  local -A expected_seen=()
  local -A actual_seen=()
  read -r -a expected_names <<<"$REQUIRED_UNSET_ENVIRONMENT"
  read -r -a actual_names <<<"$actual_text"
  [[ "${#expected_names[@]}" == "${#actual_names[@]}" ]] || return 1
  for name in "${expected_names[@]}"; do
    [[ -z "${expected_seen[$name]+configured}" ]] || return 1
    expected_seen["$name"]=1
  done
  for name in "${actual_names[@]}"; do
    [[ -z "${actual_seen[$name]+configured}" ]] || return 1
    actual_seen["$name"]=1
  done
  for name in "${expected_names[@]}"; do
    [[ -n "${actual_seen[$name]+configured}" ]] || return 1
  done
}

effective_unset_environment_matches() {
  local actual
  actual="$(systemctl show "$SERVICE" --property=UnsetEnvironment --value)" \
    || return 1
  unset_environment_matches "$actual"
}

environment_assignments_match() {
  local actual_text="$1"
  local assignment
  local -a expected_assignments=()
  local -a actual_assignments=()
  local -A expected_seen=()
  local -A actual_seen=()
  read -r -a expected_assignments <<<"$REQUIRED_SERVICE_ENVIRONMENT"
  read -r -a actual_assignments <<<"$actual_text"
  [[ "${#expected_assignments[@]}" == "${#actual_assignments[@]}" ]] || return 1
  for assignment in "${expected_assignments[@]}"; do
    [[ -z "${expected_seen[$assignment]+configured}" ]] || return 1
    expected_seen["$assignment"]=1
  done
  for assignment in "${actual_assignments[@]}"; do
    [[ -z "${actual_seen[$assignment]+configured}" ]] || return 1
    actual_seen["$assignment"]=1
  done
  for assignment in "${expected_assignments[@]}"; do
    [[ -n "${actual_seen[$assignment]+configured}" ]] || return 1
  done
}

effective_environment_matches() {
  local actual
  actual="$(systemctl show "$SERVICE" --property=Environment --value)" || return 1
  environment_assignments_match "$actual"
}

effective_restart_limit_matches() {
  [[ "$(systemctl show "$SERVICE" --property=StartLimitIntervalUSec --value)" == "1min" \
    && "$(systemctl show "$SERVICE" --property=StartLimitBurst --value)" == "3" ]]
}

process_environment_matches() {
  local pid="$1"
  "$PYTHON_BIN" -I -B -u - "$pid" "$ENV_FILE" \
    "$SCRIPT_DIR/run_with_env.py" "$RUNS_DIR" "$SECURITY_DB" <<'PY'
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

pid, env_path, loader_path, expected_runs, expected_database = sys.argv[1:]
spec = importlib.util.spec_from_file_location("mcgs_run_with_env", loader_path)
if spec is None or spec.loader is None:
    raise SystemExit(1)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
expected = module.load_environment(Path(env_path))
expected.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})
if expected.get("PROTOCOL_STUDIO_RUNS_ROOT") != expected_runs:
    raise SystemExit(1)
if expected.get("MCGS_FULL_CHAIN_RUNS_ROOT", expected_runs) != expected_runs:
    raise SystemExit(1)
if expected.get("PROTOCOL_STUDIO_SECURITY_DB") != expected_database:
    raise SystemExit(1)

raw = Path(f"/proc/{pid}/environ").read_bytes()
parts = raw.split(b"\0")
if not parts or parts[-1] != b"":
    raise SystemExit(1)
actual: dict[str, str] = {}
for part in parts[:-1]:
    if not part or b"=" not in part:
        raise SystemExit(1)
    key_bytes, value_bytes = part.split(b"=", 1)
    key = key_bytes.decode("ascii")
    if key in actual:
        raise SystemExit(1)
    actual[key] = value_bytes.decode("utf-8")
if any(actual.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
for key in actual:
    if module.is_privileged_loader_key(key) and key not in {
        "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"
    }:
        raise SystemExit(1)
PY
}

process_exec_argv() {
  "$PYTHON_BIN" -I - "$1" <<'PY'
from pathlib import Path
import sys

parts = Path(f"/proc/{sys.argv[1]}/cmdline").read_bytes().split(b"\0")
if not parts or parts[-1] != b"" or any(not part for part in parts[:-1]):
    raise SystemExit("invalid process command line")
print(" ".join(part.decode("utf-8") for part in parts[:-1]))
PY
}

process_working_directory() {
  readlink -f -- "/proc/$1/cwd"
}

fsync_file() {
  "$PYTHON_BIN" -I - "$1" <<'PY'
import os
import sys
flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(sys.argv[1], flags)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
}

fsync_directory() {
  "$PYTHON_BIN" -I - "$1" <<'PY'
import os
import sys
flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(sys.argv[1], flags)
try:
    os.fsync(descriptor)
finally:
    os.close(descriptor)
PY
}

verify_atomic_rename_boundary() {
  "$PYTHON_BIN" -I - "$PYTHON_BIN" "$SCRIPT_DIR/atomic_rename.py" \
    "$APP_ROOT" "$DEPLOYMENT_DIR" <<'PY'
import json
import subprocess
import sys

python, helper, source_dir, target_dir = sys.argv[1:5]
completed = subprocess.run(
    [python, "-I", helper, "probe", "--source-dir", source_dir, "--target-dir", target_dir],
    check=False,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    timeout=30,
)
raw = completed.stdout
if completed.returncode != 0 or completed.stderr:
    raise SystemExit("atomic rename boundary probe execution failed")
if raw.count(b"\n") != 1 or not raw.endswith(b"\n") or b"\r" in raw:
    raise SystemExit("atomic rename boundary probe output is not exactly one line")

def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

report = json.loads(
    raw[:-1].decode("utf-8"),
    object_pairs_hook=strict_object,
    parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
)
boolean_fields = {
    "ok", "same_device", "inode_preserved", "source_removed", "target_removed",
    "source_directory_synced", "target_directory_synced",
}
expected_keys = {"schema_version", "error_number"} | boolean_fields
if (
    not isinstance(report, dict)
    or set(report) != expected_keys
    or type(report["schema_version"]) is not int
    or report["schema_version"] != 1
    or type(report["error_number"]) is not int
    or report["error_number"] != 0
    or any(type(report[name]) is not bool or report[name] is not True for name in boolean_fields)
):
    raise SystemExit("atomic rename boundary probe contract failed")
PY
}

publish_committed_record() {
  local temporary="$1"
  local final="$2"
  assert_trusted_record_file "$temporary" "pending recovery evidence"
  [[ ! -e "$final" && ! -L "$final" ]] || return 1
  ln -T -- "$temporary" "$final" || return 1
  assert_trusted_record_file "$final" "published recovery evidence"
  [[ "$(stat -c '%d:%i' -- "$temporary")" == "$(stat -c '%d:%i' -- "$final")" ]] \
    || return 1
  fsync_directory "$DEPLOYMENT_DIR" || return 1
  rm -f -- "$temporary" || return 1
  [[ ! -e "$temporary" && ! -L "$temporary" ]] || return 1
  fsync_directory "$DEPLOYMENT_DIR"
}

reconcile_or_publish_committed_record() {
  local pending="$1"
  local final="$2"
  if [[ -e "$pending" || -L "$pending" ]] && [[ -e "$final" || -L "$final" ]]; then
    assert_trusted_record_file "$pending" "pending committed operation evidence"
    assert_trusted_record_file "$final" "published committed operation evidence"
    [[ "$(stat -c '%d:%i' -- "$pending")" == "$(stat -c '%d:%i' -- "$final")" ]] \
      || return 1
    cmp -s "$pending" "$final" || return 1
    fsync_file "$final" || return 1
    fsync_directory "$DEPLOYMENT_DIR" || return 1
    rm -f -- "$pending" || return 1
    [[ ! -e "$pending" && ! -L "$pending" ]] || return 1
    fsync_directory "$DEPLOYMENT_DIR"
  elif [[ -e "$final" || -L "$final" ]]; then
    assert_trusted_record_file "$final" "published committed operation evidence"
    fsync_file "$final" || return 1
    fsync_directory "$DEPLOYMENT_DIR"
  elif [[ -e "$pending" || -L "$pending" ]]; then
    publish_committed_record "$pending" "$final"
  else
    return 1
  fi
}

fsync_systemd_enablement_state() {
  local directory
  local directories=("$SYSTEMD_CONFIG_DIR")
  shopt -s nullglob
  directories+=("$SYSTEMD_CONFIG_DIR"/*.wants "$SYSTEMD_CONFIG_DIR"/*.requires)
  shopt -u nullglob
  for directory in "${directories[@]}"; do
    [[ -d "$directory" && ! -L "$directory" ]] || return 1
    fsync_directory "$directory" || return 1
  done
}

probe_service_enablement() {
  SERVICE_ENABLE_STDOUT=""
  SERVICE_ENABLE_EXIT=0
  if SERVICE_ENABLE_STDOUT="$(systemctl is-enabled "$SERVICE" 2>/dev/null)"; then
    SERVICE_ENABLE_EXIT=0
  else
    SERVICE_ENABLE_EXIT="$?"
  fi
}

collect_service_enablement_links() {
  local scan_output
  SERVICE_ENABLEMENT_LINKS=()
  scan_output="$("$PYTHON_BIN" -I - "$SYSTEMD_CONFIG_DIR" "$SYSTEMD_UNIT_FILE" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
target = Path(sys.argv[2])
if not root.is_dir() or root.is_symlink():
    raise SystemExit("systemd configuration root is not a real directory")
target_resolved = target.resolve(strict=True)
if target_resolved != target:
    raise SystemExit("systemd unit path is not canonical")

matches: list[str] = []
for directory in root.iterdir():
    if not directory.name.endswith((".wants", ".requires")):
        continue
    if directory.is_symlink() or not directory.is_dir():
        raise SystemExit("systemd enablement directory is not a real directory")
    for entry in directory.iterdir():
        if not entry.is_symlink():
            continue
        try:
            resolved = entry.resolve(strict=True)
        except FileNotFoundError:
            continue
        if resolved == target_resolved:
            value = str(entry)
            if "\n" in value or "\r" in value:
                raise SystemExit("systemd enablement link path contains a line break")
            matches.append(value)

for value in sorted(matches):
    print(value)
PY
)" || return 1
  if [[ -n "$scan_output" ]]; then
    mapfile -t SERVICE_ENABLEMENT_LINKS <<<"$scan_output"
  fi
}

acl_is_minimal() {
  local path="$1"
  local -a acl_status
  if LC_ALL=C "$TRUST_GETFACL_BIN" -c -p -- "$path" 2>/dev/null \
    | "$TRUST_GREP_BIN" -Eq '^(default:|user:[^:]|group:[^:]|mask::)'; then
    return 1
  else
    acl_status=("${PIPESTATUS[@]}")
    [[ "${acl_status[0]}" == "0" && "${acl_status[1]}" == "1" ]] || return 2
  fi
}

assert_no_extended_acl() {
  local path="$1"
  local label="$2"
  local acl_status
  if acl_is_minimal "$path"; then
    return 0
  else
    acl_status="$?"
  fi
  [[ "$acl_status" == "1" ]] \
    && fail "$label contains an extended or default ACL"
  fail "cannot verify $label ACLs"
}

assert_secure_runtime_directory() {
  local directory="$1"
  local label="$2"
  local service_account="$3"
  local current
  local mode
  assert_trusted_root_directory_path "$directory" "$label path"
  [[ -d "$directory" && ! -L "$directory" \
    && "$(realpath -e -- "$directory")" == "$directory" \
    && "$(stat -c '%u:%g' -- "$directory")" == "0:0" ]] \
    || fail "$label must be a canonical root-owned real directory"
  mode="$(stat -c '%a' -- "$directory")"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] \
    || fail "$label permission mode is invalid"
  (( (8#$mode & 0022) == 0 )) \
    || fail "$label must not be writable by group or other"
  current="$directory"
  while :; do
    assert_no_extended_acl "$current" "$label path component"
    [[ "$current" == "/" ]] && break
    current="$(dirname -- "$current")"
  done
  if runuser -u "$service_account" -- "$TEST_BIN" -w "$directory"; then
    fail "$label is writable by the systemd service account"
  fi
}

assert_service_persistently_disabled() {
  local service_account="$1"
  local unit_file_state
  local -a enablement_links
  probe_service_enablement
  [[ "$SERVICE_ENABLE_STDOUT" == "disabled" && "$SERVICE_ENABLE_EXIT" == "1" ]] \
    || return 1
  unit_file_state="$(systemctl show "$SERVICE" --property=UnitFileState --value)" \
    || return 1
  [[ "$unit_file_state" == "disabled" ]] || return 1
  collect_service_enablement_links || return 1
  enablement_links=("${SERVICE_ENABLEMENT_LINKS[@]}")
  ((${#enablement_links[@]} == 0)) || return 1
  assert_secure_runtime_directory "$SYSTEMD_CONFIG_DIR" \
    "systemd persistent unit directory" "$service_account"
}

assert_standard_enabled_topology() {
  local service_account="$1"
  local wants_directory="$SYSTEMD_CONFIG_DIR/multi-user.target.wants"
  local wants_link="$wants_directory/$SERVICE"
  local -a enablement_links
  probe_service_enablement
  [[ "$SERVICE_ENABLE_STDOUT" == "enabled" && "$SERVICE_ENABLE_EXIT" == "0" ]] \
    || return 1
  [[ "$(systemctl show "$SERVICE" --property=UnitFileState --value)" == "enabled" ]] \
    || return 1
  assert_secure_runtime_directory "$SYSTEMD_CONFIG_DIR" \
    "systemd persistent unit directory" "$service_account"
  assert_secure_runtime_directory "$wants_directory" \
    "standard multi-user enablement directory" "$service_account"
  [[ -L "$wants_link" && "$(stat -c '%u:%g' -- "$wants_link")" == "0:0" \
    && "$(readlink -f -- "$wants_link")" == "$SYSTEMD_UNIT_FILE" ]] \
    || return 1
  collect_service_enablement_links || return 1
  enablement_links=("${SERVICE_ENABLEMENT_LINKS[@]}")
  [[ "${#enablement_links[@]}" == "1" && "${enablement_links[0]}" == "$wants_link" ]]
}

assert_dropin_paths_exact() {
  local actual="$1"
  shift
  "$PYTHON_BIN" -I - "$actual" "$@" <<'PY'
import sys

actual = sys.argv[1].split() if sys.argv[1] else []
expected = sys.argv[2:]
if len(actual) != len(set(actual)) or sorted(actual) != sorted(expected):
    raise SystemExit(1)
PY
}

assert_transaction_runtime_guard_file() {
  [[ -f "$TRANSACTION_RUNTIME_GUARD" && ! -L "$TRANSACTION_RUNTIME_GUARD" \
    && "$(realpath -e -- "$TRANSACTION_RUNTIME_GUARD")" == "$TRANSACTION_RUNTIME_GUARD" \
    && "$(stat -c '%u:%g:%a' -- "$TRANSACTION_RUNTIME_GUARD")" == "0:0:644" ]] \
    || return 1
  assert_no_extended_acl "$TRANSACTION_RUNTIME_GUARD" \
    "transaction runtime guard"
  cmp -s "$TRANSACTION_RUNTIME_GUARD" <(printf '[Service]\nRestart=no\nRuntimeMaxSec=300s\n')
}

assert_transaction_runtime_guard_loaded() {
  local loaded_dropins
  local -a expected_dropins=("$TRANSACTION_RUNTIME_GUARD")
  assert_transaction_runtime_guard_file || return 1
  [[ "$(systemctl show "$SERVICE" --property=Restart --value)" == "no" \
    && "$(systemctl show "$SERVICE" --property=RuntimeMaxUSec --value)" == "5min" \
    && "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" ]] \
    || return 1
  if [[ -f "$MANAGED_DROPIN" && ! -L "$MANAGED_DROPIN" ]]; then
    expected_dropins+=("$MANAGED_DROPIN")
  fi
  loaded_dropins="$(systemctl show "$SERVICE" --property=DropInPaths --value)" \
    || return 1
  assert_dropin_paths_exact "$loaded_dropins" "${expected_dropins[@]}"
}

install_transaction_runtime_guard() {
  local service_account="$1"
  local temporary
  [[ ! -e "$TRANSACTION_RUNTIME_GUARD" && ! -L "$TRANSACTION_RUNTIME_GUARD" ]] \
    || return 1
  assert_secure_runtime_directory "$RUNTIME_SYSTEMD_DIR" \
    "systemd runtime unit directory" "$service_account"
  if [[ ! -e "$TRANSACTION_RUNTIME_GUARD_DIR" && ! -L "$TRANSACTION_RUNTIME_GUARD_DIR" ]]; then
    install -d -o root -g root -m 0755 "$TRANSACTION_RUNTIME_GUARD_DIR" || return 1
    fsync_directory "$RUNTIME_SYSTEMD_DIR" || return 1
  fi
  assert_secure_runtime_directory "$TRANSACTION_RUNTIME_GUARD_DIR" \
    "transaction runtime guard directory" "$service_account"
  shopt -s nullglob dotglob
  local entries=("$TRANSACTION_RUNTIME_GUARD_DIR"/*)
  shopt -u nullglob dotglob
  ((${#entries[@]} == 0)) || return 1
  temporary="$TRANSACTION_RUNTIME_GUARD_DIR/.99-transaction-runtime-guard-$$-$RANDOM.tmp"
  "$PYTHON_BIN" -I - "$temporary" "$TRANSACTION_RUNTIME_GUARD" \
    "$TRANSACTION_RUNTIME_GUARD_DIR" <<'PY'
import os
import stat
import sys

temporary, final, directory = sys.argv[1:]
payload = b"[Service]\nRestart=no\nRuntimeMaxSec=300s\n"
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(temporary, flags, 0o644)
try:
    os.fchmod(descriptor, 0o644)
    os.fchown(descriptor, 0, 0)
    with os.fdopen(descriptor, "wb", closefd=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
finally:
    os.close(descriptor)
if os.path.lexists(final):
    raise SystemExit("transaction runtime guard appeared during installation")
os.rename(temporary, final)
directory_fd = os.open(
    directory,
    os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
)
try:
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
PY
  assert_transaction_runtime_guard_file || return 1
  systemctl daemon-reload || return 1
  assert_transaction_runtime_guard_loaded
}

ensure_transaction_runtime_guard_loaded() {
  local service_account="$1"
  if [[ -e "$TRANSACTION_RUNTIME_GUARD" || -L "$TRANSACTION_RUNTIME_GUARD" ]]; then
    assert_secure_runtime_directory "$RUNTIME_SYSTEMD_DIR" \
      "systemd runtime unit directory" "$service_account" || return 1
    assert_secure_runtime_directory "$TRANSACTION_RUNTIME_GUARD_DIR" \
      "transaction runtime guard directory" "$service_account" || return 1
    assert_transaction_runtime_guard_file || return 1
    systemctl daemon-reload || return 1
    assert_transaction_runtime_guard_loaded
  else
    install_transaction_runtime_guard "$service_account"
  fi
}

remove_transaction_runtime_guard() {
  local service_account="$1"
  if [[ -e "$TRANSACTION_RUNTIME_GUARD" || -L "$TRANSACTION_RUNTIME_GUARD" ]]; then
    assert_secure_runtime_directory "$TRANSACTION_RUNTIME_GUARD_DIR" \
      "transaction runtime guard directory" "$service_account" || return 1
    assert_transaction_runtime_guard_file || return 1
    rm -f -- "$TRANSACTION_RUNTIME_GUARD" || return 1
    [[ ! -e "$TRANSACTION_RUNTIME_GUARD" && ! -L "$TRANSACTION_RUNTIME_GUARD" ]] \
      || return 1
    fsync_directory "$TRANSACTION_RUNTIME_GUARD_DIR" || return 1
  fi
  systemctl daemon-reload || return 1
  [[ "$(systemctl show "$SERVICE" --property=Restart --value)" == "on-failure" \
    && "$(systemctl show "$SERVICE" --property=RuntimeMaxUSec --value)" == "infinity" \
    && "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" ]] \
    || return 1
  local loaded_dropins
  local -a expected_dropins=()
  if [[ -f "$MANAGED_DROPIN" && ! -L "$MANAGED_DROPIN" ]]; then
    expected_dropins+=("$MANAGED_DROPIN")
  fi
  loaded_dropins="$(systemctl show "$SERVICE" --property=DropInPaths --value)" \
    || return 1
  assert_dropin_paths_exact "$loaded_dropins" "${expected_dropins[@]}"
}

transition_transaction_status() {
  local expected_status="$1"
  local new_status="$2"
  local recovery_activation_id="${3:-}"
  local recovery_activation_mode="${4:-}"
  local temporary="$APP_ROOT/.transaction-phase-$$-$RANDOM.tmp"
  assert_trusted_root_file_path "$TRANSACTION_FILE" "active transaction marker"
  "$PYTHON_BIN" -I - "$TRANSACTION_FILE" "$temporary" \
    "$expected_status" "$new_status" "$recovery_activation_id" \
    "$recovery_activation_mode" <<'PY'
import json
import os
import re
import stat
import sys

marker, temporary, expected, new, activation_id, activation_mode = sys.argv[1:]
read_flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(marker, read_flags)
try:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_gid != 0:
        raise SystemExit("untrusted transaction marker")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise SystemExit("invalid transaction marker mode")
    with os.fdopen(descriptor, "rb", closefd=False) as handle:
        record = json.load(handle)
finally:
    os.close(descriptor)
if (
    type(record) is not dict
    or type(record.get("schema_version")) is not int
    or record.get("schema_version") != 3
    or record.get("status") != expected
):
    raise SystemExit("transaction marker phase mismatch")
record["status"] = new
if new == "recovery_committed_pending_activation":
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}", activation_id):
        raise SystemExit("invalid recovery activation release id")
    if activation_mode not in {"release", "legacy"}:
        raise SystemExit("invalid recovery activation runtime mode")
    record["recovery_activation_release_id"] = activation_id
    record["recovery_activation_runtime_mode"] = activation_mode
elif activation_id or activation_mode:
    raise SystemExit("unexpected recovery activation identity")
payload = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
output = os.open(temporary, write_flags, 0o600)
try:
    os.fchmod(output, 0o600)
    os.fchown(output, 0, 0)
    with os.fdopen(output, "wb", closefd=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
finally:
    os.close(output)
current = os.lstat(marker)
if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
    raise SystemExit("transaction marker changed during phase transition")
os.rename(temporary, marker)
directory = os.path.dirname(marker)
directory_fd = os.open(
    directory,
    os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
)
try:
    os.fsync(directory_fd)
finally:
    os.close(directory_fd)
PY
  assert_trusted_root_file_path "$TRANSACTION_FILE" "transitioned transaction marker"
  [[ "$("$PYTHON_BIN" -I -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["status"])' "$TRANSACTION_FILE")" == "$new_status" ]]
}

stop_service_and_verify() {
  local original_pid
  local active_state
  local main_pid
  original_pid="$(systemctl show "$SERVICE" --property=MainPID --value)" || return 1
  systemctl --no-block stop "$SERVICE" || return 1
  for _ in $(seq 1 "$SERVICE_TERM_GRACE_ATTEMPTS"); do
    active_state="$(systemctl show "$SERVICE" --property=ActiveState --value 2>/dev/null || true)"
    main_pid="$(systemctl show "$SERVICE" --property=MainPID --value 2>/dev/null || true)"
    if [[ "$active_state" == "inactive" && "$main_pid" == "0" ]]; then
      break
    fi
    sleep "$SERVICE_STOP_POLL_SECONDS"
  done
  if [[ "$active_state" != "inactive" || "$main_pid" != "0" ]]; then
    systemctl kill --kill-who=all --signal=KILL "$SERVICE" || return 1
    for _ in $(seq 1 "$SERVICE_KILL_REAP_ATTEMPTS"); do
      active_state="$(systemctl show "$SERVICE" --property=ActiveState --value 2>/dev/null || true)"
      main_pid="$(systemctl show "$SERVICE" --property=MainPID --value 2>/dev/null || true)"
      if [[ "$active_state" == "inactive" && "$main_pid" == "0" ]]; then
        break
      fi
      sleep "$SERVICE_STOP_POLL_SECONDS"
    done
  fi
  systemctl reset-failed "$SERVICE" >/dev/null 2>&1 || true
  [[ "$(systemctl show "$SERVICE" --property=ActiveState --value)" == "inactive" \
    && "$(systemctl show "$SERVICE" --property=SubState --value)" == "dead" \
    && "$(systemctl show "$SERVICE" --property=MainPID --value)" == "0" ]] \
    || return 1
  if [[ "$original_pid" =~ ^[1-9][0-9]*$ ]]; then
    [[ ! -e "/proc/$original_pid" ]] || return 1
  fi
}

runtime_fingerprint() {
  local runtime_root="$1"
  local runtime_python="$2"
  local lock_file="${3:-}"
  local release_root="${4:-}"
  local arguments=(
    "$SCRIPT_DIR/runtime_fingerprint.py"
    --runtime-root "$runtime_root"
    --python "$runtime_python"
  )
  if [[ -n "$lock_file" ]]; then
    arguments+=(--lock "$lock_file")
  fi
  if [[ -n "$release_root" ]]; then
    arguments+=(--release-root "$release_root" --require-root-owned-immutable)
  fi
  "$PYTHON_BIN" -I "${arguments[@]}"
}

verify_release_runtime_baseline() {
  local release_id="$1"
  local release_root="$2"
  local expected_manifest_sha256="$3"
  [[ "$release_root" == "$RELEASES_DIR/$release_id" ]] || return 1
  "$PYTHON_BIN" -I -B -u "$RUNTIME_GUARD_HELPER" \
    --verify-release "$release_root" \
    --releases-root "$RELEASES_DIR" \
    --baseline-directory "$RUNTIME_BASELINE_DIR" \
    --expected-manifest-sha256 "$expected_manifest_sha256" \
    --require-root-owned-immutable
}

require_activatable_passed_record_schema() {
  local schema="$1"
  [[ "$schema" == "5" ]] || fail \
    "passed record schema $schema is audit-only and cannot be activated; use an explicitly reviewed migration"
}

runtime_baseline_verification_matches_record() {
  local report_json="$1"
  local release_id="$2"
  local version="$3"
  local manifest_sha256="$4"
  local baseline_sha256="$5"
  local fingerprint_sha256="$6"
  local helper_sha256="$7"
  "$PYTHON_BIN" -I -B -u - "$report_json" "$release_id" "$version" \
    "$manifest_sha256" "$baseline_sha256" "$fingerprint_sha256" \
    "$helper_sha256" <<'PY'
import json
import re
import sys

def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result

report = json.loads(
    sys.argv[1],
    object_pairs_hook=strict_object,
    parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
)
expected_keys = {
    "schema_version", "status", "release_id", "version",
    "release_manifest_sha256", "runtime_fingerprint_sha256",
    "baseline_sha256", "runtime_guard_helper_sha256",
}
if (
    not isinstance(report, dict)
    or set(report) != expected_keys
    or type(report.get("schema_version")) is not int
    or report["schema_version"] != 1
    or report.get("status") != "passed"
    or report.get("release_id") != sys.argv[2]
    or report.get("version") != sys.argv[3]
    or report.get("release_manifest_sha256") != sys.argv[4]
    or report.get("baseline_sha256") != sys.argv[5]
    or report.get("runtime_fingerprint_sha256") != sys.argv[6]
    or report.get("runtime_guard_helper_sha256") != sys.argv[7]
    or any(re.fullmatch(r"[0-9a-f]{64}", report[name]) is None for name in (
        "release_manifest_sha256", "baseline_sha256",
        "runtime_fingerprint_sha256", "runtime_guard_helper_sha256",
    ))
):
    raise SystemExit("runtime baseline verification evidence does not match the passed record")
PY
}

verify_database_backup_evidence() {
  local backup_path="$1"
  local expected_metadata="$2"
  local expected_basename="$3"
  local actual_metadata
  local resolved
  case "$backup_path" in
    "$BACKUP_DIR"/*) ;;
    *) return 1 ;;
  esac
  assert_trusted_root_directory_path "$BACKUP_DIR" "database backup evidence parent directory"
  [[ "$(basename -- "$backup_path")" == "$expected_basename" ]] || return 1
  [[ -f "$backup_path" && ! -L "$backup_path" ]] || return 1
  resolved="$(realpath -e -- "$backup_path")" || return 1
  [[ "$resolved" == "$backup_path" ]] || return 1
  [[ "$(stat -c '%u:%g:%a' -- "$backup_path")" == "0:0:600" ]] || return 1
  assert_no_extended_acl "$backup_path" "database backup evidence"
  actual_metadata="$("$PYTHON_BIN" -I "$SCRIPT_DIR/sqlite_backup.py" \
    inspect --source "$backup_path" \
    --deadline-seconds "$SQLITE_BACKUP_DEADLINE_SECONDS")" || return 1
  [[ "$actual_metadata" == "$expected_metadata" ]]
}

assert_release_tree_security() {
  local release_root="$1"
  local service_user="$2"
  local writable
  local -a acl_status
  if LC_ALL=C getfacl -R -c -p -P -- "$release_root" \
    | grep -Eq '^(default:|user:[^:]|group:[^:])'; then
    fail "release tree contains an extended or default ACL"
  else
    acl_status=("${PIPESTATUS[@]}")
    [[ "${acl_status[0]}" == "0" && "${acl_status[1]}" == "1" ]] \
      || fail "cannot verify release tree ACLs"
  fi
  writable="$(runuser -u "$service_user" -- "$SH_BIN" -c \
    'cd / && exec "$1" "$2" -xdev -writable -print -quit' \
    sh "$FIND_BIN" "$release_root")" \
    || fail "cannot evaluate release write access as the service account"
  [[ -z "$writable" ]] \
    || fail "release tree is writable by the systemd service account"
}

assert_trusted_root_directory_path() {
  local directory="$1"
  local label="$2"
  local current
  local owner_group
  local mode
  [[ -d "$directory" && ! -L "$directory" \
    && "$("$TRUST_REALPATH_BIN" -e -- "$directory" 2>/dev/null)" == "$directory" ]] \
    || fail "$label must be a canonical real directory"
  current="$directory"
  while :; do
    [[ -d "$current" && ! -L "$current" \
      && "$("$TRUST_REALPATH_BIN" -e -- "$current" 2>/dev/null)" == "$current" ]] \
      || fail "$label path contains a symbolic link or non-directory"
    owner_group="$("$TRUST_STAT_BIN" -c '%u:%g' -- "$current" 2>/dev/null)"
    mode="$("$TRUST_STAT_BIN" -c '%a' -- "$current" 2>/dev/null)"
    [[ "$owner_group" == "0:0" && "$mode" =~ ^[0-7]{3,4}$ ]] \
      || fail "$label path must be owned by root:root"
    (( (8#$mode & 0022) == 0 )) \
      || fail "$label path must not be writable by group or other"
    assert_no_extended_acl "$current" "$label path component"
    [[ "$current" == "/" ]] && break
    current="$("$TRUST_DIRNAME_BIN" -- "$current")"
  done
}

assert_trusted_root_file_path() {
  local file="$1"
  local label="$2"
  [[ -f "$file" && ! -L "$file" \
    && "$("$TRUST_REALPATH_BIN" -e -- "$file" 2>/dev/null)" == "$file" ]] \
    || fail "$label must be a canonical regular non-symlink file"
  [[ "$("$TRUST_STAT_BIN" -c '%u:%g:%a' -- "$file" 2>/dev/null)" == "0:0:600" ]] \
    || fail "$label must be root:root mode 0600"
  assert_no_extended_acl "$file" "$label"
  assert_trusted_root_directory_path \
    "$("$TRUST_DIRNAME_BIN" -- "$file")" "$label parent directory"
}

assert_trusted_code_file() {
  local file="$1"
  local label="$2"
  local mode
  [[ -f "$file" && ! -L "$file" \
    && "$("$TRUST_REALPATH_BIN" -e -- "$file" 2>/dev/null)" == "$file" ]] \
    || fail "$label must be a canonical regular non-symlink file"
  [[ "$("$TRUST_STAT_BIN" -c '%u:%g' -- "$file" 2>/dev/null)" == "0:0" ]] \
    || fail "$label must be owned by root:root"
  mode="$("$TRUST_STAT_BIN" -c '%a' -- "$file" 2>/dev/null)"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] || fail "$label mode is invalid"
  (( (8#$mode & 0022) == 0 )) || fail "$label must not be writable by group or other"
  assert_no_extended_acl "$file" "$label"
  assert_trusted_root_directory_path \
    "$("$TRUST_DIRNAME_BIN" -- "$file")" "$label parent directory"
}

assert_trusted_record_file() {
  local file="$1"
  local label="$2"
  [[ -f "$file" && ! -L "$file" \
    && "$("$TRUST_REALPATH_BIN" -e -- "$file" 2>/dev/null)" == "$file" ]] \
    || fail "$label must be a canonical regular non-symlink file"
  [[ "$("$TRUST_STAT_BIN" -c '%u:%g:%a' -- "$file" 2>/dev/null)" == "0:0:640" ]] \
    || fail "$label must be root:root mode 0640"
  assert_no_extended_acl "$file" "$label"
  assert_trusted_root_directory_path \
    "$("$TRUST_DIRNAME_BIN" -- "$file")" "$label parent directory"
}

resolve_and_pin_trusted_command() {
  local name="$1"
  local variable="$2"
  local candidate
  local resolved
  builtin unset -f "$name" 2>/dev/null || :
  candidate="$(builtin type -P -- "$name")" \
    || fail "$name is required"
  resolved="$("$TRUST_REALPATH_BIN" -e -- "$candidate" 2>/dev/null)" \
    || fail "$name executable cannot be resolved"
  case "$resolved" in
    /usr/bin/*|/usr/sbin/*) ;;
    *) fail "$name executable is outside the trusted system command roots" ;;
  esac
  assert_trusted_code_file "$resolved" "system command $name"
  builtin hash -p "$resolved" "$name" \
    || fail "$name executable cannot be pinned"
  builtin printf -v "$variable" '%s' "$resolved"
}

assert_secure_systemd_directory() {
  local directory="$1"
  local label="$2"
  local owner_group
  local mode
  assert_trusted_root_directory_path "$directory" "$label path"
  [[ -d "$directory" && ! -L "$directory" \
    && "$(realpath -e -- "$directory")" == "$directory" ]] \
    || fail "$label must be a canonical real directory"
  owner_group="$(stat -c '%u:%g' -- "$directory")"
  mode="$(stat -c '%a' -- "$directory")"
  [[ "$owner_group" == "0:0" && "$mode" =~ ^[0-7]{3,4}$ ]] \
    || fail "$label must be owned by root:root"
  (( (8#$mode & 0022) == 0 )) \
    || fail "$label must not be writable by group or other"
  if runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -w "$directory"; then
    fail "$label is writable by the service account"
  fi
}

assert_secure_systemd_file() {
  local file="$1"
  local label="$2"
  local owner_group
  local mode
  [[ -f "$file" && ! -L "$file" ]] \
    || fail "$label must be a regular non-symlink file"
  [[ "$("$TRUST_REALPATH_BIN" -e -- "$file" 2>/dev/null)" == "$file" ]] \
    || fail "$label must use a canonical path"
  owner_group="$(stat -c '%u:%g' -- "$file")"
  mode="$(stat -c '%a' -- "$file")"
  [[ "$owner_group" == "0:0" && "$mode" =~ ^[0-7]{3,4}$ ]] \
    || fail "$label must be owned by root:root"
  (( (8#$mode & 0022) == 0 )) \
    || fail "$label must not be writable by group or other"
  assert_no_extended_acl "$file" "$label"
  assert_trusted_root_directory_path \
    "$("$TRUST_DIRNAME_BIN" -- "$file")" "$label parent directory"
  if runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -w "$file"; then
    fail "$label is writable by the service account"
  fi
}

validate_passed_release_record() {
  local record="${1:-$DEPLOYMENT_DIR/$PREVIOUS_ID.json}"
  local fields
  local baseline_verification_json
  assert_trusted_record_file "$record" "recorded previous release passed record"
  mapfile -t fields < <("$PYTHON_BIN" -I - "$record" "$PREVIOUS_ID" \
    "$PUBLIC_ORIGIN" "$PUBLIC_HOST" "$MODERN_EXEC_START_PRE_ARGVS_JSON" \
    "$RUNTIME_BASELINE_DIR/$PREVIOUS_ID.json" "$MANAGED_DROPIN" <<'PY'
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result

record = json.loads(
    Path(sys.argv[1]).read_text(encoding="utf-8"),
    object_pairs_hook=strict_object,
    parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
)
if not isinstance(record, dict):
    raise SystemExit("previous release deployment record is not a JSON object")
schema = record.get("schema_version")
if type(schema) is not int or schema not in {2, 3, 4, 5}:
    raise SystemExit("previous release deployment record schema is invalid")
print(schema)
if schema != 5:
    raise SystemExit(0)

def valid_database_backup(value: object) -> bool:
    keys = {
        "basename", "sha256", "size_bytes", "integrity_check", "page_count",
        "page_size", "user_version", "schema_version", "application_id",
        "schema_sha256",
    }
    if not isinstance(value, dict) or set(value) != keys:
        return False
    if not isinstance(value["basename"], str) or not re.fullmatch(
        r"security-[0-9A-Za-z._-]{1,200}\.sqlite3", value["basename"]
    ):
        return False
    if value["integrity_check"] != "ok":
        return False
    if any(not isinstance(value[name], str) for name in ("sha256", "schema_sha256")):
        return False
    if any(not re.fullmatch(r"[0-9a-f]{64}", value[name]) for name in ("sha256", "schema_sha256")):
        return False
    integers = (
        "size_bytes", "page_count", "page_size", "user_version",
        "schema_version", "application_id",
    )
    if any(type(value[name]) is not int for name in integers):
        return False
    page_size = value["page_size"]
    return (
        value["size_bytes"] >= 0
        and value["page_count"] >= 0
        and value["schema_version"] >= 0
        and 512 <= page_size <= 65536
        and page_size & (page_size - 1) == 0
        and value["size_bytes"] == value["page_count"] * page_size
        and -(2**31) <= value["user_version"] < 2**31
        and -(2**31) <= value["application_id"] < 2**31
    )

expected_keys = {
    "schema_version", "status", "release_id", "version", "previous_release_id",
    "archive_sha256", "release_manifest_sha256", "deployed_at", "systemd",
    "public_origin", "public_host", "runtime_fingerprint", "database_backup",
    "runtime_baseline_path", "runtime_baseline_sha256",
    "runtime_fingerprint_sha256", "runtime_guard_helper_sha256", "checks",
}
expected_systemd_keys = {
    "fragment_sha256_before", "dropin_paths_before", "managed_dropin_sha256_before",
    "managed_dropin_sha256_after", "fragment_backup", "managed_dropin_backup",
    "runtime_mode", "environment_file_sha256", "exec_start_pre_argvs",
}
expected_checks = {
    "archive_manifest", "prepared_release_durable", "release_permissions_normalized",
    "release_tree_immutable", "service_user_import", "isolated_service_user_preflight",
    "security_database_backup", "known_good_health_before_switch",
    "service_disabled_during_switch", "service_stopped_before_switch", "atomic_symlink",
    "managed_systemd_dropin", "effective_runtime", "running_process_runtime",
    "systemd_active", "local_health", "public_health", "public_login_redirect",
    "production_environment_validated_three_phases",
    "final_publication_configuration_gate", "ordinary_restart_environment_gate",
    "ordinary_restart_integrity_gate", "service_enabled_after_health",
}
systemd = record.get("systemd")
checks = record.get("checks")
hex_pattern = re.compile(r"[0-9a-f]{64}\Z")
release_pattern = re.compile(r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}\Z")
name_pattern = re.compile(r"[0-9A-Za-z_.@-]{1,200}\Z")
dropins_before = systemd.get("dropin_paths_before") if isinstance(systemd, dict) else None
managed_before = systemd.get("managed_dropin_sha256_before") if isinstance(systemd, dict) else None
managed_backup = systemd.get("managed_dropin_backup") if isinstance(systemd, dict) else None
if (
    set(record) != expected_keys
    or record.get("schema_version") != 5
    or record.get("status") != "passed"
    or record.get("release_id") != sys.argv[2]
    or not isinstance(record.get("previous_release_id"), str)
    or release_pattern.fullmatch(record["previous_release_id"]) is None
    or not isinstance(record.get("version"), str)
    or not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}", record["version"])
    or not isinstance(record.get("archive_sha256"), str)
    or hex_pattern.fullmatch(record["archive_sha256"]) is None
    or not isinstance(record.get("release_manifest_sha256"), str)
    or hex_pattern.fullmatch(record["release_manifest_sha256"]) is None
    or not isinstance(record.get("deployed_at"), str)
    or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", record["deployed_at"]) is None
    or not isinstance(systemd, dict)
    or set(systemd) != expected_systemd_keys
    or systemd.get("runtime_mode") != "release-local-venv-dropin"
    or dropins_before not in ([], [sys.argv[7]])
    or (dropins_before == [] and (managed_before is not None or managed_backup is not None))
    or (dropins_before == [sys.argv[7]] and (
        not isinstance(managed_before, str)
        or hex_pattern.fullmatch(managed_before) is None
        or not isinstance(managed_backup, str)
        or name_pattern.fullmatch(managed_backup) is None
    ))
    or not isinstance(systemd.get("fragment_sha256_before"), str)
    or hex_pattern.fullmatch(systemd["fragment_sha256_before"]) is None
    or not isinstance(systemd.get("managed_dropin_sha256_after"), str)
    or hex_pattern.fullmatch(systemd["managed_dropin_sha256_after"]) is None
    or not isinstance(systemd.get("environment_file_sha256"), str)
    or hex_pattern.fullmatch(systemd["environment_file_sha256"]) is None
    or not isinstance(systemd.get("fragment_backup"), str)
    or name_pattern.fullmatch(systemd["fragment_backup"]) is None
    or systemd.get("exec_start_pre_argvs") != json.loads(sys.argv[5])
    or record.get("public_origin") != sys.argv[3]
    or record.get("public_host") != sys.argv[4]
    or not isinstance(record.get("runtime_fingerprint"), dict)
    or type(record["runtime_fingerprint"].get("schema_version")) is not int
    or record["runtime_fingerprint"]["schema_version"] != 2
    or not isinstance(record["runtime_fingerprint"].get("release_root_sha256"), str)
    or hex_pattern.fullmatch(record["runtime_fingerprint"]["release_root_sha256"]) is None
    or not valid_database_backup(record.get("database_backup"))
    or record.get("runtime_baseline_path") != sys.argv[6]
    or not isinstance(record.get("runtime_baseline_sha256"), str)
    or hex_pattern.fullmatch(record["runtime_baseline_sha256"]) is None
    or not isinstance(record.get("runtime_fingerprint_sha256"), str)
    or hex_pattern.fullmatch(record["runtime_fingerprint_sha256"]) is None
    or not isinstance(record.get("runtime_guard_helper_sha256"), str)
    or hex_pattern.fullmatch(record["runtime_guard_helper_sha256"]) is None
    or not isinstance(checks, dict)
    or set(checks) != expected_checks
    or any(value is not True for value in checks.values())
):
    raise SystemExit("previous release deployment record is not a complete passed runtime")
print(record["version"])
print(record["archive_sha256"])
print(record["release_manifest_sha256"])
print(json.dumps(record["runtime_fingerprint"], ensure_ascii=False, sort_keys=True, separators=(",", ":")))
print(record["runtime_baseline_sha256"])
print(record["runtime_fingerprint_sha256"])
print(record["runtime_guard_helper_sha256"])
PY
  )
  [[ "${#fields[@]}" -ge 1 ]] \
    || fail "recorded previous release passed record schema is unreadable"
  PREVIOUS_RECORD_SCHEMA="${fields[0]}"
  require_activatable_passed_record_schema "$PREVIOUS_RECORD_SCHEMA"
  [[ "${#fields[@]}" == "8" ]] \
    || fail "recorded previous release passed record fields are incomplete"
  PREVIOUS_EXPECTED_VERSION="${fields[1]}"
  PREVIOUS_ARCHIVE_SHA256="${fields[2]}"
  PREVIOUS_MANIFEST_SHA256="${fields[3]}"
  PREVIOUS_RUNTIME_FINGERPRINT_JSON="${fields[4]}"
  PREVIOUS_RUNTIME_BASELINE_SHA256="${fields[5]}"
  PREVIOUS_RUNTIME_FINGERPRINT_SHA256="${fields[6]}"
  PREVIOUS_RUNTIME_GUARD_HELPER_SHA256="${fields[7]}"
  [[ "$(sha256sum "$RUNTIME_BASELINE_DIR/$PREVIOUS_ID.json" | awk '{print $1}')" \
    == "$PREVIOUS_RUNTIME_BASELINE_SHA256" \
    && "$(printf '%s' "$PREVIOUS_RUNTIME_FINGERPRINT_JSON" | sha256sum | awk '{print $1}')" \
    == "$PREVIOUS_RUNTIME_FINGERPRINT_SHA256" \
    && "$(sha256sum "$RUNTIME_GUARD_HELPER" | awk '{print $1}')" \
    == "$PREVIOUS_RUNTIME_GUARD_HELPER_SHA256" ]] \
    || fail "recorded schema 5 release disagrees with runtime baseline, fingerprint, or helper bytes"
  baseline_verification_json="$(verify_release_runtime_baseline \
    "$PREVIOUS_ID" "$PREVIOUS_TARGET" "$PREVIOUS_MANIFEST_SHA256")" \
    || fail "recorded release external runtime baseline is missing or invalid"
  runtime_baseline_verification_matches_record \
    "$baseline_verification_json" "$PREVIOUS_ID" "$PREVIOUS_EXPECTED_VERSION" \
    "$PREVIOUS_MANIFEST_SHA256" "$PREVIOUS_RUNTIME_BASELINE_SHA256" \
    "$PREVIOUS_RUNTIME_FINGERPRINT_SHA256" "$PREVIOUS_RUNTIME_GUARD_HELPER_SHA256" \
    || fail "recorded release runtime baseline evidence disagrees with its schema 5 passed record"
}

validate_legacy_baseline() {
  local legacy_id="${PROTOCOL_STUDIO_LEGACY_RELEASE_ID:-20260722-114300-620b1bcf9aa9}"
  local record="$DEPLOYMENT_DIR/legacy-baseline-$legacy_id.json"
  local runtime_json
  [[ "$PREVIOUS_ID" == "$legacy_id" ]] \
    || fail "recorded shared-runtime target is not the registered legacy release"
  [[ -f "$record" && ! -L "$record" \
    && "$(stat -c '%u:%g:%a' -- "$record")" == "0:0:600" ]] \
    || fail "registered legacy baseline record is missing or unsafe"
  assert_trusted_root_file_path "$record" "registered legacy baseline record"
  runtime_json="$(runtime_fingerprint "$APP_ROOT/.venv" "$APP_ROOT/.venv/bin/python")" \
    || fail "cannot fingerprint the registered legacy runtime"
  "$PYTHON_BIN" -I - "$record" "$legacy_id" "$FRAGMENT_PATH" "$PREVIOUS_TARGET" \
    "$APP_ROOT/.venv" "$runtime_json" <<'PY'
from __future__ import annotations
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

record_path, release_id, fragment_name, release_name, runtime_name, runtime_json = sys.argv[1:]
def digest(root_name: str, include_metadata: bool) -> str:
    root = Path(root_name).resolve()
    result = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix().encode()
        metadata = path.lstat()
        prefix = f"{stat.S_IMODE(metadata.st_mode):04o}:{metadata.st_uid}:{metadata.st_gid}".encode()
        if path.is_symlink():
            if include_metadata:
                result.update(b"L\0" + rel + b"\0" + prefix + b"\0" + os.readlink(path).encode() + b"\0")
            else:
                result.update(b"L\0" + rel + b"\0" + os.readlink(path).encode() + b"\0")
        elif path.is_dir():
            result.update(b"D\0" + rel + b"\0" + (prefix + b"\0" if include_metadata else b""))
        elif path.is_file():
            result.update(b"F\0" + rel + b"\0" + (prefix + b"\0" if include_metadata else b""))
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    result.update(chunk)
            result.update(b"\0")
        else:
            raise SystemExit("unsupported legacy tree entry")
    return result.hexdigest()
fragment = Path(fragment_name)
expected = {
    "schema_version": 2,
    "release_id": release_id,
    "fragment_path": fragment_name,
    "fragment_sha256": hashlib.sha256(fragment.read_bytes()).hexdigest(),
    "dropin_paths": [],
    "legacy_release_sha256": digest(release_name, True),
    "runtime_fingerprint": json.loads(runtime_json),
}
if json.loads(Path(record_path).read_text(encoding="utf-8")) != expected:
    raise SystemExit("legacy baseline drifted from the registered runtime")
PY
}

validate_previous_runtime_provenance() {
  case "$PREVIOUS_RUNTIME_MODE" in
    release)
      [[ "$(runtime_fingerprint "$PREVIOUS_TARGET/.venv" "$PREVIOUS_RUNTIME" \
        "$PREVIOUS_TARGET/requirements.production.lock.txt" "$PREVIOUS_TARGET")" \
        == "$PREVIOUS_RUNTIME_FINGERPRINT_JSON" ]] \
        || fail "recorded previous release runtime fingerprint drifted from its passed record"
      "$PYTHON_BIN" -I "$SCRIPT_DIR/verify_installed_release.py" \
        "$PREVIOUS_TARGET" --expected-version "$PREVIOUS_EXPECTED_VERSION" \
        || fail "recorded previous release installed source verification failed"
      [[ "$(sha256sum "$PREVIOUS_TARGET/release-manifest.json" | awk '{print $1}')" \
        == "$PREVIOUS_MANIFEST_SHA256" ]] \
        || fail "recorded previous release manifest digest drifted from its passed record"
      assert_release_tree_security "$PREVIOUS_TARGET" "$PREVIOUS_SERVICE_USER"
      verify_release_runtime_baseline \
        "$PREVIOUS_ID" "$PREVIOUS_TARGET" "$PREVIOUS_MANIFEST_SHA256" >/dev/null \
        || fail "recorded previous release external runtime baseline drifted"
      ;;
    legacy)
      validate_legacy_baseline
      ;;
    *)
      fail "unsupported previous runtime mode for provenance validation"
      ;;
  esac
}

CONFIRMED="false"
while (($#)); do
  case "$1" in
    --confirm-recovery)
      CONFIRMED="true"
      shift
      ;;
    --help|-h)
      printf 'Usage: recover-transaction.sh --confirm-recovery\n'
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

[[ "$EUID" == "0" ]] || fail "run as root"
[[ "$CONFIRMED" == "true" ]] || fail "explicit interrupted-transaction recovery confirmation is required"

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
case "$SCRIPT_SOURCE" in
  */*) SCRIPT_PARENT="${SCRIPT_SOURCE%/*}" ;;
  *) SCRIPT_PARENT="." ;;
esac
SCRIPT_DIR="$(builtin cd -- "$SCRIPT_PARENT" && builtin pwd -P)"
for trusted_bootstrap in \
  "$TRUST_REALPATH_BIN" "$TRUST_STAT_BIN" "$TRUST_DIRNAME_BIN" \
  "$TRUST_GETFACL_BIN" "$TRUST_GREP_BIN"; do
  assert_trusted_code_file "$trusted_bootstrap" "trusted command bootstrap"
done
PYTHON_BIN=""
FIND_BIN=""
SH_BIN=""
TEST_BIN=""
resolve_and_pin_trusted_command python3 PYTHON_BIN
resolve_and_pin_trusted_command find FIND_BIN
resolve_and_pin_trusted_command sh SH_BIN
resolve_and_pin_trusted_command test TEST_BIN
TRUSTED_COMMAND_PATH=""
for trusted_command in \
  awk basename cat chmod chown cmp cp curl dirname flock getfacl grep id install ln \
  journalctl mv readlink realpath rm runuser sed seq sha256sum sleep stat sync \
  systemctl systemd-run; do
  resolve_and_pin_trusted_command "$trusted_command" TRUSTED_COMMAND_PATH
done
builtin unset TRUSTED_COMMAND_PATH
builtin readonly PYTHON_BIN FIND_BIN SH_BIN TEST_BIN
for trusted_helper in \
  "$SCRIPT_DIR/recover-transaction.sh" \
  "$SCRIPT_DIR/atomic_rename.py" \
  "$SCRIPT_DIR/run_with_env.py" \
  "$SCRIPT_DIR/runtime_fingerprint.py" \
  "$SCRIPT_DIR/sqlite_backup.py" \
  "$SCRIPT_DIR/validate_production_env.py" \
  "$SCRIPT_DIR/verify_installed_release.py"; do
  assert_trusted_code_file "$trusted_helper" "recovery control helper"
done
APP_ROOT="${PROTOCOL_STUDIO_DEPLOY_ROOT:-/srv/apps/protocol-studio}"
ENV_FILE="${PROTOCOL_STUDIO_ENV_FILE:-/etc/protocol-studio/protocol-studio.env}"
SERVICE="${PROTOCOL_STUDIO_SYSTEMD_SERVICE:-protocol-studio.service}"
PUBLIC_ORIGIN="${PROTOCOL_STUDIO_PUBLIC_ORIGIN:-https://protocol.feian.online}"
LOCAL_PORT="${PROTOCOL_STUDIO_LOCAL_PORT:-18771}"
PREFLIGHT_PORT="${PROTOCOL_STUDIO_PREFLIGHT_PORT:-18772}"
[[ "$SERVICE" =~ ^[0-9A-Za-z_.@-]+\.service$ ]] || fail "invalid systemd service name"
[[ "$LOCAL_PORT" =~ ^[0-9]+$ && "$PREFLIGHT_PORT" =~ ^[0-9]+$ ]] \
  || fail "local ports must be numeric"
((LOCAL_PORT >= 1 && LOCAL_PORT <= 65535)) || fail "local service port is invalid"
((PREFLIGHT_PORT >= 1 && PREFLIGHT_PORT <= 65535)) || fail "preflight port is invalid"
[[ "$LOCAL_PORT" != "$PREFLIGHT_PORT" ]] || fail "preflight port must differ from the production port"
[[ "$APP_ROOT" == /* && "$ENV_FILE" == /* ]] || fail "recovery paths must be absolute"

PUBLIC_ORIGIN="${PUBLIC_ORIGIN%/}"
PUBLIC_HOST="${PUBLIC_ORIGIN#*://}"
PUBLIC_HOST="${PUBLIC_HOST%%/*}"
PUBLIC_HOST="${PUBLIC_HOST%%:*}"
PUBLIC_HOST="${PUBLIC_HOST,,}"
[[ -n "$PUBLIC_HOST" ]] || fail "public origin has no host"
CALLER_PUBLIC_ORIGIN="$PUBLIC_ORIGIN"
CALLER_PUBLIC_HOST="$PUBLIC_HOST"
builtin readonly SQLITE_BACKUP_DEADLINE_SECONDS=300
builtin readonly SERVICE_TERM_GRACE_ATTEMPTS=50
builtin readonly SERVICE_KILL_REAP_ATTEMPTS=50
builtin readonly SERVICE_STOP_POLL_SECONDS=0.1
builtin readonly CANARY_RUNTIME_MAX_SECONDS=120
builtin readonly CANARY_HEALTH_ATTEMPTS=20
builtin readonly CANARY_HEALTH_MAX_SECONDS=1
builtin readonly CANARY_HEALTH_POLL_SECONDS=0.25
builtin readonly SERVICE_HEALTH_ATTEMPTS=30
builtin readonly SERVICE_HEALTH_MAX_SECONDS=2
builtin readonly SERVICE_HEALTH_POLL_SECONDS=1

RELEASES_DIR="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
RUNTIME_GUARD_DIR="$APP_ROOT/runtime-guard"
RUNTIME_GUARD_HELPER="$RUNTIME_GUARD_DIR/runtime_fingerprint.py"
RUNTIME_BASELINE_DIR="$RUNTIME_GUARD_DIR/baselines"
SHARED_DIR="$APP_ROOT/shared"
RUNS_DIR="$SHARED_DIR/runs"
SECURITY_DB="$SHARED_DIR/security.sqlite3"
CONTROL_DIR="$APP_ROOT/.deploy-state"
LOG_DIR="$CONTROL_DIR/logs"
BACKUP_DIR="$CONTROL_DIR/backups"
DEPLOYMENT_DIR="$CONTROL_DIR/deployments"
SYSTEMD_CONFIG_DIR="/etc/systemd/system"
SYSTEMD_UNIT_FILE="$SYSTEMD_CONFIG_DIR/$SERVICE"
MANAGED_DROPIN_DIR="/etc/systemd/system/$SERVICE.d"
MANAGED_DROPIN="$MANAGED_DROPIN_DIR/90-release-runtime.conf"
RUNTIME_SYSTEMD_DIR="/run/systemd/system"
TRANSACTION_RUNTIME_GUARD_DIR="$RUNTIME_SYSTEMD_DIR/$SERVICE.d"
TRANSACTION_RUNTIME_GUARD="$TRANSACTION_RUNTIME_GUARD_DIR/99-transaction-runtime-guard.conf"
TRANSACTION_FILE="$APP_ROOT/.deploy-transaction.json"
MODERN_EXEC_ARGV="$CURRENT_LINK/.venv/bin/python -I -B -u -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $LOCAL_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1"
MODERN_RUNTIME_GUARD_EXEC_START_PRE_ARGV="/usr/bin/python3 -I -B -u $RUNTIME_GUARD_HELPER --verify-current $CURRENT_LINK --releases-root $RELEASES_DIR --baseline-directory $RUNTIME_BASELINE_DIR --require-root-owned-immutable"
MODERN_ENVIRONMENT_EXEC_START_PRE_ARGV="$CURRENT_LINK/.venv/bin/python -I -B -u $CURRENT_LINK/deploy/validate_production_env.py --shared-runs $RUNS_DIR --security-db $SECURITY_DB --public-origin $PUBLIC_ORIGIN --public-host $PUBLIC_HOST"
MODERN_EXEC_START_PRE_ARGVS_JSON="$("$PYTHON_BIN" -I -c \
  'import json,sys; print(json.dumps(sys.argv[1:], ensure_ascii=False, separators=(",", ":")))' \
  "$MODERN_RUNTIME_GUARD_EXEC_START_PRE_ARGV" "$MODERN_ENVIRONMENT_EXEC_START_PRE_ARGV")"

assert_trusted_root_directory_path "$APP_ROOT" "application root"
assert_trusted_root_directory_path "$RELEASES_DIR" "release storage directory"
assert_trusted_root_directory_path "$CONTROL_DIR" "deployment control directory"
assert_trusted_root_directory_path "$LOG_DIR" "deployment log directory"
assert_trusted_root_directory_path "$BACKUP_DIR" "deployment backup directory"
assert_trusted_root_directory_path "$DEPLOYMENT_DIR" "deployment record directory"
[[ -d "$SHARED_DIR" && ! -L "$SHARED_DIR" \
  && "$(realpath -e -- "$SHARED_DIR")" == "$SHARED_DIR" \
  && -d "$RUNS_DIR" && ! -L "$RUNS_DIR" \
  && "$(realpath -e -- "$RUNS_DIR")" == "$RUNS_DIR" \
  && -f "$SECURITY_DB" && ! -L "$SECURITY_DB" \
  && "$(realpath -e -- "$SECURITY_DB")" == "$SECURITY_DB" ]] \
  || fail "shared production state is missing or unsafe"
assert_trusted_root_file_path "$ENV_FILE" "production environment file"
"$PYTHON_BIN" -I "$SCRIPT_DIR/run_with_env.py" --env-file "$ENV_FILE" \
  --validate-only --reject-privileged-loader-variables
assert_trusted_root_file_path "$TRANSACTION_FILE" "active interrupted-transaction marker"
LOCK_FILE="$CONTROL_DIR/deploy.lock"
[[ -f "$LOCK_FILE" && ! -L "$LOCK_FILE" \
  && "$(stat -c '%u:%g:%a' -- "$LOCK_FILE")" == "0:0:600" ]] \
  || fail "deployment lock must be a root-owned regular file with mode 0600"
assert_trusted_root_file_path "$LOCK_FILE" "deployment lock"
exec 9<>"$LOCK_FILE"
flock -n 9 || fail "another deployment operation is running"
LEGACY_LOCK_FILE="$APP_ROOT/.deploy.lock"
if [[ -e "$LEGACY_LOCK_FILE" || -L "$LEGACY_LOCK_FILE" ]]; then
  [[ -f "$LEGACY_LOCK_FILE" && ! -L "$LEGACY_LOCK_FILE" \
    && "$(realpath -e -- "$LEGACY_LOCK_FILE")" == "$LEGACY_LOCK_FILE" \
    && "$(stat -c '%u:%g' -- "$LEGACY_LOCK_FILE")" == "0:0" ]] \
    || fail "legacy deployment lock is not a trusted root-owned regular file"
  LEGACY_LOCK_MODE="$(stat -c '%a' -- "$LEGACY_LOCK_FILE")"
  [[ "$LEGACY_LOCK_MODE" =~ ^[0-7]{3,4}$ ]] \
    || fail "legacy deployment lock mode is invalid"
  (( (8#$LEGACY_LOCK_MODE & 0022) == 0 )) \
    || fail "legacy deployment lock is writable by group or other"
  assert_no_extended_acl "$LEGACY_LOCK_FILE" "legacy deployment lock"
  exec 8<>"$LEGACY_LOCK_FILE"
  flock -n 8 || fail "a legacy deployment operation is running"
fi
assert_trusted_root_file_path "$TRANSACTION_FILE" \
  "locked active interrupted-transaction marker"
verify_atomic_rename_boundary \
  || fail "application and deployment-record directories failed the atomic rename boundary gate"
probe_service_enablement
INITIAL_ENABLE_STATE="$SERVICE_ENABLE_STDOUT"
INITIAL_ENABLE_EXIT="$SERVICE_ENABLE_EXIT"
[[ ( "$INITIAL_ENABLE_STATE" == "enabled" && "$INITIAL_ENABLE_EXIT" == "0" ) \
  || ( "$INITIAL_ENABLE_STATE" == "disabled" && "$INITIAL_ENABLE_EXIT" == "1" ) ]] \
  || fail "interrupted transaction service enablement readback is neither exact enabled nor exact disabled"

mapfile -d '' -t TX_FIELDS < <("$PYTHON_BIN" -I - "$TRANSACTION_FILE" "$MANAGED_DROPIN" <<'PY'
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

path = Path(sys.argv[1])
managed = sys.argv[2]

def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result

def reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number")

record = json.loads(
    path.read_text(encoding="utf-8"),
    object_pairs_hook=strict_object,
    parse_constant=reject_constant,
)
if (
    not isinstance(record, dict)
    or type(record.get("schema_version")) is not int
    or record["schema_version"] != 3
):
    raise SystemExit("invalid interrupted-transaction schema")
status = record.get("status")
common_keys = {
    "schema_version", "status", "previous_release_id", "previous_target",
    "fragment_path", "fragment_sha256", "dropin_paths_before",
    "managed_dropin_sha256_before", "fragment_backup", "managed_dropin_backup",
    "previous_exec_path", "previous_exec_argv", "previous_working_directory",
    "previous_service_user", "previous_service_group", "previous_environment_files",
    "previous_read_write_paths", "previous_umask", "environment_file_sha256",
    "public_origin", "public_host",
    "database_backup", "prepared_release_durable", "service_enabled_before_switch",
    "known_good_health_before_switch", "started_at",
}
if status in {"switching", "deploy_committed_pending_activation"}:
    expected_keys = common_keys | {"release_id"}
    operation = "deploy"
    target_release_id = record.get("release_id")
    target_runtime_mode = "release"
    if not isinstance(record.get("release_id"), str) or not re.fullmatch(
        r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}", record["release_id"]
    ):
        raise SystemExit("invalid transaction release id")
elif status in {"rolling_back", "rollback_committed_pending_activation"}:
    expected_keys = common_keys | {"target_release_id", "target_runtime_mode"}
    operation = "rollback"
    target_release_id = record.get("target_release_id")
    target_runtime_mode = record.get("target_runtime_mode")
    if not isinstance(record.get("target_release_id"), str) or not re.fullmatch(
        r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}", record["target_release_id"]
    ):
        raise SystemExit("invalid rollback target release id")
    if record.get("target_runtime_mode") not in {"release", "legacy"}:
        raise SystemExit("invalid rollback target runtime mode")
elif status == "recovery_committed_pending_activation":
    if "release_id" in record:
        expected_keys = common_keys | {
            "release_id", "recovery_activation_release_id",
            "recovery_activation_runtime_mode",
        }
        operation = "deploy"
        if not isinstance(record.get("release_id"), str) or not re.fullmatch(
            r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}", record["release_id"]
        ):
            raise SystemExit("invalid original deploy release id")
    elif "target_release_id" in record or "target_runtime_mode" in record:
        expected_keys = common_keys | {
            "target_release_id", "target_runtime_mode",
            "recovery_activation_release_id", "recovery_activation_runtime_mode",
        }
        operation = "rollback"
        if not isinstance(record.get("target_release_id"), str) or not re.fullmatch(
            r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}", record["target_release_id"]
        ):
            raise SystemExit("invalid original rollback target release id")
        if record.get("target_runtime_mode") not in {"release", "legacy"}:
            raise SystemExit("invalid original rollback runtime mode")
    else:
        raise SystemExit("recovery-committed marker has no original operation shape")
    target_release_id = record.get("recovery_activation_release_id")
    target_runtime_mode = record.get("recovery_activation_runtime_mode")
    if target_release_id != record.get("previous_release_id"):
        raise SystemExit("recovery-committed marker changed the precommit recovery target")
    if target_runtime_mode not in {"release", "legacy"}:
        raise SystemExit("recovery-committed marker runtime mode is invalid")
else:
    raise SystemExit("unsupported interrupted-transaction status")
if set(record) != expected_keys:
    raise SystemExit("interrupted-transaction fields do not match its schema")
if not isinstance(record.get("started_at"), str) or not re.fullmatch(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
    record["started_at"],
):
    raise SystemExit("invalid interrupted-transaction timestamp")
public_origin = record.get("public_origin")
public_host = record.get("public_host")
if not isinstance(public_origin, str) or not isinstance(public_host, str):
    raise SystemExit("transaction public identity fields are invalid")
parsed_origin = urlsplit(public_origin)
if (
    parsed_origin.scheme != "https"
    or parsed_origin.hostname != public_host
    or parsed_origin.username is not None
    or parsed_origin.password is not None
    or parsed_origin.query
    or parsed_origin.fragment
    or parsed_origin.path != ""
    or public_host != public_host.casefold()
    or not re.fullmatch(
        r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*\Z",
        public_host,
    )
):
    raise SystemExit("transaction public identity is not canonical")

database_backup = record.get("database_backup")
database_keys = {
    "basename", "sha256", "size_bytes", "integrity_check", "page_count",
    "page_size", "user_version", "schema_version", "application_id",
    "schema_sha256",
}
if not isinstance(database_backup, dict) or set(database_backup) != database_keys:
    raise SystemExit("invalid database backup metadata")
if not isinstance(database_backup["basename"], str) or not re.fullmatch(
    r"security-[0-9A-Za-z._-]{1,200}\.sqlite3", database_backup["basename"]
):
    raise SystemExit("invalid database backup basename")
if database_backup["integrity_check"] != "ok":
    raise SystemExit("database backup integrity evidence is invalid")
for key in ("sha256", "schema_sha256"):
    if not isinstance(database_backup[key], str) or not re.fullmatch(
        r"[0-9a-f]{64}", database_backup[key]
    ):
        raise SystemExit("invalid database backup digest")
database_integer_keys = (
    "size_bytes", "page_count", "page_size", "user_version",
    "schema_version", "application_id",
)
if any(type(database_backup[key]) is not int for key in database_integer_keys):
    raise SystemExit("invalid database backup numeric metadata")
page_size = database_backup["page_size"]
if not (
    database_backup["size_bytes"] >= 0
    and database_backup["page_count"] >= 0
    and database_backup["schema_version"] >= 0
    and 512 <= page_size <= 65536
    and (page_size & (page_size - 1)) == 0
    and database_backup["size_bytes"] == database_backup["page_count"] * page_size
    and -(2**31) <= database_backup["user_version"] < 2**31
    and -(2**31) <= database_backup["application_id"] < 2**31
):
    raise SystemExit("database backup numeric evidence is invalid")
database_backup_json = json.dumps(
    database_backup, ensure_ascii=False, sort_keys=True, separators=(",", ":")
)
if record.get("known_good_health_before_switch") is not True:
    raise SystemExit("transaction lacks a known-good pre-switch health gate")
if record.get("prepared_release_durable") is not True:
    raise SystemExit("transaction lacks a durable prepared release gate")
if record.get("service_enabled_before_switch") is not True:
    raise SystemExit("transaction does not record the required enabled baseline")
dropins = record.get("dropin_paths_before")
if dropins not in ([], [managed]):
    raise SystemExit("transaction contains an unsupported prior drop-in set")
hex_pattern = re.compile(r"[0-9a-f]{64}\Z")
for key in ("fragment_sha256", "environment_file_sha256"):
    if not isinstance(record.get(key), str) or not hex_pattern.fullmatch(record[key]):
        raise SystemExit(f"invalid {key}")
dropin_sha = record.get("managed_dropin_sha256_before")
if dropin_sha is not None and (not isinstance(dropin_sha, str) or not hex_pattern.fullmatch(dropin_sha)):
    raise SystemExit("invalid managed drop-in hash")
name_pattern = re.compile(r"[0-9A-Za-z_.@-]{1,200}\Z")
if not isinstance(record.get("fragment_backup"), str) or not name_pattern.fullmatch(
    record["fragment_backup"]
):
    raise SystemExit("invalid fragment_backup")
managed_backup = record.get("managed_dropin_backup")
if managed_backup is not None and (
    not isinstance(managed_backup, str) or not name_pattern.fullmatch(managed_backup)
):
    raise SystemExit("invalid managed_dropin_backup")
if bool(dropins) != bool(dropin_sha) or bool(dropins) != bool(managed_backup):
    raise SystemExit("managed drop-in backup metadata is inconsistent")
required_strings = (
    "previous_release_id",
    "previous_target",
    "fragment_path",
    "previous_exec_path",
    "previous_exec_argv",
    "previous_working_directory",
    "previous_service_user",
    "previous_service_group",
    "previous_environment_files",
    "previous_read_write_paths",
    "previous_umask",
)
for key in required_strings:
    if not isinstance(record.get(key), str) or not record[key] or "\x00" in record[key]:
        raise SystemExit(f"invalid {key}")
if record["previous_umask"] != "0077":
    raise SystemExit("transaction does not preserve the private 0077 umask baseline")
fields = [
    record["status"],
    record["previous_release_id"],
    record["previous_target"],
    record["fragment_path"],
    record["fragment_sha256"],
    dropins[0] if dropins else "",
    dropin_sha or "",
    record["fragment_backup"],
    record.get("managed_dropin_backup") or "",
    record["previous_exec_path"],
    record["previous_exec_argv"],
    record["previous_working_directory"],
    record["previous_service_user"],
    record["previous_service_group"],
    record["previous_environment_files"],
    record["previous_read_write_paths"],
    record["previous_umask"],
    record["environment_file_sha256"],
    public_origin,
    public_host,
    database_backup["basename"],
    database_backup_json,
    operation,
    target_release_id,
    target_runtime_mode,
    record["started_at"],
]
for field in fields:
    sys.stdout.write(field)
    sys.stdout.write("\0")
PY
)
[[ "${#TX_FIELDS[@]}" == "26" ]] || fail "transaction marker field contract is incomplete"

TX_STATUS="${TX_FIELDS[0]}"
PREVIOUS_ID="${TX_FIELDS[1]}"
PREVIOUS_TARGET="${TX_FIELDS[2]}"
FRAGMENT_PATH="${TX_FIELDS[3]}"
FRAGMENT_SHA256="${TX_FIELDS[4]}"
DROPIN_PATHS_BEFORE="${TX_FIELDS[5]}"
DROPIN_SHA256="${TX_FIELDS[6]}"
FRAGMENT_BACKUP_NAME="${TX_FIELDS[7]}"
DROPIN_BACKUP_NAME="${TX_FIELDS[8]}"
PREVIOUS_EXEC_PATH="${TX_FIELDS[9]}"
PREVIOUS_EXEC_ARGV="${TX_FIELDS[10]}"
PREVIOUS_WORKING_DIRECTORY="${TX_FIELDS[11]}"
PREVIOUS_SERVICE_USER="${TX_FIELDS[12]}"
PREVIOUS_SERVICE_GROUP="${TX_FIELDS[13]}"
PREVIOUS_ENVIRONMENT_FILES="${TX_FIELDS[14]}"
PREVIOUS_READ_WRITE_PATHS="${TX_FIELDS[15]}"
PREVIOUS_UMASK="${TX_FIELDS[16]}"
ENV_FILE_SHA256="${TX_FIELDS[17]}"
MARKER_PUBLIC_ORIGIN="${TX_FIELDS[18]}"
MARKER_PUBLIC_HOST="${TX_FIELDS[19]}"
DATABASE_BACKUP_BASENAME="${TX_FIELDS[20]}"
DATABASE_BACKUP_METADATA_JSON="${TX_FIELDS[21]}"
TX_OPERATION="${TX_FIELDS[22]}"
TX_TARGET_ID="${TX_FIELDS[23]}"
TX_TARGET_MODE="${TX_FIELDS[24]}"
TX_STARTED_AT="${TX_FIELDS[25]}"
[[ "$CALLER_PUBLIC_ORIGIN" == "$MARKER_PUBLIC_ORIGIN" \
  && "$CALLER_PUBLIC_HOST" == "$MARKER_PUBLIC_HOST" ]] \
  || fail "caller public origin or host drifted from the active transaction marker"
PUBLIC_ORIGIN="$MARKER_PUBLIC_ORIGIN"
PUBLIC_HOST="$MARKER_PUBLIC_HOST"
TX_STAMP="${TX_STARTED_AT//[-:]/}"
[[ "$TX_STAMP" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] \
  || fail "transaction marker timestamp cannot form a deterministic evidence id"

[[ "$PREVIOUS_ID" =~ ^[0-9A-Za-z][0-9A-Za-z._-]{0,79}$ ]] \
  || fail "transaction previous release id is invalid"
PREVIOUS_TARGET_RESOLVED="$(readlink -f -- "$PREVIOUS_TARGET")"
case "$PREVIOUS_TARGET_RESOLVED" in
  "$RELEASES_DIR"/*) ;;
  *) fail "transaction previous target escaped the releases directory" ;;
esac
[[ "$PREVIOUS_TARGET" == "$PREVIOUS_TARGET_RESOLVED" ]] \
  || fail "transaction previous target is not canonical"
[[ -d "$PREVIOUS_TARGET" && ! -L "$PREVIOUS_TARGET" ]] \
  || fail "transaction previous target is missing or is a symlink"
[[ "$FRAGMENT_PATH" == "$SYSTEMD_UNIT_FILE" && -f "$FRAGMENT_PATH" ]] \
  || fail "transaction service fragment path is invalid"
[[ "$(sha256sum "$FRAGMENT_PATH" | awk '{print $1}')" == "$FRAGMENT_SHA256" ]] \
  || fail "base systemd unit drifted after the interrupted transaction"
[[ "$(sha256sum "$ENV_FILE" | awk '{print $1}')" == "$ENV_FILE_SHA256" ]] \
  || fail "production environment file drifted after the interrupted transaction"
[[ "$PREVIOUS_ENVIRONMENT_FILES" == "$ENV_FILE (ignore_errors=no)" ]] \
  || fail "transaction did not validate the active production environment file"

DATABASE_BACKUP="$BACKUP_DIR/$DATABASE_BACKUP_BASENAME"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "transaction database backup evidence is missing or invalid"

FRAGMENT_BACKUP="$BACKUP_DIR/$FRAGMENT_BACKUP_NAME"
[[ -f "$FRAGMENT_BACKUP" && ! -L "$FRAGMENT_BACKUP" ]] \
  || fail "transaction base-unit backup is missing"
[[ "$(stat -c '%u:%g:%a' -- "$FRAGMENT_BACKUP")" == "0:0:600" ]] \
  || fail "transaction base-unit backup ownership or mode is invalid"
assert_trusted_root_file_path "$FRAGMENT_BACKUP" "transaction base-unit backup"
[[ "$(sha256sum "$FRAGMENT_BACKUP" | awk '{print $1}')" == "$FRAGMENT_SHA256" ]] \
  || fail "transaction base-unit backup hash mismatch"
DROPIN_BACKUP=""
if [[ -n "$DROPIN_PATHS_BEFORE" ]]; then
  [[ "$DROPIN_PATHS_BEFORE" == "$MANAGED_DROPIN" ]] \
    || fail "transaction prior drop-in path is not managed"
  [[ -n "$DROPIN_BACKUP_NAME" && -n "$DROPIN_SHA256" ]] \
    || fail "transaction prior managed drop-in backup is incomplete"
  DROPIN_BACKUP="$BACKUP_DIR/$DROPIN_BACKUP_NAME"
  [[ -f "$DROPIN_BACKUP" && ! -L "$DROPIN_BACKUP" ]] \
    || fail "transaction managed drop-in backup is missing"
  [[ "$(stat -c '%u:%g:%a' -- "$DROPIN_BACKUP")" == "0:0:600" ]] \
    || fail "transaction managed drop-in backup ownership or mode is invalid"
  assert_trusted_root_file_path "$DROPIN_BACKUP" \
    "transaction managed systemd drop-in backup"
  [[ "$(sha256sum "$DROPIN_BACKUP" | awk '{print $1}')" == "$DROPIN_SHA256" ]] \
    || fail "transaction managed drop-in backup hash mismatch"
else
  [[ -z "$DROPIN_BACKUP_NAME" && -z "$DROPIN_SHA256" ]] \
    || fail "transaction claims an absent drop-in but retains backup metadata"
fi

# During an interrupted transaction the manager and disk may legitimately show
# either the old or new managed state, but no unrelated .conf file is allowed.
assert_secure_systemd_directory "/etc/systemd/system" "systemd administrator unit directory"
assert_secure_systemd_file "$FRAGMENT_PATH" "systemd base unit"
if [[ -e "$MANAGED_DROPIN_DIR" || -L "$MANAGED_DROPIN_DIR" ]]; then
  assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
fi
LOADED_DROPINS="$(systemctl show "$SERVICE" --property=DropInPaths --value)"
"$PYTHON_BIN" -I - "$LOADED_DROPINS" "$MANAGED_DROPIN" \
  "$TRANSACTION_RUNTIME_GUARD" <<'PY' \
  || fail "unreviewed systemd drop-ins are active during recovery"
import sys

actual = sys.argv[1].split() if sys.argv[1] else []
allowed = set(sys.argv[2:])
if len(actual) != len(set(actual)) or any(path not in allowed for path in actual):
    raise SystemExit(1)
PY
if [[ -d "$MANAGED_DROPIN_DIR" ]]; then
  shopt -s nullglob
  DISK_DROPIN_FILES=("$MANAGED_DROPIN_DIR"/*.conf)
  shopt -u nullglob
  ((${#DISK_DROPIN_FILES[@]} <= 1)) || fail "multiple on-disk systemd drop-ins block recovery"
  for dropin_file in "${DISK_DROPIN_FILES[@]}"; do
    [[ "$dropin_file" == "$MANAGED_DROPIN" && -f "$dropin_file" && ! -L "$dropin_file" ]] \
      || fail "an unreviewed on-disk systemd drop-in blocks recovery"
  done
fi

assert_secure_runtime_directory "$RUNTIME_SYSTEMD_DIR" \
  "systemd runtime unit directory" "$PREVIOUS_SERVICE_USER"
if [[ -e "$TRANSACTION_RUNTIME_GUARD_DIR" || -L "$TRANSACTION_RUNTIME_GUARD_DIR" ]]; then
  assert_secure_runtime_directory "$TRANSACTION_RUNTIME_GUARD_DIR" \
    "transaction runtime guard directory" "$PREVIOUS_SERVICE_USER"
  shopt -s nullglob dotglob
  RUNTIME_GUARD_DIR_ENTRIES=("$TRANSACTION_RUNTIME_GUARD_DIR"/*)
  shopt -u nullglob dotglob
  ((${#RUNTIME_GUARD_DIR_ENTRIES[@]} <= 1)) \
    || fail "transaction runtime guard directory contains stale or unreviewed entries"
  for runtime_guard_entry in "${RUNTIME_GUARD_DIR_ENTRIES[@]}"; do
    [[ "$runtime_guard_entry" == "$TRANSACTION_RUNTIME_GUARD" ]] \
      || fail "transaction runtime guard directory contains an unexpected entry"
  done
  if [[ -e "$TRANSACTION_RUNTIME_GUARD" || -L "$TRANSACTION_RUNTIME_GUARD" ]]; then
    assert_transaction_runtime_guard_file \
      || fail "interrupted transaction runtime guard is not the exact trusted guard"
  fi
fi

CURRENT_USER="$(systemctl show "$SERVICE" --property=User --value)"
CURRENT_GROUP="$(systemctl show "$SERVICE" --property=Group --value)"
CURRENT_ENVIRONMENT_FILES="$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)"
CURRENT_READ_WRITE_PATHS="$(systemctl show "$SERVICE" --property=ReadWritePaths --value)"
CURRENT_UMASK="$(systemctl show "$SERVICE" --property=UMask --value)"
[[ "$CURRENT_USER" == "$PREVIOUS_SERVICE_USER" && "$CURRENT_USER" != "root" ]] \
  || fail "systemd service user drifted after the interrupted transaction"
[[ "$CURRENT_GROUP" == "$PREVIOUS_SERVICE_GROUP" ]] \
  || fail "systemd service group drifted after the interrupted transaction"
RECOVERY_UID="$(id -u "$CURRENT_USER")"
RECOVERY_GID="$("$PYTHON_BIN" -I - "$CURRENT_GROUP" <<'PY'
import grp
import sys
print(grp.getgrnam(sys.argv[1]).gr_gid)
PY
)"
[[ "$RECOVERY_UID" =~ ^[1-9][0-9]*$ && "$RECOVERY_GID" =~ ^[1-9][0-9]*$ ]] \
  || fail "recovery service uid and gid must both be nonzero"
[[ "$(stat -c '%u:%g:%a' -- "$SHARED_DIR")" == "$RECOVERY_UID:$RECOVERY_GID:700" \
  && "$(stat -c '%u:%g:%a' -- "$RUNS_DIR")" == "$RECOVERY_UID:$RECOVERY_GID:700" \
  && "$(stat -c '%u:%g:%a' -- "$SECURITY_DB")" == "$RECOVERY_UID:$RECOVERY_GID:600" ]] \
  || fail "shared state ownership or mode does not match the dedicated service account"
[[ "$(getfacl -cp -- "$SHARED_DIR")" == $'user::rwx\ngroup::---\nother::---' \
  && "$(getfacl -cp -- "$RUNS_DIR")" == $'user::rwx\ngroup::---\nother::---' \
  && "$(getfacl -cp -- "$SECURITY_DB")" == $'user::rw-\ngroup::---\nother::---' ]] \
  || fail "shared state contains an unexpected access-control entry"
if runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -w "$APP_ROOT" \
  || runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -w "$RELEASES_DIR" \
  || runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -w "$CONTROL_DIR"; then
  fail "service user can write deployment control or release-selection paths"
fi
runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -x "$SHARED_DIR" \
  && runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -w "$SHARED_DIR" \
  && runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -x "$RUNS_DIR" \
  && runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -r "$RUNS_DIR" \
  && runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -w "$RUNS_DIR" \
  && runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -r "$SECURITY_DB" \
  && runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -w "$SECURITY_DB" \
  || fail "service user cannot persist shared runs or account database state"
[[ "$CURRENT_ENVIRONMENT_FILES" == "$PREVIOUS_ENVIRONMENT_FILES" ]] \
  || fail "systemd environment file drifted after the interrupted transaction"
[[ "$CURRENT_READ_WRITE_PATHS" == "$PREVIOUS_READ_WRITE_PATHS" ]] \
  || fail "systemd writable paths drifted after the interrupted transaction"
[[ "$CURRENT_UMASK" == "$PREVIOUS_UMASK" ]] \
  || fail "systemd umask drifted after the interrupted transaction"

if [[ "$PREVIOUS_EXEC_PATH" == "$CURRENT_LINK/.venv/bin/python" ]]; then
  PREVIOUS_RUNTIME_MODE="release"
  PREVIOUS_RUNTIME="$PREVIOUS_TARGET/.venv/bin/python"
  [[ "$DROPIN_PATHS_BEFORE" == "$MANAGED_DROPIN" \
    && "$PREVIOUS_EXEC_ARGV" == "$MODERN_EXEC_ARGV" \
    && -x "$PREVIOUS_RUNTIME" ]] \
    || fail "recorded previous release-local runtime is incomplete or mixed"
  validate_passed_release_record
  validate_previous_runtime_provenance
elif [[ "$PREVIOUS_EXEC_PATH" == "$APP_ROOT/.venv/bin/python" ]]; then
  PREVIOUS_RUNTIME_MODE="legacy"
  PREVIOUS_RUNTIME="$APP_ROOT/.venv/bin/python"
  LEGACY_EXEC_ARGV_SPACE="$APP_ROOT/.venv/bin/python -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $LOCAL_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1"
  LEGACY_EXEC_ARGV_EQUALS="$APP_ROOT/.venv/bin/python -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $LOCAL_PORT --proxy-headers --forwarded-allow-ips=127.0.0.1"
  [[ "$DROPIN_PATHS_BEFORE" == "" && ! -e "$PREVIOUS_TARGET/.venv" \
    && ( "$PREVIOUS_EXEC_ARGV" == "$LEGACY_EXEC_ARGV_SPACE" \
      || "$PREVIOUS_EXEC_ARGV" == "$LEGACY_EXEC_ARGV_EQUALS" ) ]] \
    || fail "recorded previous legacy runtime is incomplete or mixed"
  validate_previous_runtime_provenance
else
  fail "transaction previous executable is outside the supported runtime modes"
fi
[[ "$PREVIOUS_WORKING_DIRECTORY" == "$CURRENT_LINK" ]] \
  || fail "transaction previous working directory was not current"
runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -x "$PREVIOUS_TARGET" \
  || fail "service user cannot traverse the transaction previous target"
runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -r "$PREVIOUS_TARGET/protocol_studio/app.py" \
  || fail "service user cannot read the transaction previous target"
runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -x "$PREVIOUS_RUNTIME" \
  || fail "service user cannot execute the transaction previous runtime"

ORIGINAL_TX_STATUS="$TX_STATUS"
MARKER_PREVIOUS_ID="$PREVIOUS_ID"
MARKER_PREVIOUS_TARGET="$PREVIOUS_TARGET"
MARKER_PREVIOUS_RUNTIME_MODE="$PREVIOUS_RUNTIME_MODE"
MARKER_PREVIOUS_RUNTIME="$PREVIOUS_RUNTIME"
MARKER_PREVIOUS_EXPECTED_VERSION="${PREVIOUS_EXPECTED_VERSION:-}"
MARKER_PREVIOUS_MANIFEST_SHA256="${PREVIOUS_MANIFEST_SHA256:-}"
MARKER_PREVIOUS_RUNTIME_FINGERPRINT_JSON="${PREVIOUS_RUNTIME_FINGERPRINT_JSON:-}"

ACTIVATION_FROM_PREVIOUS="false"
case "$TX_STATUS" in
  switching|rolling_back)
    ACTIVATION_FROM_PREVIOUS="true"
    ACTIVATION_ID="$MARKER_PREVIOUS_ID"
    ACTIVATION_TARGET="$MARKER_PREVIOUS_TARGET"
    ACTIVATION_MODE="$MARKER_PREVIOUS_RUNTIME_MODE"
    ;;
  recovery_committed_pending_activation)
    [[ "$TX_TARGET_ID" == "$MARKER_PREVIOUS_ID" \
      && "$TX_TARGET_MODE" == "$MARKER_PREVIOUS_RUNTIME_MODE" ]] \
      || fail "recovery-committed marker activation identity drifted"
    ACTIVATION_FROM_PREVIOUS="true"
    ACTIVATION_ID="$TX_TARGET_ID"
    ACTIVATION_TARGET="$RELEASES_DIR/$ACTIVATION_ID"
    ACTIVATION_MODE="$TX_TARGET_MODE"
    ;;
  deploy_committed_pending_activation)
    [[ "$TX_OPERATION" == "deploy" && "$TX_TARGET_MODE" == "release" ]] \
      || fail "deploy-committed marker target encoding is invalid"
    ACTIVATION_ID="$TX_TARGET_ID"
    ACTIVATION_TARGET="$RELEASES_DIR/$ACTIVATION_ID"
    ACTIVATION_MODE="release"
    ;;
  rollback_committed_pending_activation)
    [[ "$TX_OPERATION" == "rollback" \
      && ( "$TX_TARGET_MODE" == "release" || "$TX_TARGET_MODE" == "legacy" ) ]] \
      || fail "rollback-committed marker target encoding is invalid"
    ACTIVATION_ID="$TX_TARGET_ID"
    ACTIVATION_TARGET="$RELEASES_DIR/$ACTIVATION_ID"
    ACTIVATION_MODE="$TX_TARGET_MODE"
    ;;
  *)
    fail "unsupported recovery activation phase"
    ;;
esac

[[ "$ACTIVATION_ID" =~ ^[0-9A-Za-z][0-9A-Za-z._-]{0,79}$ ]] \
  || fail "recovery activation release id is invalid"
[[ -d "$ACTIVATION_TARGET" && ! -L "$ACTIVATION_TARGET" \
  && "$(realpath -e -- "$ACTIVATION_TARGET")" == "$ACTIVATION_TARGET" ]] \
  || fail "recovery activation target is missing, noncanonical, or a symlink"
case "$ACTIVATION_TARGET" in
  "$RELEASES_DIR"/*) ;;
  *) fail "recovery activation target escaped the releases directory" ;;
esac

# Rebind the existing strict provenance helpers to the phase-selected activation
# target.  The original marker baseline remains in MARKER_PREVIOUS_* variables.
PREVIOUS_ID="$ACTIVATION_ID"
PREVIOUS_TARGET="$ACTIVATION_TARGET"
PREVIOUS_RUNTIME_MODE="$ACTIVATION_MODE"
if [[ "$ACTIVATION_MODE" == "release" ]]; then
  PREVIOUS_RUNTIME="$ACTIVATION_TARGET/.venv/bin/python"
  [[ -x "$PREVIOUS_RUNTIME" ]] || fail "recovery activation release runtime is missing"
  if [[ "$ORIGINAL_TX_STATUS" == "deploy_committed_pending_activation" ]]; then
    PENDING_DEPLOY_RECORD="$DEPLOYMENT_DIR/.pending-deploy-$ACTIVATION_ID.json"
    FINAL_DEPLOY_RECORD="$DEPLOYMENT_DIR/$ACTIVATION_ID.json"
    if [[ -f "$PENDING_DEPLOY_RECORD" && ! -L "$PENDING_DEPLOY_RECORD" ]]; then
      SELECTED_DEPLOY_RECORD="$PENDING_DEPLOY_RECORD"
    elif [[ -f "$FINAL_DEPLOY_RECORD" && ! -L "$FINAL_DEPLOY_RECORD" ]]; then
      SELECTED_DEPLOY_RECORD="$FINAL_DEPLOY_RECORD"
    else
      fail "committed deployment has neither its protected pending record nor final passed record"
    fi
    validate_passed_release_record "$SELECTED_DEPLOY_RECORD"
    mapfile -t DEPLOY_PENDING_CONTRACT < <("$PYTHON_BIN" -I - \
      "$SELECTED_DEPLOY_RECORD" <<'PY'
import json
import sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
systemd = record.get("systemd")
database = record.get("database_backup")
if not isinstance(systemd, dict) or not isinstance(database, dict):
    raise SystemExit("deployment pending record subcontracts are missing")
print(systemd.get("fragment_sha256_before", ""))
print(systemd.get("environment_file_sha256", ""))
print(systemd.get("managed_dropin_sha256_after", ""))
print(json.dumps(database, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
PY
    )
    [[ "${#DEPLOY_PENDING_CONTRACT[@]}" == "4" \
      && "${DEPLOY_PENDING_CONTRACT[0]}" == "$FRAGMENT_SHA256" \
      && "${DEPLOY_PENDING_CONTRACT[1]}" == "$ENV_FILE_SHA256" \
      && "${DEPLOY_PENDING_CONTRACT[2]}" =~ ^[0-9a-f]{64}$ \
      && "${DEPLOY_PENDING_CONTRACT[3]}" == "$DATABASE_BACKUP_METADATA_JSON" ]] \
      || fail "committed deployment pending evidence does not match the transaction marker"
  elif [[ "$ACTIVATION_FROM_PREVIOUS" == "true" ]]; then
    PREVIOUS_EXPECTED_VERSION="$MARKER_PREVIOUS_EXPECTED_VERSION"
    PREVIOUS_MANIFEST_SHA256="$MARKER_PREVIOUS_MANIFEST_SHA256"
    PREVIOUS_RUNTIME_FINGERPRINT_JSON="$MARKER_PREVIOUS_RUNTIME_FINGERPRINT_JSON"
  else
    validate_passed_release_record
  fi
  validate_previous_runtime_provenance
  if [[ "$ACTIVATION_FROM_PREVIOUS" == "true" ]]; then
    cmp -s "$DROPIN_BACKUP" <(canonical_managed_dropin_content) \
      || fail "schema 5 precommit recovery marker contains a noncanonical prior managed drop-in"
  else
    managed_dropin_matches_canonical_content \
      || fail "committed schema 5 recovery target has a noncanonical managed drop-in"
  fi
else
  PREVIOUS_RUNTIME="$APP_ROOT/.venv/bin/python"
  [[ -x "$PREVIOUS_RUNTIME" ]] || fail "registered legacy shared runtime is missing"
  validate_previous_runtime_provenance
fi
ACTIVATION_MANIFEST_SHA256="${PREVIOUS_MANIFEST_SHA256:-}"
if [[ "$ACTIVATION_MODE" == "legacy" ]]; then
  printf 'NOTICE: registered legacy recovery target health is availability-only; release identity header is unsupported.\n' >&2
fi
runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -x "$ACTIVATION_TARGET" \
  && runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -r "$ACTIVATION_TARGET/protocol_studio/app.py" \
  && runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -x "$PREVIOUS_RUNTIME" \
  || fail "service account cannot read or execute the recovery activation target"
RECOVERY_EXPECTED_LEGACY_EXEC_START_PRE_ARGV="$MODERN_ENVIRONMENT_EXEC_START_PRE_ARGV"
RECOVERY_EXPECTED_EXEC_START_PRE_ARGVS_JSON="$MODERN_EXEC_START_PRE_ARGVS_JSON"
if [[ "$ACTIVATION_MODE" == "release" ]]; then
  RECOVERY_EXPECTED_ORDINARY_RESTART_PROTECTED="true"
  RECOVERY_RUNTIME_BASELINE_PATH="$RUNTIME_BASELINE_DIR/$ACTIVATION_ID.json"
  RECOVERY_RUNTIME_BASELINE_VERIFICATION_JSON="$(verify_release_runtime_baseline \
    "$ACTIVATION_ID" "$ACTIVATION_TARGET" "$ACTIVATION_MANIFEST_SHA256")" \
    || fail "recovery activation runtime baseline is missing or invalid"
  mapfile -t RECOVERY_RUNTIME_BASELINE_FIELDS < <("$PYTHON_BIN" -I -B -u - \
    "$RECOVERY_RUNTIME_BASELINE_VERIFICATION_JSON" <<'PY'
import json
import re
import sys

def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result

report = json.loads(
    sys.argv[1],
    object_pairs_hook=reject_duplicates,
    parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
)
expected = {
    "schema_version", "status", "release_id", "version",
    "release_manifest_sha256", "runtime_fingerprint_sha256", "baseline_sha256",
    "runtime_guard_helper_sha256",
}
if (
    not isinstance(report, dict)
    or set(report) != expected
    or type(report.get("schema_version")) is not int
    or report.get("schema_version") != 1
    or report.get("status") != "passed"
    or any(
        not isinstance(report.get(name), str)
        or re.fullmatch(r"[0-9a-f]{64}", report[name]) is None
        for name in (
            "runtime_fingerprint_sha256", "baseline_sha256",
            "runtime_guard_helper_sha256",
        )
    )
):
    raise SystemExit("runtime baseline verification report is invalid")
print(report["runtime_fingerprint_sha256"])
print(report["baseline_sha256"])
print(report["runtime_guard_helper_sha256"])
PY
  )
  [[ "${#RECOVERY_RUNTIME_BASELINE_FIELDS[@]}" == "3" ]] \
    || fail "recovery activation runtime baseline evidence is incomplete"
  RECOVERY_RUNTIME_FINGERPRINT_SHA256="${RECOVERY_RUNTIME_BASELINE_FIELDS[0]}"
  RECOVERY_RUNTIME_BASELINE_SHA256="${RECOVERY_RUNTIME_BASELINE_FIELDS[1]}"
  RECOVERY_RUNTIME_GUARD_HELPER_SHA256="${RECOVERY_RUNTIME_BASELINE_FIELDS[2]}"
else
  RECOVERY_EXPECTED_ORDINARY_RESTART_PROTECTED="false"
  RECOVERY_EXPECTED_LEGACY_EXEC_START_PRE_ARGV=""
  RECOVERY_EXPECTED_EXEC_START_PRE_ARGVS_JSON="[]"
  RECOVERY_RUNTIME_BASELINE_PATH=""
  RECOVERY_RUNTIME_BASELINE_SHA256=""
  RECOVERY_RUNTIME_FINGERPRINT_SHA256=""
  RECOVERY_RUNTIME_GUARD_HELPER_SHA256=""
fi

validate_recovery_evidence_record() {
  local record_path="$1"
  [[ -f "$record_path" && ! -L "$record_path" \
    && "$(realpath -e -- "$record_path")" == "$record_path" \
    && "$(stat -c '%u:%g:%a' -- "$record_path")" == "0:0:640" ]] \
    || return 1
  assert_trusted_record_file "$record_path" "recovery evidence record"
  "$PYTHON_BIN" -I - "$record_path" "$TX_OPERATION" "$ACTIVATION_ID" \
    "$ACTIVATION_MODE" "$FRAGMENT_SHA256" "$ENV_FILE_SHA256" \
    "$PUBLIC_ORIGIN" "$PUBLIC_HOST" "$RECOVERY_EXPECTED_ORDINARY_RESTART_PROTECTED" \
    "$RECOVERY_EXPECTED_LEGACY_EXEC_START_PRE_ARGV" \
    "$RECOVERY_EXPECTED_EXEC_START_PRE_ARGVS_JSON" "$DATABASE_BACKUP_METADATA_JSON" \
    "$RECOVERY_RUNTIME_BASELINE_PATH" "$RECOVERY_RUNTIME_BASELINE_SHA256" \
    "$RECOVERY_RUNTIME_FINGERPRINT_SHA256" \
    "$RECOVERY_RUNTIME_GUARD_HELPER_SHA256" <<'PY'
import json
import re
import sys
from pathlib import Path

def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result

def reject_constant(value):
    raise ValueError("non-finite JSON number")

path = Path(sys.argv[1])
if sys.argv[9] not in {"true", "false"}:
    raise SystemExit("invalid expected ordinary restart validator flag")
ordinary_restart_protected = sys.argv[9] == "true"
record = json.loads(
    path.read_text(encoding="utf-8"),
    object_pairs_hook=strict_object,
    parse_constant=reject_constant,
)
schema = record.get("schema_version") if isinstance(record, dict) else None
expected_keys = {
    "schema_version", "status", "interrupted_operation", "activation_release_id",
    "runtime_mode", "fragment_sha256", "environment_file_sha256",
    "public_origin", "public_host", "ordinary_restart_validator",
    "database_backup", "recovered_at", "checks",
}
if schema == 5:
    expected_keys |= {
        "runtime_baseline_path", "runtime_baseline_sha256",
        "runtime_fingerprint_sha256", "runtime_guard_helper_sha256",
    }
required_checks = {
    "isolated_service_user_preflight", "service_stopped_before_restore",
    "service_disabled_during_recovery", "bounded_runtime_guard",
    "exact_activation_target", "effective_runtime", "running_process_runtime",
    "local_health", "public_health", "public_login_redirect",
    "production_environment_validated_three_phases",
    "final_publication_configuration_gate",
    "ordinary_restart_environment_gate", "service_enabled_after_health",
}
if schema == 5:
    required_checks.add("ordinary_restart_integrity_gate")
if schema == 4:
    expected_validator = {
        "protected": ordinary_restart_protected,
        "exec_start_pre_argv": sys.argv[10] or None,
    }
else:
    expected_validator = {
        "protected": ordinary_restart_protected,
        "exec_start_pre_argvs": json.loads(sys.argv[11]),
    }
if (
    type(record) is not dict
    or set(record) != expected_keys
    or type(record.get("schema_version")) is not int
    or record.get("schema_version") not in {4, 5}
    or record.get("status") != "passed"
    or record.get("interrupted_operation") != sys.argv[2]
    or record.get("activation_release_id") != sys.argv[3]
    or record.get("runtime_mode") != sys.argv[4]
    or record.get("fragment_sha256") != sys.argv[5]
    or record.get("environment_file_sha256") != sys.argv[6]
    or record.get("public_origin") != sys.argv[7]
    or record.get("public_host") != sys.argv[8]
    or record.get("ordinary_restart_validator") != expected_validator
    or record.get("database_backup") != json.loads(sys.argv[12])
    or (
        schema == 5
        and (
            record.get("runtime_baseline_path") != (sys.argv[13] or None)
            or record.get("runtime_baseline_sha256") != (sys.argv[14] or None)
            or record.get("runtime_fingerprint_sha256") != (sys.argv[15] or None)
            or record.get("runtime_guard_helper_sha256") != (sys.argv[16] or None)
        )
    )
    or not isinstance(record.get("recovered_at"), str)
    or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        record["recovered_at"],
    )
    or type(record.get("checks")) is not dict
    or set(record["checks"]) != required_checks
    or any(
        type(record["checks"].get(key)) is not bool
        or record["checks"].get(key)
        is not (
            ordinary_restart_protected
            if key in {
                "ordinary_restart_environment_gate",
                "ordinary_restart_integrity_gate",
            }
            else True
        )
        for key in required_checks
    )
):
    raise SystemExit("recovery evidence target or contract mismatch")
PY
}

# Evidence names are derived from the immutable transaction started_at field.
# A retry therefore addresses the same paths after any publication interruption.
RECOVERY_STAMP="$TX_STAMP"
RECOVERY_RECORD="$DEPLOYMENT_DIR/recovery-$RECOVERY_STAMP-$ACTIVATION_ID.json"
PENDING_RECOVERY_RECORD="$DEPLOYMENT_DIR/.pending-recovery-$ACTIVATION_ID.json"
ARCHIVED_TRANSACTION_RECORD="$DEPLOYMENT_DIR/transaction-recovered-$RECOVERY_STAMP-$ACTIVATION_ID.json"
if [[ -e "$RECOVERY_RECORD" || -L "$RECOVERY_RECORD" ]]; then
  validate_recovery_evidence_record "$RECOVERY_RECORD" \
    || fail "existing deterministic recovery evidence is not the exact committed record"
fi
[[ ! -e "$ARCHIVED_TRANSACTION_RECORD" && ! -L "$ARCHIVED_TRANSACTION_RECORD" ]] \
  || fail "recovery transaction evidence path already exists"
validate_production_environment \
  || fail "production environment failed the recovery pre-canary gate"

# Exercise the selected activation target inside a transient systemd mount
# namespace.  The original EnvironmentFile remains authoritative; its shared
# paths resolve to private state only inside the canary namespace.
PREFLIGHT_ROOT="$APP_ROOT/.recovery-preflight-$ACTIVATION_ID-$$"
PREFLIGHT_SHARED="$PREFLIGHT_ROOT/shared"
PREFLIGHT_DB="$PREFLIGHT_SHARED/security.sqlite3"
PREFLIGHT_RUNS="$PREFLIGHT_SHARED/runs"
PREFLIGHT_ESCAPE_LINK="$PREFLIGHT_SHARED/live-security.sqlite3"
install -d -o root -g root -m 0700 \
  "$PREFLIGHT_ROOT" "$PREFLIGHT_SHARED" "$PREFLIGHT_RUNS"
assert_no_extended_acl "$PREFLIGHT_ROOT" "recovery preflight isolation root"
assert_no_extended_acl "$PREFLIGHT_SHARED" "recovery preflight shared staging directory"
assert_no_extended_acl "$PREFLIGHT_RUNS" "recovery preflight runs staging directory"
PREFLIGHT_DB_METADATA_JSON="$("$PYTHON_BIN" -I "$SCRIPT_DIR/sqlite_backup.py" \
  backup --source "$SECURITY_DB" --destination "$PREFLIGHT_DB" \
  --deadline-seconds "$SQLITE_BACKUP_DEADLINE_SECONDS")" \
  || fail "cannot create the recovery preflight database"
[[ "$(stat -c '%u:%g:%a' -- "$PREFLIGHT_DB")" == "0:0:600" ]] \
  || fail "recovery preflight database was not published root-only"
assert_no_extended_acl "$PREFLIGHT_DB" "recovery preflight database"
[[ "$("$PYTHON_BIN" -I "$SCRIPT_DIR/sqlite_backup.py" inspect \
  --source "$PREFLIGHT_DB" \
  --deadline-seconds "$SQLITE_BACKUP_DEADLINE_SECONDS")" == "$PREFLIGHT_DB_METADATA_JSON" ]] \
  || fail "recovery preflight database verification drifted before delegation"
chown "$PREVIOUS_SERVICE_USER:$PREVIOUS_SERVICE_GROUP" "$PREFLIGHT_DB"
chmod 0600 "$PREFLIGHT_DB"
chown "$PREVIOUS_SERVICE_USER:$PREVIOUS_SERVICE_GROUP" "$PREFLIGHT_SHARED" "$PREFLIGHT_RUNS"
chmod 0700 "$PREFLIGHT_SHARED" "$PREFLIGHT_RUNS"
ln -s -- "$SECURITY_DB" "$PREFLIGHT_ESCAPE_LINK"
if runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -x "$PREFLIGHT_ROOT" \
  || runuser -u "$PREVIOUS_SERVICE_USER" -- "$TEST_BIN" -r "$PREFLIGHT_DB"; then
  fail "service UID can traverse the host-side recovery preflight root"
fi

if [[ "$ACTIVATION_MODE" == "release" ]]; then
  PREFLIGHT_VALIDATOR_PYTHON="$PREVIOUS_RUNTIME"
  PREFLIGHT_VALIDATOR="$ACTIVATION_TARGET/deploy/validate_production_env.py"
  assert_trusted_code_file "$PREFLIGHT_VALIDATOR" "recovery target environment validator"
else
  PREFLIGHT_VALIDATOR_PYTHON="$PYTHON_BIN"
  PREFLIGHT_VALIDATOR="$SCRIPT_DIR/validate_production_env.py"
fi
PREFLIGHT_EXPECTED_PRE_ARGV="$PREFLIGHT_VALIDATOR_PYTHON -I -B -u $PREFLIGHT_VALIDATOR --shared-runs $RUNS_DIR --security-db $SECURITY_DB --public-origin $PUBLIC_ORIGIN --public-host $PUBLIC_HOST"
PREFLIGHT_EXPECTED_ARGV="$PREVIOUS_RUNTIME -I -B -u -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $PREFLIGHT_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1"
PREFLIGHT_UNIT_KEY="$("$PYTHON_BIN" -I - "$ACTIVATION_ID" <<'PY'
import hashlib
import sys
print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest()[:16])
PY
)"
PREFLIGHT_UNIT="protocol-studio-recovery-canary-$PREFLIGHT_UNIT_KEY-$$.service"
PREFLIGHT_LOG="$LOG_DIR/$ACTIVATION_ID-recovery-preflight-$$.log"
PREFLIGHT_MAIN_PID=""

stop_preflight() {
  local active_state=""
  local load_state=""
  local main_pid=""
  [[ -n "${PREFLIGHT_UNIT:-}" ]] || return 0
  systemctl --no-block stop "$PREFLIGHT_UNIT" >/dev/null 2>&1 || true
  for _ in $(seq 1 "$SERVICE_TERM_GRACE_ATTEMPTS"); do
    active_state="$(systemctl show "$PREFLIGHT_UNIT" --property=ActiveState --value 2>/dev/null || true)"
    main_pid="$(systemctl show "$PREFLIGHT_UNIT" --property=MainPID --value 2>/dev/null || true)"
    if [[ -z "$active_state" || "$active_state" == "inactive" || "$active_state" == "failed" ]] \
      && [[ -z "$main_pid" || "$main_pid" == "0" ]]; then
      break
    fi
    sleep "$SERVICE_STOP_POLL_SECONDS"
  done
  if [[ -n "$main_pid" && "$main_pid" != "0" ]]; then
    systemctl kill --kill-who=all --signal=KILL "$PREFLIGHT_UNIT" >/dev/null 2>&1 || true
    for _ in $(seq 1 "$SERVICE_KILL_REAP_ATTEMPTS"); do
      main_pid="$(systemctl show "$PREFLIGHT_UNIT" --property=MainPID --value 2>/dev/null || true)"
      [[ -z "$main_pid" || "$main_pid" == "0" ]] && break
      sleep "$SERVICE_STOP_POLL_SECONDS"
    done
  fi
  [[ -z "$main_pid" || "$main_pid" == "0" ]] || return 1
  systemctl reset-failed "$PREFLIGHT_UNIT" >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do
    load_state="$(systemctl show "$PREFLIGHT_UNIT" --property=LoadState --value 2>/dev/null || true)"
    [[ -z "$load_state" || "$load_state" == "not-found" ]] && break
    systemctl reset-failed "$PREFLIGHT_UNIT" >/dev/null 2>&1 || true
    sleep "$SERVICE_STOP_POLL_SECONDS"
  done
  [[ -z "$load_state" || "$load_state" == "not-found" ]]
}

capture_preflight_diagnostics() {
  {
    printf 'transient recovery canary unit: %s\n' "$PREFLIGHT_UNIT"
    systemctl status --no-pager --full "$PREFLIGHT_UNIT" 2>&1 || true
    journalctl --no-pager --unit="$PREFLIGHT_UNIT" --since='-5 minutes' 2>&1 || true
    systemctl show "$PREFLIGHT_UNIT" \
      --property=LoadState,ActiveState,SubState,Result,MainPID,ExecMainStatus \
      --property=User,Group,WorkingDirectory,ExecStartPre,ExecStart,EnvironmentFiles,UnsetEnvironment \
      --property=UMask,NoNewPrivileges,PrivateTmp,PrivateDevices,ProtectSystem \
      --property=BindReadOnlyPaths,BindPaths,ReadWritePaths 2>&1 || true
  } >"$PREFLIGHT_LOG"
  chmod 0600 "$PREFLIGHT_LOG" 2>/dev/null || true
}

preflight_fail() {
  capture_preflight_diagnostics
  fail "$*; see the root-only recovery preflight log"
}

cleanup_preflight() {
  if ! stop_preflight; then
    printf 'ERROR: recovery transient canary could not be reaped; retaining private state\n' >&2
    return 0
  fi
  case "$PREFLIGHT_ROOT" in
    "$APP_ROOT"/.recovery-preflight-*) rm -rf -- "$PREFLIGHT_ROOT" ;;
    *) printf 'ERROR: refusing to clean an unexpected recovery preflight path\n' >&2 ;;
  esac
  fsync_directory "$APP_ROOT" >/dev/null 2>&1 || true
}
trap cleanup_preflight EXIT

"$PYTHON_BIN" -I - "$PREFLIGHT_PORT" <<'PY'
import socket
import sys
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    probe.bind(("127.0.0.1", int(sys.argv[1])))
PY
PREFLIGHT_LOAD_STATE="$(systemctl show "$PREFLIGHT_UNIT" --property=LoadState --value 2>/dev/null || true)"
[[ -z "$PREFLIGHT_LOAD_STATE" || "$PREFLIGHT_LOAD_STATE" == "not-found" ]] \
  || fail "unique recovery transient canary unit already exists"
if ! systemd-run --quiet --collect --unit="$PREFLIGHT_UNIT" \
  --description="MCGS recovery $ACTIVATION_ID isolated preflight" \
  --property=Type=simple \
  --property="User=$PREVIOUS_SERVICE_USER" \
  --property="Group=$PREVIOUS_SERVICE_GROUP" \
  --property="WorkingDirectory=$ACTIVATION_TARGET" \
  --property="EnvironmentFile=$ENV_FILE" \
  --property=Environment= \
  --property="Environment=PYTHONDONTWRITEBYTECODE=1" \
  --property="Environment=PYTHONUNBUFFERED=1" \
  --property="UnsetEnvironment=$REQUIRED_UNSET_ENVIRONMENT" \
  --property="ExecStartPre=$PREFLIGHT_EXPECTED_PRE_ARGV" \
  --property=Restart=no \
  --property="RuntimeMaxSec=${CANARY_RUNTIME_MAX_SECONDS}s" \
  --property=TimeoutStartSec=45s \
  --property=TimeoutStopSec=10s \
  --property=UMask=0077 \
  --property=NoNewPrivileges=yes \
  --property=CapabilityBoundingSet= \
  --property=AmbientCapabilities= \
  --property=PrivateTmp=yes \
  --property=PrivateDevices=yes \
  --property=ProtectSystem=strict \
  --property=ProtectHome=yes \
  --property=ProtectControlGroups=yes \
  --property=ProtectKernelModules=yes \
  --property=ProtectKernelTunables=yes \
  --property=ProtectKernelLogs=yes \
  --property=ProtectClock=yes \
  --property=RestrictSUIDSGID=yes \
  --property="RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" \
  --property=RestrictNamespaces=yes \
  --property=LockPersonality=yes \
  --property="BindReadOnlyPaths=$ACTIVATION_TARGET:$ACTIVATION_TARGET" \
  --property="BindPaths=$PREFLIGHT_SHARED:$SHARED_DIR" \
  --property="ReadWritePaths=$SHARED_DIR" \
  -- "$PREVIOUS_RUNTIME" -I -B -u -m uvicorn protocol_studio.app:app \
  --host 127.0.0.1 --port "$PREFLIGHT_PORT" \
  --proxy-headers --forwarded-allow-ips 127.0.0.1; then
  preflight_fail "cannot start the recovery transient systemd canary"
fi

PREFLIGHT_OK="false"
for _ in $(seq 1 "$CANARY_HEALTH_ATTEMPTS"); do
  PREFLIGHT_ACTIVE_STATE="$(systemctl show "$PREFLIGHT_UNIT" --property=ActiveState --value 2>/dev/null || true)"
  case "$PREFLIGHT_ACTIVE_STATE" in
    active)
      if runtime_health "$ACTIVATION_MODE" "$ACTIVATION_MANIFEST_SHA256" \
        "http://127.0.0.1:$PREFLIGHT_PORT/api/health" "$CANARY_HEALTH_MAX_SECONDS" "$PUBLIC_HOST" \
        && systemctl is-active --quiet "$PREFLIGHT_UNIT"; then
        PREFLIGHT_OK="true"
        break
      fi
      ;;
    activating|reloading) ;;
    *) break ;;
  esac
  sleep "$CANARY_HEALTH_POLL_SECONDS"
done
[[ "$PREFLIGHT_OK" == "true" ]] \
  || preflight_fail "recovery transient systemd canary health failed"

assert_preflight_property() {
  local property="$1"
  local expected="$2"
  local actual
  actual="$(systemctl show "$PREFLIGHT_UNIT" --property="$property" --value)" \
    || preflight_fail "cannot read recovery canary property $property"
  [[ "$actual" == "$expected" ]] \
    || preflight_fail "recovery canary property $property drifted"
}
assert_preflight_property Type simple
assert_preflight_property User "$PREVIOUS_SERVICE_USER"
assert_preflight_property Group "$PREVIOUS_SERVICE_GROUP"
assert_preflight_property WorkingDirectory "$ACTIVATION_TARGET"
assert_preflight_property EnvironmentFiles "$ENV_FILE (ignore_errors=no)"
if ! unset_environment_matches "$(systemctl show "$PREFLIGHT_UNIT" \
  --property=UnsetEnvironment --value)"; then
  preflight_fail "transient canary environment sanitization does not match the managed service"
fi
if ! environment_assignments_match "$(systemctl show "$PREFLIGHT_UNIT" \
  --property=Environment --value)"; then
  preflight_fail "transient canary explicit environment does not match the managed service"
fi
assert_preflight_property Restart no
assert_preflight_property UMask 0077
assert_preflight_property NoNewPrivileges yes
assert_preflight_property PrivateTmp yes
assert_preflight_property PrivateDevices yes
assert_preflight_property ProtectSystem strict
assert_preflight_property ProtectHome yes
assert_preflight_property ProtectControlGroups yes
assert_preflight_property ProtectKernelModules yes
assert_preflight_property ProtectKernelTunables yes
assert_preflight_property ProtectKernelLogs yes
assert_preflight_property ProtectClock yes
assert_preflight_property RestrictSUIDSGID yes
assert_preflight_property RestrictNamespaces yes
assert_preflight_property LockPersonality yes
assert_preflight_property ReadWritePaths "$SHARED_DIR"

PREFLIGHT_MAIN_PID="$(systemctl show "$PREFLIGHT_UNIT" --property=MainPID --value)"
[[ "$PREFLIGHT_MAIN_PID" =~ ^[1-9][0-9]*$ \
  && "$(stat -c '%u:%g' -- "/proc/$PREFLIGHT_MAIN_PID")" == "$RECOVERY_UID:$RECOVERY_GID" ]] \
  || preflight_fail "recovery canary process credentials are invalid"
[[ "$(process_exec_argv "$PREFLIGHT_MAIN_PID")" == "$PREFLIGHT_EXPECTED_ARGV" \
  && "$(process_working_directory "$PREFLIGHT_MAIN_PID")" == "$ACTIVATION_TARGET" ]] \
  || preflight_fail "recovery canary process argv or cwd is invalid"
process_environment_matches "$PREFLIGHT_MAIN_PID" \
  || preflight_fail "recovery canary process environment is invalid"
PREFLIGHT_EFFECTIVE_PRE="$(systemctl show "$PREFLIGHT_UNIT" --property=ExecStartPre --value)"
[[ "$PREFLIGHT_EFFECTIVE_PRE" == *"argv[]=$PREFLIGHT_EXPECTED_PRE_ARGV ; ignore_errors=no"* \
  && "$PREFLIGHT_EFFECTIVE_PRE" != *"} ; {"* ]] \
  || preflight_fail "recovery canary environment validator is not the sole ExecStartPre"

PREFLIGHT_VISIBLE_SHARED="/proc/$PREFLIGHT_MAIN_PID/root$SHARED_DIR"
PREFLIGHT_VISIBLE_TARGET="/proc/$PREFLIGHT_MAIN_PID/root$ACTIVATION_TARGET"
[[ "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_SHARED")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED")" != "$(stat -Lc '%d:%i' -- "$SHARED_DIR")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/security.sqlite3")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_DB")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/security.sqlite3")" != "$(stat -Lc '%d:%i' -- "$SECURITY_DB")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/runs")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_RUNS")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/runs")" != "$(stat -Lc '%d:%i' -- "$RUNS_DIR")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/live-security.sqlite3")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_DB")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/live-security.sqlite3")" != "$(stat -Lc '%d:%i' -- "$SECURITY_DB")" ]] \
  || preflight_fail "recovery canary private shared namespace or symlink confinement failed"
[[ "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_TARGET")" == "$(stat -Lc '%d:%i' -- "$ACTIVATION_TARGET")" ]] \
  || preflight_fail "recovery canary target bind identity is invalid"
strict_login_redirect "http://127.0.0.1:$PREFLIGHT_PORT/" "$CANARY_HEALTH_MAX_SECONDS" "$PUBLIC_HOST" \
  || preflight_fail "recovery canary did not enforce the login redirect"

capture_preflight_diagnostics
stop_preflight || preflight_fail "recovery transient canary could not be reaped"
[[ ! -e "/proc/$PREFLIGHT_MAIN_PID" ]] \
  || preflight_fail "recovery canary process survived bounded TERM and KILL"
cleanup_preflight
trap - EXIT

[[ "$(sha256sum "$FRAGMENT_PATH" | awk '{print $1}')" == "$FRAGMENT_SHA256" \
  && "$(sha256sum "$ENV_FILE" | awk '{print $1}')" == "$ENV_FILE_SHA256" ]] \
  || fail "base unit or production environment drifted during recovery preflight"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "transaction database backup drifted during recovery preflight"
validate_production_environment \
  || fail "production environment failed the recovery formal-switch gate"

atomic_link() {
  local target="$1"
  local temporary="$APP_ROOT/.current-recovery-$$"
  [[ ! -e "$temporary" && ! -L "$temporary" ]] || return 1
  ln -s -- "$target" "$temporary" || return 1
  mv -Tf -- "$temporary" "$CURRENT_LINK" || return 1
  fsync_directory "$APP_ROOT"
}
restore_marker_dropin() {
  if [[ -n "$DROPIN_PATHS_BEFORE" ]]; then
    install -d -m 0755 "$MANAGED_DROPIN_DIR" || return 1
    assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
    local temporary="$MANAGED_DROPIN_DIR/.recover-runtime-$$"
    install -m 0644 "$DROPIN_BACKUP" "$temporary" || return 1
    fsync_file "$temporary" || return 1
    mv -Tf -- "$temporary" "$MANAGED_DROPIN" || return 1
    fsync_directory "$MANAGED_DROPIN_DIR" || return 1
  else
    rm -f -- "$MANAGED_DROPIN" || return 1
    if [[ -d "$MANAGED_DROPIN_DIR" ]]; then
      fsync_directory "$MANAGED_DROPIN_DIR" || return 1
    fi
  fi
}

RECOVERY_ACTIVE="true"
RECOVERY_COMMITTED="false"
case "$TX_STATUS" in
  deploy_committed_pending_activation|rollback_committed_pending_activation|recovery_committed_pending_activation)
    RECOVERY_COMMITTED="true"
    ;;
esac
recovery_exit_guard() {
  local status="$?"
  local original_pid
  local active_state
  local sub_state
  local main_pid
  local process_gone="true"
  local marker_retained="false"
  local fail_closed="true"
  if [[ "$RECOVERY_ACTIVE" == "true" ]]; then
    ((status == 0)) && status=1
    set +e
    original_pid="$(systemctl show "$SERVICE" --property=MainPID --value 2>/dev/null)"
    systemctl disable "$SERVICE" >/dev/null 2>&1 || fail_closed="false"
    fsync_systemd_enablement_state >/dev/null 2>&1 || fail_closed="false"
    ( trap - EXIT; stop_service_and_verify ) >/dev/null 2>&1 || fail_closed="false"
    systemctl reset-failed "$SERVICE" >/dev/null 2>&1 || fail_closed="false"
    probe_service_enablement
    active_state="$(systemctl show "$SERVICE" --property=ActiveState --value 2>/dev/null)"
    sub_state="$(systemctl show "$SERVICE" --property=SubState --value 2>/dev/null)"
    main_pid="$(systemctl show "$SERVICE" --property=MainPID --value 2>/dev/null)"
    if [[ "$original_pid" =~ ^[1-9][0-9]*$ && -e "/proc/$original_pid" ]]; then
      process_gone="false"
    fi
    if [[ -f "$TRANSACTION_FILE" && ! -L "$TRANSACTION_FILE" \
      && "$(stat -c '%u:%g:%a' -- "$TRANSACTION_FILE" 2>/dev/null)" == "0:0:600" ]] \
      && acl_is_minimal "$TRANSACTION_FILE"; then
      marker_retained="true"
    fi
    [[ "$SERVICE_ENABLE_STDOUT" == "disabled" && "$SERVICE_ENABLE_EXIT" == "1" \
      && "$active_state" == "inactive" && "$sub_state" == "dead" \
      && "$main_pid" == "0" && "$process_gone" == "true" \
      && "$marker_retained" == "true" ]] \
      || fail_closed="false"
    ( trap - EXIT; assert_service_persistently_disabled "$PREVIOUS_SERVICE_USER" ) \
      >/dev/null 2>&1 || fail_closed="false"
    if [[ "$fail_closed" == "true" ]]; then
      printf 'FAIL-CLOSED CONFIRMED: service is persistently disabled, inactive/dead, MainPID=0, and the original process is gone; marker retained.\n' >&2
    else
      printf 'CRITICAL: FAIL-CLOSED NOT CONFIRMED (is-enabled=%s exit=%s ActiveState=%s SubState=%s MainPID=%s original_pid=%s original_gone=%s marker_retained=%s).\n' \
        "$SERVICE_ENABLE_STDOUT" "$SERVICE_ENABLE_EXIT" "$active_state" "$sub_state" \
        "$main_pid" "$original_pid" "$process_gone" "$marker_retained" >&2
      printf 'DO NOT REBOOT; retain the active transaction marker and obtain manual systemd recovery.\n' >&2
    fi
  fi
  exit "$status"
}
trap recovery_exit_guard EXIT
trap 'exit 130' INT TERM HUP

systemctl disable "$SERVICE" \
  || fail "cannot disable automatic startup for interrupted-transaction recovery"
assert_service_persistently_disabled "$PREVIOUS_SERVICE_USER" \
  || fail "service did not reach the exact persistent disabled topology for recovery"
fsync_systemd_enablement_state \
  || fail "cannot persist disabled systemd state for interrupted-transaction recovery"
assert_service_persistently_disabled "$PREVIOUS_SERVICE_USER" \
  || fail "disabled topology drifted before recovery guard installation"
ensure_transaction_runtime_guard_loaded "$PREVIOUS_SERVICE_USER" \
  || fail "cannot install or revalidate the bounded recovery runtime guard"
stop_service_and_verify \
  || fail "interrupted service did not reach inactive/dead state with MainPID zero"

if [[ "$RECOVERY_COMMITTED" == "false" ]]; then
  atomic_link "$ACTIVATION_TARGET" \
    || fail "cannot restore the marker-recorded previous current target"
  restore_marker_dropin \
    || fail "cannot restore the marker-recorded previous managed drop-in state"
else
  [[ "$(readlink -f -- "$CURRENT_LINK")" == "$ACTIVATION_TARGET" ]] \
    || fail "committed marker current target drifted; refusing to restore the previous release"
  if [[ "$ACTIVATION_MODE" == "release" ]]; then
    assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
    assert_secure_systemd_file "$MANAGED_DROPIN" "managed systemd runtime drop-in"
    if [[ "$ORIGINAL_TX_STATUS" == "deploy_committed_pending_activation" ]]; then
      [[ "$(sha256sum "$MANAGED_DROPIN" | awk '{print $1}')" == "${DEPLOY_PENDING_CONTRACT[2]}" ]] \
        || fail "committed deployment managed drop-in differs from its pending evidence"
    fi
  else
    [[ ! -e "$MANAGED_DROPIN" && ! -L "$MANAGED_DROPIN" ]] \
      || fail "committed legacy target unexpectedly retains a managed runtime drop-in"
  fi
fi
systemctl daemon-reload || fail "systemd daemon-reload failed during guarded recovery"
assert_transaction_runtime_guard_loaded \
  || fail "bounded transaction runtime guard is not the exact effective recovery guard"

LEGACY_EXEC_ARGV_SPACE="$APP_ROOT/.venv/bin/python -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $LOCAL_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1"
LEGACY_EXEC_ARGV_EQUALS="$APP_ROOT/.venv/bin/python -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $LOCAL_PORT --proxy-headers --forwarded-allow-ips=127.0.0.1"
if [[ "$ACTIVATION_MODE" == "release" ]]; then
  EXPECTED_EXEC_PATH="$CURRENT_LINK/.venv/bin/python"
  EXPECTED_EXEC_ARGV="$MODERN_EXEC_ARGV"
  EXPECTED_EXEC_START_PRE_ARGVS_JSON="$MODERN_EXEC_START_PRE_ARGVS_JSON"
  EXPECTED_DROPIN="$MANAGED_DROPIN"
else
  EXPECTED_EXEC_PATH="$APP_ROOT/.venv/bin/python"
  EXPECTED_EXEC_START_PRE_ARGVS_JSON="[]"
  EFFECTIVE_LEGACY_ARGV="$(effective_exec_argv)"
  [[ "$EFFECTIVE_LEGACY_ARGV" == "$LEGACY_EXEC_ARGV_SPACE" \
    || "$EFFECTIVE_LEGACY_ARGV" == "$LEGACY_EXEC_ARGV_EQUALS" ]] \
    || fail "effective legacy recovery command line is not the registered baseline"
  EXPECTED_EXEC_ARGV="$EFFECTIVE_LEGACY_ARGV"
  EXPECTED_DROPIN=""
fi
[[ "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$EXPECTED_EXEC_PATH" \
  && "$(effective_exec_argv)" == "$EXPECTED_EXEC_ARGV" \
  && "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$CURRENT_LINK" \
  && "$(systemctl show "$SERVICE" --property=User --value)" == "$PREVIOUS_SERVICE_USER" \
  && "$(systemctl show "$SERVICE" --property=Group --value)" == "$PREVIOUS_SERVICE_GROUP" \
  && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
  && "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" \
  && "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" ]] \
  || fail "guarded recovery effective runtime differs from the marker contract"
if [[ "$ACTIVATION_MODE" == "release" ]]; then
  [[ "$(effective_exec_start_pre_argvs)" == "$EXPECTED_EXEC_START_PRE_ARGVS_JSON" ]] \
    || fail "guarded recovery release lacks the ordinary-restart production environment gate"
  effective_unset_environment_matches \
    || fail "guarded recovery release environment sanitization drifted"
  effective_environment_matches \
    || fail "guarded recovery release explicit environment drifted"
  effective_restart_limit_matches \
    || fail "guarded recovery release restart limiter drifted"
else
  [[ -z "$(systemctl show "$SERVICE" --property=ExecStartPre --value)" ]] \
    || fail "legacy recovery target inherited a modern ExecStartPre that it cannot satisfy"
fi
assert_service_persistently_disabled "$PREVIOUS_SERVICE_USER" \
  || fail "service became enabled before guarded recovery validation"

systemctl --no-block start "$SERVICE" || fail "guarded recovery activation target failed to start"
GUARDED_LOCAL_OK="false"
for _ in $(seq 1 "$SERVICE_HEALTH_ATTEMPTS"); do
  if systemctl is-active --quiet "$SERVICE" \
    && runtime_health "$ACTIVATION_MODE" "$ACTIVATION_MANIFEST_SHA256" \
      "http://127.0.0.1:$LOCAL_PORT/api/health" "$SERVICE_HEALTH_MAX_SECONDS" "$PUBLIC_HOST"; then
    GUARDED_LOCAL_OK="true"
    break
  fi
  sleep "$SERVICE_HEALTH_POLL_SECONDS"
done
[[ "$GUARDED_LOCAL_OK" == "true" ]] || fail "guarded recovery target local health failed"
GUARDED_MAIN_PID="$(systemctl show "$SERVICE" --property=MainPID --value)"
[[ "$GUARDED_MAIN_PID" =~ ^[1-9][0-9]*$ ]] || fail "guarded recovery has no live main process"
[[ "$(process_exec_argv "$GUARDED_MAIN_PID")" == "$EXPECTED_EXEC_ARGV" \
  && "$(process_working_directory "$GUARDED_MAIN_PID")" == "$ACTIVATION_TARGET" ]] \
  || fail "guarded recovery process provenance is invalid"
process_environment_matches "$GUARDED_MAIN_PID" \
  || fail "guarded recovery process environment is invalid"
validate_previous_runtime_provenance
runtime_health "$ACTIVATION_MODE" "$ACTIVATION_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || fail "guarded recovery target public health or release identity failed"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || fail "guarded recovery target did not enforce the login redirect"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "transaction database backup drifted before recovery logical commit"

# Prepare hidden evidence before the logical phase transition.  A retry may
# reuse only an exact root-owned pending record for the same activation target.
if [[ ! -e "$RECOVERY_RECORD" || -e "$PENDING_RECOVERY_RECORD" \
  || -L "$PENDING_RECOVERY_RECORD" ]]; then
  if [[ -e "$PENDING_RECOVERY_RECORD" || -L "$PENDING_RECOVERY_RECORD" ]]; then
    [[ -f "$PENDING_RECOVERY_RECORD" && ! -L "$PENDING_RECOVERY_RECORD" \
      && "$(realpath -e -- "$PENDING_RECOVERY_RECORD")" == "$PENDING_RECOVERY_RECORD" \
      && "$(stat -c '%u:%g:%a' -- "$PENDING_RECOVERY_RECORD")" == "0:0:640" ]] \
      || fail "pending recovery evidence is not a trusted canonical record"
    assert_trusted_record_file "$PENDING_RECOVERY_RECORD" \
      "existing pending recovery evidence"
  fi
  if [[ "$ACTIVATION_MODE" == "release" ]]; then
    RECOVERY_ORDINARY_RESTART_PROTECTED="true"
    RECOVERY_EXEC_START_PRE_ARGVS_JSON="$EXPECTED_EXEC_START_PRE_ARGVS_JSON"
  else
    RECOVERY_ORDINARY_RESTART_PROTECTED="false"
    RECOVERY_EXEC_START_PRE_ARGVS_JSON="[]"
  fi
  "$PYTHON_BIN" -I - "$PENDING_RECOVERY_RECORD" "$TX_OPERATION" \
    "$ACTIVATION_ID" "$ACTIVATION_MODE" "$FRAGMENT_SHA256" "$ENV_FILE_SHA256" \
    "$PUBLIC_ORIGIN" "$PUBLIC_HOST" "$RECOVERY_ORDINARY_RESTART_PROTECTED" \
    "$RECOVERY_EXPECTED_LEGACY_EXEC_START_PRE_ARGV" \
    "$RECOVERY_EXEC_START_PRE_ARGVS_JSON" "$DATABASE_BACKUP_METADATA_JSON" \
    "$RECOVERY_RUNTIME_BASELINE_PATH" "$RECOVERY_RUNTIME_BASELINE_SHA256" \
    "$RECOVERY_RUNTIME_FINGERPRINT_SHA256" \
    "$RECOVERY_RUNTIME_GUARD_HELPER_SHA256" <<'PY'
from __future__ import annotations
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
if sys.argv[9] not in {"true", "false"}:
    raise SystemExit("invalid ordinary restart validator flag")
ordinary_restart_protected = sys.argv[9] == "true"
common = {
    "interrupted_operation": sys.argv[2],
    "activation_release_id": sys.argv[3],
    "runtime_mode": sys.argv[4],
    "fragment_sha256": sys.argv[5],
    "environment_file_sha256": sys.argv[6],
    "public_origin": sys.argv[7],
    "public_host": sys.argv[8],
}
legacy_stable = {
    **common,
    "ordinary_restart_validator": {
        "protected": ordinary_restart_protected,
        "exec_start_pre_argv": sys.argv[10] or None,
    },
    "database_backup": json.loads(sys.argv[12]),
}
stable = {
    **common,
    "ordinary_restart_validator": {
        "protected": ordinary_restart_protected,
        "exec_start_pre_argvs": json.loads(sys.argv[11]),
    },
    "database_backup": json.loads(sys.argv[12]),
    "runtime_baseline_path": sys.argv[13] or None,
    "runtime_baseline_sha256": sys.argv[14] or None,
    "runtime_fingerprint_sha256": sys.argv[15] or None,
    "runtime_guard_helper_sha256": sys.argv[16] or None,
}
checks = {
    "isolated_service_user_preflight": True,
    "service_stopped_before_restore": True,
    "service_disabled_during_recovery": True,
    "bounded_runtime_guard": True,
    "exact_activation_target": True,
    "effective_runtime": True,
    "running_process_runtime": True,
    "local_health": True,
    "public_health": True,
    "public_login_redirect": True,
    "production_environment_validated_three_phases": True,
    "final_publication_configuration_gate": True,
    "ordinary_restart_environment_gate": ordinary_restart_protected,
    "ordinary_restart_integrity_gate": ordinary_restart_protected,
    "service_enabled_after_health": True,
}
if path.exists():
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_gid != 0 or stat.S_IMODE(metadata.st_mode) != 0o640:
        raise SystemExit("pending recovery record is not trusted")
    record = json.loads(path.read_text(encoding="utf-8"))
    schema = record.get("schema_version") if isinstance(record, dict) else None
    expected_checks = checks if schema == 5 else {
        key: value for key, value in checks.items()
        if key != "ordinary_restart_integrity_gate"
    }
    expected_stable = stable if schema == 5 else legacy_stable
    if (
        type(record) is not dict
        or type(record.get("schema_version")) is not int
        or record.get("schema_version") not in {4, 5}
        or record.get("status") != "passed"
        or type(record.get("checks")) is not dict
        or set(record["checks"]) != set(expected_checks)
        or any(
            type(record["checks"].get(key)) is not bool
            or record["checks"].get(key) is not expected
            for key, expected in expected_checks.items()
        )
    ):
        raise SystemExit("pending recovery record contract mismatch")
    if any(record.get(key) != value for key, value in expected_stable.items()):
        raise SystemExit("pending recovery record target mismatch")
else:
    record = {
        "schema_version": 5,
        "status": "passed",
        **stable,
        "recovered_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "checks": checks,
    }
    payload = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o640)
    try:
        os.fchmod(descriptor, 0o640)
        os.fchown(descriptor, 0, 0)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
PY
  assert_trusted_record_file "$PENDING_RECOVERY_RECORD" "pending recovery evidence record"
  fsync_file "$PENDING_RECOVERY_RECORD"
  fsync_directory "$DEPLOYMENT_DIR"
fi

if [[ "$RECOVERY_COMMITTED" == "false" ]]; then
  transition_transaction_status "$TX_STATUS" "recovery_committed_pending_activation" \
    "$ACTIVATION_ID" "$ACTIVATION_MODE" \
    || fail "cannot durably commit the recovered previous target inside the active marker"
  TX_STATUS="recovery_committed_pending_activation"
  RECOVERY_COMMITTED="true"
fi

stop_service_and_verify || fail "cannot stop the guarded committed recovery process"
assert_service_persistently_disabled "$PREVIOUS_SERVICE_USER" \
  || fail "service enablement drifted while finalizing committed recovery"
remove_transaction_runtime_guard "$PREVIOUS_SERVICE_USER" \
  || fail "cannot remove the recovery runtime guard and restore the production restart policy"
assert_service_persistently_disabled "$PREVIOUS_SERVICE_USER" \
  || fail "service became enabled before final committed recovery validation"

systemctl --no-block start "$SERVICE" || fail "committed recovery target failed to start without the guard"
FINAL_LOCAL_OK="false"
for _ in $(seq 1 "$SERVICE_HEALTH_ATTEMPTS"); do
  if systemctl is-active --quiet "$SERVICE" \
    && runtime_health "$ACTIVATION_MODE" "$ACTIVATION_MANIFEST_SHA256" \
      "http://127.0.0.1:$LOCAL_PORT/api/health" "$SERVICE_HEALTH_MAX_SECONDS" "$PUBLIC_HOST"; then
    FINAL_LOCAL_OK="true"
    break
  fi
  sleep "$SERVICE_HEALTH_POLL_SECONDS"
done
[[ "$FINAL_LOCAL_OK" == "true" ]] || fail "committed recovery target final local health failed"
FINAL_MAIN_PID="$(systemctl show "$SERVICE" --property=MainPID --value)"
[[ "$FINAL_MAIN_PID" =~ ^[1-9][0-9]*$ && "$FINAL_MAIN_PID" != "$GUARDED_MAIN_PID" ]] \
  || fail "committed recovery did not replace the guarded process"
[[ "$(process_exec_argv "$FINAL_MAIN_PID")" == "$EXPECTED_EXEC_ARGV" \
  && "$(process_working_directory "$FINAL_MAIN_PID")" == "$ACTIVATION_TARGET" ]] \
  || fail "committed recovery process provenance is invalid"
process_environment_matches "$FINAL_MAIN_PID" \
  || fail "committed recovery process environment is invalid"
[[ "$(readlink -f -- "$CURRENT_LINK")" == "$ACTIVATION_TARGET" \
  && "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
  && "$(systemctl show "$SERVICE" --property=Restart --value)" == "on-failure" \
  && "$(systemctl show "$SERVICE" --property=RuntimeMaxUSec --value)" == "infinity" \
  && "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$EXPECTED_EXEC_PATH" \
  && "$(effective_exec_argv)" == "$EXPECTED_EXEC_ARGV" \
  && "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$CURRENT_LINK" \
  && "$(systemctl show "$SERVICE" --property=User --value)" == "$PREVIOUS_SERVICE_USER" \
  && "$(systemctl show "$SERVICE" --property=Group --value)" == "$PREVIOUS_SERVICE_GROUP" \
  && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
  && "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" \
  && "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" \
  && "$(systemctl show "$SERVICE" --property=MainPID --value)" == "$FINAL_MAIN_PID" ]] \
  || fail "committed recovery effective runtime drifted before enablement"
if [[ "$ACTIVATION_MODE" == "release" ]]; then
  [[ "$(effective_exec_start_pre_argvs)" == "$EXPECTED_EXEC_START_PRE_ARGVS_JSON" ]] \
    || fail "committed release recovery ordinary-restart environment gate drifted before enablement"
else
  [[ -z "$(systemctl show "$SERVICE" --property=ExecStartPre --value)" ]] \
    || fail "committed legacy recovery unexpectedly gained a modern ExecStartPre"
fi
if [[ -n "$EXPECTED_DROPIN" ]]; then
  assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" "$EXPECTED_DROPIN" \
    || fail "committed recovery managed drop-in set drifted before enablement"
else
  assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" \
    || fail "committed legacy recovery retained an unexpected drop-in before enablement"
fi
assert_service_persistently_disabled "$PREVIOUS_SERVICE_USER" \
  || fail "committed recovery became enabled before final validation"
validate_previous_runtime_provenance
runtime_health "$ACTIVATION_MODE" "$ACTIVATION_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || fail "committed recovery public health or release identity failed before enablement"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || fail "committed recovery login redirect failed before enablement"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "transaction database backup drifted before recovery enablement"
validate_production_environment \
  || fail "production environment failed the recovery final evidence and enablement gate"

systemctl enable "$SERVICE" || fail "cannot enable the committed recovery target"
assert_standard_enabled_topology "$PREVIOUS_SERVICE_USER" \
  || fail "committed recovery enablement topology is not uniquely standard"
fsync_systemd_enablement_state \
  || fail "cannot persist committed recovery enablement topology"
assert_standard_enabled_topology "$PREVIOUS_SERVICE_USER" \
  || fail "committed recovery enablement topology drifted after persistence"
[[ "$(readlink -f -- "$CURRENT_LINK")" == "$ACTIVATION_TARGET" \
  && "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
  && "$(systemctl show "$SERVICE" --property=Restart --value)" == "on-failure" \
  && "$(systemctl show "$SERVICE" --property=RuntimeMaxUSec --value)" == "infinity" \
  && "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$EXPECTED_EXEC_PATH" \
  && "$(effective_exec_argv)" == "$EXPECTED_EXEC_ARGV" \
  && "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$CURRENT_LINK" \
  && "$(systemctl show "$SERVICE" --property=User --value)" == "$PREVIOUS_SERVICE_USER" \
  && "$(systemctl show "$SERVICE" --property=Group --value)" == "$PREVIOUS_SERVICE_GROUP" \
  && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
  && "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" \
  && "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" \
  && "$(systemctl show "$SERVICE" --property=MainPID --value)" == "$FINAL_MAIN_PID" ]] \
  || fail "committed recovery effective runtime changed during enablement"
if [[ "$ACTIVATION_MODE" == "release" ]]; then
  [[ "$(effective_exec_start_pre_argvs)" == "$EXPECTED_EXEC_START_PRE_ARGVS_JSON" ]] \
    || fail "committed recovery ordinary-restart environment gate changed during enablement"
else
  [[ -z "$(systemctl show "$SERVICE" --property=ExecStartPre --value)" ]] \
    || fail "legacy recovery gained an unsupported modern ExecStartPre during enablement"
fi
if [[ -n "$EXPECTED_DROPIN" ]]; then
  assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" "$EXPECTED_DROPIN" \
    || fail "committed recovery managed drop-in set changed during enablement"
else
  assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" \
    || fail "committed legacy recovery acquired an unexpected drop-in during enablement"
fi
systemctl is-active --quiet "$SERVICE" || fail "committed recovery service stopped during enablement"
[[ "$(process_exec_argv "$FINAL_MAIN_PID")" == "$EXPECTED_EXEC_ARGV" \
  && "$(process_working_directory "$FINAL_MAIN_PID")" == "$ACTIVATION_TARGET" ]] \
  || fail "committed recovery process provenance drifted after enablement"
validate_previous_runtime_provenance
runtime_health "$ACTIVATION_MODE" "$ACTIVATION_MANIFEST_SHA256" \
  "http://127.0.0.1:$LOCAL_PORT/api/health" 8 "$PUBLIC_HOST" \
  || fail "committed recovery local health or release identity drifted after enablement"
runtime_health "$ACTIVATION_MODE" "$ACTIVATION_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || fail "committed recovery public health or release identity drifted after enablement"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || fail "committed recovery login redirect drifted after enablement"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "transaction database backup drifted after recovery enablement"

# Publish the original operation's protected pending evidence, if recovery is
# finalizing an already-committed deploy or rollback, before archiving its marker.
validate_rollback_evidence_record() {
  local record_path="$1"
  assert_trusted_record_file "$record_path" "rollback evidence record"
  "$PYTHON_BIN" -I - "$record_path" "$ACTIVATION_ID" "$MARKER_PREVIOUS_ID" \
    "$ACTIVATION_MODE" "$FRAGMENT_SHA256" "$ENV_FILE_SHA256" \
    "$PUBLIC_ORIGIN" "$PUBLIC_HOST" "$RECOVERY_EXPECTED_ORDINARY_RESTART_PROTECTED" \
    "$RECOVERY_EXPECTED_LEGACY_EXEC_START_PRE_ARGV" \
    "$RECOVERY_EXPECTED_EXEC_START_PRE_ARGVS_JSON" "$DATABASE_BACKUP_METADATA_JSON" \
    "$RECOVERY_RUNTIME_BASELINE_PATH" "$RECOVERY_RUNTIME_BASELINE_SHA256" \
    "$RECOVERY_RUNTIME_FINGERPRINT_SHA256" \
    "$RECOVERY_RUNTIME_GUARD_HELPER_SHA256" <<'PY'
import json
import re
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
if sys.argv[9] not in {"true", "false"}:
    raise SystemExit("invalid expected ordinary restart validator flag")
ordinary_restart_protected = sys.argv[9] == "true"
metadata = path.stat()
if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_gid != 0 or stat.S_IMODE(metadata.st_mode) != 0o640:
    raise SystemExit("rollback evidence file is not trusted")
record = json.loads(path.read_text(encoding="utf-8"))
schema = record.get("schema_version") if isinstance(record, dict) else None
expected_keys = {
    "schema_version", "status", "target_release_id", "previous_release_id",
    "runtime_mode", "fragment_sha256", "managed_dropin_sha256_before",
    "environment_file_sha256", "public_origin", "public_host",
    "ordinary_restart_validator", "database_backup", "rolled_back_at", "checks",
}
if schema == 5:
    expected_keys |= {
        "runtime_baseline_path", "runtime_baseline_sha256",
        "runtime_fingerprint_sha256", "runtime_guard_helper_sha256",
    }
required_checks = {
    "isolated_service_user_preflight", "security_database_backup",
    "known_good_health_before_switch", "service_disabled_during_switch",
    "service_stopped_before_switch", "atomic_symlink", "effective_runtime",
    "running_process_runtime", "local_health", "public_health",
    "public_login_redirect", "production_environment_validated_three_phases",
    "final_publication_configuration_gate",
    "ordinary_restart_environment_gate", "service_enabled_after_health",
}
if schema == 5:
    required_checks.add("ordinary_restart_integrity_gate")
if schema == 4:
    expected_validator = {
        "protected": ordinary_restart_protected,
        "exec_start_pre_argv": sys.argv[10] or None,
    }
else:
    expected_validator = {
        "protected": ordinary_restart_protected,
        "exec_start_pre_argvs": json.loads(sys.argv[11]),
    }
if (
    type(record) is not dict
    or set(record) != expected_keys
    or type(record.get("schema_version")) is not int
    or record.get("schema_version") not in {4, 5}
    or record.get("status") != "passed"
    or record.get("target_release_id") != sys.argv[2]
    or record.get("previous_release_id") != sys.argv[3]
    or record.get("runtime_mode") != sys.argv[4]
    or record.get("fragment_sha256") != sys.argv[5]
    or record.get("environment_file_sha256") != sys.argv[6]
    or record.get("public_origin") != sys.argv[7]
    or record.get("public_host") != sys.argv[8]
    or record.get("ordinary_restart_validator") != expected_validator
    or record.get("database_backup") != json.loads(sys.argv[12])
    or (
        schema == 5
        and (
            record.get("runtime_baseline_path") != (sys.argv[13] or None)
            or record.get("runtime_baseline_sha256") != (sys.argv[14] or None)
            or record.get("runtime_fingerprint_sha256") != (sys.argv[15] or None)
            or record.get("runtime_guard_helper_sha256") != (sys.argv[16] or None)
        )
    )
    or not isinstance(record.get("rolled_back_at"), str)
    or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", record["rolled_back_at"])
    or type(record.get("checks")) is not dict
    or set(record["checks"]) != required_checks
    or any(
        type(record["checks"][key]) is not bool
        or record["checks"][key]
        is not (
            ordinary_restart_protected
            if key in {
                "ordinary_restart_environment_gate",
                "ordinary_restart_integrity_gate",
            }
            else True
        )
        for key in required_checks
    )
):
    raise SystemExit("rollback evidence target or contract mismatch")
PY
}

if [[ "$ORIGINAL_TX_STATUS" == "deploy_committed_pending_activation" ]]; then
  ORIGINAL_FINAL_RECORD="$DEPLOYMENT_DIR/$ACTIVATION_ID.json"
  ORIGINAL_PENDING_RECORD="$DEPLOYMENT_DIR/.pending-deploy-$ACTIVATION_ID.json"
  validate_final_publication_configuration \
    || fail "committed deployment recovery configuration drifted before original passed-record publication"
  validate_production_environment \
    || fail "production environment failed immediately before recovered deployment passed-record publication"
  reconcile_or_publish_committed_record "$ORIGINAL_PENDING_RECORD" "$ORIGINAL_FINAL_RECORD" \
    || fail "cannot reconcile or publish the committed deployment passed record during recovery"
  validate_passed_release_record "$ORIGINAL_FINAL_RECORD"
elif [[ "$ORIGINAL_TX_STATUS" == "rollback_committed_pending_activation" ]]; then
  ORIGINAL_PENDING_RECORD="$DEPLOYMENT_DIR/.pending-rollback-$MARKER_PREVIOUS_ID-to-$ACTIVATION_ID.json"
  ORIGINAL_FINAL_RECORD="$DEPLOYMENT_DIR/rollback-$TX_STAMP-to-$ACTIVATION_ID.json"
  if [[ -e "$ORIGINAL_PENDING_RECORD" || -L "$ORIGINAL_PENDING_RECORD" ]]; then
    validate_rollback_evidence_record "$ORIGINAL_PENDING_RECORD" \
      || fail "committed rollback pending evidence does not match the marker target"
  fi
  validate_final_publication_configuration \
    || fail "committed rollback recovery configuration drifted before original passed-record publication"
  validate_production_environment \
    || fail "production environment failed immediately before recovered rollback passed-record publication"
  reconcile_or_publish_committed_record "$ORIGINAL_PENDING_RECORD" "$ORIGINAL_FINAL_RECORD" \
    || fail "cannot reconcile or publish the committed rollback passed record during recovery"
  validate_rollback_evidence_record "$ORIGINAL_FINAL_RECORD" \
    || fail "committed rollback final evidence does not match the marker target"
fi

validate_final_publication_configuration \
  || fail "recovery target configuration drifted before recovery passed-record publication"
validate_production_environment \
  || fail "production environment failed immediately before recovery passed-record publication"
reconcile_or_publish_committed_record "$PENDING_RECOVERY_RECORD" "$RECOVERY_RECORD" \
  || fail "recovery target remains committed under the active marker because passed evidence publication failed; rerun recover-transaction.sh"
validate_recovery_evidence_record "$RECOVERY_RECORD" \
  || fail "published recovery evidence no longer matches the committed target"
mv -T -- "$TRANSACTION_FILE" "$ARCHIVED_TRANSACTION_RECORD" \
  || fail "activated recovery target published its passed evidence but could not archive the active marker"
RECOVERY_ACTIVE="false"
assert_trusted_root_file_path "$ARCHIVED_TRANSACTION_RECORD" \
  "archived recovered transaction evidence"
fsync_file "$ARCHIVED_TRANSACTION_RECORD" \
  || fail "recovery activation completed but transaction evidence durability is incomplete"
fsync_directory "$DEPLOYMENT_DIR" \
  || fail "recovery activation completed but evidence directory durability is incomplete"
fsync_directory "$APP_ROOT" \
  || fail "recovery activation completed but marker archive durability is incomplete"
trap - EXIT INT TERM HUP

printf 'RECOVERY PASS: activated %s (%s) from %s\n' \
  "$ACTIVATION_ID" "$ACTIVATION_MODE" "$ORIGINAL_TX_STATUS"
printf 'The committed marker remained active through unguarded start, enablement, and full provenance/health revalidation.\n'
