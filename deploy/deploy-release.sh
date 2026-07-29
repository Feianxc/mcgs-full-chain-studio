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

usage() {
  builtin printf '%s\n' \
    'Usage:' \
    '  deploy-release.sh --archive FILE --archive-sha256 SHA256 --release-id ID --expected-version VERSION \' \
    '    (--prepare-only | --confirm-switch-production)' \
    '' \
    'Optional environment:' \
    '  PROTOCOL_STUDIO_DEPLOY_ROOT       default /srv/apps/protocol-studio' \
    '  PROTOCOL_STUDIO_ENV_FILE          default /etc/protocol-studio/protocol-studio.env' \
    '  PROTOCOL_STUDIO_SYSTEMD_SERVICE   default protocol-studio.service' \
    '  PROTOCOL_STUDIO_PUBLIC_ORIGIN     default https://protocol.feian.online' \
    '  PROTOCOL_STUDIO_LOCAL_PORT        default 18771' \
    '  PROTOCOL_STUDIO_PREFLIGHT_PORT    default 18772' \
    '  PROTOCOL_STUDIO_WHEELHOUSE        required root-owned offline wheel directory'
}

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
  assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" \
    "managed systemd drop-in directory" || return 1
  assert_secure_systemd_file "$MANAGED_DROPIN" \
    "managed systemd runtime drop-in" || return 1
  [[ "$(sha256sum "$MANAGED_DROPIN" | awk '{print $1}')" == "$MANAGED_DROPIN_SHA256" ]] \
    || return 1
  managed_dropin_matches_canonical_content || return 1
  [[ "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
    && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
    && "$(effective_exec_start_pre_argvs)" == "$MODERN_EXEC_START_PRE_ARGVS_JSON" ]] \
    || return 1
  effective_unset_environment_matches || return 1
  effective_environment_matches || return 1
  effective_restart_limit_matches || return 1
  assert_dropin_paths_exact \
    "$(systemctl show "$SERVICE" --property=DropInPaths --value)" "$MANAGED_DROPIN"
}

service_enable_state() {
  systemctl is-enabled "$SERVICE" 2>/dev/null || true
}

assert_secure_systemd_directory() {
  local directory="$1"
  local label="$2"
  local resolved
  local owner_group
  local mode
  assert_trusted_root_directory_path "$directory" "$label path"
  [[ -d "$directory" && ! -L "$directory" ]] \
    || fail "$label must be a real directory"
  resolved="$(realpath -e -- "$directory")" \
    || fail "$label cannot be resolved"
  [[ "$resolved" == "$directory" ]] \
    || fail "$label resolves through an unexpected symbolic-link path"
  owner_group="$(stat -c '%u:%g' -- "$directory")"
  mode="$(stat -c '%a' -- "$directory")"
  [[ "$owner_group" == "0:0" ]] \
    || fail "$label must be owned by root:root"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] \
    || fail "$label has an unreadable permission mode"
  (( (8#$mode & 0022) == 0 )) \
    || fail "$label must not be writable by group or other"
  if runuser -u "$SERVICE_USER" -- "$TEST_BIN" -w "$directory"; then
    fail "$label is writable by the systemd service account"
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
  [[ "$owner_group" == "0:0" ]] \
    || fail "$label must be owned by root:root"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] \
    || fail "$label has an unreadable permission mode"
  (( (8#$mode & 0022) == 0 )) \
    || fail "$label must not be writable by group or other"
  assert_no_extended_acl "$file" "$label"
  assert_trusted_root_directory_path \
    "$("$TRUST_DIRNAME_BIN" -- "$file")" "$label parent directory"
  if runuser -u "$SERVICE_USER" -- "$TEST_BIN" -w "$file"; then
    fail "$label is writable by the systemd service account"
  fi
}

assert_trusted_root_file_path() {
  local file="$1"
  local label="$2"
  local resolved
  local current
  local owner_group
  local mode
  [[ -f "$file" && ! -L "$file" ]] \
    || fail "$label must be a regular non-symlink file"
  resolved="$("$TRUST_REALPATH_BIN" -e -- "$file" 2>/dev/null)" \
    || fail "$label cannot be resolved"
  [[ "$resolved" == "$file" ]] \
    || fail "$label resolves through an unexpected symbolic-link path"
  [[ "$("$TRUST_STAT_BIN" -c '%u:%g:%a' -- "$file" 2>/dev/null)" == "0:0:600" ]] \
    || fail "$label must be root:root mode 0600"
  assert_no_extended_acl "$file" "$label"
  current="$("$TRUST_DIRNAME_BIN" -- "$file")"
  while :; do
    [[ -d "$current" && ! -L "$current" ]] \
      || fail "$label parent path contains a non-directory or symbolic link"
    [[ "$("$TRUST_REALPATH_BIN" -e -- "$current" 2>/dev/null)" == "$current" ]] \
      || fail "$label parent path resolves through a symbolic link"
    owner_group="$("$TRUST_STAT_BIN" -c '%u:%g' -- "$current" 2>/dev/null)"
    mode="$("$TRUST_STAT_BIN" -c '%a' -- "$current" 2>/dev/null)"
    [[ "$owner_group" == "0:0" ]] \
      || fail "$label parent directories must be owned by root:root"
    [[ "$mode" =~ ^[0-7]{3,4}$ ]] \
      || fail "$label parent directory has an unreadable permission mode"
    (( (8#$mode & 0022) == 0 )) \
      || fail "$label parent directories must not be writable by group or other"
    assert_no_extended_acl "$current" "$label parent path component"
    [[ "$current" == "/" ]] && break
    current="$("$TRUST_DIRNAME_BIN" -- "$current")"
  done
}

assert_trusted_root_directory_path() {
  local directory="$1"
  local label="$2"
  local resolved
  local current
  local owner_group
  local mode
  [[ -d "$directory" && ! -L "$directory" ]] \
    || fail "$label must be a real directory"
  resolved="$("$TRUST_REALPATH_BIN" -e -- "$directory" 2>/dev/null)" \
    || fail "$label cannot be resolved"
  [[ "$resolved" == "$directory" ]] \
    || fail "$label resolves through an unexpected symbolic-link path"
  current="$directory"
  while :; do
    [[ -d "$current" && ! -L "$current" ]] \
      || fail "$label path contains a non-directory or symbolic link"
    [[ "$("$TRUST_REALPATH_BIN" -e -- "$current" 2>/dev/null)" == "$current" ]] \
      || fail "$label path resolves through a symbolic link"
    owner_group="$("$TRUST_STAT_BIN" -c '%u:%g' -- "$current" 2>/dev/null)"
    mode="$("$TRUST_STAT_BIN" -c '%a' -- "$current" 2>/dev/null)"
    [[ "$owner_group" == "0:0" ]] \
      || fail "$label and its parent path must be owned by root:root"
    [[ "$mode" =~ ^[0-7]{3,4}$ ]] \
      || fail "$label path has an unreadable permission mode"
    (( (8#$mode & 0022) == 0 )) \
      || fail "$label path must not be writable by group or other"
    assert_no_extended_acl "$current" "$label path component"
    [[ "$current" == "/" ]] && break
    current="$("$TRUST_DIRNAME_BIN" -- "$current")"
  done
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
  assert_trusted_record_file "$temporary" "pending deployment evidence"
  [[ ! -e "$final" && ! -L "$final" ]] || return 1
  ln -T -- "$temporary" "$final" || return 1
  assert_trusted_record_file "$final" "published deployment evidence"
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

audit_current_activation_schema() {
  local current_target
  local current_id
  local record
  local schema

  [[ -L "$CURRENT_LINK" ]] || fail "current must be an existing symbolic link"
  current_target="$(readlink -f -- "$CURRENT_LINK")" \
    || fail "current target cannot be resolved"
  case "$current_target" in
    "$RELEASES_DIR"/*) ;;
    *) fail "current target is outside the releases directory" ;;
  esac
  [[ -d "$current_target" ]] || fail "current target does not exist"
  current_id="$(basename -- "$current_target")"

  if [[ "$current_id" == "$LEGACY_RELEASE_ID" ]]; then
    [[ ! -e "$current_target/.venv" && ! -L "$current_target/.venv" ]] \
      || fail "registered legacy baseline unexpectedly contains a release-local venv"
    return 0
  fi

  [[ -x "$current_target/.venv/bin/python" ]] \
    || fail "current runtime is neither the registered legacy baseline nor a release-local deployment"
  record="$DEPLOYMENT_DIR/$current_id.json"
  assert_trusted_record_file "$record" \
    "current release-local passed deployment record"
  schema="$("$PYTHON_BIN" -I - "$record" <<'PY'
from __future__ import annotations
import json
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
    raise SystemExit("current release deployment record is not a JSON object")
schema = record.get("schema_version")
if type(schema) is not int or schema not in {2, 3, 4, 5}:
    raise SystemExit("current release deployment record schema is invalid")
print(schema)
PY
  )" || fail "current release deployment record schema is unreadable"
  require_activatable_passed_record_schema "$schema"
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

install_runtime_guard_helper() {
  local source="$CANDIDATE_DIR/deploy/runtime_fingerprint.py"
  install -d -o root -g root -m 0755 "$RUNTIME_GUARD_DIR" "$RUNTIME_BASELINE_DIR" \
    || return 1
  assert_trusted_root_directory_path "$RUNTIME_GUARD_DIR" "runtime guard directory" \
    || return 1
  assert_trusted_root_directory_path "$RUNTIME_BASELINE_DIR" "runtime baseline directory" \
    || return 1
  [[ "$(stat -c '%u:%g:%a' -- "$RUNTIME_GUARD_DIR")" == "0:0:755" \
    && "$(stat -c '%u:%g:%a' -- "$RUNTIME_BASELINE_DIR")" == "0:0:755" ]] \
    || return 1
  if [[ -e "$RUNTIME_GUARD_HELPER" || -L "$RUNTIME_GUARD_HELPER" ]]; then
    [[ -f "$RUNTIME_GUARD_HELPER" && ! -L "$RUNTIME_GUARD_HELPER" \
      && "$(stat -c '%u:%g:%a' -- "$RUNTIME_GUARD_HELPER")" == "0:0:444" ]] \
      || return 1
    assert_no_extended_acl "$RUNTIME_GUARD_HELPER" "runtime guard helper" || return 1
    if ! cmp -s "$source" "$RUNTIME_GUARD_HELPER"; then
      printf 'ERROR: candidate runtime guard differs from the installed immutable helper; automatic helper upgrades are intentionally blocked and require a separately audited migration\n' >&2
      return 1
    fi
  else
    "$PYTHON_BIN" -I -B -u - "$source" "$RUNTIME_GUARD_HELPER" <<'PY'
from __future__ import annotations
import os
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
payload = source.read_bytes()
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(target, flags, 0o444)
try:
    os.fchmod(descriptor, 0o444)
    os.fchown(descriptor, 0, 0)
    with os.fdopen(descriptor, "wb", closefd=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
finally:
    os.close(descriptor)
PY
    fsync_directory "$RUNTIME_GUARD_DIR" || return 1
  fi
  [[ -f "$RUNTIME_GUARD_HELPER" && ! -L "$RUNTIME_GUARD_HELPER" \
    && "$(stat -c '%u:%g:%a' -- "$RUNTIME_GUARD_HELPER")" == "0:0:444" ]] \
    || return 1
  cmp -s "$source" "$RUNTIME_GUARD_HELPER" || return 1
  fsync_file "$RUNTIME_GUARD_HELPER" || return 1
  fsync_directory "$RUNTIME_GUARD_DIR" || return 1
  fsync_directory "$RUNTIME_BASELINE_DIR"
}

create_runtime_baseline() {
  local runtime_fingerprint_json="$1"
  local release_manifest_sha256="$2"
  local runtime_guard_helper_sha256="$3"
  [[ ! -e "$RUNTIME_BASELINE_TEMP" && ! -L "$RUNTIME_BASELINE_TEMP" ]] || return 1
  "$PYTHON_BIN" -I -B -u - "$RUNTIME_BASELINE_TEMP" "$RELEASE_ID" \
    "$EXPECTED_VERSION" "$RELEASE_DIR" "$ARCHIVE_SHA256" \
    "$release_manifest_sha256" "$runtime_guard_helper_sha256" \
    "$runtime_fingerprint_json" <<'PY'
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
fingerprint = json.loads(
    sys.argv[8],
    parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
)
if not isinstance(fingerprint, dict) or fingerprint.get("schema_version") != 2:
    raise SystemExit("runtime fingerprint contract is invalid")
if not isinstance(sys.argv[7], str) or re.fullmatch(r"[0-9a-f]{64}", sys.argv[7]) is None:
    raise SystemExit("runtime guard helper digest is invalid")
record = {
    "schema_version": 1,
    "project": "mcgs-full-chain-studio",
    "release_id": sys.argv[2],
    "version": sys.argv[3],
    "release_root": sys.argv[4],
    "archive_sha256": sys.argv[5],
    "release_manifest_sha256": sys.argv[6],
    "runtime_guard_helper_sha256": sys.argv[7],
    "runtime_fingerprint": fingerprint,
}
payload = (json.dumps(
    record,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
) + "\n").encode("utf-8")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
descriptor = os.open(path, flags, 0o444)
try:
    os.fchmod(descriptor, 0o444)
    os.fchown(descriptor, 0, 0)
    with os.fdopen(descriptor, "wb", closefd=False) as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
finally:
    os.close(descriptor)
PY
  [[ -f "$RUNTIME_BASELINE_TEMP" && ! -L "$RUNTIME_BASELINE_TEMP" \
    && "$(stat -c '%u:%g:%a' -- "$RUNTIME_BASELINE_TEMP")" == "0:0:444" ]] \
    || return 1
  assert_no_extended_acl "$RUNTIME_BASELINE_TEMP" "pending release runtime baseline" || return 1
  fsync_file "$RUNTIME_BASELINE_TEMP" || return 1
  fsync_directory "$RUNTIME_BASELINE_DIR"
}

relocate_runtime_fingerprint() {
  local fingerprint_json="$1"
  "$PYTHON_BIN" -I -B -u - "$CANDIDATE_DIR" "$RELEASE_DIR" \
    "$fingerprint_json" <<'PY'
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

candidate = Path(sys.argv[1])
release = Path(sys.argv[2])
record = json.loads(
    sys.argv[3],
    parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non-finite number")),
)
if not isinstance(record, dict) or record.get("schema_version") != 2:
    raise SystemExit("runtime fingerprint contract is invalid")
interpreter = record.get("interpreter")
if not isinstance(interpreter, dict) or not isinstance(interpreter.get("realpath"), str):
    raise SystemExit("runtime interpreter contract is invalid")
realpath = Path(interpreter["realpath"])
try:
    relative = realpath.relative_to(candidate)
except ValueError:
    pass
else:
    interpreter["realpath"] = os.fspath(release / relative)
print(json.dumps(
    record,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
))
PY
}

publish_runtime_baseline() {
  [[ -f "$RUNTIME_BASELINE_TEMP" && ! -L "$RUNTIME_BASELINE_TEMP" \
    && "$(stat -c '%u:%g:%a' -- "$RUNTIME_BASELINE_TEMP")" == "0:0:444" \
    && ! -e "$RUNTIME_BASELINE" && ! -L "$RUNTIME_BASELINE" ]] \
    || return 1
  ln -T -- "$RUNTIME_BASELINE_TEMP" "$RUNTIME_BASELINE" || return 1
  [[ "$(stat -c '%d:%i' -- "$RUNTIME_BASELINE_TEMP")" \
    == "$(stat -c '%d:%i' -- "$RUNTIME_BASELINE")" ]] \
    || return 1
  fsync_file "$RUNTIME_BASELINE" || return 1
  fsync_directory "$RUNTIME_BASELINE_DIR" || return 1
  rm -f -- "$RUNTIME_BASELINE_TEMP" || return 1
  [[ ! -e "$RUNTIME_BASELINE_TEMP" && ! -L "$RUNTIME_BASELINE_TEMP" ]] \
    || return 1
  fsync_directory "$RUNTIME_BASELINE_DIR"
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
  # runuser preserves the invoking cwd.  A deployment started from /root can
  # therefore make GNU find fail while restoring its initial directory after
  # it has dropped to the service account.  Change to a universally
  # traversable cwd inside the unprivileged process and pass both command and
  # release path as positional arguments rather than interpolating shell text.
  writable="$(runuser -u "$service_user" -- \
    "$SH_BIN" -c 'cd / && exec "$1" "$2" -xdev -writable -print -quit' \
    sh "$FIND_BIN" "$release_root")" \
    || fail "cannot evaluate release write access as the service account"
  [[ -z "$writable" ]] \
    || fail "release tree is writable by the systemd service account"
}

ARCHIVE=""
EXPECTED_ARCHIVE_SHA256=""
RELEASE_ID=""
EXPECTED_VERSION=""
MODE=""
while (($#)); do
  case "$1" in
    --archive)
      (($# >= 2)) || fail "--archive requires a value"
      ARCHIVE="$2"
      shift 2
      ;;
    --release-id)
      (($# >= 2)) || fail "--release-id requires a value"
      RELEASE_ID="$2"
      shift 2
      ;;
    --archive-sha256)
      (($# >= 2)) || fail "--archive-sha256 requires a value"
      EXPECTED_ARCHIVE_SHA256="${2,,}"
      shift 2
      ;;
    --expected-version)
      (($# >= 2)) || fail "--expected-version requires a value"
      EXPECTED_VERSION="$2"
      shift 2
      ;;
    --prepare-only)
      [[ -z "$MODE" ]] || fail "choose exactly one deployment mode"
      MODE="prepare"
      shift
      ;;
    --confirm-switch-production)
      [[ -z "$MODE" ]] || fail "choose exactly one deployment mode"
      MODE="switch"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

[[ "$EUID" == "0" ]] || fail "run as root"
[[ -n "$ARCHIVE" && -n "$EXPECTED_ARCHIVE_SHA256" && -n "$RELEASE_ID" \
  && -n "$EXPECTED_VERSION" && -n "$MODE" ]] \
  || { usage >&2; fail "required arguments are missing"; }
[[ "$EXPECTED_ARCHIVE_SHA256" =~ ^[0-9a-f]{64}$ ]] \
  || fail "archive sha256 must contain exactly 64 hexadecimal characters"
[[ "$RELEASE_ID" =~ ^[0-9A-Za-z][0-9A-Za-z._-]{0,79}$ ]] \
  || fail "release id contains unsupported characters"
[[ "$EXPECTED_VERSION" =~ ^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$ ]] \
  || fail "expected version contains unsupported characters"

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
case "$SCRIPT_SOURCE" in
  */*) SCRIPT_PARENT="${SCRIPT_SOURCE%/*}" ;;
  *) SCRIPT_PARENT="." ;;
esac
SCRIPT_DIR="$(builtin cd -- "$SCRIPT_PARENT" && builtin pwd -P)"
REPO_TOOLS="$(builtin cd -- "$SCRIPT_DIR/.." && builtin pwd -P)"
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
  install journalctl ln mv readlink realpath rm rmdir runuser sed seq sha256sum \
  sleep stat sync systemctl systemd-run; do
  resolve_and_pin_trusted_command "$trusted_command" TRUSTED_COMMAND_PATH
done
builtin unset TRUSTED_COMMAND_PATH
builtin readonly PYTHON_BIN FIND_BIN SH_BIN TEST_BIN
for trusted_helper in \
  "$SCRIPT_DIR/deploy-release.sh" \
  "$SCRIPT_DIR/atomic_rename.py" \
  "$SCRIPT_DIR/run_with_env.py" \
  "$SCRIPT_DIR/runtime_fingerprint.py" \
  "$SCRIPT_DIR/safe_extract.py" \
  "$SCRIPT_DIR/sqlite_backup.py" \
  "$SCRIPT_DIR/validate_production_env.py" \
  "$SCRIPT_DIR/verify_installed_release.py" \
  "$REPO_TOOLS/packaging/release-allowlist.json" \
  "$REPO_TOOLS/packaging/verify_release.py"; do
  assert_trusted_code_file "$trusted_helper" "deployment control helper"
done
"$PYTHON_BIN" -I - <<'PY' \
  || fail "deployment requires Linux x86_64 CPython 3.11 to match the production wheelhouse ABI"
import platform
import struct
import sys

if (
    sys.implementation.name != "cpython"
    or sys.version_info[:2] != (3, 11)
    or platform.system() != "Linux"
    or platform.machine().lower() not in {"x86_64", "amd64"}
    or struct.calcsize("P") * 8 != 64
):
    raise SystemExit(1)
PY

[[ -f "$ARCHIVE" && ! -L "$ARCHIVE" ]] \
  || fail "release archive must be a regular non-symlink file"
ARCHIVE="$(realpath -e -- "$ARCHIVE")"

APP_ROOT="${PROTOCOL_STUDIO_DEPLOY_ROOT:-/srv/apps/protocol-studio}"
ENV_FILE="${PROTOCOL_STUDIO_ENV_FILE:-/etc/protocol-studio/protocol-studio.env}"
SERVICE="${PROTOCOL_STUDIO_SYSTEMD_SERVICE:-protocol-studio.service}"
PUBLIC_ORIGIN="${PROTOCOL_STUDIO_PUBLIC_ORIGIN:-https://protocol.feian.online}"
LOCAL_PORT="${PROTOCOL_STUDIO_LOCAL_PORT:-18771}"
PREFLIGHT_PORT="${PROTOCOL_STUDIO_PREFLIGHT_PORT:-18772}"
WHEELHOUSE="${PROTOCOL_STUDIO_WHEELHOUSE:-}"
[[ "$SERVICE" =~ ^[0-9A-Za-z_.@-]+\.service$ ]] || fail "invalid systemd service name"
[[ "$LOCAL_PORT" =~ ^[0-9]+$ && "$PREFLIGHT_PORT" =~ ^[0-9]+$ ]] \
  || fail "local ports must be numeric"
((LOCAL_PORT >= 1 && LOCAL_PORT <= 65535)) || fail "local service port is invalid"
((PREFLIGHT_PORT >= 1 && PREFLIGHT_PORT <= 65535)) || fail "preflight port is invalid"
[[ "$LOCAL_PORT" != "$PREFLIGHT_PORT" ]] || fail "preflight port must differ from the production port"
[[ "$APP_ROOT" == /* && "$ENV_FILE" == /* ]] || fail "deployment paths must be absolute"
[[ -n "$WHEELHOUSE" ]] || fail "PROTOCOL_STUDIO_WHEELHOUSE is required for hash-locked offline installation"

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
RUNTIME_BASELINE="$RUNTIME_BASELINE_DIR/$RELEASE_ID.json"
RUNTIME_BASELINE_TEMP="$RUNTIME_BASELINE_DIR/.pending-$RELEASE_ID.json"
SHARED_DIR="$APP_ROOT/shared"
RUNS_DIR="$SHARED_DIR/runs"
SECURITY_DB="$SHARED_DIR/security.sqlite3"
CONTROL_DIR="$APP_ROOT/.deploy-state"
LOG_DIR="$CONTROL_DIR/logs"
BACKUP_DIR="$CONTROL_DIR/backups"
DEPLOYMENT_DIR="$CONTROL_DIR/deployments"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"
INCOMING_DIR="$RELEASES_DIR/.incoming-$RELEASE_ID-$$"
SYSTEMD_CONFIG_DIR="/etc/systemd/system"
SYSTEMD_UNIT_FILE="$SYSTEMD_CONFIG_DIR/$SERVICE"
MANAGED_DROPIN_DIR="/etc/systemd/system/$SERVICE.d"
MANAGED_DROPIN="$MANAGED_DROPIN_DIR/90-release-runtime.conf"
RUNTIME_SYSTEMD_DIR="/run/systemd/system"
TRANSACTION_RUNTIME_GUARD_DIR="$RUNTIME_SYSTEMD_DIR/$SERVICE.d"
TRANSACTION_RUNTIME_GUARD="$TRANSACTION_RUNTIME_GUARD_DIR/99-transaction-runtime-guard.conf"
TRANSACTION_FILE="$APP_ROOT/.deploy-transaction.json"
TRANSACTION_TEMP="$APP_ROOT/.deploy-transaction-$RELEASE_ID-$$.tmp"
LEGACY_RELEASE_ID="${PROTOCOL_STUDIO_LEGACY_RELEASE_ID:-20260722-114300-620b1bcf9aa9}"

case "$RELEASE_DIR" in
  "$RELEASES_DIR"/*) ;;
  *) fail "resolved release path escaped the releases directory" ;;
esac
[[ -d "$APP_ROOT" ]] || fail "application root is missing"
assert_trusted_root_directory_path "$APP_ROOT" "application root"
assert_trusted_root_file_path "$ENV_FILE" "production environment file"
WHEELHOUSE="$(realpath -e -- "$WHEELHOUSE")"
assert_trusted_root_directory_path "$WHEELHOUSE" "offline wheelhouse"
shopt -s nullglob dotglob
WHEELHOUSE_ENTRIES=("$WHEELHOUSE"/*)
shopt -u nullglob dotglob
((${#WHEELHOUSE_ENTRIES[@]} > 0)) || fail "offline wheelhouse is empty"
for wheel_entry in "${WHEELHOUSE_ENTRIES[@]}"; do
  [[ -f "$wheel_entry" && ! -L "$wheel_entry" ]] \
    || fail "offline wheelhouse may contain only regular wheel files"
  [[ "$wheel_entry" == *.whl ]] \
    || fail "offline wheelhouse contains a non-wheel artifact"
  wheel_mode="$(stat -c '%a' -- "$wheel_entry")"
  [[ "$(stat -c '%u:%g' -- "$wheel_entry")" == "0:0" \
    && "$wheel_mode" =~ ^[0-7]{3,4}$ ]] \
    || fail "offline wheel files must be owned by root:root"
  (( (8#$wheel_mode & 0022) == 0 )) \
    || fail "offline wheel files must not be writable by group or other"
  assert_no_extended_acl "$wheel_entry" "offline wheel file"
done
"$PYTHON_BIN" -I "$SCRIPT_DIR/run_with_env.py" --env-file "$ENV_FILE" \
  --validate-only --reject-privileged-loader-variables
[[ -d "$SHARED_DIR" && ! -L "$SHARED_DIR" \
  && "$(realpath -e -- "$SHARED_DIR")" == "$SHARED_DIR" ]] \
  || fail "shared production state root must be a canonical real directory"
[[ -d "$RUNS_DIR" && ! -L "$RUNS_DIR" \
  && "$(realpath -e -- "$RUNS_DIR")" == "$RUNS_DIR" ]] \
  || fail "shared runs directory is missing or unsafe"
[[ -f "$SECURITY_DB" && ! -L "$SECURITY_DB" \
  && "$(realpath -e -- "$SECURITY_DB")" == "$SECURITY_DB" ]] \
  || fail "shared security database is missing or unsafe; refusing to create or reset it"
[[ ! -e "$RELEASE_DIR" && ! -L "$RELEASE_DIR" ]] \
  || fail "release id already exists; releases are immutable"
[[ ! -e "$INCOMING_DIR" && ! -L "$INCOMING_DIR" ]] \
  || fail "incoming path already exists"

# The systemd service is unprivileged and resolves WorkingDirectory through the
# releases parent. Preserve existing administrator-selected permissions; a new
# installation gets a traversable root-owned parent. The service-user gates
# below verify the complete prepared tree before any production change.
if [[ ! -e "$RELEASES_DIR" && ! -L "$RELEASES_DIR" ]]; then
  install -d -o root -g root -m 0755 "$RELEASES_DIR"
fi
assert_trusted_root_directory_path "$RELEASES_DIR" "release storage directory"
install -d -o root -g root -m 0700 "$CONTROL_DIR"
assert_trusted_root_directory_path "$CONTROL_DIR" "deployment control directory"
install -d -o root -g root -m 0750 "$LOG_DIR" "$BACKUP_DIR" "$DEPLOYMENT_DIR"
assert_trusted_root_directory_path "$LOG_DIR" "deployment log directory"
assert_trusted_root_directory_path "$BACKUP_DIR" "deployment backup directory"
assert_trusted_root_directory_path "$DEPLOYMENT_DIR" "deployment record directory"
LOCK_FILE="$CONTROL_DIR/deploy.lock"
if [[ -e "$LOCK_FILE" || -L "$LOCK_FILE" ]]; then
  [[ -f "$LOCK_FILE" && ! -L "$LOCK_FILE" \
    && "$(stat -c '%u:%g:%a' -- "$LOCK_FILE")" == "0:0:600" ]] \
    || fail "deployment lock must be a root-owned regular file with mode 0600"
else
  install -o root -g root -m 0600 /dev/null "$LOCK_FILE"
  fsync_file "$LOCK_FILE"
  fsync_directory "$CONTROL_DIR"
fi
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
  || fail "an unfinished deployment transaction exists; recover it before continuing"
if [[ "$MODE" == "switch" ]]; then
  audit_current_activation_schema
fi
verify_atomic_rename_boundary \
  || fail "application and deployment-record directories failed the atomic rename boundary gate"
DEPLOYMENT_RECORD="$DEPLOYMENT_DIR/$RELEASE_ID.json"
PENDING_DEPLOYMENT_RECORD="$DEPLOYMENT_DIR/.pending-deploy-$RELEASE_ID.json"
COMMITTED_TRANSACTION_RECORD="$DEPLOYMENT_DIR/transaction-deploy-$RELEASE_ID.json"
[[ ! -e "$DEPLOYMENT_RECORD" && ! -L "$DEPLOYMENT_RECORD" ]] \
  || fail "deployment passed-record path already exists"
[[ ! -e "$PENDING_DEPLOYMENT_RECORD" && ! -L "$PENDING_DEPLOYMENT_RECORD" ]] \
  || fail "deployment pending-record path already exists; recover or quarantine it before retrying"
[[ ! -e "$COMMITTED_TRANSACTION_RECORD" && ! -L "$COMMITTED_TRANSACTION_RECORD" ]] \
  || fail "deployment transaction evidence path already exists"
[[ ! -e "$RUNTIME_BASELINE" && ! -L "$RUNTIME_BASELINE" ]] \
  || fail "runtime baseline path already exists; quarantine the release and baseline together"
[[ ! -e "$RUNTIME_BASELINE_TEMP" && ! -L "$RUNTIME_BASELINE_TEMP" ]] \
  || fail "pending runtime baseline exists; quarantine it before retrying"

ARCHIVE_SOURCE="$ARCHIVE"
TRUSTED_ARCHIVE="$CONTROL_DIR/.archive-$RELEASE_ID-$$.tar.gz"
cleanup_trusted_archive() {
  if [[ -n "${TRUSTED_ARCHIVE:-}" ]]; then
    rm -f -- "$TRUSTED_ARCHIVE"
    fsync_directory "$CONTROL_DIR" >/dev/null 2>&1 || true
  fi
}
trap cleanup_trusted_archive EXIT
ARCHIVE_SHA256_FIXED="$($PYTHON_BIN -I - "$ARCHIVE_SOURCE" "$TRUSTED_ARCHIVE" <<'PY'
from __future__ import annotations
import hashlib
import os
import stat
import sys

source_path, target_path = sys.argv[1:3]
read_flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
source = os.open(source_path, read_flags)
target = -1
try:
    before = os.fstat(source)
    if not stat.S_ISREG(before.st_mode):
        raise SystemExit("release archive source is not a regular file")
    target = os.open(target_path, write_flags, 0o600)
    digest = hashlib.sha256()
    while True:
        chunk = os.read(source, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        view = memoryview(chunk)
        while view:
            written = os.write(target, view)
            view = view[written:]
    os.fsync(target)
    after = os.fstat(source)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    if identity_before != identity_after:
        raise SystemExit("release archive changed while it was snapshotted")
    print(digest.hexdigest())
finally:
    if target >= 0:
        os.close(target)
    os.close(source)
PY
)"
[[ "$ARCHIVE_SHA256_FIXED" == "$EXPECTED_ARCHIVE_SHA256" ]] \
  || fail "trusted release archive sha256 does not match the required digest"
assert_trusted_root_file_path "$TRUSTED_ARCHIVE" "trusted release archive snapshot"
fsync_file "$TRUSTED_ARCHIVE"
fsync_directory "$CONTROL_DIR"
ARCHIVE="$TRUSTED_ARCHIVE"

"$PYTHON_BIN" -I "$REPO_TOOLS/packaging/verify_release.py" \
  "$ARCHIVE" --expected-version "$EXPECTED_VERSION"

install -d -m 0755 "$INCOMING_DIR"
TOP_LEVEL="$("$PYTHON_BIN" -I "$SCRIPT_DIR/safe_extract.py" "$ARCHIVE" "$INCOMING_DIR")"
EXTRACTED_ROOT="$INCOMING_DIR/$TOP_LEVEL"
[[ -d "$EXTRACTED_ROOT" ]] || fail "safe extractor did not produce a release root"
"$PYTHON_BIN" -I "$REPO_TOOLS/packaging/verify_release.py" \
  "$EXTRACTED_ROOT" --expected-version "$EXPECTED_VERSION"
RELEASE_MANIFEST_SHA256="$(sha256sum "$EXTRACTED_ROOT/release-manifest.json" | awk '{print $1}')"
[[ "$RELEASE_MANIFEST_SHA256" =~ ^[0-9a-f]{64}$ ]] \
  || fail "prepared release manifest digest is invalid"
rm -f -- "$TRUSTED_ARCHIVE"
fsync_directory "$CONTROL_DIR"
TRUSTED_ARCHIVE=""
trap - EXIT

CANDIDATE_DIR="$EXTRACTED_ROOT"
CANDIDATE_PYTHON="$CANDIDATE_DIR/.venv/bin/python"
CANDIDATE_CLEANUP_ACTIVE="true"
RELEASE_PROMOTED="false"
cleanup_candidate() {
  [[ "$CANDIDATE_CLEANUP_ACTIVE" == "true" ]] || return 0
  if [[ "$RELEASE_PROMOTED" == "true" ]]; then
    # A promoted release is durable transaction evidence.  The EXIT trap must
    # never move or remove it; operators quarantine it manually after review.
    return 0
  fi
  if [[ -e "$RUNTIME_BASELINE_TEMP" || -L "$RUNTIME_BASELINE_TEMP" ]]; then
    if [[ -f "$RUNTIME_BASELINE_TEMP" && ! -L "$RUNTIME_BASELINE_TEMP" \
      && "$(stat -c '%u:%g:%a' -- "$RUNTIME_BASELINE_TEMP" 2>/dev/null)" == "0:0:444" ]]; then
      rm -f -- "$RUNTIME_BASELINE_TEMP"
      fsync_directory "$RUNTIME_BASELINE_DIR" >/dev/null 2>&1 || true
    else
      printf 'ERROR: refusing to clean an unsafe pending runtime baseline\n' >&2
    fi
  fi
  if [[ -e "$TRANSACTION_TEMP" || -L "$TRANSACTION_TEMP" ]]; then
    if [[ -f "$TRANSACTION_TEMP" && ! -L "$TRANSACTION_TEMP" \
      && "$(stat -c '%u:%g:%a' -- "$TRANSACTION_TEMP" 2>/dev/null)" == "0:0:600" ]]; then
      rm -f -- "$TRANSACTION_TEMP"
      fsync_directory "$APP_ROOT" >/dev/null 2>&1 || true
    else
      printf 'ERROR: refusing to clean an unsafe pending transaction marker\n' >&2
    fi
  fi
  case "$INCOMING_DIR" in
    "$RELEASES_DIR"/.incoming-*) rm -rf -- "$INCOMING_DIR" ;;
    *) printf 'ERROR: refusing to clean an unexpected incoming release path\n' >&2 ;;
  esac
  fsync_directory "$RELEASES_DIR" >/dev/null 2>&1 || true
}
trap cleanup_candidate EXIT

[[ ! -e "$CANDIDATE_DIR/.venv" && ! -L "$CANDIDATE_DIR/.venv" ]] \
  || fail "release payload must not contain a pre-existing runtime directory"
"$PYTHON_BIN" -I -m venv "$CANDIDATE_DIR/.venv"
[[ -f "$CANDIDATE_DIR/requirements.production.lock.txt" ]] \
  || fail "hash-locked production requirements are missing from the release"
"$CANDIDATE_PYTHON" -I - "$WHEELHOUSE" <<'PY'
from pathlib import Path
import sys

from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import InvalidWheelFilename, parse_wheel_filename

supported = set(sys_tags())
wheelhouse = Path(sys.argv[1])
errors = []
for wheel in sorted(wheelhouse.glob("*.whl")):
    try:
        _name, _version, _build, tags = parse_wheel_filename(wheel.name)
    except InvalidWheelFilename:
        errors.append(f"invalid wheel filename: {wheel.name}")
        continue
    if supported.isdisjoint(tags):
        errors.append(f"wheel is incompatible with this interpreter: {wheel.name}")
if errors:
    raise SystemExit("\n".join(errors))
PY
"$CANDIDATE_PYTHON" -I -m pip install --disable-pip-version-check --no-cache-dir \
  --no-index --find-links "$WHEELHOUSE" --only-binary=:all: --require-hashes \
  --requirement "$CANDIDATE_DIR/requirements.production.lock.txt"
"$CANDIDATE_PYTHON" -I -m pip check

# safe_extract.py and venv creation inherit umask 027. The release contains no
# secrets and is immutable, so normalize every directory/file for read/execute
# access by the service account while retaining root ownership and write access.
chown -R root:root "$CANDIDATE_DIR"
chmod -R u=rwX,go=rX "$CANDIDATE_DIR"

"$PYTHON_BIN" -I "$SCRIPT_DIR/verify_installed_release.py" \
  "$CANDIDATE_DIR" --expected-version "$EXPECTED_VERSION"

validate_production_environment \
  || fail "production environment failed the pre-canary gate"

sync -f "$CANDIDATE_DIR" || fail "cannot make the staged candidate durable"
RELEASE_PYTHON="$CANDIDATE_PYTHON"

SERVICE_USER="$(systemctl show "$SERVICE" --property=User --value)"
SERVICE_GROUP="$(systemctl show "$SERVICE" --property=Group --value)"
[[ -n "$SERVICE_USER" && "$SERVICE_USER" != "root" ]] \
  || fail "systemd service must use a named unprivileged account"
[[ -n "$SERVICE_GROUP" ]] || SERVICE_GROUP="$SERVICE_USER"
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
runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$RELEASES_DIR" \
  || fail "systemd service user cannot traverse the releases directory"
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
runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$CANDIDATE_DIR" \
  || fail "systemd service user cannot traverse the prepared release"
runuser -u "$SERVICE_USER" -- "$TEST_BIN" -r "$CANDIDATE_DIR/protocol_studio/app.py" \
  || fail "systemd service user cannot read the prepared application"
runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$RELEASE_PYTHON" \
  || fail "systemd service user cannot execute the prepared release runtime"
assert_release_tree_security "$CANDIDATE_DIR" "$SERVICE_USER"

# The candidate must exercise the production EnvironmentFile and shared paths
# without ever opening the live account database or runs tree.  Make an online
# SQLite copy in a private shared tree; the transient systemd unit bind-mounts
# that tree over the production shared path inside its private mount namespace.
# The host namespace and the running production service continue to see the
# real shared tree.
PREFLIGHT_ROOT="$APP_ROOT/.preflight-$RELEASE_ID-$$"
PREFLIGHT_SHARED="$PREFLIGHT_ROOT/shared"
PREFLIGHT_DB="$PREFLIGHT_SHARED/security.sqlite3"
PREFLIGHT_RUNS="$PREFLIGHT_SHARED/runs"
PREFLIGHT_RELEASE_PYTHON="$RELEASE_DIR/.venv/bin/python"
install -d -o root -g root -m 0700 \
  "$PREFLIGHT_ROOT" "$PREFLIGHT_SHARED" "$PREFLIGHT_RUNS"
assert_no_extended_acl "$PREFLIGHT_ROOT" "preflight isolation root"
assert_no_extended_acl "$PREFLIGHT_SHARED" "preflight shared staging directory"
assert_no_extended_acl "$PREFLIGHT_RUNS" "preflight runs staging directory"
PREFLIGHT_DB_METADATA_JSON="$("$PYTHON_BIN" -I "$SCRIPT_DIR/sqlite_backup.py" \
  backup --source "$SECURITY_DB" --destination "$PREFLIGHT_DB" \
  --deadline-seconds "$SQLITE_BACKUP_DEADLINE_SECONDS")" \
  || fail "cannot create the isolated preflight security database backup"
[[ "$(stat -c '%u:%g:%a' -- "$PREFLIGHT_DB")" == "0:0:600" ]] \
  || fail "isolated preflight database was not published root-only"
assert_no_extended_acl "$PREFLIGHT_DB" "isolated preflight database"
[[ "$("$PYTHON_BIN" -I "$SCRIPT_DIR/sqlite_backup.py" inspect \
  --source "$PREFLIGHT_DB" \
  --deadline-seconds "$SQLITE_BACKUP_DEADLINE_SECONDS")" == "$PREFLIGHT_DB_METADATA_JSON" ]] \
  || fail "isolated preflight database verification drifted before delegation"
chown "$SERVICE_USER:$SERVICE_GROUP" "$PREFLIGHT_DB"
chmod 0600 "$PREFLIGHT_DB"
chown "$SERVICE_USER:$SERVICE_GROUP" "$PREFLIGHT_SHARED" "$PREFLIGHT_RUNS"
chmod 0700 "$PREFLIGHT_SHARED" "$PREFLIGHT_RUNS"
PREFLIGHT_ESCAPE_LINK="$PREFLIGHT_SHARED/live-security.sqlite3"
ln -s -- "$SECURITY_DB" "$PREFLIGHT_ESCAPE_LINK"
if runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$PREFLIGHT_ROOT" \
  || runuser -u "$SERVICE_USER" -- "$TEST_BIN" -r "$PREFLIGHT_DB"; then
  fail "service UID can traverse the host-side isolated preflight root"
fi

PREFLIGHT_UNIT_KEY="$("$PYTHON_BIN" -I - "$RELEASE_ID" <<'PY'
import hashlib
import sys
print(hashlib.sha256(sys.argv[1].encode("utf-8")).hexdigest()[:16])
PY
)"
PREFLIGHT_UNIT="protocol-studio-canary-$PREFLIGHT_UNIT_KEY-$$.service"
PREFLIGHT_LOG="$LOG_DIR/$RELEASE_ID-preflight-$$.log"
PREFLIGHT_MAIN_PID=""

stop_preflight() {
  local active_state=""
  local load_state
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
    if [[ -z "$load_state" || "$load_state" == "not-found" ]]; then
      break
    fi
    systemctl reset-failed "$PREFLIGHT_UNIT" >/dev/null 2>&1 || true
    sleep 0.1
  done
  [[ -z "$load_state" || "$load_state" == "not-found" ]]
}

capture_preflight_diagnostics() {
  {
    printf 'transient canary unit: %s\n' "$PREFLIGHT_UNIT"
    systemctl status --no-pager --full "$PREFLIGHT_UNIT" 2>&1 || true
    journalctl --no-pager --unit="$PREFLIGHT_UNIT" --since='-5 minutes' 2>&1 || true
    systemctl show "$PREFLIGHT_UNIT" \
      --property=LoadState,ActiveState,SubState,Result,MainPID,ExecMainStatus \
      --property=User,Group,WorkingDirectory,EnvironmentFiles,UnsetEnvironment,ReadWritePaths \
      --property=UMask,NoNewPrivileges,PrivateTmp,PrivateDevices,ProtectSystem \
      2>&1 || true
  } >"$PREFLIGHT_LOG"
  chmod 0600 "$PREFLIGHT_LOG" 2>/dev/null || true
}

preflight_fail() {
  capture_preflight_diagnostics
  fail "$*; see the root-only preflight log"
}

cleanup_preflight() {
  local keep_candidate="${1:-}"
  if ! stop_preflight; then
    printf 'ERROR: transient canary could not be stopped; retaining candidate and private state for manual recovery\n' >&2
    return 0
  fi
  case "$PREFLIGHT_ROOT" in
    "$APP_ROOT"/.preflight-*) rm -rf -- "$PREFLIGHT_ROOT" ;;
    *) printf 'ERROR: refusing to clean an unexpected preflight path\n' >&2 ;;
  esac
  fsync_directory "$APP_ROOT" >/dev/null 2>&1 || true
  if [[ "$keep_candidate" != "--keep-candidate" ]]; then
    cleanup_candidate
  fi
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

PREFLIGHT_LOAD_STATE="$(systemctl show "$PREFLIGHT_UNIT" \
  --property=LoadState --value 2>/dev/null || true)"
[[ -z "$PREFLIGHT_LOAD_STATE" || "$PREFLIGHT_LOAD_STATE" == "not-found" ]] \
  || fail "unique transient canary unit name unexpectedly already exists"

if ! systemd-run --quiet --collect --unit="$PREFLIGHT_UNIT" \
  --description="MCGS release $RELEASE_ID isolated preflight" \
  --property=Type=simple \
  --property="User=$SERVICE_USER" \
  --property="Group=$SERVICE_GROUP" \
  --property="WorkingDirectory=$RELEASE_DIR" \
  --property="EnvironmentFile=$ENV_FILE" \
  --property=Environment= \
  --property="Environment=PYTHONDONTWRITEBYTECODE=1" \
  --property="Environment=PYTHONUNBUFFERED=1" \
  --property="UnsetEnvironment=$REQUIRED_UNSET_ENVIRONMENT" \
  --property="ExecStartPre=$PREFLIGHT_RELEASE_PYTHON -I -B -u $RELEASE_DIR/deploy/validate_production_env.py --shared-runs $RUNS_DIR --security-db $SECURITY_DB --public-origin $PUBLIC_ORIGIN --public-host $PUBLIC_HOST" \
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
  --property="BindReadOnlyPaths=$CANDIDATE_DIR:$RELEASE_DIR" \
  --property="BindPaths=$PREFLIGHT_SHARED:$SHARED_DIR" \
  --property="ReadWritePaths=$SHARED_DIR" \
  -- "$PREFLIGHT_RELEASE_PYTHON" -I -B -u -m uvicorn protocol_studio.app:app \
  --host 127.0.0.1 --port "$PREFLIGHT_PORT" \
  --proxy-headers --forwarded-allow-ips 127.0.0.1; then
  preflight_fail "cannot start the isolated transient systemd canary"
fi

PREFLIGHT_OK="false"
for _ in $(seq 1 "$CANARY_HEALTH_ATTEMPTS"); do
  PREFLIGHT_ACTIVE_STATE="$(systemctl show "$PREFLIGHT_UNIT" \
    --property=ActiveState --value 2>/dev/null || true)"
  case "$PREFLIGHT_ACTIVE_STATE" in
    active)
      if manifest_bound_health "$RELEASE_MANIFEST_SHA256" \
        "http://127.0.0.1:$PREFLIGHT_PORT/api/health" "$CANARY_HEALTH_MAX_SECONDS" "$PUBLIC_HOST"; then
        if systemctl is-active --quiet "$PREFLIGHT_UNIT"; then
          PREFLIGHT_OK="true"
          break
        fi
      fi
      ;;
    activating|reloading)
      ;;
    *)
      break
      ;;
  esac
  sleep "$CANARY_HEALTH_POLL_SECONDS"
done
[[ "$PREFLIGHT_OK" == "true" ]] \
  || preflight_fail "isolated transient systemd canary health check failed"

assert_preflight_property() {
  local property="$1"
  local expected="$2"
  local actual
  if ! actual="$(systemctl show "$PREFLIGHT_UNIT" --property="$property" --value)"; then
    preflight_fail "cannot read transient canary property $property"
  fi
  [[ "$actual" == "$expected" ]] \
    || preflight_fail "transient canary property $property does not match the managed service"
}

assert_preflight_property Type simple
assert_preflight_property User "$SERVICE_USER"
assert_preflight_property Group "$SERVICE_GROUP"
assert_preflight_property WorkingDirectory "$RELEASE_DIR"
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
assert_preflight_property CapabilityBoundingSet ""
assert_preflight_property AmbientCapabilities ""
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

PREFLIGHT_ADDRESS_FAMILIES="$(systemctl show "$PREFLIGHT_UNIT" \
  --property=RestrictAddressFamilies --value)"
if ! "$PYTHON_BIN" -I - "$PREFLIGHT_ADDRESS_FAMILIES" <<'PY'
import sys
if set(sys.argv[1].split()) != {"AF_UNIX", "AF_INET", "AF_INET6"}:
    raise SystemExit(1)
PY
then
  preflight_fail "transient canary address-family restriction does not match the managed service"
fi

PREFLIGHT_MAIN_PID="$(systemctl show "$PREFLIGHT_UNIT" --property=MainPID --value)"
[[ "$PREFLIGHT_MAIN_PID" =~ ^[1-9][0-9]*$ ]] \
  || preflight_fail "transient canary has no live main process"
[[ "$(stat -c '%u:%g' -- "/proc/$PREFLIGHT_MAIN_PID")" == "$SERVICE_UID:$SERVICE_GID" ]] \
  || preflight_fail "transient canary process credentials do not match the service account"
PREFLIGHT_EXEC_PATH="$(systemctl show "$PREFLIGHT_UNIT" --property=ExecStart --value \
  | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')"
[[ "$PREFLIGHT_EXEC_PATH" == "$PREFLIGHT_RELEASE_PYTHON" ]] \
  || preflight_fail "transient canary effective executable is not the candidate runtime"
PREFLIGHT_EXPECTED_ARGV="$PREFLIGHT_RELEASE_PYTHON -I -B -u -m uvicorn protocol_studio.app:app --host 127.0.0.1 --port $PREFLIGHT_PORT --proxy-headers --forwarded-allow-ips 127.0.0.1"
[[ "$(process_exec_argv "$PREFLIGHT_MAIN_PID")" == "$PREFLIGHT_EXPECTED_ARGV" ]] \
  || preflight_fail "transient canary process argv is not the candidate command"
[[ "$(readlink -- "/proc/$PREFLIGHT_MAIN_PID/cwd")" == "$RELEASE_DIR" ]] \
  || preflight_fail "transient canary process cwd is not the final release path"

# EnvironmentFiles proves the manager-side configuration; /proc proves the
# candidate process received the production paths and canonical environment.
# The process argv independently binds Python's effective -B/-u behavior because
# isolated mode ignores PYTHON* environment controls.  Together with the bind
# inode checks below this demonstrates that production paths resolve only to the
# private canary state.
if ! "$PYTHON_BIN" -I - "$PREFLIGHT_MAIN_PID" "$RUNS_DIR" "$SECURITY_DB" <<'PY'
from pathlib import Path
import sys

raw = Path(f"/proc/{sys.argv[1]}/environ").read_bytes()
parts = raw.split(b"\0")
if not parts or parts[-1] != b"":
    raise SystemExit(1)
environment: dict[str, str] = {}
for part in parts[:-1]:
    if not part or b"=" not in part:
        raise SystemExit(1)
    key_bytes, value_bytes = part.split(b"=", 1)
    key = key_bytes.decode("ascii")
    if key in environment:
        raise SystemExit(1)
    environment[key] = value_bytes.decode("utf-8")

expected_runs = sys.argv[2]
expected_database = sys.argv[3]
if environment.get("PROTOCOL_STUDIO_RUNS_ROOT") != expected_runs:
    raise SystemExit(1)
if environment.get("MCGS_FULL_CHAIN_RUNS_ROOT", expected_runs) != expected_runs:
    raise SystemExit(1)
if environment.get("PROTOCOL_STUDIO_SECURITY_DB") != expected_database:
    raise SystemExit(1)
if environment.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit(1)
if environment.get("PYTHONUNBUFFERED") != "1":
    raise SystemExit(1)
safe_python = {"PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"}
for key in environment:
    if key in safe_python:
        continue
    if key in {
        "BASHOPTS", "BASH_ENV", "CDPATH", "ENV", "GCONV_PATH",
        "GLIBC_TUNABLES", "GLOBIGNORE", "LOCPATH", "OPENSSL_CONF",
        "OPENSSL_CONF_INCLUDE", "OPENSSL_ENGINES", "OPENSSL_MODULES", "PATH",
        "PYTHONHOME", "PYTHONINSPECT", "PYTHONPATH", "PYTHONSTARTUP", "SHELLOPTS",
        "FORWARDED_ALLOW_IPS", "WEB_CONCURRENCY", "_UVICORN_COMPLETE",
    } or key.startswith((
        "BASH_FUNC_", "LD_", "DYLD_", "PYTHON", "UVICORN_", "_UVICORN_",
    )):
        raise SystemExit(1)
PY
then
  preflight_fail "transient canary process environment does not match the validated production contract"
fi
process_environment_matches "$PREFLIGHT_MAIN_PID" \
  || preflight_fail "transient canary process environment failed the reusable production contract"

PREFLIGHT_VISIBLE_SHARED="/proc/$PREFLIGHT_MAIN_PID/root$SHARED_DIR"
PREFLIGHT_VISIBLE_RELEASE="/proc/$PREFLIGHT_MAIN_PID/root$RELEASE_DIR"
[[ -d "$PREFLIGHT_VISIBLE_SHARED" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_SHARED")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED")" != "$(stat -Lc '%d:%i' -- "$SHARED_DIR")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/security.sqlite3")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_DB")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/security.sqlite3")" != "$(stat -Lc '%d:%i' -- "$SECURITY_DB")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/runs")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_RUNS")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/runs")" != "$(stat -Lc '%d:%i' -- "$RUNS_DIR")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/live-security.sqlite3")" == "$(stat -Lc '%d:%i' -- "$PREFLIGHT_DB")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED/live-security.sqlite3")" != "$(stat -Lc '%d:%i' -- "$SECURITY_DB")" ]] \
  || preflight_fail "transient canary is not bound to the private shared database and runs tree"
[[ -d "$PREFLIGHT_VISIBLE_RELEASE" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_RELEASE")" == "$(stat -Lc '%d:%i' -- "$CANDIDATE_DIR")" \
  && "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_RELEASE/.venv/bin/python")" == "$(stat -Lc '%d:%i' -- "$CANDIDATE_PYTHON")" ]] \
  || preflight_fail "transient canary final release path is not bound to the incoming candidate"

strict_login_redirect "http://127.0.0.1:$PREFLIGHT_PORT/" "$CANARY_HEALTH_MAX_SECONDS" "$PUBLIC_HOST" \
  || preflight_fail "isolated transient canary did not enforce the login redirect"
{
  printf 'status=PASS\nunit=%s\ncandidate_source=%s\nfinal_path=%s\nmain_pid=%s\n' \
    "$PREFLIGHT_UNIT" "$CANDIDATE_DIR" "$RELEASE_DIR" "$PREFLIGHT_MAIN_PID"
  printf 'exec_path=%s\nargv=%s\ncwd=%s\nenvironment_contract=verified\n' \
    "$PREFLIGHT_EXEC_PATH" "$PREFLIGHT_EXPECTED_ARGV" "$RELEASE_DIR"
  printf 'private_shared_identity=%s\nvisible_shared_identity=%s\n' \
    "$(stat -Lc '%d:%i' -- "$PREFLIGHT_SHARED")" \
    "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_SHARED")"
  printf 'candidate_identity=%s\nvisible_release_identity=%s\n' \
    "$(stat -Lc '%d:%i' -- "$CANDIDATE_DIR")" \
    "$(stat -Lc '%d:%i' -- "$PREFLIGHT_VISIBLE_RELEASE")"
  systemctl show "$PREFLIGHT_UNIT" \
    --property=Type,User,Group,WorkingDirectory,ExecStartPre,ExecStart,EnvironmentFiles,UnsetEnvironment \
    --property=UMask,NoNewPrivileges,CapabilityBoundingSet,AmbientCapabilities \
    --property=PrivateTmp,PrivateDevices,ProtectSystem,ProtectHome \
    --property=ProtectControlGroups,ProtectKernelModules,ProtectKernelTunables \
    --property=ProtectKernelLogs,ProtectClock,RestrictSUIDSGID \
    --property=RestrictAddressFamilies,RestrictNamespaces,LockPersonality \
    --property=BindReadOnlyPaths,BindPaths,ReadWritePaths
} >"$PREFLIGHT_LOG"
chmod 0600 "$PREFLIGHT_LOG"
stop_preflight \
  || preflight_fail "transient canary could not be stopped cleanly"
[[ ! -e "/proc/$PREFLIGHT_MAIN_PID" ]] \
  || preflight_fail "transient canary process still exists after stop"
CANDIDATE_RUNTIME_FINGERPRINT_JSON="$(runtime_fingerprint \
  "$CANDIDATE_DIR/.venv" "$CANDIDATE_PYTHON" \
  "$CANDIDATE_DIR/requirements.production.lock.txt" "$CANDIDATE_DIR")"
cleanup_preflight --keep-candidate
[[ ! -e "$PREFLIGHT_ROOT" && ! -L "$PREFLIGHT_ROOT" ]] \
  || fail "transient canary private state cleanup failed"
[[ ! -e "$RELEASE_DIR" && ! -L "$RELEASE_DIR" ]] \
  || fail "transient canary final-path mount cleanup failed"

if [[ "$MODE" == "prepare" ]]; then
  CANDIDATE_CLEANUP_ACTIVE="true"
  RELEASE_PROMOTED="false"
  trap cleanup_candidate EXIT
  sync -f "$CANDIDATE_DIR" || fail "cannot persist the prepare-only dry-run candidate"
  case "$INCOMING_DIR" in
    "$RELEASES_DIR"/.incoming-*) rm -rf -- "$INCOMING_DIR" ;;
    *) fail "refusing to clean an unexpected prepare-only incoming path" ;;
  esac
  fsync_directory "$RELEASES_DIR" \
    || fail "prepare-only candidate cleanup durability is uncertain"
  CANDIDATE_CLEANUP_ACTIVE="false"
  trap - EXIT
  printf 'PREPARE-ONLY PASS: %s (ephemeral dry-run)\n' "$RELEASE_ID"
  printf 'Archive, offline dependencies, permissions and transient systemd canary passed. current, systemd, service and shared product data were unchanged; only root-only validation logs and deployment locks were retained.\n'
  exit 0
fi

[[ -L "$CURRENT_LINK" ]] || fail "current must be an existing symbolic link"
assert_standard_enabled_topology "$SERVICE_USER" \
  || fail "existing service enablement is not the unique standard multi-user topology"
systemctl is-active --quiet "$SERVICE" || fail "existing systemd service is not active"
[[ "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" ]] \
  || fail "systemd has unapplied unit changes; review and daemon-reload before deploying"
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
PREVIOUS_TARGET="$(readlink -f -- "$CURRENT_LINK")"
case "$PREVIOUS_TARGET" in
  "$RELEASES_DIR"/*) ;;
  *) fail "current target is outside the releases directory" ;;
esac
[[ -d "$PREVIOUS_TARGET" ]] || fail "current target does not exist"
PREVIOUS_ID="$(basename -- "$PREVIOUS_TARGET")"

FRAGMENT_PATH="$(systemctl show "$SERVICE" --property=FragmentPath --value)"
[[ "$FRAGMENT_PATH" == "$SYSTEMD_UNIT_FILE" ]] \
  || fail "active service fragment is not the expected administrator unit"
assert_secure_systemd_directory "/etc/systemd/system" "systemd administrator unit directory"
assert_secure_systemd_file "$FRAGMENT_PATH" "systemd base unit"
if [[ -e "$MANAGED_DROPIN_DIR" || -L "$MANAGED_DROPIN_DIR" ]]; then
  assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
fi
DROPIN_PATHS_BEFORE="$(systemctl show "$SERVICE" --property=DropInPaths --value)"
if [[ -n "$DROPIN_PATHS_BEFORE" && "$DROPIN_PATHS_BEFORE" != "$MANAGED_DROPIN" ]]; then
  fail "unreviewed systemd drop-ins are active; refusing to change the runtime"
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

DROPIN_CANDIDATE="$LOG_DIR/.runtime-dropin-$RELEASE_ID-$$"
DROPIN_TEMP=""
canonical_managed_dropin_content >"$DROPIN_CANDIDATE"
chmod 0644 "$DROPIN_CANDIDATE"

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

PREVIOUS_MAIN_PID="$(systemctl show "$SERVICE" --property=MainPID --value)"
[[ "$PREVIOUS_MAIN_PID" =~ ^[1-9][0-9]*$ ]] \
  || fail "current known-good service has no live main process"
[[ "$(process_exec_argv "$PREVIOUS_MAIN_PID")" == "$PREVIOUS_EXEC_ARGV" ]] \
  || fail "current live process argv does not match the effective systemd baseline"
[[ "$(process_working_directory "$PREVIOUS_MAIN_PID")" == "$PREVIOUS_TARGET" ]] \
  || fail "current live process working directory does not match the current release"

BACKUP_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
UNIT_BACKUP="$BACKUP_DIR/$SERVICE-$BACKUP_STAMP-before-$RELEASE_ID"
install -m 0600 "$FRAGMENT_PATH" "$UNIT_BACKUP"
assert_trusted_root_file_path "$UNIT_BACKUP" "systemd base-unit backup"
fsync_file "$UNIT_BACKUP"
UNIT_FRAGMENT_SHA256="$(sha256sum "$UNIT_BACKUP" | awk '{print $1}')"
[[ "$(sha256sum "$FRAGMENT_PATH" | awk '{print $1}')" == "$UNIT_FRAGMENT_SHA256" ]] \
  || fail "systemd base unit changed while its rollback backup was created"
DROPIN_BACKUP=""
DROPIN_SHA256=""
if [[ "$PREVIOUS_DROPIN_EXISTED" == "true" ]]; then
  DROPIN_BACKUP="$BACKUP_DIR/$SERVICE-runtime-$BACKUP_STAMP-before-$RELEASE_ID.conf"
  install -m 0600 "$MANAGED_DROPIN" "$DROPIN_BACKUP"
  assert_trusted_root_file_path "$DROPIN_BACKUP" "managed systemd drop-in backup"
  fsync_file "$DROPIN_BACKUP"
  DROPIN_SHA256="$(sha256sum "$DROPIN_BACKUP" | awk '{print $1}')"
  [[ "$(sha256sum "$MANAGED_DROPIN" | awk '{print $1}')" == "$DROPIN_SHA256" ]] \
    || fail "managed runtime drop-in changed while its rollback backup was created"
fi
fsync_directory "$BACKUP_DIR"

# Register the only permitted no-.venv rollback target and freeze the legacy
# shared runtime fingerprint. This is created once and compared byte-for-byte
# by the explicit rollback script.
LEGACY_BASELINE_RECORD="$DEPLOYMENT_DIR/legacy-baseline-$LEGACY_RELEASE_ID.json"
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
  [[ ! -e "$PREVIOUS_TARGET/.venv" ]] \
    || fail "registered legacy baseline unexpectedly contains a release-local venv"
  [[ "$DROPIN_PATHS_BEFORE" == "" ]] \
    || fail "legacy baseline must not have an active runtime drop-in"
  [[ "$PREVIOUS_EXEC_PATH" == "$APP_ROOT/.venv/bin/python" ]] \
    || fail "legacy baseline is not using the registered shared runtime"
  [[ "$PREVIOUS_EXEC_ARGV" == "$LEGACY_EXEC_ARGV_SPACE" \
    || "$PREVIOUS_EXEC_ARGV" == "$LEGACY_EXEC_ARGV_EQUALS" ]] \
    || fail "legacy baseline effective command line is unexpected"
  [[ "$PREVIOUS_WORKING_DIRECTORY" == "$CURRENT_LINK" ]] \
    || fail "legacy baseline working directory is not current"
  PREVIOUS_RUNTIME_MODE="legacy-shared-venv"
elif [[ -x "$PREVIOUS_TARGET/.venv/bin/python" ]]; then
  [[ "$DROPIN_PATHS_BEFORE" == "$MANAGED_DROPIN" ]] \
    || fail "release-local current target is missing the managed runtime drop-in"
  [[ "$PREVIOUS_EXEC_PATH" == "$CURRENT_LINK/.venv/bin/python" ]] \
    || fail "release-local current target has an unexpected effective executable"
  [[ "$PREVIOUS_EXEC_ARGV" == "$MODERN_EXEC_ARGV" ]] \
    || fail "release-local current target has an unexpected effective command line"
  PREVIOUS_DEPLOYMENT_RECORD="$DEPLOYMENT_DIR/$PREVIOUS_ID.json"
  assert_trusted_record_file "$PREVIOUS_DEPLOYMENT_RECORD" \
    "current release-local passed deployment record"
  mapfile -t PREVIOUS_RECORD_FIELDS < <("$PYTHON_BIN" -I - \
    "$PREVIOUS_DEPLOYMENT_RECORD" "$PREVIOUS_ID" "$PUBLIC_ORIGIN" \
    "$PUBLIC_HOST" "$MODERN_EXEC_START_PRE_ARGVS_JSON" \
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
    raise SystemExit("current release deployment record is not a JSON object")
schema = record.get("schema_version")
if type(schema) is not int or schema not in {2, 3, 4, 5}:
    raise SystemExit("current release deployment record schema is invalid")
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
    raise SystemExit("current release deployment record is not a passed release-local runtime")
print(record["version"])
print(record["archive_sha256"])
print(record["release_manifest_sha256"])
print(json.dumps(record["runtime_fingerprint"], ensure_ascii=False, sort_keys=True, separators=(",", ":")))
print(record["runtime_baseline_sha256"])
print(record["runtime_fingerprint_sha256"])
print(record["runtime_guard_helper_sha256"])
PY
  )
  [[ "${#PREVIOUS_RECORD_FIELDS[@]}" -ge 1 ]] \
    || fail "current passed deployment record schema is unreadable"
  PREVIOUS_RECORD_SCHEMA="${PREVIOUS_RECORD_FIELDS[0]}"
  require_activatable_passed_record_schema "$PREVIOUS_RECORD_SCHEMA"
  [[ "${#PREVIOUS_RECORD_FIELDS[@]}" == "8" ]] \
    || fail "current passed deployment record fields are incomplete"
  PREVIOUS_EXPECTED_VERSION="${PREVIOUS_RECORD_FIELDS[1]}"
  PREVIOUS_ARCHIVE_SHA256="${PREVIOUS_RECORD_FIELDS[2]}"
  PREVIOUS_MANIFEST_SHA256="${PREVIOUS_RECORD_FIELDS[3]}"
  PREVIOUS_RUNTIME_FINGERPRINT_JSON="${PREVIOUS_RECORD_FIELDS[4]}"
  PREVIOUS_RUNTIME_BASELINE_SHA256="${PREVIOUS_RECORD_FIELDS[5]}"
  PREVIOUS_RUNTIME_FINGERPRINT_SHA256="${PREVIOUS_RECORD_FIELDS[6]}"
  PREVIOUS_RUNTIME_GUARD_HELPER_SHA256="${PREVIOUS_RECORD_FIELDS[7]}"
  cmp -s "$DROPIN_CANDIDATE" "$MANAGED_DROPIN" \
    || fail "schema 5 managed systemd drop-in has unrecognized content"
  [[ "$(runtime_fingerprint "$PREVIOUS_TARGET/.venv" \
    "$PREVIOUS_TARGET/.venv/bin/python" \
    "$PREVIOUS_TARGET/requirements.production.lock.txt" "$PREVIOUS_TARGET")" == "$PREVIOUS_RUNTIME_FINGERPRINT_JSON" ]] \
    || fail "current release-local runtime fingerprint drifted from its passed record"
  "$PYTHON_BIN" -I "$SCRIPT_DIR/verify_installed_release.py" \
    "$PREVIOUS_TARGET" --expected-version "$PREVIOUS_EXPECTED_VERSION"
  assert_release_tree_security "$PREVIOUS_TARGET" "$SERVICE_USER"
  [[ "$(sha256sum "$PREVIOUS_TARGET/release-manifest.json" | awk '{print $1}')" \
    == "$PREVIOUS_MANIFEST_SHA256" ]] \
    || fail "current release manifest digest drifted from its passed record"
  [[ "$(sha256sum "$RUNTIME_BASELINE_DIR/$PREVIOUS_ID.json" | awk '{print $1}')" \
    == "$PREVIOUS_RUNTIME_BASELINE_SHA256" \
    && "$(printf '%s' "$PREVIOUS_RUNTIME_FINGERPRINT_JSON" | sha256sum | awk '{print $1}')" \
    == "$PREVIOUS_RUNTIME_FINGERPRINT_SHA256" \
    && "$(sha256sum "$RUNTIME_GUARD_HELPER" | awk '{print $1}')" \
    == "$PREVIOUS_RUNTIME_GUARD_HELPER_SHA256" ]] \
    || fail "current schema 5 record disagrees with runtime baseline, fingerprint, or helper bytes"
  PREVIOUS_RUNTIME_BASELINE_VERIFICATION_JSON="$(verify_release_runtime_baseline \
    "$PREVIOUS_ID" "$PREVIOUS_TARGET" "$PREVIOUS_MANIFEST_SHA256")" \
    || fail "current release external runtime baseline verification failed"
  runtime_baseline_verification_matches_record \
    "$PREVIOUS_RUNTIME_BASELINE_VERIFICATION_JSON" "$PREVIOUS_ID" \
    "$PREVIOUS_EXPECTED_VERSION" "$PREVIOUS_MANIFEST_SHA256" \
    "$PREVIOUS_RUNTIME_BASELINE_SHA256" "$PREVIOUS_RUNTIME_FINGERPRINT_SHA256" \
    "$PREVIOUS_RUNTIME_GUARD_HELPER_SHA256" \
    || fail "current release runtime baseline evidence disagrees with its schema 5 passed record"
  PREVIOUS_RUNTIME_MODE="release-local-venv"
else
  fail "current runtime is neither the registered legacy baseline nor a passed release-local deployment"
fi

# A rollback target is only known-good if production is healthy before the
# switch begins. Modern releases must prove that both local and public routing
# reach the recorded manifest. The registered legacy baseline predates this
# header, so its checks are deliberately availability-only and are not identity
# evidence.
if [[ "$PREVIOUS_RUNTIME_MODE" == "legacy-shared-venv" ]]; then
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

if [[ "$PREVIOUS_RUNTIME_MODE" == "legacy-shared-venv" ]]; then
  LEGACY_SHARED_PYTHON="$APP_ROOT/.venv/bin/python"
  [[ -x "$LEGACY_SHARED_PYTHON" ]] || fail "legacy shared runtime is missing"
  LEGACY_RELEASE_SHA256="$("$PYTHON_BIN" -I - "$PREVIOUS_TARGET" <<'PY'
from __future__ import annotations
import hashlib
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
digest = hashlib.sha256()
for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
    relative = path.relative_to(root).as_posix().encode("utf-8")
    metadata = path.lstat()
    prefix = f"{stat.S_IMODE(metadata.st_mode):04o}:{metadata.st_uid}:{metadata.st_gid}".encode()
    if path.is_symlink():
        digest.update(b"L\0" + relative + b"\0" + prefix + b"\0" + os.readlink(path).encode("utf-8") + b"\0")
    elif path.is_dir():
        digest.update(b"D\0" + relative + b"\0" + prefix + b"\0")
    elif path.is_file():
        digest.update(b"F\0" + relative + b"\0" + prefix + b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    else:
        raise SystemExit(f"unsupported legacy release entry: {relative!r}")
print(digest.hexdigest())
PY
)"
  LEGACY_RUNTIME_FINGERPRINT_JSON="$(runtime_fingerprint \
    "$APP_ROOT/.venv" "$LEGACY_SHARED_PYTHON")"
  if [[ -f "$LEGACY_BASELINE_RECORD" ]]; then
    [[ ! -L "$LEGACY_BASELINE_RECORD" \
      && "$(stat -c '%u:%g:%a' -- "$LEGACY_BASELINE_RECORD")" == "0:0:600" ]] \
      || fail "legacy baseline record ownership or mode is invalid"
    assert_trusted_root_file_path "$LEGACY_BASELINE_RECORD" "legacy baseline record"
    "$PYTHON_BIN" -I - "$LEGACY_BASELINE_RECORD" "$PREVIOUS_ID" \
      "$FRAGMENT_PATH" "$UNIT_FRAGMENT_SHA256" "$LEGACY_RELEASE_SHA256" \
      "$LEGACY_RUNTIME_FINGERPRINT_JSON" <<'PY'
from __future__ import annotations
import json
import sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "schema_version": 2,
    "release_id": sys.argv[2],
    "fragment_path": sys.argv[3],
    "fragment_sha256": sys.argv[4],
    "dropin_paths": [],
    "legacy_release_sha256": sys.argv[5],
    "runtime_fingerprint": json.loads(sys.argv[6]),
}
if record != expected:
    raise SystemExit("legacy baseline record drifted from the active production baseline")
PY
  else
    [[ ! -e "$LEGACY_BASELINE_RECORD" && ! -L "$LEGACY_BASELINE_RECORD" ]] \
      || fail "legacy baseline record path is unsafe"
    LEGACY_BASELINE_RECORD_TEMP="$DEPLOYMENT_DIR/.legacy-baseline-$LEGACY_RELEASE_ID-$$.tmp"
    "$PYTHON_BIN" -I - "$LEGACY_BASELINE_RECORD_TEMP" "$PREVIOUS_ID" \
      "$FRAGMENT_PATH" "$UNIT_FRAGMENT_SHA256" "$LEGACY_RELEASE_SHA256" \
      "$LEGACY_RUNTIME_FINGERPRINT_JSON" <<'PY'
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
record = {
    "schema_version": 2,
    "release_id": sys.argv[2],
    "fragment_path": sys.argv[3],
    "fragment_sha256": sys.argv[4],
    "dropin_paths": [],
    "legacy_release_sha256": sys.argv[5],
    "runtime_fingerprint": json.loads(sys.argv[6]),
}
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
    chmod 0600 "$LEGACY_BASELINE_RECORD_TEMP"
    assert_trusted_root_file_path "$LEGACY_BASELINE_RECORD_TEMP" \
      "pending legacy baseline record"
    fsync_file "$LEGACY_BASELINE_RECORD_TEMP"
    mv -Tf -- "$LEGACY_BASELINE_RECORD_TEMP" "$LEGACY_BASELINE_RECORD"
    assert_trusted_root_file_path "$LEGACY_BASELINE_RECORD" "legacy baseline record"
    fsync_directory "$DEPLOYMENT_DIR"
  fi
fi

DATABASE_BACKUP="$BACKUP_DIR/security-$BACKUP_STAMP-before-$RELEASE_ID.sqlite3"
DATABASE_BACKUP_BASENAME="$(basename -- "$DATABASE_BACKUP")"
DATABASE_BACKUP_METADATA_JSON="$("$PYTHON_BIN" -I "$SCRIPT_DIR/sqlite_backup.py" \
  backup --source "$SECURITY_DB" --destination "$DATABASE_BACKUP" \
  --deadline-seconds "$SQLITE_BACKUP_DEADLINE_SECONDS")" \
  || fail "cannot create the pre-switch security database backup"
chown root:root "$DATABASE_BACKUP"
chmod 0600 "$DATABASE_BACKUP"
fsync_file "$DATABASE_BACKUP"
fsync_directory "$BACKUP_DIR"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "durable security database backup evidence is invalid"
RUNTIME_FINGERPRINT_JSON="$(runtime_fingerprint \
  "$CANDIDATE_DIR/.venv" "$CANDIDATE_PYTHON" \
  "$CANDIDATE_DIR/requirements.production.lock.txt" "$CANDIDATE_DIR")"

atomic_link() {
  local target="$1"
  local temporary="$APP_ROOT/.current-next-$$"
  [[ ! -e "$temporary" && ! -L "$temporary" ]] || return 1
  ln -s -- "$target" "$temporary" || return 1
  mv -Tf -- "$temporary" "$CURRENT_LINK" || return 1
  fsync_directory "$APP_ROOT"
}

restore_previous_dropin() {
  if [[ "$PREVIOUS_DROPIN_EXISTED" == "true" ]]; then
    install -d -m 0755 "$MANAGED_DROPIN_DIR" || return 1
    local temporary="$MANAGED_DROPIN_DIR/.restore-runtime-$$"
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

ROLLBACK_RUNNING="false"
TRANSACTION_ACTIVE="false"
TRANSACTION_COMMITTED="false"
rollback_to_previous() {
  local reason="$1"
  local original_pid
  local active_state
  local sub_state
  local main_pid
  local process_gone="true"
  local marker_retained="false"
  local fail_closed="true"
  if [[ "$ROLLBACK_RUNNING" == "true" ]]; then
    printf 'CRITICAL: FAIL-CLOSED NOT CONFIRMED (recursive transaction failure)\n' >&2
    printf 'DO NOT REBOOT; retain the active transaction marker for audited recovery.\n' >&2
    exit 1
  fi
  trap '' INT TERM HUP
  ROLLBACK_RUNNING="true"
  # This compensation handler owns the terminal path after it starts.  Explicit
  # `command || rollback_to_previous` calls must not re-enter it via EXIT.
  trap - EXIT
  set +e
  printf 'SWITCH FAILED: %s\n' "$reason" >&2
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
  cleanup_candidate >/dev/null 2>&1 || true
  exit 1
}

transaction_exit_guard() {
  local status="$?"
  if [[ "$TRANSACTION_ACTIVE" == "true" ]]; then
    rollback_to_previous "deployment transaction exited unexpectedly with status $status"
  else
    cleanup_candidate >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap transaction_exit_guard EXIT
trap 'exit 130' INT TERM HUP

# Keep the fully installed and canary-tested payload under its incoming name
# throughout the final production-state recheck.  This avoids an orphan release
# during dependency installation, canary execution, rollback-baseline
# verification, database backup and public health checks.  Promotion happens
# only after the durable transaction marker payload has been prepared.
sync -f "$CANDIDATE_DIR" \
  || fail "cannot make the prepared release durable"
sync -f "$CONTROL_DIR" \
  || fail "cannot make rollback evidence durable"
sync -f "$APP_ROOT" \
  || fail "cannot make the release-selection filesystem durable"
"$PYTHON_BIN" -I "$SCRIPT_DIR/verify_installed_release.py" \
  "$CANDIDATE_DIR" --expected-version "$EXPECTED_VERSION"
runuser -u "$SERVICE_USER" -- "$TEST_BIN" -r "$CANDIDATE_DIR/protocol_studio/app.py" \
  || fail "service user lost read access to the durable prepared release"
runuser -u "$SERVICE_USER" -- "$TEST_BIN" -x "$CANDIDATE_PYTHON" \
  || fail "service user lost execute access to the durable prepared runtime"
assert_release_tree_security "$CANDIDATE_DIR" "$SERVICE_USER"
[[ "$(runtime_fingerprint "$CANDIDATE_DIR/.venv" "$CANDIDATE_PYTHON" \
  "$CANDIDATE_DIR/requirements.production.lock.txt" "$CANDIDATE_DIR")" == "$RUNTIME_FINGERPRINT_JSON" ]] \
  || fail "prepared release runtime fingerprint changed after durability sync"

# Freeze the already-reviewed production state immediately before the durable
# marker is created. Long-running dependency installation and canary work must
# not hide a concurrent unit, drop-in, symlink or effective-runtime change.
systemctl is-enabled --quiet "$SERVICE" \
  || fail "systemd service stopped being enabled before the deployment transaction"
systemctl is-active --quiet "$SERVICE" \
  || fail "systemd service stopped being active before the deployment transaction"
[[ "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" ]] \
  || fail "systemd configuration changed before the deployment transaction"
[[ "$(readlink -f -- "$CURRENT_LINK")" == "$PREVIOUS_TARGET" ]] \
  || fail "current release changed before the deployment transaction"
[[ "$(sha256sum "$FRAGMENT_PATH" | awk '{print $1}')" == "$UNIT_FRAGMENT_SHA256" ]] \
  || fail "systemd base unit changed before the deployment transaction"
assert_trusted_root_file_path "$UNIT_BACKUP" "durable systemd base-unit backup"
[[ -f "$UNIT_BACKUP" && ! -L "$UNIT_BACKUP" \
  && "$(stat -c '%u:%g:%a' -- "$UNIT_BACKUP")" == "0:0:600" \
  && "$(sha256sum "$UNIT_BACKUP" | awk '{print $1}')" == "$UNIT_FRAGMENT_SHA256" ]] \
  || fail "durable systemd base-unit backup changed before the deployment transaction"
assert_secure_systemd_directory "/etc/systemd/system" "systemd administrator unit directory"
assert_secure_systemd_file "$FRAGMENT_PATH" "systemd base unit"
if [[ -e "$MANAGED_DROPIN_DIR" || -L "$MANAGED_DROPIN_DIR" ]]; then
  assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
fi
DROPIN_PATHS_RECHECK="$(systemctl show "$SERVICE" --property=DropInPaths --value)"
[[ "$DROPIN_PATHS_RECHECK" == "$DROPIN_PATHS_BEFORE" ]] \
  || fail "effective systemd drop-in set changed before the deployment transaction"
DISK_DROPIN_PATHS_RECHECK=""
if [[ -d "$MANAGED_DROPIN_DIR" ]]; then
  shopt -s nullglob
  DISK_DROPIN_FILES_RECHECK=("$MANAGED_DROPIN_DIR"/*.conf)
  shopt -u nullglob
  for dropin_file in "${DISK_DROPIN_FILES_RECHECK[@]}"; do
    [[ -f "$dropin_file" && ! -L "$dropin_file" ]] \
      || fail "a systemd drop-in changed into a non-regular file before the transaction"
  done
  if ((${#DISK_DROPIN_FILES_RECHECK[@]} > 0)); then
    DISK_DROPIN_PATHS_RECHECK="${DISK_DROPIN_FILES_RECHECK[*]}"
  fi
fi
[[ "$DISK_DROPIN_PATHS_RECHECK" == "$DROPIN_PATHS_BEFORE" ]] \
  || fail "systemd manager and disk drop-in views changed before the transaction"
if [[ "$PREVIOUS_DROPIN_EXISTED" == "true" ]]; then
  assert_secure_systemd_file "$MANAGED_DROPIN" "managed systemd runtime drop-in"
  [[ "$(sha256sum "$MANAGED_DROPIN" | awk '{print $1}')" == "$DROPIN_SHA256" ]] \
    || fail "managed runtime drop-in changed before the deployment transaction"
  cmp -s "$DROPIN_CANDIDATE" "$MANAGED_DROPIN" \
    || fail "managed runtime drop-in content changed before the deployment transaction"
  assert_trusted_root_file_path "$DROPIN_BACKUP" \
    "durable managed systemd drop-in backup"
  [[ -f "$DROPIN_BACKUP" && ! -L "$DROPIN_BACKUP" \
    && "$(stat -c '%u:%g:%a' -- "$DROPIN_BACKUP")" == "0:0:600" \
    && "$(sha256sum "$DROPIN_BACKUP" | awk '{print $1}')" == "$DROPIN_SHA256" ]] \
    || fail "durable managed runtime drop-in backup changed before the deployment transaction"
elif [[ -e "$MANAGED_DROPIN" || -L "$MANAGED_DROPIN" ]]; then
  fail "an unexpected managed runtime drop-in appeared before the transaction"
fi
[[ "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$PREVIOUS_EXEC_PATH" ]] \
  || fail "effective systemd executable changed before the deployment transaction"
[[ "$(effective_exec_argv)" == "$PREVIOUS_EXEC_ARGV" ]] \
  || fail "effective systemd command line changed before the deployment transaction"
[[ "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$PREVIOUS_WORKING_DIRECTORY" ]] \
  || fail "effective systemd working directory changed before the deployment transaction"
[[ "$(systemctl show "$SERVICE" --property=User --value)" == "$PREVIOUS_SERVICE_USER" ]] \
  || fail "effective systemd service user changed before the deployment transaction"
[[ "$(systemctl show "$SERVICE" --property=Group --value)" == "$PREVIOUS_SERVICE_GROUP" ]] \
  || fail "effective systemd service group changed before the deployment transaction"
[[ "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" ]] \
  || fail "effective systemd environment files changed before the deployment transaction"
[[ "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" ]] \
  || fail "effective systemd writable paths changed before the deployment transaction"
[[ "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" ]] \
  || fail "effective systemd umask changed before the deployment transaction"
[[ "$(systemctl show "$SERVICE" --property=MainPID --value)" == "$PREVIOUS_MAIN_PID" ]] \
  || fail "systemd main process changed before the deployment transaction"
[[ "$(process_exec_argv "$PREVIOUS_MAIN_PID")" == "$PREVIOUS_EXEC_ARGV" ]] \
  || fail "live process argv changed before the deployment transaction"
[[ "$(process_working_directory "$PREVIOUS_MAIN_PID")" == "$PREVIOUS_TARGET" ]] \
  || fail "live process working directory changed before the deployment transaction"
runtime_health "$PREVIOUS_RUNTIME_MODE" "$PREVIOUS_MANIFEST_SHA256" \
  "http://127.0.0.1:$LOCAL_PORT/api/health" 8 "$PUBLIC_HOST" \
  || fail "current local production health or release identity changed before the deployment transaction"
runtime_health "$PREVIOUS_RUNTIME_MODE" "$PREVIOUS_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || fail "current public production health or release identity changed before the deployment transaction"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || fail "current public login redirect changed before the deployment transaction"
[[ "$(sha256sum "$ENV_FILE" | awk '{print $1}')" == "$ENV_FILE_SHA256" ]] \
  || fail "production environment file changed after canary validation"
if [[ "$PREVIOUS_RUNTIME_MODE" == "legacy-shared-venv" ]]; then
  [[ "$(runtime_fingerprint "$APP_ROOT/.venv" "$LEGACY_SHARED_PYTHON")" \
    == "$LEGACY_RUNTIME_FINGERPRINT_JSON" ]] \
    || fail "legacy shared runtime fingerprint changed before the deployment transaction"
else
  [[ "$(runtime_fingerprint "$PREVIOUS_TARGET/.venv" \
    "$PREVIOUS_TARGET/.venv/bin/python" \
    "$PREVIOUS_TARGET/requirements.production.lock.txt" "$PREVIOUS_TARGET")" \
    == "$PREVIOUS_RUNTIME_FINGERPRINT_JSON" ]] \
    || fail "current release-local runtime fingerprint changed before deployment"
fi
fsync_systemd_enablement_state \
  || fail "cannot preflight persistence of systemd enablement directories"
"$PYTHON_BIN" -I "$SCRIPT_DIR/verify_installed_release.py" \
  "$CANDIDATE_DIR" --expected-version "$EXPECTED_VERSION"
assert_release_tree_security "$CANDIDATE_DIR" "$SERVICE_USER"
[[ "$(runtime_fingerprint "$CANDIDATE_DIR/.venv" "$CANDIDATE_PYTHON" \
  "$CANDIDATE_DIR/requirements.production.lock.txt" "$CANDIDATE_DIR")" == "$RUNTIME_FINGERPRINT_JSON" ]] \
  || fail "incoming release fingerprint changed immediately before transaction preparation"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "security database backup drifted before transaction preparation"
validate_production_environment \
  || fail "production environment failed the formal-switch gate"
"$PYTHON_BIN" -I - "$TRANSACTION_TEMP" "$RELEASE_ID" "$PREVIOUS_ID" \
  "$PREVIOUS_TARGET" "$FRAGMENT_PATH" "$UNIT_FRAGMENT_SHA256" \
  "$DROPIN_PATHS_BEFORE" "$DROPIN_SHA256" \
  "$(basename -- "$UNIT_BACKUP")" \
  "$(if [[ -n "$DROPIN_BACKUP" ]]; then basename -- "$DROPIN_BACKUP"; fi)" \
  "$PREVIOUS_EXEC_PATH" "$PREVIOUS_EXEC_ARGV" "$PREVIOUS_WORKING_DIRECTORY" \
  "$PREVIOUS_SERVICE_USER" "$PREVIOUS_SERVICE_GROUP" \
  "$PREVIOUS_ENVIRONMENT_FILES" "$PREVIOUS_READ_WRITE_PATHS" \
  "$PREVIOUS_UMASK" "$ENV_FILE_SHA256" \
  "$PUBLIC_ORIGIN" "$PUBLIC_HOST" "$DATABASE_BACKUP_METADATA_JSON" <<'PY'
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
record = {
    "schema_version": 3,
    "status": "switching",
    "release_id": sys.argv[2],
    "previous_release_id": sys.argv[3],
    "previous_target": sys.argv[4],
    "fragment_path": sys.argv[5],
    "fragment_sha256": sys.argv[6],
    "dropin_paths_before": [] if not sys.argv[7] else [sys.argv[7]],
    "managed_dropin_sha256_before": sys.argv[8] or None,
    "fragment_backup": sys.argv[9],
    "managed_dropin_backup": sys.argv[10] or None,
    "previous_exec_path": sys.argv[11],
    "previous_exec_argv": sys.argv[12],
    "previous_working_directory": sys.argv[13],
    "previous_service_user": sys.argv[14],
    "previous_service_group": sys.argv[15],
    "previous_environment_files": sys.argv[16],
    "previous_read_write_paths": sys.argv[17],
    "previous_umask": sys.argv[18],
    "environment_file_sha256": sys.argv[19],
    "public_origin": sys.argv[20],
    "public_host": sys.argv[21],
    "database_backup": json.loads(sys.argv[22]),
    "prepared_release_durable": True,
    "service_enabled_before_switch": True,
    "known_good_health_before_switch": True,
    "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
}
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

# Complete all expensive integrity work while the release still has its
# incoming name.  The baseline payload names the intended final path, while its
# fingerprint is relocated only when the interpreter itself is stored inside
# the candidate.  rename(2) preserves every hashed inode, byte, mode and owner.
install_runtime_guard_helper \
  || fail "cannot install or verify the immutable external runtime guard"
RUNTIME_GUARD_HELPER_SHA256="$(sha256sum "$RUNTIME_GUARD_HELPER" | awk '{print $1}')"
[[ "$RUNTIME_GUARD_HELPER_SHA256" =~ ^[0-9a-f]{64}$ ]] \
  || fail "installed runtime guard helper digest is invalid"
FINAL_RELEASE_MANIFEST_SHA256="$(sha256sum "$CANDIDATE_DIR/release-manifest.json" | awk '{print $1}')"
FINAL_RUNTIME_FINGERPRINT_JSON="$(relocate_runtime_fingerprint \
  "$RUNTIME_FINGERPRINT_JSON")" \
  || fail "cannot prepare the final-path runtime fingerprint"
create_runtime_baseline \
  "$FINAL_RUNTIME_FINGERPRINT_JSON" "$FINAL_RELEASE_MANIFEST_SHA256" \
  "$RUNTIME_GUARD_HELPER_SHA256" \
  || fail "cannot prepare the immutable external runtime baseline"

chmod 0600 "$TRANSACTION_TEMP"
fsync_file "$TRANSACTION_TEMP"
fsync_directory "$APP_ROOT"
mv -T -- "$CANDIDATE_DIR" "$RELEASE_DIR" \
  || fail "cannot atomically promote the canary-tested candidate release"
RELEASE_PROMOTED="true"
rmdir -- "$INCOMING_DIR" \
  || fail "cannot remove the empty incoming release parent after promotion"
fsync_directory "$RELEASES_DIR" \
  || fail "cannot persist the candidate release promotion"
CANDIDATE_DIR="$RELEASE_DIR"
CANDIDATE_PYTHON="$RELEASE_DIR/.venv/bin/python"
RELEASE_PYTHON="$CANDIDATE_PYTHON"
[[ -d "$RELEASE_DIR" && ! -L "$RELEASE_DIR" \
  && -x "$RELEASE_PYTHON" ]] \
  || fail "promoted release is not a durable executable candidate"
publish_runtime_baseline \
  || fail "cannot exclusively publish the immutable external runtime baseline"
RUNTIME_BASELINE_SHA256="$(sha256sum "$RUNTIME_BASELINE" | awk '{print $1}')"
# Promotion-to-marker now contains only directory-entry publication and fsync.
# A power loss can still leave a release-only or release+baseline orphan.  The
# exclusive names deliberately block retry until both are manually quarantined.
mv -Tf -- "$TRANSACTION_TEMP" "$TRANSACTION_FILE"
assert_trusted_root_file_path "$TRANSACTION_FILE" "active deployment transaction marker"
fsync_directory "$APP_ROOT"
if [[ "$(sha256sum "$ENV_FILE" | awk '{print $1}')" != "$ENV_FILE_SHA256" ]]; then
  fail "production environment changed after marker publication; marker retained and systemd untouched"
fi
if ! RUNTIME_BASELINE_VERIFICATION_JSON="$(verify_release_runtime_baseline \
  "$RELEASE_ID" "$RELEASE_DIR" "$FINAL_RELEASE_MANIFEST_SHA256")"; then
  fail "promoted release failed its baseline verification; marker retained and systemd untouched"
fi
TRANSACTION_ACTIVE="true"

# Disable automatic boot before stopping. A machine restart or abrupt script
# death must leave the service fail-closed until this transaction or the
# recovery script has restored one complete runtime configuration.
systemctl disable "$SERVICE" \
  || rollback_to_previous "cannot disable automatic service startup before the switch"
assert_service_persistently_disabled "$SERVICE_USER" \
  || rollback_to_previous "service remained enabled or retained a nonstandard enablement link before the switch"
fsync_systemd_enablement_state \
  || rollback_to_previous "cannot persist the disabled systemd enablement state"
assert_service_persistently_disabled "$SERVICE_USER" \
  || rollback_to_previous "disabled systemd state was not durable before guard installation"
install_transaction_runtime_guard "$SERVICE_USER" \
  || rollback_to_previous "cannot install and verify the bounded transaction runtime guard"
stop_service_and_verify \
  || rollback_to_previous "existing service did not reach inactive/dead state with MainPID zero"
atomic_link "$RELEASE_DIR" || rollback_to_previous "atomic current symlink replacement failed"
install -d -m 0755 "$MANAGED_DROPIN_DIR" \
  || rollback_to_previous "cannot create the managed systemd drop-in directory"
assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
DROPIN_TEMP="$MANAGED_DROPIN_DIR/.install-runtime-$$"
install -m 0644 "$DROPIN_CANDIDATE" "$DROPIN_TEMP" \
  || rollback_to_previous "cannot stage the managed systemd runtime drop-in"
fsync_file "$DROPIN_TEMP" \
  || rollback_to_previous "cannot persist the staged managed systemd runtime drop-in"
mv -Tf -- "$DROPIN_TEMP" "$MANAGED_DROPIN" \
  || rollback_to_previous "cannot atomically install the managed systemd runtime drop-in"
fsync_directory "$MANAGED_DROPIN_DIR" \
  || rollback_to_previous "cannot persist the managed systemd runtime drop-in rename"
systemctl daemon-reload || rollback_to_previous "systemd daemon-reload failed"
[[ "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" ]] \
  || rollback_to_previous "systemd still requires daemon-reload after the runtime change"
assert_transaction_runtime_guard_loaded \
  || rollback_to_previous "transaction runtime guard drifted after the runtime change"

TARGET_EXEC_PATH="$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')"
TARGET_EXEC_ARGV="$(effective_exec_argv)"
TARGET_EXEC_START_PRE_ARGVS_JSON="$(effective_exec_start_pre_argvs)"
TARGET_WORKING_DIRECTORY="$(systemctl show "$SERVICE" --property=WorkingDirectory --value)"
TARGET_SERVICE_USER="$(systemctl show "$SERVICE" --property=User --value)"
TARGET_SERVICE_GROUP="$(systemctl show "$SERVICE" --property=Group --value)"
TARGET_ENVIRONMENT_FILES="$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)"
TARGET_READ_WRITE_PATHS="$(systemctl show "$SERVICE" --property=ReadWritePaths --value)"
TARGET_UMASK="$(systemctl show "$SERVICE" --property=UMask --value)"
TARGET_DROPINS="$(systemctl show "$SERVICE" --property=DropInPaths --value)"
[[ "$TARGET_EXEC_PATH" == "$CURRENT_LINK/.venv/bin/python" ]] \
  || rollback_to_previous "effective systemd executable is not the release-local runtime"
[[ "$TARGET_EXEC_ARGV" == "$MODERN_EXEC_ARGV" ]] \
  || rollback_to_previous "effective systemd command line is not the release-local runtime"
[[ "$TARGET_EXEC_START_PRE_ARGVS_JSON" == "$MODERN_EXEC_START_PRE_ARGVS_JSON" ]] \
  || rollback_to_previous "effective systemd ExecStartPre chain is not the ordered integrity and environment gate"
effective_unset_environment_matches \
  || rollback_to_previous "effective systemd environment sanitization is not the managed release contract"
effective_environment_matches \
  || rollback_to_previous "effective systemd explicit environment is not the managed release contract"
effective_restart_limit_matches \
  || rollback_to_previous "effective systemd restart limiter is not the bounded integrity-failure contract"
[[ "$TARGET_WORKING_DIRECTORY" == "$CURRENT_LINK" ]] \
  || rollback_to_previous "effective systemd working directory is not current"
[[ "$TARGET_SERVICE_USER" == "$SERVICE_USER" && "$TARGET_SERVICE_USER" != "root" ]] \
  || rollback_to_previous "effective systemd service user changed unexpectedly"
[[ "$TARGET_SERVICE_GROUP" == "$SERVICE_GROUP" ]] \
  || rollback_to_previous "effective systemd service group changed unexpectedly"
[[ "$TARGET_ENVIRONMENT_FILES" == "$PREVIOUS_ENVIRONMENT_FILES" ]] \
  || rollback_to_previous "effective systemd environment file changed unexpectedly"
[[ "$TARGET_READ_WRITE_PATHS" == "$PREVIOUS_READ_WRITE_PATHS" ]] \
  || rollback_to_previous "effective systemd writable paths changed unexpectedly"
[[ "$TARGET_UMASK" == "$PREVIOUS_UMASK" && "$TARGET_UMASK" == "0077" ]] \
  || rollback_to_previous "effective systemd umask changed unexpectedly"
assert_dropin_paths_exact "$TARGET_DROPINS" "$MANAGED_DROPIN" "$TRANSACTION_RUNTIME_GUARD" \
  || rollback_to_previous "effective guarded systemd drop-in set is unexpected"
assert_secure_systemd_directory "/etc/systemd/system" "systemd administrator unit directory"
assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
assert_secure_systemd_file "$MANAGED_DROPIN" "managed systemd runtime drop-in"
cmp -s "$DROPIN_CANDIDATE" "$MANAGED_DROPIN" \
  || rollback_to_previous "installed managed runtime drop-in does not match its reviewed candidate"

assert_service_persistently_disabled "$SERVICE_USER" \
  || rollback_to_previous "service became enabled before release health validation"
assert_transaction_runtime_guard_loaded \
  || rollback_to_previous "transaction runtime guard is not loaded before candidate start"
systemctl --no-block start "$SERVICE" || rollback_to_previous "systemd start failed"
systemctl is-active --quiet "$SERVICE" || rollback_to_previous "service is not active"
MAIN_PID="$(systemctl show "$SERVICE" --property=MainPID --value)"
[[ "$MAIN_PID" =~ ^[1-9][0-9]*$ ]] \
  || rollback_to_previous "systemd did not report a live main process"
[[ "$MAIN_PID" != "$PREVIOUS_MAIN_PID" ]] \
  || rollback_to_previous "systemd did not replace the previous process"
RUNNING_PROCESS_ARGV="$(process_exec_argv "$MAIN_PID")"
[[ "$RUNNING_PROCESS_ARGV" == "$MODERN_EXEC_ARGV" ]] \
  || rollback_to_previous "running process command line is not the release-local runtime"
process_environment_matches "$MAIN_PID" \
  || rollback_to_previous "running process environment is not the validated production contract"

LOCAL_OK="false"
for _ in $(seq 1 "$SERVICE_HEALTH_ATTEMPTS"); do
  if manifest_bound_health "$RELEASE_MANIFEST_SHA256" \
    "http://127.0.0.1:$LOCAL_PORT/api/health" "$SERVICE_HEALTH_MAX_SECONDS" "$PUBLIC_HOST"; then
    LOCAL_OK="true"
    break
  fi
  sleep "$SERVICE_HEALTH_POLL_SECONDS"
done
[[ "$LOCAL_OK" == "true" ]] || rollback_to_previous "local health endpoint failed"

manifest_bound_health "$RELEASE_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || rollback_to_previous "public health endpoint or release identity failed"

strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || rollback_to_previous "public root did not enforce the login redirect"

[[ "$(readlink -f -- "$CURRENT_LINK")" == "$RELEASE_DIR" \
  && "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
  && "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$CURRENT_LINK/.venv/bin/python" \
  && "$(effective_exec_argv)" == "$MODERN_EXEC_ARGV" \
  && "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$CURRENT_LINK" \
  && "$(systemctl show "$SERVICE" --property=User --value)" == "$SERVICE_USER" \
  && "$(systemctl show "$SERVICE" --property=Group --value)" == "$SERVICE_GROUP" \
  && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
  && "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" \
  && "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" \
  && "$(systemctl show "$SERVICE" --property=MainPID --value)" == "$MAIN_PID" ]] \
  || rollback_to_previous "release runtime drifted before deployment commit"
assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" \
  "$MANAGED_DROPIN" "$TRANSACTION_RUNTIME_GUARD" \
  || rollback_to_previous "guarded drop-in set drifted before deployment commit"
assert_transaction_runtime_guard_loaded \
  || rollback_to_previous "transaction runtime guard drifted before deployment commit"
systemctl is-active --quiet "$SERVICE" \
  || rollback_to_previous "release service stopped before deployment commit"
assert_service_persistently_disabled "$SERVICE_USER" \
  || rollback_to_previous "release service became enabled before transaction commit"
[[ "$(sha256sum "$FRAGMENT_PATH" | awk '{print $1}')" == "$UNIT_FRAGMENT_SHA256" \
  && "$(sha256sum "$ENV_FILE" | awk '{print $1}')" == "$ENV_FILE_SHA256" ]] \
  || rollback_to_previous "base unit or production environment drifted before deployment commit"
assert_secure_systemd_directory "/etc/systemd/system" "systemd administrator unit directory"
assert_secure_systemd_directory "$MANAGED_DROPIN_DIR" "managed systemd drop-in directory"
assert_secure_systemd_file "$FRAGMENT_PATH" "systemd base unit"
assert_secure_systemd_file "$MANAGED_DROPIN" "managed systemd runtime drop-in"
cmp -s "$DROPIN_CANDIDATE" "$MANAGED_DROPIN" \
  || rollback_to_previous "managed runtime drop-in drifted before deployment commit"
FINAL_PROCESS_ARGV="$(process_exec_argv "$MAIN_PID")"
[[ "$FINAL_PROCESS_ARGV" == "$MODERN_EXEC_ARGV" \
  && "$(readlink -f -- "/proc/$MAIN_PID/cwd")" == "$RELEASE_DIR" ]] \
  || rollback_to_previous "release process drifted before deployment commit"
manifest_bound_health "$RELEASE_MANIFEST_SHA256" \
  "http://127.0.0.1:$LOCAL_PORT/api/health" 8 "$PUBLIC_HOST" \
  || rollback_to_previous "release local health or identity drifted before deployment commit"
manifest_bound_health "$RELEASE_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || rollback_to_previous "release public health or identity drifted before deployment commit"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || rollback_to_previous "release public login redirect drifted before deployment commit"
assert_release_tree_security "$RELEASE_DIR" "$SERVICE_USER"
[[ "$(runtime_fingerprint "$RELEASE_DIR/.venv" "$RELEASE_PYTHON" \
  "$RELEASE_DIR/requirements.production.lock.txt" "$RELEASE_DIR")" == "$FINAL_RUNTIME_FINGERPRINT_JSON" ]] \
  || rollback_to_previous "release runtime fingerprint drifted before deployment commit"
"$PYTHON_BIN" -I "$SCRIPT_DIR/verify_installed_release.py" \
  "$RELEASE_DIR" --expected-version "$EXPECTED_VERSION" \
  || rollback_to_previous "release source verification failed before deployment commit"
[[ "$(sha256sum "$RELEASE_DIR/release-manifest.json" | awk '{print $1}')" \
  == "$RELEASE_MANIFEST_SHA256" ]] \
  || rollback_to_previous "release manifest digest changed before deployment record creation"
RUNTIME_BASELINE_VERIFICATION_JSON="$(verify_release_runtime_baseline \
  "$RELEASE_ID" "$RELEASE_DIR" "$RELEASE_MANIFEST_SHA256")" \
  || rollback_to_previous "release external runtime baseline drifted before deployment commit"
mapfile -t RUNTIME_BASELINE_FIELDS < <("$PYTHON_BIN" -I -B -u - \
  "$RUNTIME_BASELINE_VERIFICATION_JSON" <<'PY'
from __future__ import annotations
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
    or report["schema_version"] != 1
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
[[ "${#RUNTIME_BASELINE_FIELDS[@]}" == "3" \
  && "${RUNTIME_BASELINE_FIELDS[1]}" == "$RUNTIME_BASELINE_SHA256" \
  && "${RUNTIME_BASELINE_FIELDS[2]}" == "$RUNTIME_GUARD_HELPER_SHA256" ]] \
  || rollback_to_previous "runtime baseline verification evidence is inconsistent"
RUNTIME_FINGERPRINT_SHA256="${RUNTIME_BASELINE_FIELDS[0]}"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || rollback_to_previous "security database backup drifted before deployment commit"

ARCHIVE_SHA256="$ARCHIVE_SHA256_FIXED"
MANAGED_DROPIN_SHA256="$(sha256sum "$MANAGED_DROPIN" | awk '{print $1}')"
DEPLOYMENT_RECORD_TEMP="$PENDING_DEPLOYMENT_RECORD"
"$PYTHON_BIN" -I - "$DEPLOYMENT_RECORD_TEMP" "$RELEASE_ID" "$EXPECTED_VERSION" \
  "$PREVIOUS_ID" "$ARCHIVE_SHA256" "$RELEASE_MANIFEST_SHA256" "$UNIT_FRAGMENT_SHA256" \
  "$DROPIN_PATHS_BEFORE" "$DROPIN_SHA256" "$MANAGED_DROPIN_SHA256" \
  "$(basename -- "$UNIT_BACKUP")" \
  "$(if [[ -n "$DROPIN_BACKUP" ]]; then basename -- "$DROPIN_BACKUP"; fi)" \
  "$ENV_FILE_SHA256" "$PUBLIC_ORIGIN" "$PUBLIC_HOST" \
  "$MODERN_EXEC_START_PRE_ARGVS_JSON" "$FINAL_RUNTIME_FINGERPRINT_JSON" \
  "$DATABASE_BACKUP_METADATA_JSON" "$RUNTIME_BASELINE" \
  "$RUNTIME_BASELINE_SHA256" "$RUNTIME_FINGERPRINT_SHA256" \
  "$RUNTIME_GUARD_HELPER_SHA256" <<'PY'
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
record = {
    "schema_version": 5,
    "status": "passed",
    "release_id": sys.argv[2],
    "version": sys.argv[3],
    "previous_release_id": sys.argv[4],
    "archive_sha256": sys.argv[5],
    "release_manifest_sha256": sys.argv[6],
    "deployed_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "systemd": {
        "fragment_sha256_before": sys.argv[7],
        "dropin_paths_before": [] if not sys.argv[8] else [sys.argv[8]],
        "managed_dropin_sha256_before": sys.argv[9] or None,
        "managed_dropin_sha256_after": sys.argv[10],
        "fragment_backup": sys.argv[11],
        "managed_dropin_backup": sys.argv[12] or None,
        "runtime_mode": "release-local-venv-dropin",
        "environment_file_sha256": sys.argv[13],
        "exec_start_pre_argvs": json.loads(sys.argv[16]),
    },
    "public_origin": sys.argv[14],
    "public_host": sys.argv[15],
    "runtime_fingerprint": json.loads(sys.argv[17]),
    "database_backup": json.loads(sys.argv[18]),
    "runtime_baseline_path": sys.argv[19],
    "runtime_baseline_sha256": sys.argv[20],
    "runtime_fingerprint_sha256": sys.argv[21],
    "runtime_guard_helper_sha256": sys.argv[22],
    "checks": {
        "archive_manifest": True,
        "prepared_release_durable": True,
        "release_permissions_normalized": True,
        "release_tree_immutable": True,
        "service_user_import": True,
        "isolated_service_user_preflight": True,
        "security_database_backup": True,
        "known_good_health_before_switch": True,
        "service_disabled_during_switch": True,
        "service_stopped_before_switch": True,
        "atomic_symlink": True,
        "managed_systemd_dropin": True,
        "effective_runtime": True,
        "running_process_runtime": True,
        "systemd_active": True,
        "local_health": True,
        "public_health": True,
        "public_login_redirect": True,
        "production_environment_validated_three_phases": True,
        "final_publication_configuration_gate": True,
        "ordinary_restart_environment_gate": True,
        "ordinary_restart_integrity_gate": True,
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
chmod 0640 "$DEPLOYMENT_RECORD_TEMP"
assert_trusted_record_file "$DEPLOYMENT_RECORD_TEMP" "pending deployment passed record"
fsync_file "$DEPLOYMENT_RECORD_TEMP"

rm -f -- "$DROPIN_CANDIDATE" "$TRANSACTION_TEMP"
[[ ! -e "$COMMITTED_TRANSACTION_RECORD" && ! -L "$COMMITTED_TRANSACTION_RECORD" ]] \
  || rollback_to_previous "deployment transaction evidence path already exists"
transition_transaction_status "switching" "deploy_committed_pending_activation" \
  || rollback_to_previous "cannot durably commit the deployment target inside the active marker"
TRANSACTION_COMMITTED="true"

# The target is now logically committed, but it is still running under the
# bounded guard.  From this point every failure retains the marker and must
# finalize this target; it must never restore the previous release.
GUARDED_MAIN_PID="$MAIN_PID"
stop_service_and_verify \
  || rollback_to_previous "cannot stop the guarded committed deployment process"
assert_service_persistently_disabled "$SERVICE_USER" \
  || rollback_to_previous "service enablement drifted while finalizing the committed deployment"
remove_transaction_runtime_guard "$SERVICE_USER" \
  || rollback_to_previous "cannot remove the transaction runtime guard and restore the production restart policy"
assert_service_persistently_disabled "$SERVICE_USER" \
  || rollback_to_previous "service became enabled before unguarded committed-target validation"

systemctl --no-block start "$SERVICE" \
  || rollback_to_previous "committed deployment target failed to start without the transaction guard"
FINAL_LOCAL_OK="false"
for _ in $(seq 1 "$SERVICE_HEALTH_ATTEMPTS"); do
  if systemctl is-active --quiet "$SERVICE" \
    && manifest_bound_health "$RELEASE_MANIFEST_SHA256" \
      "http://127.0.0.1:$LOCAL_PORT/api/health" "$SERVICE_HEALTH_MAX_SECONDS" "$PUBLIC_HOST"; then
    FINAL_LOCAL_OK="true"
    break
  fi
  sleep "$SERVICE_HEALTH_POLL_SECONDS"
done
[[ "$FINAL_LOCAL_OK" == "true" ]] \
  || rollback_to_previous "committed deployment target failed final local health validation"
MAIN_PID="$(systemctl show "$SERVICE" --property=MainPID --value)"
[[ "$MAIN_PID" =~ ^[1-9][0-9]*$ && "$MAIN_PID" != "$GUARDED_MAIN_PID" ]] \
  || rollback_to_previous "committed deployment target did not receive a new unguarded process"
[[ "$(process_exec_argv "$MAIN_PID")" == "$MODERN_EXEC_ARGV" \
  && "$(process_working_directory "$MAIN_PID")" == "$RELEASE_DIR" ]] \
  || rollback_to_previous "committed deployment process provenance is invalid"
process_environment_matches "$MAIN_PID" \
  || rollback_to_previous "committed deployment process environment is invalid"
[[ "$(readlink -f -- "$CURRENT_LINK")" == "$RELEASE_DIR" \
  && "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
  && "$(systemctl show "$SERVICE" --property=Restart --value)" == "on-failure" \
  && "$(systemctl show "$SERVICE" --property=RuntimeMaxUSec --value)" == "infinity" \
  && "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$CURRENT_LINK/.venv/bin/python" \
  && "$(effective_exec_argv)" == "$MODERN_EXEC_ARGV" \
  && "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$CURRENT_LINK" \
  && "$(systemctl show "$SERVICE" --property=User --value)" == "$SERVICE_USER" \
  && "$(systemctl show "$SERVICE" --property=Group --value)" == "$SERVICE_GROUP" \
  && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
  && "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" \
  && "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" \
  && "$(systemctl show "$SERVICE" --property=MainPID --value)" == "$MAIN_PID" ]] \
  || rollback_to_previous "committed deployment effective runtime drifted before enablement"
[[ "$(effective_exec_start_pre_argvs)" == "$MODERN_EXEC_START_PRE_ARGVS_JSON" ]] \
  || rollback_to_previous "committed deployment ordinary-restart environment gate drifted before enablement"
assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" "$MANAGED_DROPIN" \
  || rollback_to_previous "committed deployment drop-in set drifted before enablement"
assert_service_persistently_disabled "$SERVICE_USER" \
  || rollback_to_previous "committed deployment became enabled before final validation"
( trap - EXIT; assert_release_tree_security "$RELEASE_DIR" "$SERVICE_USER" ) \
  || rollback_to_previous "committed deployment source permissions drifted before enablement"
[[ "$(runtime_fingerprint "$RELEASE_DIR/.venv" "$RELEASE_PYTHON" \
  "$RELEASE_DIR/requirements.production.lock.txt" "$RELEASE_DIR")" == "$FINAL_RUNTIME_FINGERPRINT_JSON" ]] \
  || rollback_to_previous "committed deployment runtime provenance drifted before enablement"
( trap - EXIT; "$PYTHON_BIN" -I "$SCRIPT_DIR/verify_installed_release.py" \
  "$RELEASE_DIR" --expected-version "$EXPECTED_VERSION" ) \
  || rollback_to_previous "committed deployment source verification failed before enablement"
manifest_bound_health "$RELEASE_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || rollback_to_previous "committed deployment public health or identity failed before enablement"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || rollback_to_previous "committed deployment login redirect failed before enablement"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || rollback_to_previous "committed deployment database backup evidence drifted before enablement"
validate_production_environment \
  || rollback_to_previous "production environment failed the final evidence and enablement gate"

systemctl enable "$SERVICE" \
  || rollback_to_previous "cannot persist automatic startup for the committed deployment target"
assert_standard_enabled_topology "$SERVICE_USER" \
  || rollback_to_previous "committed deployment enablement topology is not uniquely standard"
fsync_systemd_enablement_state \
  || rollback_to_previous "cannot persist the committed deployment enablement topology"
assert_standard_enabled_topology "$SERVICE_USER" \
  || rollback_to_previous "committed deployment enablement topology drifted after persistence"
[[ "$(readlink -f -- "$CURRENT_LINK")" == "$RELEASE_DIR" \
  && "$(systemctl show "$SERVICE" --property=NeedDaemonReload --value)" == "no" \
  && "$(systemctl show "$SERVICE" --property=Restart --value)" == "on-failure" \
  && "$(systemctl show "$SERVICE" --property=RuntimeMaxUSec --value)" == "infinity" \
  && "$(systemctl show "$SERVICE" --property=ExecStart --value | sed -n 's/^{ path=\([^ ;]*\).*/\1/p')" == "$CURRENT_LINK/.venv/bin/python" \
  && "$(effective_exec_argv)" == "$MODERN_EXEC_ARGV" \
  && "$(systemctl show "$SERVICE" --property=WorkingDirectory --value)" == "$CURRENT_LINK" \
  && "$(systemctl show "$SERVICE" --property=User --value)" == "$SERVICE_USER" \
  && "$(systemctl show "$SERVICE" --property=Group --value)" == "$SERVICE_GROUP" \
  && "$(systemctl show "$SERVICE" --property=EnvironmentFiles --value)" == "$PREVIOUS_ENVIRONMENT_FILES" \
  && "$(systemctl show "$SERVICE" --property=ReadWritePaths --value)" == "$PREVIOUS_READ_WRITE_PATHS" \
  && "$(systemctl show "$SERVICE" --property=UMask --value)" == "$PREVIOUS_UMASK" \
  && "$(systemctl show "$SERVICE" --property=MainPID --value)" == "$MAIN_PID" ]] \
  || fail "deployment target is committed but runtime identity drifted after enablement; manual recovery is required and the service remains in its actual state"
[[ "$(effective_exec_start_pre_argvs)" == "$MODERN_EXEC_START_PRE_ARGVS_JSON" ]] \
  || fail "deployment target is committed but its ordinary-restart environment gate drifted after enablement; manual recovery is required"
assert_dropin_paths_exact "$(systemctl show "$SERVICE" --property=DropInPaths --value)" "$MANAGED_DROPIN" \
  || fail "deployment target is committed but drop-in identity drifted after enablement; manual recovery is required"
systemctl is-active --quiet "$SERVICE" \
  || fail "deployment target is committed but the service is not active after enablement; manual recovery is required and the service remains in its actual state"
[[ "$(process_exec_argv "$MAIN_PID")" == "$MODERN_EXEC_ARGV" \
  && "$(process_working_directory "$MAIN_PID")" == "$RELEASE_DIR" ]] \
  || fail "deployment target is committed but process provenance drifted after enablement; manual recovery is required and the service remains in its actual state"
( trap - EXIT; assert_release_tree_security "$RELEASE_DIR" "$SERVICE_USER" ) \
  || fail "deployment target is committed but source permissions drifted after enablement; manual recovery is required and the service remains in its actual state"
[[ "$(runtime_fingerprint "$RELEASE_DIR/.venv" "$RELEASE_PYTHON" \
  "$RELEASE_DIR/requirements.production.lock.txt" "$RELEASE_DIR")" == "$FINAL_RUNTIME_FINGERPRINT_JSON" ]] \
  || fail "deployment target is committed but runtime provenance drifted after enablement; manual recovery is required and the service remains in its actual state"
( trap - EXIT; "$PYTHON_BIN" -I "$SCRIPT_DIR/verify_installed_release.py" \
  "$RELEASE_DIR" --expected-version "$EXPECTED_VERSION" ) \
  || fail "deployment target is committed but source verification failed after enablement; manual recovery is required and the service remains in its actual state"
manifest_bound_health "$RELEASE_MANIFEST_SHA256" \
  "http://127.0.0.1:$LOCAL_PORT/api/health" 8 "$PUBLIC_HOST" \
  || fail "deployment target is committed but local health or identity failed after enablement; manual recovery is required and the service remains in its actual state"
manifest_bound_health "$RELEASE_MANIFEST_SHA256" \
  "$PUBLIC_ORIGIN/api/health" 15 \
  || fail "deployment target is committed but public health or identity failed after enablement; manual recovery is required and the service remains in its actual state"
strict_login_redirect "$PUBLIC_ORIGIN/" 15 \
  || fail "deployment target is committed but login redirect validation failed after enablement; manual recovery is required and the service remains in its actual state"
verify_database_backup_evidence "$DATABASE_BACKUP" \
  "$DATABASE_BACKUP_METADATA_JSON" "$DATABASE_BACKUP_BASENAME" \
  || fail "deployment target is committed but database backup evidence drifted before publication; manual recovery is required and the service remains in its actual state"
validate_final_publication_configuration \
  || fail "deployment target is committed but the final publication configuration binding failed; manual recovery is required and passed evidence was not published"
validate_production_environment \
  || fail "deployment target is committed but the production environment failed immediately before passed-record publication; manual recovery is required"

publish_committed_record "$DEPLOYMENT_RECORD_TEMP" "$DEPLOYMENT_RECORD" \
  || fail "deployment target remains committed under the active marker because passed evidence publication failed; rerun recover-transaction.sh"
mv -T -- "$TRANSACTION_FILE" "$COMMITTED_TRANSACTION_RECORD" \
  || rollback_to_previous "committed deployment passed activation and evidence publication but its active marker could not be archived"
TRANSACTION_ACTIVE="false"
CANDIDATE_CLEANUP_ACTIVE="false"
assert_trusted_root_file_path "$COMMITTED_TRANSACTION_RECORD" \
  "archived deployment transaction evidence"
fsync_file "$COMMITTED_TRANSACTION_RECORD" \
  || fail "deployment activation is complete but transaction evidence durability is incomplete"
fsync_directory "$DEPLOYMENT_DIR" \
  || fail "deployment activation is complete but transaction evidence directory durability is incomplete"
fsync_directory "$APP_ROOT" \
  || fail "deployment activation is complete but marker archive durability is incomplete"
trap - EXIT INT TERM HUP

printf 'DEPLOYMENT PASS: %s (previous: %s)\n' "$RELEASE_ID" "$PREVIOUS_ID"
printf 'Release-local runtime is active; shared runs and security database were preserved.\n'
printf 'Cloudflare and the base systemd unit were not modified.\n'
