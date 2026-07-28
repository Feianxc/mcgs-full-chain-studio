#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

usage() {
  cat <<'EOF'
Usage:
  deploy-release.sh --archive FILE --release-id ID --expected-version VERSION \
    (--prepare-only | --confirm-switch-production)

Optional environment:
  PROTOCOL_STUDIO_DEPLOY_ROOT       default /srv/apps/protocol-studio
  PROTOCOL_STUDIO_ENV_FILE          default /etc/protocol-studio/protocol-studio.env
  PROTOCOL_STUDIO_SYSTEMD_SERVICE   default protocol-studio.service
  PROTOCOL_STUDIO_PUBLIC_ORIGIN     default https://protocol.feian.online
  PROTOCOL_STUDIO_PREFLIGHT_PORT    default 18772
  PROTOCOL_STUDIO_WHEELHOUSE        optional offline wheel directory
EOF
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

ARCHIVE=""
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

[[ "$(id -u)" == "0" ]] || fail "run as root"
[[ -n "$ARCHIVE" && -n "$RELEASE_ID" && -n "$EXPECTED_VERSION" && -n "$MODE" ]] \
  || { usage >&2; fail "required arguments are missing"; }
[[ "$RELEASE_ID" =~ ^[0-9A-Za-z][0-9A-Za-z._-]{0,79}$ ]] \
  || fail "release id contains unsupported characters"
[[ "$EXPECTED_VERSION" =~ ^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$ ]] \
  || fail "expected version contains unsupported characters"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_TOOLS="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "python3 is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v flock >/dev/null 2>&1 || fail "flock is required"

ARCHIVE="$(realpath -- "$ARCHIVE")"
[[ -f "$ARCHIVE" ]] || fail "release archive does not exist"

APP_ROOT="${PROTOCOL_STUDIO_DEPLOY_ROOT:-/srv/apps/protocol-studio}"
ENV_FILE="${PROTOCOL_STUDIO_ENV_FILE:-/etc/protocol-studio/protocol-studio.env}"
SERVICE="${PROTOCOL_STUDIO_SYSTEMD_SERVICE:-protocol-studio.service}"
PUBLIC_ORIGIN="${PROTOCOL_STUDIO_PUBLIC_ORIGIN:-https://protocol.feian.online}"
PUBLIC_HOST="${PUBLIC_ORIGIN#*://}"
PUBLIC_HOST="${PUBLIC_HOST%%/*}"
PUBLIC_HOST="${PUBLIC_HOST%%:*}"
PREFLIGHT_PORT="${PROTOCOL_STUDIO_PREFLIGHT_PORT:-18772}"
WHEELHOUSE="${PROTOCOL_STUDIO_WHEELHOUSE:-}"

RELEASES_DIR="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
SHARED_DIR="$APP_ROOT/shared"
RUNS_DIR="$SHARED_DIR/runs"
SECURITY_DB="$SHARED_DIR/security.sqlite3"
LOG_DIR="$SHARED_DIR/deploy-logs"
BACKUP_DIR="$SHARED_DIR/backups"
DEPLOYMENT_DIR="$SHARED_DIR/deployments"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_ID"
INCOMING_DIR="$RELEASES_DIR/.incoming-$RELEASE_ID-$$"

case "$RELEASE_DIR" in
  "$RELEASES_DIR"/*) ;;
  *) fail "resolved release path escaped the releases directory" ;;
esac
[[ -f "$ENV_FILE" ]] || fail "production environment file is missing"
[[ -d "$RUNS_DIR" ]] || fail "shared runs directory is missing"
[[ -f "$SECURITY_DB" ]] || fail "shared security database is missing; refusing to create or reset it"
[[ ! -e "$RELEASE_DIR" ]] || fail "release id already exists; releases are immutable"
[[ ! -e "$INCOMING_DIR" ]] || fail "incoming path already exists"

install -d -m 0750 "$RELEASES_DIR" "$LOG_DIR" "$BACKUP_DIR" "$DEPLOYMENT_DIR"
exec 9>"$APP_ROOT/.deploy.lock"
flock -n 9 || fail "another deployment is running"

"$PYTHON_BIN" "$REPO_TOOLS/packaging/verify_release.py" \
  "$ARCHIVE" --expected-version "$EXPECTED_VERSION"

install -d -m 0750 "$INCOMING_DIR"
TOP_LEVEL="$("$PYTHON_BIN" "$SCRIPT_DIR/safe_extract.py" "$ARCHIVE" "$INCOMING_DIR")"
EXTRACTED_ROOT="$INCOMING_DIR/$TOP_LEVEL"
[[ -d "$EXTRACTED_ROOT" ]] || fail "safe extractor did not produce a release root"
"$PYTHON_BIN" "$REPO_TOOLS/packaging/verify_release.py" \
  "$EXTRACTED_ROOT" --expected-version "$EXPECTED_VERSION"

mv -- "$EXTRACTED_ROOT" "$RELEASE_DIR"
rmdir -- "$INCOMING_DIR"

"$PYTHON_BIN" -m venv "$RELEASE_DIR/.venv"
RELEASE_PYTHON="$RELEASE_DIR/.venv/bin/python"
"$RELEASE_PYTHON" -m pip install --disable-pip-version-check --no-cache-dir --upgrade pip
if [[ -n "$WHEELHOUSE" ]]; then
  WHEELHOUSE="$(realpath -- "$WHEELHOUSE")"
  [[ -d "$WHEELHOUSE" ]] || fail "configured wheelhouse is not a directory"
  "$RELEASE_PYTHON" -m pip install --disable-pip-version-check --no-cache-dir \
    --no-index --find-links "$WHEELHOUSE" --requirement "$RELEASE_DIR/requirements.production.txt"
else
  "$RELEASE_PYTHON" -m pip install --disable-pip-version-check --no-cache-dir \
    --requirement "$RELEASE_DIR/requirements.production.txt"
fi

"$RELEASE_PYTHON" "$RELEASE_DIR/deploy/verify_installed_release.py" \
  "$RELEASE_DIR" --expected-version "$EXPECTED_VERSION"

"$RELEASE_PYTHON" "$RELEASE_DIR/deploy/run_with_env.py" --env-file "$ENV_FILE" -- \
  "$RELEASE_PYTHON" "$RELEASE_DIR/deploy/validate_production_env.py" \
  --shared-runs "$RUNS_DIR" \
  --security-db "$SECURITY_DB" \
  --public-origin "$PUBLIC_ORIGIN" \
  --public-host "$PUBLIC_HOST"

"$RELEASE_PYTHON" - "$PREFLIGHT_PORT" <<'PY'
from __future__ import annotations
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    probe.bind(("127.0.0.1", port))
PY

PREFLIGHT_LOG="$LOG_DIR/$RELEASE_ID-preflight.log"
PREFLIGHT_PID=""
stop_preflight() {
  if [[ -n "$PREFLIGHT_PID" ]] && kill -0 "$PREFLIGHT_PID" 2>/dev/null; then
    kill "$PREFLIGHT_PID" 2>/dev/null || true
    wait "$PREFLIGHT_PID" 2>/dev/null || true
  fi
  PREFLIGHT_PID=""
}
trap stop_preflight EXIT

(
  cd -- "$RELEASE_DIR"
  exec "$RELEASE_PYTHON" "$RELEASE_DIR/deploy/run_with_env.py" --env-file "$ENV_FILE" -- \
    "$RELEASE_PYTHON" -m uvicorn protocol_studio.app:app \
    --host 127.0.0.1 --port "$PREFLIGHT_PORT" \
    --proxy-headers --forwarded-allow-ips 127.0.0.1
) >"$PREFLIGHT_LOG" 2>&1 &
PREFLIGHT_PID="$!"

PREFLIGHT_OK="false"
for _ in $(seq 1 40); do
  if ! kill -0 "$PREFLIGHT_PID" 2>/dev/null; then
    break
  fi
  if curl --silent --show-error --fail --max-time 3 \
    --header "Host: $PUBLIC_HOST" \
    "http://127.0.0.1:$PREFLIGHT_PORT/api/health" >/dev/null; then
    if kill -0 "$PREFLIGHT_PID" 2>/dev/null; then
      PREFLIGHT_OK="true"
      break
    fi
  fi
  sleep 0.5
done
[[ "$PREFLIGHT_OK" == "true" ]] || fail "isolated preflight health check failed; see the preflight log"

REDIRECT_LINE="$(curl --silent --show-error --max-time 3 --max-redirs 0 \
  --output /dev/null --write-out '%{http_code} %{redirect_url}' \
  --header "Host: $PUBLIC_HOST" "http://127.0.0.1:$PREFLIGHT_PORT/")"
[[ "$REDIRECT_LINE" == 30[23]\ *"/login"* ]] \
  || fail "isolated preflight did not enforce the login redirect"
stop_preflight

if [[ "$MODE" == "prepare" ]]; then
  printf 'PREPARED: %s\n' "$RELEASE_ID"
  printf 'Production current symlink and service were not changed.\n'
  exit 0
fi

[[ -L "$CURRENT_LINK" ]] || fail "current must be an existing symbolic link"
systemctl is-enabled --quiet "$SERVICE" || fail "existing systemd service is not enabled"
systemctl is-active --quiet "$SERVICE" || fail "existing systemd service is not active"
PREVIOUS_TARGET="$(readlink -f -- "$CURRENT_LINK")"
case "$PREVIOUS_TARGET" in
  "$RELEASES_DIR"/*) ;;
  *) fail "current target is outside the releases directory" ;;
esac
[[ -d "$PREVIOUS_TARGET" ]] || fail "current target does not exist"
PREVIOUS_ID="$(basename -- "$PREVIOUS_TARGET")"

BACKUP_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DATABASE_BACKUP="$BACKUP_DIR/security-$BACKUP_STAMP-before-$RELEASE_ID.sqlite3"
"$RELEASE_PYTHON" - "$SECURITY_DB" "$DATABASE_BACKUP" <<'PY'
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
backup_path = Path(sys.argv[2])
if not source_path.is_file() or backup_path.exists():
    raise SystemExit("database backup precondition failed")
source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
destination = sqlite3.connect(backup_path)
try:
    source.backup(destination)
    if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("database backup integrity check failed")
finally:
    destination.close()
    source.close()
PY
chmod 0600 "$DATABASE_BACKUP"

atomic_link() {
  local target="$1"
  local temporary="$APP_ROOT/.current-next-$$"
  [[ ! -e "$temporary" && ! -L "$temporary" ]] || fail "temporary current link already exists"
  ln -s -- "$target" "$temporary"
  mv -Tf -- "$temporary" "$CURRENT_LINK"
}

rollback_to_previous() {
  local reason="$1"
  printf 'SWITCH FAILED: %s\n' "$reason" >&2
  atomic_link "$PREVIOUS_TARGET"
  systemctl restart "$SERVICE" || true
  if systemctl is-active --quiet "$SERVICE" \
    && curl --silent --show-error --fail --max-time 8 \
      --header "Host: $PUBLIC_HOST" "http://127.0.0.1:18771/api/health" >/dev/null; then
    printf 'ROLLBACK PASS: restored %s\n' "$PREVIOUS_ID" >&2
  else
    printf 'ROLLBACK INCOMPLETE: manual intervention required\n' >&2
  fi
  exit 1
}

atomic_link "$RELEASE_DIR"
systemctl restart "$SERVICE" || rollback_to_previous "systemd restart failed"
systemctl is-active --quiet "$SERVICE" || rollback_to_previous "service is not active"
systemctl is-enabled --quiet "$SERVICE" || rollback_to_previous "service is not enabled"

for _ in $(seq 1 30); do
  if curl --silent --show-error --fail --max-time 5 \
    --header "Host: $PUBLIC_HOST" \
    "http://127.0.0.1:18771/api/health" >/dev/null; then
    LOCAL_OK="true"
    break
  fi
  LOCAL_OK="false"
  sleep 1
done
[[ "$LOCAL_OK" == "true" ]] || rollback_to_previous "local health endpoint failed"

curl --silent --show-error --fail --max-time 15 \
  "$PUBLIC_ORIGIN/api/health" >/dev/null \
  || rollback_to_previous "public health endpoint failed"

PUBLIC_REDIRECT="$(curl --silent --show-error --max-time 15 --max-redirs 0 \
  --output /dev/null --write-out '%{http_code} %{redirect_url}' "$PUBLIC_ORIGIN/")"
[[ "$PUBLIC_REDIRECT" == 30[23]\ *"/login"* ]] \
  || rollback_to_previous "public root did not enforce the login redirect"

ARCHIVE_SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
DEPLOYMENT_RECORD="$DEPLOYMENT_DIR/$RELEASE_ID.json"
"$RELEASE_PYTHON" - "$DEPLOYMENT_RECORD" "$RELEASE_ID" "$EXPECTED_VERSION" \
  "$PREVIOUS_ID" "$ARCHIVE_SHA256" <<'PY'
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
record = {
    "schema_version": 1,
    "status": "passed",
    "release_id": sys.argv[2],
    "version": sys.argv[3],
    "previous_release_id": sys.argv[4],
    "archive_sha256": sys.argv[5],
    "deployed_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "checks": {
        "archive_manifest": True,
        "isolated_preflight": True,
        "security_database_backup": True,
        "atomic_symlink": True,
        "systemd_active": True,
        "local_health": True,
        "public_health": True,
        "public_login_redirect": True
    }
}
path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
chmod 0640 "$DEPLOYMENT_RECORD"

printf 'DEPLOYMENT PASS: %s (previous: %s)\n' "$RELEASE_ID" "$PREVIOUS_ID"
printf 'Shared runs and security database were preserved; Cloudflare was not modified.\n'
