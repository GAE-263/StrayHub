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

gcloud compute ssh "$INSTANCE" "${gcloud_common[@]}" \
  --command "sudo -n /opt/strayhub/current/infra/gce/scripts/deploy-release.sh \
    --artifact-dir '$remote_dir' \
    --deployment-role 'GitHub Actions production deployer' \
    --confirm-production DEPLOY_STRAYHUB_PRODUCTION"

gcloud compute ssh "$INSTANCE" "${gcloud_common[@]}" \
  --command "rm -f \
    '$remote_dir/release-manifest.json' \
    '$remote_dir/deployment-bundle.tar' \
    '$remote_dir/checksums.sha256' && rmdir '$remote_dir'"

printf '[GCE CI deploy] PASS: exact release %s deployed to %s\n' "$GIT_SHA" "$INSTANCE"
