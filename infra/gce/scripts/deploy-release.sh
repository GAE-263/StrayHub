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
RESUME=false
STATE_TOOL="$SCRIPT_DIR/deployment-state.py"
checkpoint_ready=false

checkpoint_stage() {
  stage="$1"
  if [[ "$checkpoint_ready" == true ]]; then
    python3 "$STATE_TOOL" checkpoint --manifest "$manifest" --state-dir "$STATE_DIR" \
      --current-link "$CURRENT_LINK" --stage "$stage"
  fi
}

usage() {
  cat <<'EOF'
Usage: deploy-release.sh \
  --artifact-dir DIRECTORY \
  --deployment-role ROLE \
  --confirm-production DEPLOY_STRAYHUB_PRODUCTION
  [--resume]

Deploys an already-published immutable release. It never builds images or downgrades the database.
EOF
}

fail() {
  printf '[GCE release] FAIL: %s\n' "$*" >&2
  exit 1
}

stage=validation
last_completed=none
report_deployment_exit() {
  local status=$?
  trap - EXIT
  if [[ "$status" -ne 0 ]]; then
    # A failing command may already have changed DB, pointer, runtime or receipt
    # state. Report acknowledgements, not an assumption that those changes rolled back.
    printf '[GCE release] deployment failed: exit=%s stage=%s last_completed=%s; state requires read-only verification; no automatic recovery attempted\n' \
      "$status" "$stage" "$last_completed" >&2 || :
  fi
  exit "$status"
}
trap report_deployment_exit EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact-dir) ARTIFACT_DIR="${2:-}"; shift 2 ;;
    --deployment-role) DEPLOYMENT_ROLE="${2:-}"; shift 2 ;;
    --confirm-production) CONFIRM_PRODUCTION="${2:-}"; shift 2 ;;
    --resume) RESUME=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown or incomplete argument: $1" ;;
  esac
done

[[ "${EUID:-$(id -u)}" == "0" ]] || fail "run as root through the approved OS Login/IAP path"
[[ "$CONFIRM_PRODUCTION" == "DEPLOY_STRAYHUB_PRODUCTION" ]] || fail "explicit production confirmation is required"
[[ -n "$DEPLOYMENT_ROLE" ]] || fail "--deployment-role is required for provenance"
[[ -d "$ARTIFACT_DIR" ]] || fail "release artifact directory is missing"
[[ -x "$MANIFEST_TOOL" ]] || fail "release manifest tool is unavailable"
for command_name in docker systemctl curl python3 flock cmp; do
  command -v "$command_name" >/dev/null || fail "$command_name is required"
done
install -d -o root -g root -m 0755 "$STATE_DIR"
[[ ! -L "$STATE_DIR/.operation.lock" ]] || fail "operation lock must not be a symlink"
exec 9>"$STATE_DIR/.operation.lock"
flock -n 9 || fail "another deployment or recovery operation holds the host lock"

# Everything above and through production preflight must pass before the running app is stopped.
"$MANIFEST_TOOL" validate-artifact --artifact-dir "$ARTIFACT_DIR" >/dev/null
manifest="$ARTIFACT_DIR/release-manifest.json"
release_id="$("$MANIFEST_TOOL" show-field --manifest "$manifest" --field release_id)"
migration_revision="$("$MANIFEST_TOOL" show-field --manifest "$manifest" --field migration_revision)"
release_dir="$RELEASE_ROOT/$release_id"
[[ "$release_dir" =~ ^/opt/strayhub/releases/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] ||
  fail "release destination is outside the canonical root"
if [[ "$RESUME" != true ]]; then
  [[ ! -e "$release_dir" ]] || fail "immutable release directory already exists; use reviewed --resume"
elif [[ -e "$release_dir" ]]; then
  [[ ! -L "$release_dir" ]] || fail "release directory must not be a symlink"
  "$MANIFEST_TOOL" validate-release-dir --release-dir "$release_dir" >/dev/null
  cmp -s "$manifest" "$release_dir/release-manifest.json" || fail "resume artifact differs from release"
fi
[[ -f "$CONFIG_ENV" ]] || fail "protected production configuration is missing"
[[ -L "$SECRETS_ROOT/current" ]] || fail "current secret generation is missing"
for protected_file in runtime.env jwt-private.pem jwt-public.pem; do
  [[ -s "$SECRETS_ROOT/current/$protected_file" ]] || fail "required protected runtime material is missing"
done

state_args=(--manifest "$manifest" --state-dir "$STATE_DIR" --current-link "$CURRENT_LINK")
if [[ "$RESUME" != true && -L "$CURRENT_LINK" ]]; then
  "$MANIFEST_TOOL" validate-predecessor --manifest "$manifest" \
    --previous-manifest "$CURRENT_LINK/release-manifest.json"
fi
if [[ "$RESUME" == true ]]; then state_args+=(--resume); fi
resume_plan="$(python3 "$STATE_TOOL" plan "${state_args[@]}")"
read -r resume_mode previous_release <<<"$resume_plan"
[[ "$previous_release" != none ]] || previous_release=""
[[ "$resume_mode" == prepare || "$resume_mode" == verify ]] || fail "invalid recovery plan"
checkpoint_ready=true

last_completed=validation
if [[ "$resume_mode" == prepare ]]; then
  checkpoint_stage release_preparation
  install -d -o root -g root -m 0755 "$RELEASE_ROOT" "$STATE_DIR"
  if [[ ! -d "$release_dir" ]]; then
    "$MANIFEST_TOOL" extract-artifact --artifact-dir "$ARTIFACT_DIR" --destination "$release_dir"
  fi
  chown -R root:root "$release_dir"
  chmod -R a-w "$release_dir"
fi

image_env="$release_dir/image-digests.env"
runtime_env="$SECRETS_ROOT/current/runtime.env"
compose_file="$release_dir/infra/gce/docker-compose.production.yml"
[[ -f "$compose_file" && -f "$image_env" ]] || fail "extracted release is incomplete"

last_completed=release_preparation
if [[ "$resume_mode" == prepare ]]; then
  checkpoint_stage secret_materialization
  # Materialize the candidate inventory, not the still-active release's inventory.
  # Restarting the secrets unit here can also stop dependent production units.
  systemctl daemon-reload
  "$release_dir/infra/gce/scripts/fetch-secrets.sh" \
    --project canvas-primacy-502703-k1 \
    --environment prod \
    --output-root "$SECRETS_ROOT" \
    --secret-map "$release_dir/infra/gce/secrets/production-secret-map.tsv"
  chown -R strayhub:strayhub "$SECRETS_ROOT"
  runtime_env="$SECRETS_ROOT/current/runtime.env"
  [[ -s "$runtime_env" ]] || fail "fresh secret generation is incomplete"
  last_completed=secret_materialization
fi

compose=(
  docker compose
  --project-name strayhub-production
  --file "$compose_file"
  --env-file "$CONFIG_ENV"
  --env-file "$runtime_env"
  --env-file "$image_env"
)

# Exact registry digests are pulled before production preflight; no image is built on the host.
if [[ "$resume_mode" == prepare ]]; then
  checkpoint_stage image_pull
  "${compose[@]}" pull api worker web
  last_completed=image_pull
  checkpoint_stage preflight
  "$release_dir/infra/gce/scripts/production-preflight.sh" \
    --config-env "$CONFIG_ENV" \
    --secrets-root "$SECRETS_ROOT" \
    --project-name "strayhub-d1-preflight-release" \
    --image-env "$image_env"

  last_completed=preflight
  checkpoint_stage previous_pointer_read
  previous_target=""
  if [[ -L "$CURRENT_LINK" ]]; then
    previous_target="$(readlink -f "$CURRENT_LINK")"
    [[ "$previous_target" == "$RELEASE_ROOT/$previous_release" ]] || fail "previous pointer changed"
  elif [[ -n "$previous_release" ]]; then
    fail "previous pointer disappeared"
  fi

  last_completed=previous_pointer_read
  checkpoint_stage runtime_stop
  systemctl stop strayhub.service
  last_completed=runtime_stop

  # Reuse the accepted one-shot migration service definition with migration-only credentials.
  checkpoint_stage migration
  "${compose[@]}" --profile tools run --rm migration
  last_completed=migration
fi
# Resume after pointer switch never upgrades or restarts: only read back the DB revision.
# Do not regress the original checkpoint during verify-only recovery.
if [[ "$resume_mode" == prepare ]]; then
  checkpoint_stage migration_head
else
  stage=resume_head_readback
fi
current_output="$("${compose[@]}" --profile tools run --rm --no-deps migration \
  alembic -c services/api/alembic.ini current 2>&1)"
python3 "$STATE_TOOL" head --revision "$migration_revision" <<<"$current_output" || fail "database did not reach manifest migration revision"
last_completed=migration_head

if [[ "$resume_mode" == prepare ]]; then
  checkpoint_stage pointer_prepare
  temporary_link="/opt/strayhub/.current-${release_id}"
  [[ ! -e "$temporary_link" && ! -L "$temporary_link" ]] || fail "temporary current pointer already exists"
  ln -s "$release_dir" "$temporary_link"
  last_completed=pointer_prepare
  checkpoint_stage pointer_switch
  mv -Tf "$temporary_link" "$CURRENT_LINK"
  last_completed=pointer_switch

  checkpoint_stage unit_install
  "$release_dir/infra/gce/scripts/install-systemd-units.sh"
  systemctl reset-failed strayhub.service strayhub-migrate.service || true
  last_completed=unit_install
  checkpoint_stage runtime_start
  systemctl restart strayhub.service
  last_completed=runtime_start
fi

checkpoint_stage runtime_verification
"$release_dir/infra/gce/scripts/verify-systemd-runtime.sh" \
  --config-env "$CONFIG_ENV" \
  --secrets-env "$runtime_env" \
  --image-env "$image_env" \
  --timeout 180
last_completed=runtime_verification

checkpoint_stage public_verification
canonical_hostname="$(awk -F= '$1 == "E4_CANONICAL_HOSTNAME" {sub(/^[^=]*=/, ""); print; found = 1} END {exit !found}' "$CONFIG_ENV")"
[[ "$canonical_hostname" == "strayhub.enadv.quest" ]] || fail "canonical public hostname is invalid"
curl --fail --silent --show-error --max-time 15 "https://$canonical_hostname/" >/dev/null
curl --fail --silent --show-error --max-time 15 "https://$canonical_hostname/healthz" >/dev/null
last_completed=public_verification

checkpoint_stage receipt_write
deployed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
receipt="$STATE_DIR/$release_id.json"
if [[ -e "$receipt" || -L "$receipt" ]]; then
  [[ ! -L "$receipt" ]] || fail "receipt must not be a symlink"
  "$MANIFEST_TOOL" validate-receipt --manifest "$manifest" --receipt "$receipt" \
    --previous-release "$previous_release"
else
  "$release_dir/infra/gce/scripts/release-manifest.py" write-receipt \
    --manifest "$release_dir/release-manifest.json" \
    --previous-release "$previous_release" \
    --deployed-at "$deployed_at" \
    --actor "$DEPLOYMENT_ROLE" \
    --output "$receipt"
fi
chmod 0444 "$receipt"
last_completed=receipt_write
checkpoint_stage receipt_activation
current_receipt="$STATE_DIR/.current.json.tmp"
if [[ -L "$current_receipt" ]]; then
  [[ "$(readlink -f "$current_receipt")" == "$receipt" ]] || fail "conflicting receipt staging pointer"
else
  [[ ! -e "$current_receipt" ]] || fail "receipt staging path occupied"
  ln -s "$receipt" "$current_receipt"
fi
mv -Tf "$current_receipt" "$STATE_DIR/current.json"
last_completed=receipt_activation
checkpoint_stage complete
python3 "$STATE_TOOL" clear --manifest "$manifest" --state-dir "$STATE_DIR" --current-link "$CURRENT_LINK"

trap - EXIT
printf '[GCE release] PASS: %s (previous: %s)\n' "$release_id" "${previous_release:-none}"
