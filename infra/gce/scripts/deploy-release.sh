#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_TOOL="$SCRIPT_DIR/release-manifest.py"
RELEASE_ROOT="/opt/strayhub/releases"
CURRENT_LINK="/opt/strayhub/current"
CONFIG_ENV="/etc/strayhub/production.env"
SECRETS_ROOT="/var/lib/strayhub/secrets"
STATE_DIR="/var/lib/strayhub/releases"
ARTIFACT_DIR=""
DEPLOYMENT_ROLE=""
CONFIRM_PRODUCTION=""

usage() {
  cat <<'EOF'
Usage: deploy-release.sh \
  --artifact-dir DIRECTORY \
  --deployment-role ROLE \
  --confirm-production DEPLOY_STRAYHUB_PRODUCTION

Deploys an already-published immutable release. It never builds images or downgrades the database.
EOF
}

fail() {
  printf '[GCE release] FAIL: %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact-dir) ARTIFACT_DIR="${2:-}"; shift 2 ;;
    --deployment-role) DEPLOYMENT_ROLE="${2:-}"; shift 2 ;;
    --confirm-production) CONFIRM_PRODUCTION="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown or incomplete argument: $1" ;;
  esac
done

[[ "${EUID:-$(id -u)}" == "0" ]] || fail "run as root through the approved OS Login/IAP path"
[[ "$CONFIRM_PRODUCTION" == "DEPLOY_STRAYHUB_PRODUCTION" ]] || fail "explicit production confirmation is required"
[[ -n "$DEPLOYMENT_ROLE" ]] || fail "--deployment-role is required for provenance"
[[ -d "$ARTIFACT_DIR" ]] || fail "release artifact directory is missing"
[[ -x "$MANIFEST_TOOL" ]] || fail "release manifest tool is unavailable"
for command_name in docker systemctl curl python3; do
  command -v "$command_name" >/dev/null || fail "$command_name is required"
done

# Everything above and through production preflight must pass before the running app is stopped.
"$MANIFEST_TOOL" validate-artifact --artifact-dir "$ARTIFACT_DIR" >/dev/null
manifest="$ARTIFACT_DIR/release-manifest.json"
release_id="$("$MANIFEST_TOOL" show-field --manifest "$manifest" --field release_id)"
migration_revision="$("$MANIFEST_TOOL" show-field --manifest "$manifest" --field migration_revision)"
release_dir="$RELEASE_ROOT/$release_id"
[[ "$release_dir" =~ ^/opt/strayhub/releases/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] ||
  fail "release destination is outside the canonical root"
[[ ! -e "$release_dir" ]] || fail "immutable release directory already exists"
[[ -f "$CONFIG_ENV" ]] || fail "protected production configuration is missing"
[[ -L "$SECRETS_ROOT/current" ]] || fail "current secret generation is missing"
for protected_file in runtime.env jwt-private.pem jwt-public.pem; do
  [[ -s "$SECRETS_ROOT/current/$protected_file" ]] || fail "required protected runtime material is missing"
done

install -d -o root -g root -m 0755 "$RELEASE_ROOT" "$STATE_DIR"
"$MANIFEST_TOOL" extract-artifact --artifact-dir "$ARTIFACT_DIR" --destination "$release_dir"
chown -R root:root "$release_dir"
chmod -R a-w "$release_dir"

image_env="$release_dir/image-digests.env"
runtime_env="$SECRETS_ROOT/current/runtime.env"
compose_file="$release_dir/infra/gce/docker-compose.production.yml"
[[ -f "$compose_file" && -f "$image_env" ]] || fail "extracted release is incomplete"

systemctl restart strayhub-secrets.service
runtime_env="$SECRETS_ROOT/current/runtime.env"
[[ -s "$runtime_env" ]] || fail "fresh secret generation is incomplete"

compose=(
  docker compose
  --project-name strayhub-production
  --file "$compose_file"
  --env-file "$CONFIG_ENV"
  --env-file "$runtime_env"
  --env-file "$image_env"
)

# Exact registry digests are pulled before production preflight; no image is built on the host.
"${compose[@]}" pull api worker web
"$release_dir/infra/gce/scripts/production-preflight.sh" \
  --config-env "$CONFIG_ENV" \
  --secrets-root "$SECRETS_ROOT" \
  --project-name "strayhub-d1-preflight-release" \
  --image-env "$image_env"

previous_release=""
previous_target=""
if [[ -L "$CURRENT_LINK" ]]; then
  previous_target="$(readlink -f "$CURRENT_LINK")"
  if [[ "$previous_target" =~ ^/opt/strayhub/releases/([0-9]{8}T[0-9]{6}Z-[0-9a-f]{12})$ ]]; then
    previous_release="${BASH_REMATCH[1]}"
  fi
fi

runtime_stopped=false
pointer_switched=false
recover_before_switch() {
  local status=$?
  if [[ "$status" -ne 0 && "$runtime_stopped" == true && "$pointer_switched" == false ]]; then
    systemctl start strayhub.service >/dev/null 2>&1 || true
  fi
  if [[ "$status" -ne 0 ]]; then
    printf '[GCE release] deployment did not complete; no success receipt was written\n' >&2
  fi
  return "$status"
}
trap recover_before_switch EXIT

systemctl stop strayhub.service
runtime_stopped=true

# Reuse the accepted one-shot migration service definition with migration-only credentials.
"${compose[@]}" --profile tools run --rm migration
current_output="$("${compose[@]}" --profile tools run --rm --no-deps migration \
  alembic -c services/api/alembic.ini current 2>&1)"
grep -Fq "$migration_revision" <<<"$current_output" || fail "database did not reach manifest migration revision"

temporary_link="/opt/strayhub/.current-${release_id}"
[[ ! -e "$temporary_link" && ! -L "$temporary_link" ]] || fail "temporary current pointer already exists"
ln -s "$release_dir" "$temporary_link"
mv -Tf "$temporary_link" "$CURRENT_LINK"
pointer_switched=true

"$release_dir/infra/gce/scripts/install-systemd-units.sh"
systemctl reset-failed strayhub.service strayhub-migrate.service || true
systemctl restart strayhub.service
runtime_stopped=false

"$release_dir/infra/gce/scripts/verify-systemd-runtime.sh" \
  --config-env "$CONFIG_ENV" \
  --secrets-env "$runtime_env" \
  --image-env "$image_env" \
  --timeout 180

canonical_hostname="$(awk -F= '$1 == "E4_CANONICAL_HOSTNAME" {sub(/^[^=]*=/, ""); print; found = 1} END {exit !found}' "$CONFIG_ENV")"
[[ "$canonical_hostname" == "strayhub.enadv.quest" ]] || fail "canonical public hostname is invalid"
curl --fail --silent --show-error --max-time 15 "https://$canonical_hostname/" >/dev/null
curl --fail --silent --show-error --max-time 15 "https://$canonical_hostname/healthz" >/dev/null

deployed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
receipt="$STATE_DIR/$release_id.json"
"$release_dir/infra/gce/scripts/release-manifest.py" write-receipt \
  --manifest "$release_dir/release-manifest.json" \
  --previous-release "$previous_release" \
  --deployed-at "$deployed_at" \
  --actor "$DEPLOYMENT_ROLE" \
  --output "$receipt"
chmod 0444 "$receipt"
current_receipt="$STATE_DIR/.current.json.tmp"
ln -s "$receipt" "$current_receipt"
mv -Tf "$current_receipt" "$STATE_DIR/current.json"

trap - EXIT
printf '[GCE release] PASS: %s (previous: %s)\n' "$release_id" "${previous_release:-none}"
