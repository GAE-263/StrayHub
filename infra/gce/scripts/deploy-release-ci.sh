#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_TOOL="$SCRIPT_DIR/release-manifest.py"
ARTIFACT_DIR=""
GIT_SHA=""
INSTANCE=""
PROJECT=""
RUN_ID=""
ZONE=""

usage() {
  cat <<'EOF'
Usage: deploy-release-ci.sh \
  --artifact-dir DIRECTORY \
  --git-sha FULL_SHA \
  --instance INSTANCE \
  --project PROJECT_ID \
  --run-id GITHUB_RUN_ID \
  --zone ZONE

Transfers one validated, non-secret immutable release over IAP and invokes the canonical host
deployment script. The remote staging directory is removed only after a successful deployment.
EOF
}

fail() {
  printf '[GCE CI deploy] FAIL: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --artifact-dir) ARTIFACT_DIR="${2:-}"; shift 2 ;;
    --git-sha) GIT_SHA="${2:-}"; shift 2 ;;
    --instance) INSTANCE="${2:-}"; shift 2 ;;
    --project) PROJECT="${2:-}"; shift 2 ;;
    --run-id) RUN_ID="${2:-}"; shift 2 ;;
    --zone) ZONE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown or incomplete argument: $1" ;;
  esac
done

[[ -d "$ARTIFACT_DIR" ]] || fail "release artifact directory is missing"
[[ "$GIT_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "--git-sha must be a full lowercase Git SHA"
[[ "$INSTANCE" =~ ^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$ ]] || fail "invalid instance"
[[ "$PROJECT" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || fail "invalid project"
[[ "$RUN_ID" =~ ^[1-9][0-9]{0,19}$ ]] || fail "invalid run ID"
[[ "$ZONE" =~ ^[a-z]+-[a-z]+[0-9]+-[a-z]$ ]] || fail "invalid zone"
[[ -x "$MANIFEST_TOOL" ]] || fail "release manifest tool is unavailable"
command -v gcloud >/dev/null || fail "gcloud is required"

"$MANIFEST_TOOL" validate-artifact --artifact-dir "$ARTIFACT_DIR" >/dev/null
manifest_sha="$(
  "$MANIFEST_TOOL" show-field \
    --manifest "$ARTIFACT_DIR/release-manifest.json" \
    --field git_sha
)"
[[ "$manifest_sha" == "$GIT_SHA" ]] || fail "artifact Git SHA does not match deployment SHA"

remote_dir="/tmp/strayhub-ci-release-${RUN_ID}-${GIT_SHA}"
remote_target="${INSTANCE}:${remote_dir}/"
gcloud_common=(--project "$PROJECT" --zone "$ZONE" --tunnel-through-iap --quiet)

gcloud compute ssh "$INSTANCE" "${gcloud_common[@]}" \
  --command "install -d -m 0700 '$remote_dir'"
gcloud compute scp "${gcloud_common[@]}" \
  "$ARTIFACT_DIR/release-manifest.json" \
  "$ARTIFACT_DIR/deployment-bundle.tar" \
  "$ARTIFACT_DIR/checksums.sha256" \
  "$remote_target"

# The old release validates the envelope, but must not supply the deployment logic:
# its secret inventory and preflight can be older than the incoming Compose contract.
# Copy into a root-owned parent before validation/execution, avoiding writable IAP
# staging paths during privileged execution. Retain the bootstrap as failure evidence.
bootstrap_command="$(cat <<'BOOTSTRAP'
set -euo pipefail
artifact_source="$1"
expected_sha="$2"
validator=/opt/strayhub/current/infra/gce/scripts/release-manifest.py
bootstrap_dir="$(mktemp -d /var/lib/strayhub/releases/.deploy-bootstrap.XXXXXX)"
for file in release-manifest.json deployment-bundle.tar checksums.sha256; do
  install -o root -g root -m 0444 "$artifact_source/$file" "$bootstrap_dir/$file"
done
"$validator" validate-artifact --artifact-dir "$bootstrap_dir" >/dev/null
actual_sha="$("$validator" show-field --manifest "$bootstrap_dir/release-manifest.json" --field git_sha)"
[[ "$actual_sha" == "$expected_sha" ]]
"$validator" extract-artifact --artifact-dir "$bootstrap_dir" --destination "$bootstrap_dir/payload"
chown -R root:root "$bootstrap_dir"
chmod -R a-w "$bootstrap_dir"
exec "$bootstrap_dir/payload/infra/gce/scripts/deploy-release.sh" \
  --artifact-dir "$bootstrap_dir" \
  --deployment-role 'GitHub Actions production deployer' \
  --confirm-production DEPLOY_STRAYHUB_PRODUCTION
BOOTSTRAP
)"
printf -v quoted_bootstrap '%q' "$bootstrap_command"
gcloud compute ssh "$INSTANCE" "${gcloud_common[@]}" \
  --command "sudo -n bash -c $quoted_bootstrap -- '$remote_dir' '$GIT_SHA'"

gcloud compute ssh "$INSTANCE" "${gcloud_common[@]}" \
  --command "rm -f \
    '$remote_dir/release-manifest.json' \
    '$remote_dir/deployment-bundle.tar' \
    '$remote_dir/checksums.sha256' && rmdir '$remote_dir'"

printf '[GCE CI deploy] PASS: exact release %s deployed to %s\n' "$GIT_SHA" "$INSTANCE"
