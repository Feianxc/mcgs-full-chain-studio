#!/usr/bin/env bash
set -Eeuo pipefail

PUBLIC_ORIGIN="${PROTOCOL_STUDIO_PUBLIC_ORIGIN:-https://protocol.feian.online}"
PUBLIC_HOST="${PUBLIC_ORIGIN#*://}"
PUBLIC_HOST="${PUBLIC_HOST%%/*}"
PUBLIC_HOST="${PUBLIC_HOST%%:*}"
LOCAL_ORIGIN="${PROTOCOL_STUDIO_LOCAL_ORIGIN:-http://127.0.0.1:18771}"

LOCAL_HEALTH="failed"
PUBLIC_HEALTH="failed"
LOGIN_REDIRECT="failed"

if curl --silent --show-error --fail --max-time 8 \
  --header "Host: $PUBLIC_HOST" "$LOCAL_ORIGIN/api/health" >/dev/null; then
  LOCAL_HEALTH="passed"
fi
if curl --silent --show-error --fail --max-time 15 \
  "$PUBLIC_ORIGIN/api/health" >/dev/null; then
  PUBLIC_HEALTH="passed"
fi
REDIRECT="$(curl --silent --show-error --max-time 15 --max-redirs 0 \
  --output /dev/null --write-out '%{http_code} %{redirect_url}' \
  "$PUBLIC_ORIGIN/" || true)"
if [[ "$REDIRECT" == 30[23]\ *"/login"* ]]; then
  LOGIN_REDIRECT="passed"
fi

printf 'local_health=%s\n' "$LOCAL_HEALTH"
printf 'public_health=%s\n' "$PUBLIC_HEALTH"
printf 'public_login_redirect=%s\n' "$LOGIN_REDIRECT"

[[ "$LOCAL_HEALTH" == "passed" && "$PUBLIC_HEALTH" == "passed" && "$LOGIN_REDIRECT" == "passed" ]]
