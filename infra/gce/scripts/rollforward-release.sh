#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_TOOL="$SCRIPT_DIR/release-manifest.py"
RELEASE_ROOT="/opt/strayhub/releases"
CURRENT_LINK="/opt/strayhub/current"
CONFIG_ENV="/etc/strayhub/production.env"
SECRETS_ROOT="/var/lib/strayhub/secrets"
STATE_DIR="/var/lib/strayhub/releases"
TARGET_RELEASE=""
DEPLOYMENT_ROLE=""
CONFIRM_ROLLFORWARD=""

fail() {
  printf '[GCE roll-forward] REFUSED: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: rollforward-release.sh \
  --target-release RELEASE_ID \
  --deployment-role ROLE \
  --confirm-rollforward ROLLFORWARD_STRAYHUB_APPLICATION

Roll-forward reactivates the recorded newer release after a successful rollback. It never runs a
migration or rebuilds an image, and it requires equal migration revisions.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-release) TARGET_RELEASE="${2:-}"; shift 2 ;;
    --deployment-role) DEPLOYMENT_ROLE="${2:-}"; shift 2 ;;
    --confirm-rollforward) CONFIRM_ROLLFORWARD="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown or incomplete argument: $1" ;;
  esac
done

[[ "${EUID:-$(id -u)}" == "0" ]] || fail "run as root through approved OS Login/IAP"
[[ "$TARGET_RELEASE" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] || fail "invalid target release ID"
[[ "$CONFIRM_ROLLFORWARD" == "ROLLFORWARD_STRAYHUB_APPLICATION" ]] ||
  fail "explicit roll-forward confirmation is required"
[[ -n "$DEPLOYMENT_ROLE" ]] || fail "--deployment-role is required"
[[ -L "$CURRENT_LINK" ]] || fail "current release pointer is missing"
[[ -L "$STATE_DIR/current.json" ]] || fail "successful current deployment receipt is missing"
[[ -f "$CONFIG_ENV" && -s "$SECRETS_ROOT/current/runtime.env" ]] ||
  fail "protected runtime configuration is incomplete"

current_dir="$(readlink -f "$CURRENT_LINK")"
[[ "$current_dir" =~ ^/opt/strayhub/releases/([0-9]{8}T[0-9]{6}Z-[0-9a-f]{12})$ ]] ||
  fail "current release is not immutable"
current_release="${BASH_REMATCH[1]}"
[[ "$TARGET_RELEASE" != "$current_release" ]] || fail "target is already current"
target_dir="$RELEASE_ROOT/$TARGET_RELEASE"
[[ -d "$target_dir" ]] || fail "target release directory does not exist"

"$MANIFEST_TOOL" validate-release-dir --release-dir "$current_dir" >/dev/null
"$MANIFEST_TOOL" validate-release-dir --release-dir "$target_dir" >/dev/null
"$MANIFEST_TOOL" validate-rollforward \
  --current-manifest "$current_dir/release-manifest.json" \
  --target-manifest "$target_dir/release-manifest.json" \
  --receipt "$STATE_DIR/current.json" >/dev/null

runtime_env="$SECRETS_ROOT/current/runtime.env"
target_image_env="$target_dir/image-digests.env"
target_compose="$target_dir/infra/gce/docker-compose.production.yml"
compose=(
  docker compose
  --project-name strayhub-production
  --file "$target_compose"
  --env-file "$CONFIG_ENV"
  --env-file "$runtime_env"
  --env-file "$target_image_env"
)

"${compose[@]}" pull api worker web
"$target_dir/infra/gce/scripts/production-preflight.sh" \
  --config-env "$CONFIG_ENV" \
  --secrets-root "$SECRETS_ROOT" \
  --project-name "strayhub-d1-preflight-rollforward" \
  --image-env "$target_image_env"

pointer_switched=false
recovery_link="/opt/strayhub/.current-rollforward-recovery-${current_release}-$$"
temporary_link="/opt/strayhub/.current-rollforward-${TARGET_RELEASE}"
[[ ! -e "$recovery_link" && ! -L "$recovery_link" ]] ||
  fail "temporary recovery pointer exists"
[[ ! -e "$temporary_link" && ! -L "$temporary_link" ]] ||
  fail "temporary roll-forward pointer exists"
restore_current_on_failure() {
  local status=$?
  if [[ "$status" -ne 0 && "$pointer_switched" == true ]]; then
    ln -s "$current_dir" "$recovery_link"
    mv -Tf "$recovery_link" "$CURRENT_LINK"
    "$current_dir/infra/gce/scripts/install-systemd-units.sh" >/dev/null 2>&1 || true
    systemctl restart strayhub.service >/dev/null 2>&1 || true
    printf '[GCE roll-forward] target failed; restored preserved rollback release\n' >&2
  fi
  return "$status"
}
trap restore_current_on_failure EXIT

systemctl stop strayhub.service
ln -s "$target_dir" "$temporary_link"
mv -Tf "$temporary_link" "$CURRENT_LINK"
pointer_switched=true

"$target_dir/infra/gce/scripts/install-systemd-units.sh"
systemctl restart strayhub.service
"$target_dir/infra/gce/scripts/verify-systemd-runtime.sh" \
  --config-env "$CONFIG_ENV" \
  --secrets-env "$runtime_env" \
  --image-env "$target_image_env" \
  --timeout 180

canonical_hostname="$(awk -F= '$1 == "E4_CANONICAL_HOSTNAME" {sub(/^[^=]*=/, ""); print; found = 1} END {exit !found}' "$CONFIG_ENV")"
[[ "$canonical_hostname" == "strayhub.enadv.quest" ]] || fail "canonical public hostname is invalid"
curl --fail --silent --show-error --max-time 15 "https://$canonical_hostname/" >/dev/null
curl --fail --silent --show-error --max-time 15 "https://$canonical_hostname/healthz" >/dev/null

rolled_forward_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
receipt="$STATE_DIR/rollforward-${rolled_forward_at//[:\-]/}-$TARGET_RELEASE.json"
"$MANIFEST_TOOL" write-receipt \
  --manifest "$target_dir/release-manifest.json" \
  --previous-release "$current_release" \
  --deployed-at "$rolled_forward_at" \
  --actor "$DEPLOYMENT_ROLE" \
  --output "$receipt"
chmod 0444 "$receipt"
current_receipt="$STATE_DIR/.current.json.rollforward.tmp"
ln -s "$receipt" "$current_receipt"
mv -Tf "$current_receipt" "$STATE_DIR/current.json"

trap - EXIT
printf '[GCE roll-forward] PASS: %s -> %s; migration: NONE\n' "$current_release" "$TARGET_RELEASE"
