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
builtin unset BASH_ENV ENV CDPATH
builtin unset CURL_HOME ALL_PROXY HTTPS_PROXY HTTP_PROXY NO_PROXY \
  all_proxy https_proxy http_proxy no_proxy

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

APP_ROOT="${PROTOCOL_STUDIO_DEPLOY_ROOT-/srv/apps/protocol-studio}"
if [[ ! "$APP_ROOT" =~ ^/[0-9A-Za-z_][0-9A-Za-z._-]*(/[0-9A-Za-z_][0-9A-Za-z._-]*)*$ ]]; then
  printf 'ERROR: PROTOCOL_STUDIO_DEPLOY_ROOT must be a canonical absolute path without dot segments or a trailing slash\n' >&2
  exit 1
fi

verify_installed_runtime() {
  local expected_manifest_sha256="$1"
  local resolved_app_root
  # Every activatable release-local runtime is schema 5. Historical schema 2-4
  # evidence is audit-only, so this check never falls back around the external
  # baseline/helper/fingerprint gate for a modern current target.
  [[ -d "$APP_ROOT" && ! -L "$APP_ROOT" ]] || return 1
  resolved_app_root="$(/usr/bin/realpath -e -- "$APP_ROOT")" || return 1
  [[ "$resolved_app_root" == "$APP_ROOT" ]] || return 1
  /usr/bin/python3 -I -B -u \
    "$APP_ROOT/runtime-guard/runtime_fingerprint.py" \
    --verify-current "$APP_ROOT/current" \
    --releases-root "$APP_ROOT/releases" \
    --baseline-directory "$APP_ROOT/runtime-guard/baselines" \
    --expected-manifest-sha256 "$expected_manifest_sha256" \
    --require-root-owned-immutable >/dev/null 2>&1
}

PUBLIC_ORIGIN="${PROTOCOL_STUDIO_PUBLIC_ORIGIN-https://protocol.feian.online}"
LOCAL_ORIGIN="${PROTOCOL_STUDIO_LOCAL_ORIGIN-http://127.0.0.1:18771}"
if [[ ! "$PUBLIC_ORIGIN" =~ ^https://([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+)$ ]]; then
  printf 'ERROR: PROTOCOL_STUDIO_PUBLIC_ORIGIN must be a canonical lowercase HTTPS origin with no credentials, port, path, query or fragment\n' >&2
  exit 1
fi
PUBLIC_HOST="${BASH_REMATCH[1]}"
if [[ ! "$PUBLIC_HOST" =~ \.[a-z]([a-z0-9-]*[a-z0-9])?$ ]]; then
  printf 'ERROR: PROTOCOL_STUDIO_PUBLIC_ORIGIN host must end in a DNS name, not an IP address or numeric top-level label\n' >&2
  exit 1
fi
if [[ ! "$LOCAL_ORIGIN" =~ ^http://127\.0\.0\.1:([1-9][0-9]{0,4})$ ]]; then
  printf 'ERROR: PROTOCOL_STUDIO_LOCAL_ORIGIN must be an origin-only http://127.0.0.1 URL with an explicit valid port\n' >&2
  exit 1
fi
LOCAL_PORT="${BASH_REMATCH[1]}"
if (( 10#$LOCAL_PORT > 65535 )); then
  printf 'ERROR: PROTOCOL_STUDIO_LOCAL_ORIGIN port must be between 1 and 65535\n' >&2
  exit 1
fi
[[ "$PUBLIC_ORIGIN" != "$LOCAL_ORIGIN" ]] || {
  printf 'ERROR: public and local origins must be distinct endpoints\n' >&2
  exit 1
}
EXPECTED_MANIFEST_CONFIGURED="false"
EXPECTED_MANIFEST_SHA256="${PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256-}"
ALLOW_AVAILABILITY_ONLY="${PROTOCOL_STUDIO_ALLOW_AVAILABILITY_ONLY-false}"
[[ "$ALLOW_AVAILABILITY_ONLY" == "true" || "$ALLOW_AVAILABILITY_ONLY" == "false" ]] || {
  printf 'ERROR: PROTOCOL_STUDIO_ALLOW_AVAILABILITY_ONLY must be exactly true or false\n' >&2
  exit 1
}
if [[ "${PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256+x}" == "x" ]]; then
  EXPECTED_MANIFEST_CONFIGURED="true"
  [[ "$EXPECTED_MANIFEST_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    printf 'ERROR: PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256 must be exactly 64 lowercase hexadecimal characters\n' >&2
    exit 1
  }
fi
if [[ "$EXPECTED_MANIFEST_CONFIGURED" == "true" && "$ALLOW_AVAILABILITY_ONLY" == "true" ]]; then
  printf 'ERROR: availability-only mode must not be enabled when an expected Manifest digest is configured\n' >&2
  exit 1
fi
if [[ "$EXPECTED_MANIFEST_CONFIGURED" == "false" && "$ALLOW_AVAILABILITY_ONLY" != "true" ]]; then
  printf 'ERROR: PROTOCOL_STUDIO_EXPECTED_MANIFEST_SHA256 is required unless explicit availability-only mode is enabled\n' >&2
  exit 1
fi

LOCAL_HEALTH="failed"
PUBLIC_HEALTH="failed"
LOGIN_REDIRECT="failed"
RELEASE_IDENTITY="not_requested"
INSTALLED_RUNTIME_IDENTITY="not_requested"

if [[ "$EXPECTED_MANIFEST_CONFIGURED" == "true" ]]; then
  if verify_installed_runtime "$EXPECTED_MANIFEST_SHA256"; then
    INSTALLED_RUNTIME_IDENTITY="passed"
  else
    INSTALLED_RUNTIME_IDENTITY="failed"
  fi
  if manifest_bound_health "$EXPECTED_MANIFEST_SHA256" \
    "$LOCAL_ORIGIN/api/health" 8 "$PUBLIC_HOST"; then
    LOCAL_HEALTH="passed"
  fi
  if manifest_bound_health "$EXPECTED_MANIFEST_SHA256" \
    "$PUBLIC_ORIGIN/api/health" 15; then
    PUBLIC_HEALTH="passed"
  fi
  if [[ "$INSTALLED_RUNTIME_IDENTITY" == "passed" \
    && "$LOCAL_HEALTH" == "passed" && "$PUBLIC_HEALTH" == "passed" ]]; then
    RELEASE_IDENTITY="passed"
  else
    RELEASE_IDENTITY="failed"
  fi
else
  if availability_health "$LOCAL_ORIGIN/api/health" 8 "$PUBLIC_HOST"; then
    LOCAL_HEALTH="passed"
  fi
  if availability_health "$PUBLIC_ORIGIN/api/health" 15; then
    PUBLIC_HEALTH="passed"
  fi
fi
if strict_login_redirect "$PUBLIC_ORIGIN/" 15; then
  LOGIN_REDIRECT="passed"
fi

printf 'local_health=%s\n' "$LOCAL_HEALTH"
printf 'public_health=%s\n' "$PUBLIC_HEALTH"
printf 'public_login_redirect=%s\n' "$LOGIN_REDIRECT"
printf 'installed_runtime_identity=%s\n' "$INSTALLED_RUNTIME_IDENTITY"
printf 'release_identity=%s\n' "$RELEASE_IDENTITY"

[[ "$LOCAL_HEALTH" == "passed" && "$PUBLIC_HEALTH" == "passed" \
  && "$LOGIN_REDIRECT" == "passed" \
  && ( "$EXPECTED_MANIFEST_CONFIGURED" == "false" \
    || ( "$INSTALLED_RUNTIME_IDENTITY" == "passed" && "$RELEASE_IDENTITY" == "passed" ) ) ]]
