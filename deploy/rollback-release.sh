#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
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

[[ "$(id -u)" == "0" ]] || fail "run as root"
[[ "$CONFIRMED" == "true" && -n "$RELEASE_ID" ]] || fail "explicit rollback confirmation is required"
[[ "$RELEASE_ID" =~ ^[0-9A-Za-z][0-9A-Za-z._-]{0,79}$ ]] || fail "invalid release id"

APP_ROOT="${PROTOCOL_STUDIO_DEPLOY_ROOT:-/srv/apps/protocol-studio}"
SERVICE="${PROTOCOL_STUDIO_SYSTEMD_SERVICE:-protocol-studio.service}"
PUBLIC_ORIGIN="${PROTOCOL_STUDIO_PUBLIC_ORIGIN:-https://protocol.feian.online}"
PUBLIC_HOST="${PUBLIC_ORIGIN#*://}"
PUBLIC_HOST="${PUBLIC_HOST%%/*}"
PUBLIC_HOST="${PUBLIC_HOST%%:*}"
RELEASES_DIR="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
TARGET="$RELEASES_DIR/$RELEASE_ID"

[[ -d "$TARGET" ]] || fail "target release does not exist"
[[ -x "$TARGET/.venv/bin/python" ]] || fail "target release has no independent virtual environment"
[[ -L "$CURRENT_LINK" ]] || fail "current is not a symbolic link"
PREVIOUS_TARGET="$(readlink -f -- "$CURRENT_LINK")"
case "$PREVIOUS_TARGET" in
  "$RELEASES_DIR"/*) ;;
  *) fail "current target is outside the releases directory" ;;
esac

"$TARGET/.venv/bin/python" "$TARGET/deploy/verify_installed_release.py" "$TARGET"
exec 9>"$APP_ROOT/.deploy.lock"
flock -n 9 || fail "another deployment is running"

atomic_link() {
  local target="$1"
  local temporary="$APP_ROOT/.current-rollback-$$"
  [[ ! -e "$temporary" && ! -L "$temporary" ]] || fail "temporary current link already exists"
  ln -s -- "$target" "$temporary"
  mv -Tf -- "$temporary" "$CURRENT_LINK"
}

restore_previous() {
  atomic_link "$PREVIOUS_TARGET"
  systemctl restart "$SERVICE" || true
  fail "rollback target failed health checks; restored the prior current link"
}

atomic_link "$TARGET"
systemctl restart "$SERVICE" || restore_previous
systemctl is-active --quiet "$SERVICE" || restore_previous

LOCAL_OK="false"
for _ in $(seq 1 30); do
  if curl --silent --show-error --fail --max-time 5 \
    --header "Host: $PUBLIC_HOST" \
    "http://127.0.0.1:18771/api/health" >/dev/null; then
    LOCAL_OK="true"
    break
  fi
  sleep 1
done
[[ "$LOCAL_OK" == "true" ]] || restore_previous
curl --silent --show-error --fail --max-time 15 \
  "$PUBLIC_ORIGIN/api/health" >/dev/null || restore_previous

printf 'ROLLBACK PASS: current -> %s\n' "$RELEASE_ID"
printf 'No release, shared run, account database, backup or Cloudflare setting was removed.\n'
