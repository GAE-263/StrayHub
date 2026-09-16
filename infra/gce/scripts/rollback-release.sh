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
CONFIRM_ROLLBACK=""

fail() {
  printf '[GCE rollback] REFUSED: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: rollback-release.sh \
  --target-release RELEASE_ID \
  --deployment-role ROLE \
  --confirm-rollback ROLLBACK_STRAYHUB_APPLICATION

Rollback switches application artifacts only. It never runs a database downgrade.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-release) TARGET_RELEASE="${2:-}"; shift 2 ;;
    --deployment-role) DEPLOYMENT_ROLE="${2:-}"; shift 2 ;;
    --confirm-rollback) CONFIRM_ROLLBACK="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown or incomplete argument: $1" ;;
  esac
done

[[ "${EUID:-$(id -u)}" == "0" ]] || fail "run as root through approved OS Login/IAP"
[[ "$TARGET_RELEASE" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] || fail "invalid target release ID"
[[ "$CONFIRM_ROLLBACK" == "ROLLBACK_STRAYHUB_APPLICATION" ]] || fail "explicit rollback confirmation is required"
[[ -n "$DEPLOYMENT_ROLE" ]] || fail "--deployment-role is required"
[[ ! -L "$STATE_DIR/.operation.lock" ]] || fail "invalid operation lock"
exec 9>"$STATE_DIR/.operation.lock"
flock -n 9 || fail "another deployment or recovery holds the host lock"
[[ ! -e "$STATE_DIR/active-deployment.json" && ! -L "$STATE_DIR/active-deployment.json" ]] || fail "incomplete deployment requires recovery first"
[[ -L "$CURRENT_LINK" ]] || fail "current release pointer is missing"
[[ -L "$STATE_DIR/current.json" ]] || fail "successful current deployment receipt is missing"
[[ -f "$CONFIG_ENV" && -s "$SECRETS_ROOT/current/runtime.env" ]] || fail "protected runtime configuration is incomplete"

current_dir="$(readlink -f "$CURRENT_LINK")"
[[ "$current_dir" =~ ^/opt/strayhub/releases/([0-9]{8}T[0-9]{6}Z-[0-9a-f]{12})$ ]] ||
  fail "current release is not an immutable F3 release"
current_release="${BASH_REMATCH[1]}"
[[ "$TARGET_RELEASE" != "$current_release" ]] || fail "target is already current"
target_dir="$RELEASE_ROOT/$TARGET_RELEASE"
[[ -d "$target_dir" ]] || fail "target release directory does not exist"

"$MANIFEST_TOOL" validate-release-dir --release-dir "$current_dir" >/dev/null
"$MANIFEST_TOOL" validate-release-dir --release-dir "$target_dir" >/dev/null
"$MANIFEST_TOOL" validate-receipt --manifest "$current_dir/release-manifest.json" --receipt "$STATE_DIR/current.json"
"$MANIFEST_TOOL" validate-receipt --manifest "$target_dir/release-manifest.json" --receipt "$STATE_DIR/$TARGET_RELEASE.json"
# Fail closed across schema changes; compatible metadata alone cannot prove live DB state.
current_revision="$("$MANIFEST_TOOL" show-field --manifest "$current_dir/release-manifest.json" --field migration_revision)"
target_revision="$("$MANIFEST_TOOL" show-field --manifest "$target_dir/release-manifest.json" --field migration_revision)"
[[ "$current_revision" == "$target_revision" ]] || fail "rollback across migration revisions requires separate review"
"$MANIFEST_TOOL" validate-rollback \
  --current-manifest "$current_dir/release-manifest.json" \
  --target-release "$TARGET_RELEASE" \
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

# Validate and pull N-1 before touching the current runtime. No migration is executed.
for dependency in strayhub-secrets.service strayhub-migrate.service; do
  systemctl is-active --quiet "$dependency" || \
    fail "dependency units must already be active; refusing implicit migration on restart"
done
db_revision="$("${compose[@]}" --profile tools run --rm --no-deps migration alembic -c services/api/alembic.ini current 2>&1)"
python3 "$SCRIPT_DIR/deployment-state.py" head --revision "$current_revision" <<<"$db_revision" || fail "live database revision differs"
"${compose[@]}" pull api worker web
"$target_dir/infra/gce/scripts/production-preflight.sh" \
  --config-env "$CONFIG_ENV" \
  --secrets-root "$SECRETS_ROOT" \
  --project-name "strayhub-d1-preflight-rollback" \
  --image-env "$target_image_env"

pointer_switched=false
restore_current_on_failure() {
  local status=$?
  if [[ "$status" -ne 0 && "$pointer_switched" == true ]]; then
    recovery_link="/opt/strayhub/.current-recovery-${current_release}"
    if [[ ! -e "$recovery_link" && ! -L "$recovery_link" ]]; then
      ln -s "$current_dir" "$recovery_link"
      mv -Tf "$recovery_link" "$CURRENT_LINK"
      "$current_dir/infra/gce/scripts/install-systemd-units.sh" >/dev/null 2>&1 || true
      systemctl restart strayhub.service >/dev/null 2>&1 || true
    fi
    printf '[GCE rollback] target failed; attempted roll-forward to preserved current release\n' >&2
  fi
  return "$status"
}
trap restore_current_on_failure EXIT

systemctl stop strayhub.service
temporary_link="/opt/strayhub/.current-rollback-${TARGET_RELEASE}"
[[ ! -e "$temporary_link" && ! -L "$temporary_link" ]] || fail "temporary rollback pointer exists"
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

rolled_back_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
receipt="$STATE_DIR/rollback-${rolled_back_at//[:\-]/}-$TARGET_RELEASE.json"
"$MANIFEST_TOOL" write-receipt \
  --manifest "$target_dir/release-manifest.json" \
  --previous-release "$current_release" \
  --deployed-at "$rolled_back_at" \
  --actor "$DEPLOYMENT_ROLE" \
  --output "$receipt"
chmod 0444 "$receipt"
current_receipt="$STATE_DIR/.current.json.rollback.tmp"
ln -s "$receipt" "$current_receipt"
mv -Tf "$current_receipt" "$STATE_DIR/current.json"

trap - EXIT
printf '[GCE rollback] PASS: %s -> %s; database downgrade: NONE\n' "$current_release" "$TARGET_RELEASE"
