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
  [[ "$(sha256sum "$ENV_FILE" | awk '{print $1}')" == "$ENV_FILE_SHA256" \
    && "$(sha256sum "$FRAGMENT_PATH" | awk '{print $1}')" == "$UNIT_FRAGMENT_SHA256" ]] \
    || return 1
  cmp -s "$FRAGMENT_PATH" "$UNIT_BACKUP" || return 1
  assert_trusted_root_file_path "$ENV_FILE" "production environment file" || return 1
  assert_secure_systemd_directory "/etc/systemd/system" \
    "systemd administrator unit directory" || return 1
  assert_secure_systemd_file "$FRAGMENT_PATH" "systemd base unit" || return 1
  [[ "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
    && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" ]] \
    || return 1
  if [[ "$TARGET_MODE" == "release" ]]; then
    assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" \
      "managed systemd drop-in directory" || return 1
    assert_secure_systemd_file "$MANAGED_DROPIN" \
      "managed systemd runtime drop-in" || return 1
    [[ "$(sha256sum "$MANAGED_DROPIN" | awk '{print $1}')" == "$TARGET_MANAGED_DROPIN_SHA256" \
      && "$(effective_exec_start_pre_argvs)" == "$MODERN_EXEC_START_PRE_ARGVS_JSON" ]] \
      || return 1
    managed_dropin_matches_canonical_content || return 1
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
  assert_trusted_record_file "$temporary" "pending rollback evidence"
  [[ ! -e "$final" && ! -L "$final" ]] || return 1
  ln -T -- "$temporary" "$final" || return 1
  assert_trusted_record_file "$final" "published rollback evidence"
  [[ "$(stat -c '%d:%i' -- "$temporary")" == "$(stat -c '%d:%i' -- "$final")" ]] \
    || return 1
  fsync_directory "$DEPLOYMENT_DIR" || return 1
  rm -f -- "$temporary" || return 1
  [[ ! -e "$temporary" && ! -L "$temporary" ]] || return 1
  fsync_directory "$DEPLOYMENT_DIR"
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
  local temporary="$APP_ROOT/.transaction-phase-$$-$RANDOM.tmp"
  assert_trusted_root_file_path "$TRANSACTION_FILE" "active transaction marker"
  "$PYTHON_BIN" -I - "$TRANSACTION_FILE" "$temporary" \
    "$expected_status" "$new_status" <<'PY'
import json
import os
import stat
import sys

marker, temporary, expected, new = sys.argv[1:]
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
  if runuser -u "$SERVICE_USER" -- "$TEST_BIN" -w "$directory"; then
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
  if runuser -u "$SERVICE_USER" -- "$TEST_BIN" -w "$file"; then
    fail "$label is writable by the service account"
  fi
}

validate_passed_release_record() {
  local record="$1"
  local release_id="$2"
  local target="$3"
  local fields
  local baseline_verification_json
  assert_trusted_record_file "$record" "release $release_id passed deployment record"
  mapfile -t fields < <("$PYTHON_BIN" -I - "$record" "$release_id" \
    "$PUBLIC_ORIGIN" "$PUBLIC_HOST" "$MODERN_EXEC_START_PRE_ARGVS_JSON" \
    "$RUNTIME_BASELINE_DIR/$release_id.json" "$MANAGED_DROPIN" <<'PY'
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
    raise SystemExit("release deployment record is not a JSON object")
schema = record.get("schema_version")
if type(schema) is not int or schema not in {2, 3, 4, 5}:
    raise SystemExit("release deployment record schema is invalid")
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
    raise SystemExit("release deployment record is not a complete passed release-local runtime")
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
    || fail "release $release_id passed record schema is unreadable"
  require_activatable_passed_record_schema "${fields[0]}"
  [[ "${#fields[@]}" == "8" ]] \
    || fail "release $release_id passed record fields are incomplete"
  [[ "$(runtime_fingerprint "$target/.venv" "$target/.venv/bin/python" \
    "$target/requirements.production.lock.txt" "$target")" == "${fields[4]}" ]] \
    || fail "release $release_id runtime fingerprint drifted from its passed record"
  "$PYTHON_BIN" -I "$SCRIPT_DIR/verify_installed_release.py" \
    "$target" --expected-version "${fields[1]}" \
    || fail "release $release_id installed source verification failed"
  assert_release_tree_security "$target" "$SERVICE_USER"
  [[ "$(sha256sum "$target/release-manifest.json" | awk '{print $1}')" == "${fields[3]}" ]] \
    || fail "release $release_id manifest digest drifted from its passed record"
  [[ "$(sha256sum "$RUNTIME_BASELINE_DIR/$release_id.json" | awk '{print $1}')" \
    == "${fields[5]}" \
    && "$(printf '%s' "${fields[4]}" | sha256sum | awk '{print $1}')" \
    == "${fields[6]}" \
    && "$(sha256sum "$RUNTIME_GUARD_HELPER" | awk '{print $1}')" \
    == "${fields[7]}" ]] \
    || fail "release $release_id schema 5 record disagrees with runtime baseline, fingerprint, or helper bytes"
  baseline_verification_json="$(verify_release_runtime_baseline \
    "$release_id" "$target" "${fields[3]}")" \
    || fail "release $release_id external runtime baseline is missing or invalid"
  runtime_baseline_verification_matches_record \
    "$baseline_verification_json" "$release_id" "${fields[1]}" "${fields[3]}" \
    "${fields[5]}" "${fields[6]}" "${fields[7]}" \
    || fail "release $release_id runtime baseline evidence disagrees with its schema 5 passed record"
}

validate_legacy_baseline() {
  local target="$1"
  local record="$DEPLOYMENT_DIR/legacy-baseline-$LEGACY_RELEASE_ID.json"
  local runtime_json
  [[ -f "$record" && ! -L "$record" \
    && "$(stat -c '%u:%g:%a' -- "$record")" == "0:0:600" ]] \
    || fail "registered legacy baseline record is missing or unsafe"
  assert_trusted_root_file_path "$record" "registered legacy baseline record"
  runtime_json="$(runtime_fingerprint "$APP_ROOT/.venv" "$APP_ROOT/.venv/bin/python")" \
    || fail "cannot fingerprint the registered legacy runtime"
  "$PYTHON_BIN" -I - "$record" "$LEGACY_RELEASE_ID" "$SYSTEMD_UNIT_FILE" \
    "$target" "$APP_ROOT/.venv" "$runtime_json" <<'PY'
from __future__ import annotations
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

record_path, release_id, fragment_name, release_name, runtime_name, runtime_json = sys.argv[1:]

def release_digest(root_name: str) -> str:
    root = Path(root_name).resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        metadata = path.lstat()
        prefix = f"{stat.S_IMODE(metadata.st_mode):04o}:{metadata.st_uid}:{metadata.st_gid}".encode()
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + prefix + b"\0" + os.readlink(path).encode() + b"\0")
        elif path.is_dir():
            digest.update(b"D\0" + relative + b"\0" + prefix + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0" + prefix + b"\0")
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            digest.update(b"\0")
        else:
            raise SystemExit("unsupported legacy release entry")
    return digest.hexdigest()

def runtime_digest(root_name: str) -> str:
    root = Path(root_name).resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + os.readlink(path).encode() + b"\0")
        elif path.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0")
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            digest.update(b"\0")
        else:
            raise SystemExit("unsupported legacy runtime entry")
    return digest.hexdigest()

fragment = Path(fragment_name)
expected = {
    "schema_version": 2,
    "release_id": release_id,
    "fragment_path": fragment_name,
    "fragment_sha256": hashlib.sha256(fragment.read_bytes()).hexdigest(),
    "dropin_paths": [],
    "legacy_release_sha256": release_digest(release_name),
    "runtime_fingerprint": json.loads(runtime_json),
}
record = json.loads(Path(record_path).read_text(encoding="utf-8"))
if record != expected:
    raise SystemExit("legacy baseline record drifted from the registered runtime")
PY
}

validate_runtime_provenance() {
  local runtime_mode="$1"
  local release_id="$2"
  local target="$3"
  case "$runtime_mode" in
    release)
      validate_passed_release_record \
        "$DEPLOYMENT_DIR/$release_id.json" "$release_id" "$target"
      ;;
    legacy)
      [[ "$release_id" == "$LEGACY_RELEASE_ID" ]] \
        || fail "legacy runtime provenance does not match the registered release"
      validate_legacy_baseline "$target"
      ;;
    *)
      fail "unsupported runtime mode for provenance validation"
      ;;
  esac
}

RELEASE_ID=""
CONFIRMED="false"
while (($#)); do
  case "$1" in
    --release-id)
      (($# >= 2)) || fail "--release-id requires a value"
      RELEASE_ID="$2"
      shift 2
      ;;
    --confirm-rollback)
      CONFIRMED="true"
      shift
      ;;
    --help|-h)
      printf 'Usage: rollback-release.sh --release-id ID --confirm-rollback\n'
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

[[ "$EUID" == "0" ]] || fail "run as root"
[[ "$CONFIRMED" == "true" && -n "$RELEASE_ID" ]] || fail "explicit rollback confirmation is required"
[[ "$RELEASE_ID" =~ ^[0-9A-Za-z][0-9A-Za-z._-]{0,79}$ ]] || fail "invalid release id"

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
  awk basename cat chmod chown cmp cp curl date dirname flock getfacl grep id \
  install journalctl ln mv readlink realpath rm runuser sed seq sha256sum sleep stat \
  sync systemctl systemd-run; do
  resolve_and_pin_trusted_command "$trusted_command" TRUSTED_COMMAND_PATH
done
builtin unset TRUSTED_COMMAND_PATH
builtin readonly PYTHON_BIN FIND_BIN SH_BIN TEST_BIN
for trusted_helper in \
  "$SCRIPT_DIR/rollback-release.sh" \
  "$SCRIPT_DIR/atomic_rename.py" \
  "$SCRIPT_DIR/run_with_env.py" \
  "$SCRIPT_DIR/runtime_fingerprint.py" \
  "$SCRIPT_DIR/sqlite_backup.py" \
  "$SCRIPT_DIR/validate_production_env.py" \
  "$SCRIPT_DIR/verify_installed_release.py"; do
  assert_trusted_code_file "$trusted_helper" "rollback control helper"
done

APP_ROOT="${PROTOCOL_STUDIO_DEPLOY_ROOT:-/srv/apps/protocol-studio}"
ENV_FILE="${PROTOCOL_STUDIO_ENV_FILE:-/etc/protocol-studio/protocol-studio.env}"
SERVICE="${PROTOCOL_STUDIO_SYSTEMD_SERVICE:-protocol-studio.service}"
PUBLIC_ORIGIN="${PROTOCOL_STUDIO_PUBLIC_ORIGIN:-https://protocol.feian.online}"
LOCAL_PORT="${PROTOCOL_STUDIO_LOCAL_PORT:-18771}"
PREFLIGHT_PORT="${PROTOCOL_STUDIO_PREFLIGHT_PORT:-18772}"
LEGACY_RELEASE_ID="${PROTOCOL_STUDIO_LEGACY_RELEASE_ID:-20260722-114300-620b1bcf9aa9}"
[[ "$SERVICE" =~ ^[0-9A-Za-z_.@-]+\.service$ ]] || fail "invalid systemd service name"
[[ "$LOCAL_PORT" =~ ^[0-9]+$ && "$PREFLIGHT_PORT" =~ ^[0-9]+$ ]] \
  || fail "local ports must be numeric"
((LOCAL_PORT >= 1 && LOCAL_PORT <= 65535)) || fail "local service port is invalid"
((PREFLIGHT_PORT >= 1 && PREFLIGHT_PORT <= 65535)) || fail "preflight port is invalid"
[[ "$LOCAL_PORT" != "$PREFLIGHT_PORT" ]] || fail "preflight port must differ from the production port"
[[ "$APP_ROOT" == /* && "$ENV_FILE" == /* ]] || fail "rollback paths must be absolute"

PUBLIC_ORIGIN="${PUBLIC_ORIGIN%/}"
PUBLIC_HOST="${PUBLIC_ORIGIN#*://}"
PUBLIC_HOST="${PUBLIC_HOST%%/*}"
PUBLIC_HOST="${PUBLIC_HOST%%:*}"
PUBLIC_HOST="${PUBLIC_HOST,,}"
[[ -n "$PUBLIC_HOST" ]] || fail "public origin has no host"
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
TARGET="$RELEASES_DIR/$RELEASE_ID"
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
TRANSACTION_TEMP="$APP_ROOT/.rollback-transaction-$RELEASE_ID-$$.tmp"

case "$TARGET" in
  "$RELEASES_DIR"/*) ;;
  *) fail "target escaped the releases directory" ;;
esac
assert_trusted_root_directory_path "$APP_ROOT" "application root"
assert_trusted_root_directory_path "$RELEASES_DIR" "release storage directory"
assert_trusted_root_directory_path "$CONTROL_DIR" "deployment control directory"
assert_trusted_root_directory_path "$LOG_DIR" "deployment log directory"
assert_trusted_root_directory_path "$BACKUP_DIR" "deployment backup directory"
assert_trusted_root_directory_path "$DEPLOYMENT_DIR" "deployment record directory"
[[ -d "$TARGET" && ! -L "$TARGET" \
  && "$(realpath -e -- "$TARGET")" == "$TARGET" ]] \
  || fail "target release must be a canonical real directory"
assert_trusted_root_file_path "$ENV_FILE" "production environment file"
"$PYTHON_BIN" -I "$SCRIPT_DIR/run_with_env.py" --env-file "$ENV_FILE" \
  --validate-only --reject-privileged-loader-variables
[[ -d "$SHARED_DIR" && ! -L "$SHARED_DIR" \
  && "$(realpath -e -- "$SHARED_DIR")" == "$SHARED_DIR" \
  && -d "$RUNS_DIR" && ! -L "$RUNS_DIR" \
  && "$(realpath -e -- "$RUNS_DIR")" == "$RUNS_DIR" \
  && -f "$SECURITY_DB" && ! -L "$SECURITY_DB" \
  && "$(realpath -e -- "$SECURITY_DB")" == "$SECURITY_DB" ]] \
  || fail "shared production state is missing or unsafe"
LOCK_FILE="$CONTROL_DIR/deploy.lock"
[[ -f "$LOCK_FILE" && ! -L "$LOCK_FILE" \
  && "$(stat -c '%u:%g:%a' -- "$LOCK_FILE")" == "0:0:600" ]] \
  || fail "deployment lock must be a root-owned regular file with mode 0600"
assert_trusted_root_file_path "$LOCK_FILE" "deployment lock"
exec 9<>"$LOCK_FILE"
flock -n 9 || fail "another deployment is running"
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
[[ ! -e "$TRANSACTION_FILE" && ! -L "$TRANSACTION_FILE" ]] \
  || fail "an unfinished deployment transaction exists; recover it before starting a rollback"
verify_atomic_rename_boundary \
  || fail "application and deployment-record directories failed the atomic rename boundary gate"

[[ -L "$CURRENT_LINK" ]] || fail "current is not a symbolic link"
PREVIOUS_TARGET="$(readlink -f -- "$CURRENT_LINK")"
case "$PREVIOUS_TARGET" in
  "$RELEASES_DIR"/*) ;;
  *) fail "current target is outside the releases directory" ;;
esac
[[ -d "$PREVIOUS_TARGET" ]] || fail "current target is missing"
[[ "$PREVIOUS_TARGET" != "$TARGET" ]] || fail "target release is already current"
PREVIOUS_ID="$(basename -- "$PREVIOUS_TARGET")"

systemctl is-enabled --quiet "$SERVICE" || fail "systemd service is not enabled"
systemctl is-active --quiet "$SERVICE" || fail "systemd service is not active"
[[ "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" ]] \
  || fail "systemd has unapplied unit changes; review and daemon-reload before rollback"
SERVICE_USER="$(systemctl show "$SERVICE" --property=User --value)"
SERVICE_GROUP="$(systemctl show "$SERVICE" --property=Group --value)"
[[ -n "$SERVICE_USER" && "$SERVICE_USER" != "root" ]] \
  || fail "systemd service must use a named unprivileged account"
[[ -n "$SERVICE_GROUP" ]] || SERVICE_GROUP="$SERVICE_USER"
assert_standard_enabled_topology "$SERVICE_USER" \
  || fail "existing service enablement is not the unique standard multi-user topology"
assert_secure_runtime_directory "$RUNTIME_SYSTEMD_DIR" \
  "systemd runtime unit directory" "$SERVICE_USER"
[[ ! -e "$TRANSACTION_RUNTIME_GUARD" && ! -L "$TRANSACTION_RUNTIME_GUARD" ]] \
  || fail "a transaction runtime guard already exists; recover the interrupted transaction"
if [[ -e "$TRANSACTION_RUNTIME_GUARD_DIR" || -L "$TRANSACTION_RUNTIME_GUARD_DIR" ]]; then
  assert_secure_runtime_directory "$TRANSACTION_RUNTIME_GUARD_DIR" \
    "transaction runtime guard directory" "$SERVICE_USER"
  shopt -s nullglob dotglob
  RUNTIME_GUARD_DIR_ENTRIES=("$TRANSACTION_RUNTIME_GUARD_DIR"/*)
  shopt -u nullglob dotglob
  ((${#RUNTIME_GUARD_DIR_ENTRIES[@]} == 0)) \
    || fail "the transaction runtime guard directory contains stale or unreviewed entries"
fi
SERVICE_UID="$(id -u "$SERVICE_USER")"
SERVICE_GID="$("$PYTHON_BIN" -I - "$SERVICE_GROUP" <<'PY'
import grp
import sys
print(grp.getgrnam(sys.argv[1]).gr_gid)
PY
)"
[[ "$SERVICE_UID" =~ ^[1-9][0-9]*$ && "$SERVICE_GID" =~ ^[1-9][0-9]*$ ]] \
  || fail "systemd service uid and gid must both be nonzero"
[[ "$(stat -c '%u:%g:%a' -- "$SHARED_DIR")" == "$SERVICE_UID:$SERVICE_GID:700" \
  && "$(stat -c '%u:%g:%a' -- "$RUNS_DIR")" == "$SERVICE_UID:$SERVICE_GID:700" \
  && "$(stat -c '%u:%g:%a' -- "$SECURITY_DB")" == "$SERVICE_UID:$SERVICE_GID:600" ]] \
  || fail "shared state ownership or mode does not match the dedicated service account"
[[ "$(getfacl -cp -- "$SHARED_DIR")" == $'user::rwx\ngroup::---\nother::---' \
  && "$(getfacl -cp -- "$RUNS_DIR")" == $'user::rwx\ngroup::---\nother::---' \
  && "$(getfacl -cp -- "$SECURITY_DB")" == $'user::rw-\ngroup::---\nother::---' ]] \
  || fail "shared state contains an unexpected access-control entry"
if runuser -u "$SERVICE_USER" -- "$TEST_BIN" -w "$APP_ROOT" \
  || runuser -u "$SERVICE_USER" -- "$TEST_BIN" -w "$RELEASES_DIR" \
  || runuser -u "$SERVICE_USER" -- "$TEST_BIN" -w "$CONTROL_DIR"; then
  fail "systemd service user can write deployment control or release-selection paths"
fi
runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$SHARED_DIR" \
  && runuser -u "$SERVICE_USER" -- "$TEST_BIN" -w "$SHARED_DIR" \
  && runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$RUNS_DIR" \
  && runuser -u "$SERVICE_USER" -- "$TEST_BIN" -r "$RUNS_DIR" \
  && runuser -u "$SERVICE_USER" -- "$TEST_BIN" -w "$RUNS_DIR" \
  && runuser -u "$SERVICE_USER" -- "$TEST_BIN" -r "$SECURITY_DB" \
  && runuser -u "$SERVICE_USER" -- "$TEST_BIN" -w "$SECURITY_DB" \
  || fail "systemd service user cannot persist shared runs or account database state"
FRAGMENT_PATH="$(systemctl show "$SERVICE" --property=FragmentPath --value)"
[[ "$FRAGMENT_PATH" == "$SYSTEMD_UNIT_FILE" ]] \
  || fail "active service fragment is not the expected administrator unit"
assert_secure_systemd_directory "/etc/systemd/system" "systemd administrator unit directory"
assert_secure_systemd_file "$FRAGMENT_PATH" "systemd base unit"
if [[ -e "$MANAGED_DROPIN_DIR" || -L "$MANAGED_DROPIN_DIR" ]]; then
  assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
fi

DROPIN_CANDIDATE="$LOG_DIR/.runtime-dropin-rollback-$RELEASE_ID-$$"
DROPIN_TEMP=""
canonical_managed_dropin_content >"$DROPIN_CANDIDATE"
chmod 0644 "$DROPIN_CANDIDATE"
TARGET_MANAGED_DROPIN_SHA256="$(sha256sum "$DROPIN_CANDIDATE" | awk '{print $1}')"

DROPIN_PATHS_BEFORE="$(systemctl show "$SERVICE" --property=DropInPaths --value)"
if [[ -n "$DROPIN_PATHS_BEFORE" && "$DROPIN_PATHS_BEFORE" != "$MANAGED_DROPIN" ]]; then
  fail "unreviewed systemd drop-ins are active; refusing rollback"
fi
DISK_DROPIN_PATHS=""
if [[ -d "$MANAGED_DROPIN_DIR" ]]; then
  shopt -s nullglob
  DISK_DROPIN_FILES=("$MANAGED_DROPIN_DIR"/*.conf)
  shopt -u nullglob
  for dropin_file in "${DISK_DROPIN_FILES[@]}"; do
    [[ -f "$dropin_file" && ! -L "$dropin_file" ]] \
      || fail "a systemd drop-in is not a regular file"
  done
  if ((${#DISK_DROPIN_FILES[@]} > 0)); then
    DISK_DROPIN_PATHS="${DISK_DROPIN_FILES[*]}"
  fi
fi
[[ "$DISK_DROPIN_PATHS" == "$DROPIN_PATHS_BEFORE" ]] \
  || fail "systemd manager and on-disk drop-in views differ; daemon-reload review is required"
PREVIOUS_DROPIN_EXISTED="false"
if [[ -e "$MANAGED_DROPIN" ]]; then
  assert_secure_systemd_file "$MANAGED_DROPIN" "managed systemd runtime drop-in"
  [[ "$(stat -Lc '%u:%g:%a' "$MANAGED_DROPIN")" == "0:0:644" ]] \
    || fail "managed systemd drop-in ownership or mode drifted"
  PREVIOUS_DROPIN_EXISTED="true"
elif [[ -n "$DROPIN_PATHS_BEFORE" ]]; then
  fail "systemd reports a managed drop-in that is missing on disk"
fi

PREVIOUS_EXEC_PATH="$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')"
PREVIOUS_EXEC_ARGV="$(effective_exec_argv)"
PREVIOUS_WORKING_DIRECTORY="$(systemctl show "$SERVICE" --property=WorkingDirectory --value)"
PREVIOUS_SERVICE_USER="$(systemctl show "$SERVICE" --property=User --value)"
PREVIOUS_SERVICE_GROUP="$(systemctl show "$SERVICE" --property=Group --value)"
PREVIOUS_ENVIRONMENT_FILES="$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)"
PREVIOUS_READ_WRITE_PATHS="$(systemctl show "$SERVICE" --property=ReadWritePaths --value)"
PREVIOUS_UMASK="$(systemctl show "$SERVICE" --property=UMask --value)"
[[ -n "$PREVIOUS_EXEC_PATH" && -n "$PREVIOUS_EXEC_ARGV" ]] \
  || fail "cannot resolve the active service executable and argv"
[[ "$PREVIOUS_ENVIRONMENT_FILES" == "$ENV_FILE (ignore_errors=no)" ]] \
  || fail "systemd service is not using the environment file validated by the canary"
[[ "$PREVIOUS_UMASK" == "0077" ]] \
  || fail "systemd service umask must preserve the private 0077 baseline"
ENV_FILE_SHA256="$(sha256sum "$ENV_FILE" | awk '{print $1}')"

MODERN_EXEC_ARGV="$CURRENT_LINK/.venv/bin/python -I -B -u -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $LOCAL_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1"
MODERN_RUNTIME_GUARD_EXEC_START_PRE_ARGV="/usr/bin/python3 -I -B -u $RUNTIME_GUARD_HELPER --verify-current $CURRENT_LINK --releases-root $RELEASES_DIR --baseline-directory $RUNTIME_BASELINE_DIR --require-root-owned-immutable"
MODERN_ENVIRONMENT_EXEC_START_PRE_ARGV="$CURRENT_LINK/.venv/bin/python -I -B -u $CURRENT_LINK/deploy/validate_production_env.py --shared-runs $RUNS_DIR --security-db $SECURITY_DB --public-origin $PUBLIC_ORIGIN --public-host $PUBLIC_HOST"
MODERN_EXEC_START_PRE_ARGVS_JSON="$("$PYTHON_BIN" -I -c \
  'import json,sys; print(json.dumps(sys.argv[1:], ensure_ascii=False, separators=(",", ":")))' \
  "$MODERN_RUNTIME_GUARD_EXEC_START_PRE_ARGV" "$MODERN_ENVIRONMENT_EXEC_START_PRE_ARGV")"
LEGACY_EXEC_ARGV_SPACE="$APP_ROOT/.venv/bin/python -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $LOCAL_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1"
LEGACY_EXEC_ARGV_EQUALS="$APP_ROOT/.venv/bin/python -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $LOCAL_PORT --proxy-headers --forwarded-allow-ips=127.0.0.1"
PREVIOUS_RUNTIME_MODE=""
PREVIOUS_MANIFEST_SHA256=""
if [[ "$PREVIOUS_ID" == "$LEGACY_RELEASE_ID" ]]; then
  [[ ! -e "$PREVIOUS_TARGET/.venv" && "$DROPIN_PATHS_BEFORE" == "" \
    && "$PREVIOUS_EXEC_PATH" == "$APP_ROOT/.venv/bin/python" \
    && "$PREVIOUS_WORKING_DIRECTORY" == "$CURRENT_LINK" ]] \
    || fail "current legacy runtime is a mixed or unsupported state"
  [[ "$PREVIOUS_EXEC_ARGV" == "$LEGACY_EXEC_ARGV_SPACE" \
    || "$PREVIOUS_EXEC_ARGV" == "$LEGACY_EXEC_ARGV_EQUALS" ]] \
    || fail "current legacy runtime command line is unexpected"
  validate_legacy_baseline "$PREVIOUS_TARGET"
  PREVIOUS_RUNTIME_MODE="legacy"
elif [[ -x "$PREVIOUS_TARGET/.venv/bin/python" ]]; then
  [[ "$DROPIN_PATHS_BEFORE" == "$MANAGED_DROPIN" \
    && "$PREVIOUS_EXEC_PATH" == "$CURRENT_LINK/.venv/bin/python" \
    && "$PREVIOUS_EXEC_ARGV" == "$MODERN_EXEC_ARGV" \
    && "$PREVIOUS_WORKING_DIRECTORY" == "$CURRENT_LINK" ]] \
    || fail "current release-local runtime is a mixed or unsupported state"
  validate_passed_release_record "$DEPLOYMENT_DIR/$PREVIOUS_ID.json" "$PREVIOUS_ID" "$PREVIOUS_TARGET"
  cmp -s "$DROPIN_CANDIDATE" "$MANAGED_DROPIN" \
    || fail "schema 5 current managed systemd drop-in has unrecognized content"
  PREVIOUS_MANIFEST_SHA256="$(sha256sum "$PREVIOUS_TARGET/release-manifest.json" | awk '{print $1}')"
  PREVIOUS_RUNTIME_MODE="release"
else
  fail "current runtime is neither the registered legacy baseline nor a passed release-local deployment"
fi

if [[ "$PREVIOUS_RUNTIME_MODE" == "legacy" ]]; then
  printf 'NOTICE: registered legacy baseline health is availability-only; release identity header is unsupported.\n' >&2
fi
runtime_health "$PREVIOUS_RUNTIME_MODE" "$PREVIOUS_MANIFEST_SHA256" \
  "http://127.0.0.1:$LOCAL_PORT/api/health" 8 "$PUBLIC_HOST" \
  || fail "current local production health or release identity is not passing"
runtime_health "$PREVIOUS_RUNTIME_MODE" "$PREVIOUS_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || fail "current public production health or release identity is not passing"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || fail "current public root does not enforce the login redirect"
PREVIOUS_MAIN_PID="$(systemctl show "$SERVICE" --property=MainPID --value)"
[[ "$PREVIOUS_MAIN_PID" =~ ^[1-9][0-9]*$ ]] \
  || fail "current known-good service has no live main process"
[[ "$(process_exec_argv "$PREVIOUS_MAIN_PID")" == "$PREVIOUS_EXEC_ARGV" ]] \
  || fail "current live process argv does not match the effective systemd baseline"
[[ "$(process_working_directory "$PREVIOUS_MAIN_PID")" == "$PREVIOUS_TARGET" ]] \
  || fail "current live process working directory does not match the current release"

TARGET_MODE="release"
TARGET_PYTHON="$TARGET/.venv/bin/python"
TARGET_MANIFEST_SHA256=""
if [[ -x "$TARGET_PYTHON" ]]; then
  TARGET_DEPLOYMENT_RECORD="$DEPLOYMENT_DIR/$RELEASE_ID.json"
  validate_passed_release_record "$TARGET_DEPLOYMENT_RECORD" "$RELEASE_ID" "$TARGET"
  TARGET_MANIFEST_SHA256="$(sha256sum "$TARGET/release-manifest.json" | awk '{print $1}')"
  TARGET_EXPECTED_VERSION="$("$PYTHON_BIN" -I - "$TARGET_DEPLOYMENT_RECORD" <<'PY'
import json
import sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["version"])
PY
)"
  runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$TARGET" \
    || fail "service user cannot traverse the rollback target"
  runuser -u "$SERVICE_USER" -- "$TEST_BIN" -r "$TARGET/protocol_studio/app.py" \
    || fail "service user cannot read the rollback target"
  runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$TARGET_PYTHON" \
    || fail "service user cannot execute the rollback target runtime"
else
  TARGET_MODE="legacy"
  [[ "$RELEASE_ID" == "$LEGACY_RELEASE_ID" ]] \
    || fail "a release without its own venv is not the registered legacy baseline"
  [[ -f "$TARGET/protocol_studio/app.py" ]] || fail "legacy target application is missing"
  TARGET_PYTHON="$APP_ROOT/.venv/bin/python"
  [[ -x "$TARGET_PYTHON" ]] || fail "legacy shared runtime is missing"
  runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$TARGET" \
    || fail "service user cannot traverse the legacy target"
  runuser -u "$SERVICE_USER" -- "$TEST_BIN" -r "$TARGET/protocol_studio/app.py" \
    || fail "service user cannot read the legacy target"
  runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$TARGET_PYTHON" \
    || fail "service user cannot execute the legacy shared runtime"

  LEGACY_BASELINE_RECORD="$DEPLOYMENT_DIR/legacy-baseline-$LEGACY_RELEASE_ID.json"
  validate_legacy_baseline "$TARGET"
  grep -Fqx "WorkingDirectory=$CURRENT_LINK" "$FRAGMENT_PATH" \
    || fail "legacy base unit working directory drifted"
  grep -Fq "ExecStart=$APP_ROOT/.venv/bin/python " "$FRAGMENT_PATH" \
    || fail "legacy base unit no longer selects the shared runtime"
fi
if [[ "$TARGET_MODE" == "legacy" ]]; then
  printf 'NOTICE: registered legacy rollback target health is availability-only; release identity header is unsupported.\n' >&2
fi
validate_production_environment \
  || fail "production environment failed the rollback pre-canary gate"

# Exercise the rollback target inside a transient systemd mount namespace.  The
# EnvironmentFile keeps its production path strings; only those paths are bound
# to a private online SQLite copy and private runs tree inside the canary.
PREFLIGHT_ROOT="$APP_ROOT/.rollback-preflight-$RELEASE_ID-$$"
PREFLIGHT_SHARED="$PREFLIGHT_ROOT/shared"
PREFLIGHT_DB="$PREFLIGHT_SHARED/security.sqlite3"
PREFLIGHT_RUNS="$PREFLIGHT_SHARED/runs"
PREFLIGHT_ESCAPE_LINK="$PREFLIGHT_SHARED/live-security.sqlite3"
install -d -o root -g root -m 0700 \
  "$PREFLIGHT_ROOT" "$PREFLIGHT_SHARED" "$PREFLIGHT_RUNS"
assert_no_extended_acl "$PREFLIGHT_ROOT" "rollback preflight isolation root"
assert_no_extended_acl "$PREFLIGHT_SHARED" "rollback preflight shared staging directory"
assert_no_extended_acl "$PREFLIGHT_RUNS" "rollback preflight runs staging directory"
PREFLIGHT_DB_METADATA_JSON="$("$PYTHON_BIN" -I "$SCRIPT_DIR/sqlite_backup.py" \
  backup --source "$SECURITY_DB" --destination "$PREFLIGHT_DB" \
  --deadline-seconds "$SQLITE_BACKUP_DEADLINE_SECONDS")" \
  || fail "cannot create the rollback preflight database"
[[ "$(stat -c '%u:%g:%a' -- "$PREFLIGHT_DB")" == "0:0:600" ]] \
  || fail "rollback preflight database was not published root-only"
assert_no_extended_acl "$PREFLIGHT_DB" "rollback preflight database"
[[ "$("$PYTHON_BIN" -I "$SCRIPT_DIR/sqlite_backup.py" inspect \
  --source "$PREFLIGHT_DB" \
  --deadline-seconds "$SQLITE_BACKUP_DEADLINE_SECONDS")" == "$PREFLIGHT_DB_METADATA_JSON" ]] \
  || fail "rollback preflight database verification drifted before delegation"
chown "$SERVICE_USER:$SERVICE_GROUP" "$PREFLIGHT_DB"
chmod 0600 "$PREFLIGHT_DB"
chown "$SERVICE_USER:$SERVICE_GROUP" "$PREFLIGHT_SHARED" "$PREFLIGHT_RUNS"
chmod 0700 "$PREFLIGHT_SHARED" "$PREFLIGHT_RUNS"
ln -s -- "$SECURITY_DB" "$PREFLIGHT_ESCAPE_LINK"
if runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$PREFLIGHT_ROOT" \
  || runuser -u "$SERVICE_USER" -- "$TEST_BIN" -r "$PREFLIGHT_DB"; then
  fail "service UID can traverse the host-side rollback preflight root"
fi

if [[ "$TARGET_MODE" == "release" ]]; then
  PREFLIGHT_VALIDATOR_PYTHON="$TARGET_PYTHON"
  PREFLIGHT_VALIDATOR="$TARGET/deploy/validate_production_env.py"
  assert_trusted_code_file "$PREFLIGHT_VALIDATOR" "rollback target environment validator"
else
  PREFLIGHT_VALIDATOR_PYTHON="$PYTHON_BIN"
  PREFLIGHT_VALIDATOR="$SCRIPT_DIR/validate_production_env.py"
fi
PREFLIGHT_EXPECTED_PRE_ARGV="$PREFLIGHT_VALIDATOR_PYTHON -I -B -u $PREFLIGHT_VALIDATOR --shared-runs $RUNS_DIR --security-db $SECURITY_DB --public-origin $PUBLIC_ORIGIN --public-host $PUBLIC_HOST"
PREFLIGHT_EXPECTED_ARGV="$TARGET_PYTHON -I -B -u -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $PREFLIGHT_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1"
PREFLIGHT_UNIT_KEY="$("$PYTHON_BIN" -I - "$RELEASE_ID" <<'PY'
import hashlib
import sys
print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest()[:16])
PY
)"
PREFLIGHT_UNIT="protocol-studio-rollback-canary-$PREFLIGHT_UNIT_KEY-$$.service"
PREFLIGHT_LOG="$LOG_DIR/$RELEASE_ID-rollback-preflight-$$.log"
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
    printf 'transient rollback canary unit: %s\n' "$PREFLIGHT_UNIT"
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
  fail "$*; see the root-only rollback preflight log"
}

cleanup_preflight() {
  if ! stop_preflight; then
    printf 'ERROR: rollback transient canary could not be reaped; retaining private state\n' >&2
    return 0
  fi
  case "$PREFLIGHT_ROOT" in
    "$APP_ROOT"/.rollback-preflight-*) rm -rf -- "$PREFLIGHT_ROOT" ;;
    *) printf 'ERROR: refusing to clean an unexpected rollback preflight path\n' >&2 ;;
  esac
  fsync_directory "$APP_ROOT" >/dev/null 2>&1 || true
}
trap cleanup_preflight EXIT

"$PYTHON_BIN" -I - "$PREFLIGHT_PORT" <<'PY'
from __future__ import annotations
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    probe.bind(("127.0.0.1", port))
PY

PREFLIGHT_LOAD_STATE="$(systemctl show "$PREFLIGHT_UNIT" --property=LoadState --value 2>/dev/null || true)"
[[ -z "$PREFLIGHT_LOAD_STATE" || "$PREFLIGHT_LOAD_STATE" == "not-found" ]] \
  || fail "unique rollback transient canary unit already exists"
if ! systemd-run --quiet --collect --unit="$PREFLIGHT_UNIT" \
  --description="MCGS rollback $RELEASE_ID isolated preflight" \
  --property=Type=simple \
  --property="User=$SERVICE_USER" \
  --property="Group=$SERVICE_GROUP" \
  --property="WorkingDirectory=$TARGET" \
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
  --property="BindReadOnlyPaths=$TARGET:$TARGET" \
  --property="BindPaths=$PREFLIGHT_SHARED:$SHARED_DIR" \
  --property="ReadWritePaths=$SHARED_DIR" \
  -- "$TARGET_PYTHON" -I -B -u -m uvicorn protocol_studio.app:app \
  --host 127.0.0.1 --port "$PREFLIGHT_PORT" \
  --proxy-headers --forwarded-allow-ips 127.0.0.1; then
  preflight_fail "cannot start the rollback transient systemd canary"
fi

PREFLIGHT_OK="false"
for _ in $(seq 1 "$CANARY_HEALTH_ATTEMPTS"); do
  PREFLIGHT_ACTIVE_STATE="$(systemctl show "$PREFLIGHT_UNIT" --property=ActiveState --value 2>/dev/null || true)"
  case "$PREFLIGHT_ACTIVE_STATE" in
    active)
      if runtime_health "$TARGET_MODE" "$TARGET_MANIFEST_SHA256" \
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
  || preflight_fail "rollback transient systemd canary health failed"

assert_preflight_property() {
  local property="$1"
  local expected="$2"
  local actual
  actual="$(systemctl show "$PREFLIGHT_UNIT" --property="$property" --value)" \
    || preflight_fail "cannot read rollback canary property $property"
  [[ "$actual" == "$expected" ]] \
    || preflight_fail "rollback canary property $property drifted"
}
assert_preflight_property Type simple
assert_preflight_property User "$SERVICE_USER"
assert_preflight_property Group "$SERVICE_GROUP"
assert_preflight_property WorkingDirectory "$TARGET"
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
  && "$(stat -c '%u:%g' -- "/proc/$PREFLIGHT_MAIN_PID")" == "$SERVICE_UID:$SERVICE_GID" ]] \
  || preflight_fail "rollback canary process credentials are invalid"
[[ "$(process_exec_argv "$PREFLIGHT_MAIN_PID")" == "$PREFLIGHT_EXPECTED_ARGV" \
  && "$(process_working_directory "$PREFLIGHT_MAIN_PID")" == "$TARGET" ]] \
  || preflight_fail "rollback canary process argv or cwd is invalid"
process_environment_matches "$PREFLIGHT_MAIN_PID" \
  || preflight_fail "rollback canary process environment is invalid"
PREFLIGHT_EFFECTIVE_PRE="$(systemctl show "$PREFLIGHT_UNIT" --property=ExecStartPre --value)"
[[ "$PREFLIGHT_EFFECTIVE_PRE" == *"argv[]=$PREFLIGHT_EXPECTED_PRE_ARGV ; ignore_errors=no"* \
  && "$PREFLIGHT_EFFECTIVE_PRE" != *"} ; {"* ]] \
  || preflight_fail "rollback canary environment validator is not the sole ExecStartPre"

PREFLIGHT_VISIBLE_SHARED="/proc/$PREFLIGHT_MAIN_PID/root$SHARED_DIR"
PREFLIGHT_VISIBLE_TARGET="/proc/$PREFLIGHT_MAIN_PID/root$TARGET"
[[ "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_SHARED")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED")" != "$(stat -Lc '%d:%i' -- "$SHARED_DIR")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/security.sqlite3")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_DB")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/security.sqlite3")" != "$(stat -Lc '%d:%i' -- "$SECURITY_DB")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/runs")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_RUNS")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/runs")" != "$(stat -Lc '%d:%i' -- "$RUNS_DIR")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/live-security.sqlite3")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_DB")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/live-security.sqlite3")" != "$(stat -Lc '%d:%i' -- "$SECURITY_DB")" ]] \
  || preflight_fail "rollback canary private shared namespace or symlink confinement failed"
[[ "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_TARGET")" == "$(stat -Lc '%d:%i' -- "$TARGET")" ]] \
  || preflight_fail "rollback canary target bind identity is invalid"
strict_login_redirect "http://127.0.0.1:$PREFLIGHT_PORT/" "$CANARY_HEALTH_MAX_SECONDS" "$PUBLIC_HOST" \
  || preflight_fail "rollback canary did not enforce the login redirect"

capture_preflight_diagnostics
stop_preflight || preflight_fail "rollback transient canary could not be reaped"
[[ ! -e "/proc/$PREFLIGHT_MAIN_PID" ]] \
  || preflight_fail "rollback canary process survived bounded TERM and KILL"
cleanup_preflight
trap - EXIT

BACKUP_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TRANSACTION_STARTED_AT="${BACKUP_STAMP:0:4}-${BACKUP_STAMP:4:2}-${BACKUP_STAMP:6:2}T${BACKUP_STAMP:9:2}:${BACKUP_STAMP:11:2}:${BACKUP_STAMP:13:2}Z"
ROLLBACK_RECORD="$DEPLOYMENT_DIR/rollback-$BACKUP_STAMP-to-$RELEASE_ID.json"
PENDING_ROLLBACK_RECORD="$DEPLOYMENT_DIR/.pending-rollback-$PREVIOUS_ID-to-$RELEASE_ID.json"
COMMITTED_TRANSACTION_RECORD="$DEPLOYMENT_DIR/transaction-rollback-$BACKUP_STAMP-to-$RELEASE_ID.json"
[[ ! -e "$ROLLBACK_RECORD" && ! -L "$ROLLBACK_RECORD" ]] \
  || fail "rollback passed-record path already exists"
[[ ! -e "$PENDING_ROLLBACK_RECORD" && ! -L "$PENDING_ROLLBACK_RECORD" ]] \
  || fail "rollback pending-record path already exists; recover or quarantine it before retrying"
[[ ! -e "$COMMITTED_TRANSACTION_RECORD" && ! -L "$COMMITTED_TRANSACTION_RECORD" ]] \
  || fail "rollback transaction evidence path already exists"
UNIT_BACKUP="$BACKUP_DIR/$SERVICE-$BACKUP_STAMP-before-rollback-$RELEASE_ID"
install -m 0600 "$FRAGMENT_PATH" "$UNIT_BACKUP"
assert_trusted_root_file_path "$UNIT_BACKUP" "rollback systemd base-unit backup"
fsync_file "$UNIT_BACKUP"
UNIT_FRAGMENT_SHA256="$(sha256sum "$UNIT_BACKUP" | awk '{print $1}')"
[[ "$(sha256sum "$FRAGMENT_PATH" | awk '{print $1}')" == "$UNIT_FRAGMENT_SHA256" ]] \
  || fail "systemd base unit changed while its rollback backup was created"
DROPIN_BACKUP=""
DROPIN_SHA256=""
if [[ "$PREVIOUS_DROPIN_EXISTED" == "true" ]]; then
  DROPIN_BACKUP="$BACKUP_DIR/$SERVICE-runtime-$BACKUP_STAMP-before-rollback-$RELEASE_ID.conf"
  install -m 0600 "$MANAGED_DROPIN" "$DROPIN_BACKUP"
  assert_trusted_root_file_path "$DROPIN_BACKUP" \
    "rollback managed systemd drop-in backup"
  fsync_file "$DROPIN_BACKUP"
  DROPIN_SHA256="$(sha256sum "$DROPIN_BACKUP" | awk '{print $1}')"
  [[ "$(sha256sum "$MANAGED_DROPIN" | awk '{print $1}')" == "$DROPIN_SHA256" ]] \
    || fail "managed runtime drop-in changed while its rollback backup was created"
fi
fsync_directory "$BACKUP_DIR"

DATABASE_BACKUP="$BACKUP_DIR/security-$BACKUP_STAMP-before-rollback-$RELEASE_ID.sqlite3"
DATABASE_BACKUP_BASENAME="$(basename -- "$DATABASE_BACKUP")"
DATABASE_BACKUP_METADATA_JSON="$("$PYTHON_BIN" -I "$SCRIPT_DIR/sqlite_backup.py" \
  backup --source "$SECURITY_DB" --destination "$DATABASE_BACKUP" \
  --deadline-seconds "$SQLITE_BACKUP_DEADLINE_SECONDS")" \
  || fail "cannot create the pre-switch rollback database backup"
chown root:root "$DATABASE_BACKUP"
chmod 0600 "$DATABASE_BACKUP"
fsync_file "$DATABASE_BACKUP"
fsync_directory "$BACKUP_DIR"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "durable rollback database backup evidence is invalid"

atomic_link() {
  local target="$1"
  local temporary="$APP_ROOT/.current-rollback-$$"
  [[ ! -e "$temporary" && ! -L "$temporary" ]] || return 1
  ln -s -- "$target" "$temporary" || return 1
  mv -Tf -- "$temporary" "$CURRENT_LINK" || return 1
  fsync_directory "$APP_ROOT"
}

restore_previous_dropin() {
  if [[ "$PREVIOUS_DROPIN_EXISTED" == "true" ]]; then
    install -d -m 0755 "$MANAGED_DROPIN_DIR" || return 1
    local temporary="$MANAGED_DROPIN_DIR/.restore-runtime-rollback-$$"
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

ROLLBACK_RECOVERY_RUNNING="false"
TRANSACTION_ACTIVE="false"
TRANSACTION_COMMITTED="false"
restore_previous() {
  local reason="$1"
  local original_pid
  local active_state
  local sub_state
  local main_pid
  local process_gone="true"
  local marker_retained="false"
  local fail_closed="true"
  if [[ "$ROLLBACK_RECOVERY_RUNNING" == "true" ]]; then
    printf 'CRITICAL: FAIL-CLOSED NOT CONFIRMED (recursive transaction failure)\n' >&2
    printf 'DO NOT REBOOT; retain the active transaction marker for audited recovery.\n' >&2
    exit 1
  fi
  trap '' INT TERM HUP
  ROLLBACK_RECOVERY_RUNNING="true"
  # This compensation handler owns the terminal path after it starts.  Explicit
  # `command || restore_previous` calls must not re-enter it via EXIT.
  trap - EXIT
  set +e
  printf 'ROLLBACK TARGET FAILED: %s\n' "$reason" >&2
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
  ( trap - EXIT; assert_service_persistently_disabled "$SERVICE_USER" ) \
    >/dev/null 2>&1 || fail_closed="false"
  if [[ "$fail_closed" == "true" ]]; then
    printf 'FAIL-CLOSED CONFIRMED: service is persistently disabled, inactive/dead, MainPID=0, and the original process is gone.\n' >&2
    if [[ "$TRANSACTION_COMMITTED" == "true" ]]; then
      printf 'Committed target retained; rerun recover-transaction.sh to finalize activation.\n' >&2
    else
      printf 'Precommit marker retained; rerun recover-transaction.sh to restore the recorded previous target.\n' >&2
    fi
  else
    printf 'CRITICAL: FAIL-CLOSED NOT CONFIRMED (is-enabled=%s exit=%s ActiveState=%s SubState=%s MainPID=%s original_pid=%s original_gone=%s marker_retained=%s).\n' \
      "$SERVICE_ENABLE_STDOUT" "$SERVICE_ENABLE_EXIT" "$active_state" "$sub_state" \
      "$main_pid" "$original_pid" "$process_gone" "$marker_retained" >&2
    printf 'DO NOT REBOOT; retain the active transaction marker and obtain manual systemd recovery.\n' >&2
  fi
  exit 1
}

transaction_exit_guard() {
  local status="${1:-$?}"
  trap '' INT TERM HUP
  trap - EXIT
  if [[ "$TRANSACTION_ACTIVE" == "true" ]]; then
    restore_previous "rollback transaction exited unexpectedly with status $status"
  fi
  exit "$status"
}
transaction_signal_guard() {
  trap '' INT TERM HUP
  transaction_exit_guard 130
}
trap transaction_exit_guard EXIT
trap transaction_signal_guard INT TERM HUP

sync -f "$TARGET" || fail "cannot make the rollback target durable"
sync -f "$CONTROL_DIR" || fail "cannot make rollback evidence durable"
if [[ "$TARGET_MODE" == "release" ]]; then
  validate_passed_release_record "$TARGET_DEPLOYMENT_RECORD" "$RELEASE_ID" "$TARGET"
else
  validate_legacy_baseline "$TARGET"
fi
assert_standard_enabled_topology "$SERVICE_USER" \
  || fail "systemd service enablement topology changed before the rollback transaction"
systemctl is-active --quiet "$SERVICE" \
  || fail "systemd service stopped being active before the rollback transaction"
[[ "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" ]] \
  || fail "systemd configuration changed before the rollback transaction"
[[ "$(readlink -f -- "$CURRENT_LINK")" == "$PREVIOUS_TARGET" ]] \
  || fail "current release changed before the rollback transaction"
[[ "$(sha256sum "$FRAGMENT_PATH" | awk '{print $1}')" == "$UNIT_FRAGMENT_SHA256" ]] \
  || fail "systemd base unit changed before the rollback transaction"
assert_trusted_root_file_path "$UNIT_BACKUP" "durable rollback base-unit backup"
[[ -f "$UNIT_BACKUP" && ! -L "$UNIT_BACKUP" \
  && "$(stat -c '%u:%g:%a' -- "$UNIT_BACKUP")" == "0:0:600" \
  && "$(sha256sum "$UNIT_BACKUP" | awk '{print $1}')" == "$UNIT_FRAGMENT_SHA256" ]] \
  || fail "durable systemd base-unit backup changed before rollback"
assert_secure_systemd_directory "/etc/systemd/system" "systemd administrator unit directory"
assert_secure_systemd_file "$FRAGMENT_PATH" "systemd base unit"
if [[ -e "$MANAGED_DROPIN_DIR" || -L "$MANAGED_DROPIN_DIR" ]]; then
  assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
fi
DROPIN_PATHS_RECHECK="$(systemctl show "$SERVICE" --property=DropInPaths --value)"
[[ "$DROPIN_PATHS_RECHECK" == "$DROPIN_PATHS_BEFORE" ]] \
  || fail "effective systemd drop-in set changed before the rollback transaction"
DISK_DROPIN_PATHS_RECHECK=""
if [[ -d "$MANAGED_DROPIN_DIR" ]]; then
  shopt -s nullglob
  DISK_DROPIN_FILES_RECHECK=("$MANAGED_DROPIN_DIR"/*.conf)
  shopt -u nullglob
  for dropin_file in "${DISK_DROPIN_FILES_RECHECK[@]}"; do
    [[ -f "$dropin_file" && ! -L "$dropin_file" ]] \
      || fail "a systemd drop-in changed into a non-regular file before rollback"
  done
  if ((${#DISK_DROPIN_FILES_RECHECK[@]} > 0)); then
    DISK_DROPIN_PATHS_RECHECK="${DISK_DROPIN_FILES_RECHECK[*]}"
  fi
fi
[[ "$DISK_DROPIN_PATHS_RECHECK" == "$DROPIN_PATHS_BEFORE" ]] \
  || fail "systemd manager and disk drop-in views changed before rollback"
if [[ "$PREVIOUS_DROPIN_EXISTED" == "true" ]]; then
  assert_secure_systemd_file "$MANAGED_DROPIN" "managed systemd runtime drop-in"
  [[ "$(sha256sum "$MANAGED_DROPIN" | awk '{print $1}')" == "$DROPIN_SHA256" ]] \
    || fail "managed runtime drop-in changed before rollback"
  cmp -s "$DROPIN_CANDIDATE" "$MANAGED_DROPIN" \
    || fail "managed runtime drop-in content changed before rollback"
  assert_trusted_root_file_path "$DROPIN_BACKUP" \
    "durable rollback managed systemd drop-in backup"
  [[ -f "$DROPIN_BACKUP" && ! -L "$DROPIN_BACKUP" \
    && "$(stat -c '%u:%g:%a' -- "$DROPIN_BACKUP")" == "0:0:600" \
    && "$(sha256sum "$DROPIN_BACKUP" | awk '{print $1}')" == "$DROPIN_SHA256" ]] \
    || fail "durable managed runtime drop-in backup changed before rollback"
elif [[ -e "$MANAGED_DROPIN" || -L "$MANAGED_DROPIN" ]]; then
  fail "an unexpected managed runtime drop-in appeared before rollback"
fi
[[ "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$PREVIOUS_EXEC_PATH" ]] \
  || fail "effective systemd executable changed before rollback"
[[ "$(effective_exec_argv)" == "$PREVIOUS_EXEC_ARGV" ]] \
  || fail "effective systemd command line changed before rollback"
[[ "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$PREVIOUS_WORKING_DIRECTORY" \
  && "$(systemctl show "$SERVICE" --property=User --value)" == "$PREVIOUS_SERVICE_USER" \
  && "$(systemctl show "$SERVICE" --property=Group --value)" == "$PREVIOUS_SERVICE_GROUP" \
  && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
  && "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" \
  && "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" \
  && "$(systemctl show "$SERVICE" --property=MainPID --value)" == "$PREVIOUS_MAIN_PID" ]] \
  || fail "effective systemd runtime changed before rollback"
[[ "$(process_exec_argv "$PREVIOUS_MAIN_PID")" == "$PREVIOUS_EXEC_ARGV" ]] \
  || fail "live process argv changed before rollback"
[[ "$(process_working_directory "$PREVIOUS_MAIN_PID")" == "$PREVIOUS_TARGET" ]] \
  || fail "live process working directory changed before rollback"
runtime_health "$PREVIOUS_RUNTIME_MODE" "$PREVIOUS_MANIFEST_SHA256" \
  "http://127.0.0.1:$LOCAL_PORT/api/health" 8 "$PUBLIC_HOST" \
  || fail "current local production health or release identity changed before rollback"
runtime_health "$PREVIOUS_RUNTIME_MODE" "$PREVIOUS_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || fail "current public production health or release identity changed before rollback"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || fail "current public login redirect changed before rollback"
[[ "$(sha256sum "$ENV_FILE" | awk '{print $1}')" == "$ENV_FILE_SHA256" ]] \
  || fail "production environment file changed after rollback canary validation"
fsync_systemd_enablement_state \
  || fail "cannot preflight persistence of systemd enablement directories"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "rollback database backup drifted before transaction preparation"
validate_production_environment \
  || fail "production environment failed the rollback formal-switch gate"
"$PYTHON_BIN" -I - "$TRANSACTION_TEMP" "$RELEASE_ID" "$PREVIOUS_ID" "$PREVIOUS_TARGET" \
  "$TARGET_MODE" "$FRAGMENT_PATH" "$UNIT_FRAGMENT_SHA256" \
  "$DROPIN_PATHS_BEFORE" "$DROPIN_SHA256" \
  "$(basename -- "$UNIT_BACKUP")" \
  "$(if [[ -n "$DROPIN_BACKUP" ]]; then basename -- "$DROPIN_BACKUP"; fi)" \
  "$PREVIOUS_EXEC_PATH" "$PREVIOUS_EXEC_ARGV" "$PREVIOUS_WORKING_DIRECTORY" \
  "$PREVIOUS_SERVICE_USER" "$PREVIOUS_SERVICE_GROUP" \
  "$PREVIOUS_ENVIRONMENT_FILES" "$PREVIOUS_READ_WRITE_PATHS" \
  "$PREVIOUS_UMASK" "$ENV_FILE_SHA256" \
  "$PUBLIC_ORIGIN" "$PUBLIC_HOST" "$DATABASE_BACKUP_METADATA_JSON" \
  "$TRANSACTION_STARTED_AT" <<'PY'
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
record = {
    "schema_version": 3,
    "status": "rolling_back",
    "target_release_id": sys.argv[2],
    "previous_release_id": sys.argv[3],
    "previous_target": sys.argv[4],
    "target_runtime_mode": sys.argv[5],
    "fragment_path": sys.argv[6],
    "fragment_sha256": sys.argv[7],
    "dropin_paths_before": [] if not sys.argv[8] else [sys.argv[8]],
    "managed_dropin_sha256_before": sys.argv[9] or None,
    "fragment_backup": sys.argv[10],
    "managed_dropin_backup": sys.argv[11] or None,
    "previous_exec_path": sys.argv[12],
    "previous_exec_argv": sys.argv[13],
    "previous_working_directory": sys.argv[14],
    "previous_service_user": sys.argv[15],
    "previous_service_group": sys.argv[16],
    "previous_environment_files": sys.argv[17],
    "previous_read_write_paths": sys.argv[18],
    "previous_umask": sys.argv[19],
    "environment_file_sha256": sys.argv[20],
    "public_origin": sys.argv[21],
    "public_host": sys.argv[22],
    "database_backup": json.loads(sys.argv[23]),
    "prepared_release_durable": True,
    "service_enabled_before_switch": True,
    "known_good_health_before_switch": True,
    "started_at": sys.argv[24],
}
if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", record["started_at"]):
    raise SystemExit("invalid transaction timestamp")
payload = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(path, flags, 0o600)
try:
    with os.fdopen(descriptor, "wb", closefd=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
finally:
    os.close(descriptor)
PY
chmod 0600 "$TRANSACTION_TEMP"
fsync_file "$TRANSACTION_TEMP"
mv -Tf -- "$TRANSACTION_TEMP" "$TRANSACTION_FILE"
assert_trusted_root_file_path "$TRANSACTION_FILE" "active rollback transaction marker"
fsync_directory "$APP_ROOT"
if [[ "$(sha256sum "$ENV_FILE" | awk '{print $1}')" != "$ENV_FILE_SHA256" ]]; then
  rm -f -- "$TRANSACTION_FILE"
  fsync_directory "$APP_ROOT"
  fail "production environment file changed while the rollback marker was written"
fi
TRANSACTION_ACTIVE="true"

systemctl disable "$SERVICE" \
  || restore_previous "cannot disable automatic service startup before rollback"
assert_service_persistently_disabled "$SERVICE_USER" \
  || restore_previous "service remained enabled or retained a nonstandard enablement link before rollback"
fsync_systemd_enablement_state \
  || restore_previous "cannot persist the disabled systemd state before rollback"
assert_service_persistently_disabled "$SERVICE_USER" \
  || restore_previous "disabled systemd state was not durable before guard installation"
install_transaction_runtime_guard "$SERVICE_USER" \
  || restore_previous "cannot install and verify the bounded transaction runtime guard"
stop_service_and_verify \
  || restore_previous "current service did not reach inactive/dead state with MainPID zero"
atomic_link "$TARGET" || restore_previous "atomic current symlink replacement failed"

if [[ "$TARGET_MODE" == "release" ]]; then
  install -d -m 0755 "$MANAGED_DROPIN_DIR" \
    || restore_previous "cannot create the managed systemd drop-in directory"
  assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
  DROPIN_TEMP="$MANAGED_DROPIN_DIR/.install-runtime-rollback-$$"
  install -m 0644 "$DROPIN_CANDIDATE" "$DROPIN_TEMP" \
    || restore_previous "cannot stage the managed systemd runtime drop-in"
  fsync_file "$DROPIN_TEMP" \
    || restore_previous "cannot persist the staged managed systemd runtime drop-in"
  mv -Tf -- "$DROPIN_TEMP" "$MANAGED_DROPIN" \
    || restore_previous "cannot atomically install the managed runtime drop-in"
  fsync_directory "$MANAGED_DROPIN_DIR" \
    || restore_previous "cannot persist the managed runtime drop-in rename"
  EXPECTED_EXEC_PATH="$CURRENT_LINK/.venv/bin/python"
  EXPECTED_EXEC_ARGV="$MODERN_EXEC_ARGV"
  EXPECTED_DROPINS="$MANAGED_DROPIN"
else
  rm -f -- "$MANAGED_DROPIN" \
    || restore_previous "cannot remove the managed drop-in for legacy rollback"
  if [[ -d "$MANAGED_DROPIN_DIR" ]]; then
    fsync_directory "$MANAGED_DROPIN_DIR" \
      || restore_previous "cannot persist managed drop-in removal for legacy rollback"
  fi
  EXPECTED_EXEC_PATH="$APP_ROOT/.venv/bin/python"
  EXPECTED_EXEC_ARGV=""
  EXPECTED_DROPINS=""
fi
systemctl daemon-reload || restore_previous "systemd daemon-reload failed"
[[ "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" ]] \
  || restore_previous "systemd still requires daemon-reload after rollback runtime change"
assert_transaction_runtime_guard_loaded \
  || restore_previous "transaction runtime guard drifted after rollback runtime change"

TARGET_EXEC_PATH="$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')"
TARGET_EXEC_ARGV="$(effective_exec_argv)"
TARGET_EXEC_START_PRE_RAW="$(systemctl show "$SERVICE" --property=ExecStartPre --value)"
TARGET_EXEC_START_PRE_ARGVS_JSON="[]"
TARGET_WORKING_DIRECTORY="$(systemctl show "$SERVICE" --property=WorkingDirectory --value)"
TARGET_SERVICE_USER="$(systemctl show "$SERVICE" --property=User --value)"
TARGET_SERVICE_GROUP="$(systemctl show "$SERVICE" --property=Group --value)"
TARGET_ENVIRONMENT_FILES="$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)"
TARGET_READ_WRITE_PATHS="$(systemctl show "$SERVICE" --property=ReadWritePaths --value)"
TARGET_UMASK="$(systemctl show "$SERVICE" --property=UMask --value)"
TARGET_DROPINS="$(systemctl show "$SERVICE" --property=DropInPaths --value)"
[[ "$TARGET_EXEC_PATH" == "$EXPECTED_EXEC_PATH" ]] \
  || restore_previous "effective systemd executable does not match the rollback target mode"
if [[ "$TARGET_MODE" == "release" ]]; then
  TARGET_EXEC_START_PRE_ARGVS_JSON="$(effective_exec_start_pre_argvs)"
  [[ "$TARGET_EXEC_ARGV" == "$EXPECTED_EXEC_ARGV" ]] \
    || restore_previous "effective systemd command line does not match the rollback target"
  [[ "$TARGET_EXEC_START_PRE_ARGVS_JSON" == "$MODERN_EXEC_START_PRE_ARGVS_JSON" ]] \
    || restore_previous "release rollback target lacks the ordered ordinary-restart integrity and environment gates"
  effective_unset_environment_matches \
    || restore_previous "release rollback target environment sanitization drifted"
  effective_environment_matches \
    || restore_previous "release rollback target explicit environment drifted"
  effective_restart_limit_matches \
    || restore_previous "release rollback target restart limiter drifted"
else
  [[ -z "$TARGET_EXEC_START_PRE_RAW" ]] \
    || restore_previous "legacy rollback target inherited a modern ExecStartPre that it cannot satisfy"
  [[ "$TARGET_EXEC_ARGV" == "$LEGACY_EXEC_ARGV_SPACE" \
    || "$TARGET_EXEC_ARGV" == "$LEGACY_EXEC_ARGV_EQUALS" ]] \
    || restore_previous "effective legacy command line does not match the registered baseline"
  EXPECTED_EXEC_ARGV="$TARGET_EXEC_ARGV"
fi
[[ "$TARGET_WORKING_DIRECTORY" == "$CURRENT_LINK" ]] \
  || restore_previous "effective systemd working directory drifted"
[[ "$TARGET_SERVICE_USER" == "$SERVICE_USER" && "$TARGET_SERVICE_USER" != "root" ]] \
  || restore_previous "effective systemd user drifted"
[[ "$TARGET_SERVICE_GROUP" == "$SERVICE_GROUP" ]] \
  || restore_previous "effective systemd group drifted"
[[ "$TARGET_ENVIRONMENT_FILES" == "$PREVIOUS_ENVIRONMENT_FILES" ]] \
  || restore_previous "effective systemd environment file drifted"
[[ "$TARGET_READ_WRITE_PATHS" == "$PREVIOUS_READ_WRITE_PATHS" ]] \
  || restore_previous "effective systemd writable paths drifted"
[[ "$TARGET_UMASK" == "$PREVIOUS_UMASK" && "$TARGET_UMASK" == "0077" ]] \
  || restore_previous "effective systemd umask drifted"
if [[ "$TARGET_MODE" == "release" ]]; then
  assert_dropin_paths_exact "$TARGET_DROPINS" "$MANAGED_DROPIN" "$TRANSACTION_RUNTIME_GUARD" \
    || restore_previous "effective guarded release drop-in set drifted"
else
  assert_dropin_paths_exact "$TARGET_DROPINS" "$TRANSACTION_RUNTIME_GUARD" \
    || restore_previous "effective guarded legacy drop-in set drifted"
fi

assert_service_persistently_disabled "$SERVICE_USER" \
  || restore_previous "service became enabled before rollback health validation"
assert_transaction_runtime_guard_loaded \
  || restore_previous "transaction runtime guard is not loaded before rollback target start"
systemctl --no-block start "$SERVICE" || restore_previous "rollback target failed to start"
systemctl is-active --quiet "$SERVICE" || restore_previous "rollback target is not active"
MAIN_PID="$(systemctl show "$SERVICE" --property=MainPID --value)"
[[ "$MAIN_PID" =~ ^[1-9][0-9]*$ ]] \
  || restore_previous "systemd did not report a live rollback process"
[[ "$MAIN_PID" != "$PREVIOUS_MAIN_PID" ]] \
  || restore_previous "systemd did not replace the previous process"
RUNNING_PROCESS_ARGV="$("$PYTHON_BIN" -I - "$MAIN_PID" <<'PY'
from pathlib import Path
import sys

parts = Path(f"/proc/{sys.argv[1]}/cmdline").read_bytes().split(b"\0")
print(" ".join(part.decode("utf-8") for part in parts if part))
PY
)"
[[ "$RUNNING_PROCESS_ARGV" == "$EXPECTED_EXEC_ARGV" ]] \
  || restore_previous "running process command line does not match the rollback runtime mode"
[[ "$(process_working_directory "$MAIN_PID")" == "$TARGET" ]] \
  || restore_previous "running process working directory does not match the rollback target"
process_environment_matches "$MAIN_PID" \
  || restore_previous "running rollback process environment is invalid"
( trap - EXIT; validate_runtime_provenance "$TARGET_MODE" "$RELEASE_ID" "$TARGET" ) \
  || restore_previous "rollback target provenance changed after service start"

LOCAL_OK="false"
for _ in $(seq 1 "$SERVICE_HEALTH_ATTEMPTS"); do
  if runtime_health "$TARGET_MODE" "$TARGET_MANIFEST_SHA256" \
    "http://127.0.0.1:$LOCAL_PORT/api/health" "$SERVICE_HEALTH_MAX_SECONDS" "$PUBLIC_HOST"; then
    LOCAL_OK="true"
    break
  fi
  sleep "$SERVICE_HEALTH_POLL_SECONDS"
done
[[ "$LOCAL_OK" == "true" ]] || restore_previous "rollback target local health failed"
runtime_health "$TARGET_MODE" "$TARGET_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || restore_previous "rollback target public health or release identity failed"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || restore_previous "rollback target did not enforce the public login redirect"

[[ "$(readlink -f -- "$CURRENT_LINK")" == "$TARGET" \
  && "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
  && "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$EXPECTED_EXEC_PATH" \
  && "$(effective_exec_argv)" == "$EXPECTED_EXEC_ARGV" \
  && "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$CURRENT_LINK" \
  && "$(systemctl show "$SERVICE" --property=User --value)" == "$SERVICE_USER" \
  && "$(systemctl show "$SERVICE" --property=Group --value)" == "$SERVICE_GROUP" \
  && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
  && "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" \
  && "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" \
  && "$(systemctl show "$SERVICE" --property=MainPID --value)" == "$MAIN_PID" ]] \
  || restore_previous "rollback runtime drifted before transaction commit"
if [[ "$TARGET_MODE" == "release" ]]; then
  assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" \
    "$MANAGED_DROPIN" "$TRANSACTION_RUNTIME_GUARD" \
    || restore_previous "guarded release drop-in set drifted before rollback commit"
else
  assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" \
    "$TRANSACTION_RUNTIME_GUARD" \
    || restore_previous "guarded legacy drop-in set drifted before rollback commit"
fi
assert_transaction_runtime_guard_loaded \
  || restore_previous "transaction runtime guard drifted before rollback commit"
systemctl is-active --quiet "$SERVICE" \
  || restore_previous "rollback service stopped before transaction commit"
assert_service_persistently_disabled "$SERVICE_USER" \
  || restore_previous "rollback service became enabled before transaction commit"
[[ "$(sha256sum "$FRAGMENT_PATH" | awk '{print $1}')" == "$UNIT_FRAGMENT_SHA256" \
  && "$(sha256sum "$ENV_FILE" | awk '{print $1}')" == "$ENV_FILE_SHA256" ]] \
  || restore_previous "base unit or production environment drifted before rollback commit"
assert_secure_systemd_directory "/etc/systemd/system" "systemd administrator unit directory"
assert_secure_systemd_file "$FRAGMENT_PATH" "systemd base unit"
if [[ "$TARGET_MODE" == "release" ]]; then
  assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
  assert_secure_systemd_file "$MANAGED_DROPIN" "managed systemd runtime drop-in"
  cmp -s "$DROPIN_CANDIDATE" "$MANAGED_DROPIN" \
    || restore_previous "managed runtime drop-in drifted before rollback commit"
else
  [[ ! -e "$MANAGED_DROPIN" && ! -L "$MANAGED_DROPIN" ]] \
    || restore_previous "managed runtime drop-in reappeared before legacy rollback commit"
fi
FINAL_PROCESS_ARGV="$("$PYTHON_BIN" -I - "$MAIN_PID" <<'PY'
from pathlib import Path
import sys
parts = Path(f"/proc/{sys.argv[1]}/cmdline").read_bytes().split(b"\0")
print(" ".join(part.decode("utf-8") for part in parts if part))
PY
)"
[[ "$FINAL_PROCESS_ARGV" == "$EXPECTED_EXEC_ARGV" ]] \
  || restore_previous "rollback process command line drifted before transaction commit"
[[ "$(readlink -f -- "/proc/$MAIN_PID/cwd")" == "$TARGET" ]] \
  || restore_previous "rollback process working directory drifted before transaction commit"
( trap - EXIT; validate_runtime_provenance "$TARGET_MODE" "$RELEASE_ID" "$TARGET" ) \
  || restore_previous "rollback target provenance drifted before transaction commit"
runtime_health "$TARGET_MODE" "$TARGET_MANIFEST_SHA256" \
  "http://127.0.0.1:$LOCAL_PORT/api/health" 8 "$PUBLIC_HOST" \
  || restore_previous "rollback local health or release identity drifted before transaction commit"
runtime_health "$TARGET_MODE" "$TARGET_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || restore_previous "rollback public health or release identity drifted before transaction commit"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || restore_previous "rollback public login redirect drifted before transaction commit"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || restore_previous "rollback database backup drifted before transaction commit"

ROLLBACK_RECORD_TEMP="$PENDING_ROLLBACK_RECORD"
if [[ "$TARGET_MODE" == "release" ]]; then
  ORDINARY_RESTART_PROTECTED="true"
  EVIDENCE_EXEC_START_PRE_ARGVS_JSON="$MODERN_EXEC_START_PRE_ARGVS_JSON"
  EVIDENCE_RUNTIME_BASELINE_PATH="$RUNTIME_BASELINE_DIR/$RELEASE_ID.json"
  RUNTIME_BASELINE_VERIFICATION_JSON="$(verify_release_runtime_baseline \
    "$RELEASE_ID" "$TARGET" "$TARGET_MANIFEST_SHA256")" \
    || restore_previous "rollback target baseline drifted before evidence creation"
  mapfile -t RUNTIME_BASELINE_FIELDS < <("$PYTHON_BIN" -I -B -u - \
    "$RUNTIME_BASELINE_VERIFICATION_JSON" <<'PY'
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
  [[ "${#RUNTIME_BASELINE_FIELDS[@]}" == "3" ]] \
    || restore_previous "rollback target baseline evidence is incomplete"
  EVIDENCE_RUNTIME_FINGERPRINT_SHA256="${RUNTIME_BASELINE_FIELDS[0]}"
  EVIDENCE_RUNTIME_BASELINE_SHA256="${RUNTIME_BASELINE_FIELDS[1]}"
  EVIDENCE_RUNTIME_GUARD_HELPER_SHA256="${RUNTIME_BASELINE_FIELDS[2]}"
else
  ORDINARY_RESTART_PROTECTED="false"
  EVIDENCE_EXEC_START_PRE_ARGVS_JSON="[]"
  EVIDENCE_RUNTIME_BASELINE_PATH=""
  EVIDENCE_RUNTIME_BASELINE_SHA256=""
  EVIDENCE_RUNTIME_FINGERPRINT_SHA256=""
  EVIDENCE_RUNTIME_GUARD_HELPER_SHA256=""
fi
"$PYTHON_BIN" -I - "$ROLLBACK_RECORD_TEMP" "$RELEASE_ID" "$PREVIOUS_ID" "$TARGET_MODE" \
  "$UNIT_FRAGMENT_SHA256" "$DROPIN_SHA256" "$ENV_FILE_SHA256" \
  "$PUBLIC_ORIGIN" "$PUBLIC_HOST" "$EVIDENCE_EXEC_START_PRE_ARGVS_JSON" \
  "$ORDINARY_RESTART_PROTECTED" "$DATABASE_BACKUP_METADATA_JSON" \
  "$EVIDENCE_RUNTIME_BASELINE_PATH" "$EVIDENCE_RUNTIME_BASELINE_SHA256" \
  "$EVIDENCE_RUNTIME_FINGERPRINT_SHA256" \
  "$EVIDENCE_RUNTIME_GUARD_HELPER_SHA256" <<'PY'
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
if sys.argv[11] not in {"true", "false"}:
    raise SystemExit("invalid ordinary restart validator flag")
ordinary_restart_protected = sys.argv[11] == "true"
record = {
    "schema_version": 5,
    "status": "passed",
    "target_release_id": sys.argv[2],
    "previous_release_id": sys.argv[3],
    "runtime_mode": sys.argv[4],
    "fragment_sha256": sys.argv[5],
    "managed_dropin_sha256_before": sys.argv[6] or None,
    "environment_file_sha256": sys.argv[7],
    "public_origin": sys.argv[8],
    "public_host": sys.argv[9],
    "ordinary_restart_validator": {
        "protected": ordinary_restart_protected,
        "exec_start_pre_argvs": json.loads(sys.argv[10]),
    },
    "database_backup": json.loads(sys.argv[12]),
    "runtime_baseline_path": sys.argv[13] or None,
    "runtime_baseline_sha256": sys.argv[14] or None,
    "runtime_fingerprint_sha256": sys.argv[15] or None,
    "runtime_guard_helper_sha256": sys.argv[16] or None,
    "rolled_back_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "checks": {
        "isolated_service_user_preflight": True,
        "security_database_backup": True,
        "known_good_health_before_switch": True,
        "service_disabled_during_switch": True,
        "service_stopped_before_switch": True,
        "atomic_symlink": True,
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
    },
}
payload = (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(path, flags, 0o640)
try:
    with os.fdopen(descriptor, "wb", closefd=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
finally:
    os.close(descriptor)
PY
chmod 0640 "$ROLLBACK_RECORD_TEMP"
assert_trusted_record_file "$ROLLBACK_RECORD_TEMP" "pending rollback passed record"
fsync_file "$ROLLBACK_RECORD_TEMP"

rm -f -- "$DROPIN_CANDIDATE" "$TRANSACTION_TEMP"
[[ ! -e "$COMMITTED_TRANSACTION_RECORD" && ! -L "$COMMITTED_TRANSACTION_RECORD" ]] \
  || restore_previous "rollback transaction evidence path already exists"
transition_transaction_status "rolling_back" "rollback_committed_pending_activation" \
  || restore_previous "cannot durably commit the rollback target inside the active marker"
TRANSACTION_COMMITTED="true"

# The rollback target is now the only permissible recovery target.  Stop its
# bounded guarded process, remove the ephemeral guard, then prove the normal
# production restart policy and runtime again before enabling boot startup.
GUARDED_MAIN_PID="$MAIN_PID"
stop_service_and_verify \
  || restore_previous "cannot stop the guarded committed rollback process"
assert_service_persistently_disabled "$SERVICE_USER" \
  || restore_previous "service enablement drifted while finalizing the committed rollback"
remove_transaction_runtime_guard "$SERVICE_USER" \
  || restore_previous "cannot remove the transaction runtime guard and restore the production restart policy"
assert_service_persistently_disabled "$SERVICE_USER" \
  || restore_previous "service became enabled before unguarded rollback validation"

systemctl --no-block start "$SERVICE" \
  || restore_previous "committed rollback target failed to start without the transaction guard"
FINAL_LOCAL_OK="false"
for _ in $(seq 1 "$SERVICE_HEALTH_ATTEMPTS"); do
  if systemctl is-active --quiet "$SERVICE" \
    && runtime_health "$TARGET_MODE" "$TARGET_MANIFEST_SHA256" \
      "http://127.0.0.1:$LOCAL_PORT/api/health" "$SERVICE_HEALTH_MAX_SECONDS" "$PUBLIC_HOST"; then
    FINAL_LOCAL_OK="true"
    break
  fi
  sleep "$SERVICE_HEALTH_POLL_SECONDS"
done
[[ "$FINAL_LOCAL_OK" == "true" ]] \
  || restore_previous "committed rollback target failed final local health validation"
MAIN_PID="$(systemctl show "$SERVICE" --property=MainPID --value)"
[[ "$MAIN_PID" =~ ^[1-9][0-9]*$ && "$MAIN_PID" != "$GUARDED_MAIN_PID" ]] \
  || restore_previous "committed rollback target did not receive a new unguarded process"
[[ "$(process_exec_argv "$MAIN_PID")" == "$EXPECTED_EXEC_ARGV" \
  && "$(process_working_directory "$MAIN_PID")" == "$TARGET" ]] \
  || restore_previous "committed rollback process provenance is invalid"
process_environment_matches "$MAIN_PID" \
  || restore_previous "committed rollback process environment is invalid"
[[ "$(readlink -f -- "$CURRENT_LINK")" == "$TARGET" \
  && "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
  && "$(systemctl show "$SERVICE" --property=Restart --value)" == "on-failure" \
  && "$(systemctl show "$SERVICE" --property=RuntimeMaxUSec --value)" == "infinity" \
  && "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$EXPECTED_EXEC_PATH" \
  && "$(effective_exec_argv)" == "$EXPECTED_EXEC_ARGV" \
  && "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$CURRENT_LINK" \
  && "$(systemctl show "$SERVICE" --property=User --value)" == "$SERVICE_USER" \
  && "$(systemctl show "$SERVICE" --property=Group --value)" == "$SERVICE_GROUP" \
  && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
  && "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" \
  && "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" \
  && "$(systemctl show "$SERVICE" --property=MainPID --value)" == "$MAIN_PID" ]] \
  || restore_previous "committed rollback effective runtime drifted before enablement"
if [[ "$TARGET_MODE" == "release" ]]; then
  [[ "$(effective_exec_start_pre_argvs)" == "$MODERN_EXEC_START_PRE_ARGVS_JSON" ]] \
    || restore_previous "committed release rollback ordinary-restart environment gate drifted before enablement"
else
  [[ -z "$(systemctl show "$SERVICE" --property=ExecStartPre --value)" ]] \
    || restore_previous "committed legacy rollback unexpectedly gained a modern ExecStartPre"
fi
if [[ -n "$EXPECTED_DROPINS" ]]; then
  assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" "$EXPECTED_DROPINS" \
    || restore_previous "committed rollback drop-in set drifted before enablement"
else
  assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" \
    || restore_previous "committed legacy rollback retained an unexpected drop-in before enablement"
fi
assert_service_persistently_disabled "$SERVICE_USER" \
  || restore_previous "committed rollback became enabled before final validation"
( trap - EXIT; validate_runtime_provenance "$TARGET_MODE" "$RELEASE_ID" "$TARGET" ) \
  || restore_previous "committed rollback source/runtime provenance drifted before enablement"
runtime_health "$TARGET_MODE" "$TARGET_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || restore_previous "committed rollback public health or release identity failed before enablement"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || restore_previous "committed rollback login redirect failed before enablement"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || restore_previous "committed rollback database backup evidence drifted before enablement"
validate_production_environment \
  || restore_previous "production environment failed the rollback final evidence and enablement gate"

systemctl enable "$SERVICE" \
  || restore_previous "cannot persist automatic startup for the committed rollback target"
assert_standard_enabled_topology "$SERVICE_USER" \
  || restore_previous "committed rollback enablement topology is not uniquely standard"
fsync_systemd_enablement_state \
  || restore_previous "cannot persist the committed rollback enablement topology"
assert_standard_enabled_topology "$SERVICE_USER" \
  || restore_previous "committed rollback enablement topology drifted after persistence"
[[ "$(readlink -f -- "$CURRENT_LINK")" == "$TARGET" \
  && "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
  && "$(systemctl show "$SERVICE" --property=Restart --value)" == "on-failure" \
  && "$(systemctl show "$SERVICE" --property=RuntimeMaxUSec --value)" == "infinity" \
  && "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$EXPECTED_EXEC_PATH" \
  && "$(effective_exec_argv)" == "$EXPECTED_EXEC_ARGV" \
  && "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$CURRENT_LINK" \
  && "$(systemctl show "$SERVICE" --property=User --value)" == "$SERVICE_USER" \
  && "$(systemctl show "$SERVICE" --property=Group --value)" == "$SERVICE_GROUP" \
  && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
  && "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" \
  && "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" \
  && "$(systemctl show "$SERVICE" --property=MainPID --value)" == "$MAIN_PID" ]] \
  || fail "rollback target is committed but runtime identity drifted after enablement; manual recovery is required and the service remains in its actual state"
if [[ "$TARGET_MODE" == "release" ]]; then
  [[ "$(effective_exec_start_pre_argvs)" == "$MODERN_EXEC_START_PRE_ARGVS_JSON" ]] \
    || fail "rollback target is committed but its ordinary-restart environment gate drifted after enablement"
else
  [[ -z "$(systemctl show "$SERVICE" --property=ExecStartPre --value)" ]] \
    || fail "legacy rollback target is committed but inherited an unsupported modern ExecStartPre"
fi
if [[ -n "$EXPECTED_DROPINS" ]]; then
  assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" "$EXPECTED_DROPINS" \
    || fail "rollback target is committed but drop-in identity drifted after enablement"
else
  assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" \
    || fail "legacy rollback target is committed but retained an unexpected drop-in after enablement"
fi
systemctl is-active --quiet "$SERVICE" \
  || fail "rollback target is committed but the service is not active after enablement; manual recovery is required and the service remains in its actual state"
[[ "$(process_exec_argv "$MAIN_PID")" == "$EXPECTED_EXEC_ARGV" \
  && "$(process_working_directory "$MAIN_PID")" == "$TARGET" ]] \
  || fail "rollback target is committed but process provenance drifted after enablement; manual recovery is required and the service remains in its actual state"
( trap - EXIT; validate_runtime_provenance "$TARGET_MODE" "$RELEASE_ID" "$TARGET" ) \
  || fail "rollback target is committed but source/runtime provenance drifted after enablement; manual recovery is required and the service remains in its actual state"
runtime_health "$TARGET_MODE" "$TARGET_MANIFEST_SHA256" \
  "http://127.0.0.1:$LOCAL_PORT/api/health" 8 "$PUBLIC_HOST" \
  || fail "rollback target is committed but local health or release identity failed after enablement; manual recovery is required and the service remains in its actual state"
runtime_health "$TARGET_MODE" "$TARGET_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || fail "rollback target is committed but public health or release identity failed after enablement; manual recovery is required and the service remains in its actual state"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || fail "rollback target is committed but login redirect validation failed after enablement; manual recovery is required and the service remains in its actual state"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "rollback target is committed but database backup evidence drifted before publication; manual recovery is required and the service remains in its actual state"
validate_final_publication_configuration \
  || fail "rollback target is committed but the final publication configuration binding failed; manual recovery is required and passed evidence was not published"
validate_production_environment \
  || fail "rollback target is committed but the production environment failed immediately before passed-record publication; manual recovery is required"

publish_committed_record "$ROLLBACK_RECORD_TEMP" "$ROLLBACK_RECORD" \
  || fail "rollback target remains committed under the active marker because passed evidence publication failed; rerun recover-transaction.sh"
mv -T -- "$TRANSACTION_FILE" "$COMMITTED_TRANSACTION_RECORD" \
  || restore_previous "committed rollback passed activation and evidence publication but its active marker could not be archived"
TRANSACTION_ACTIVE="false"
assert_trusted_root_file_path "$COMMITTED_TRANSACTION_RECORD" \
  "archived rollback transaction evidence"
fsync_file "$COMMITTED_TRANSACTION_RECORD" \
  || fail "rollback activation is complete but transaction evidence durability is incomplete"
fsync_directory "$DEPLOYMENT_DIR" \
  || fail "rollback activation is complete but transaction evidence directory durability is incomplete"
fsync_directory "$APP_ROOT" \
  || fail "rollback activation is complete but marker archive durability is incomplete"
trap - EXIT INT TERM HUP

printf 'ROLLBACK PASS: current -> %s (%s runtime)\n' "$RELEASE_ID" "$TARGET_MODE"
printf 'Shared runs, account database, backups and Cloudflare settings were preserved.\n'
