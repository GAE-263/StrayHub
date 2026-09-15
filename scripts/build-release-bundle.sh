#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_TOOL="$ROOT_DIR/infra/gce/scripts/release-manifest.py"

usage() {
  cat <<'EOF'
Usage: build-release-bundle.sh \
  --git-sha FULL_SHA \
  --api-image REPOSITORY@sha256:DIGEST \
  --worker-image REPOSITORY@sha256:DIGEST \
  --web-image REPOSITORY@sha256:DIGEST \
  --output-dir DIRECTORY \
  [--created-at RFC3339_UTC] \
  [--schema-compatibility unknown|forward-only|backward-compatible-with-previous] \
  [--ci-run-id ID] [--ci-workflow NAME]

The source checkout must be clean and HEAD must equal --git-sha. The output directory must not exist.
EOF
}

fail() {
  printf '[Release bundle] FAIL: %s\n' "$*" >&2
  exit 1
}

git_sha=""
api_image=""
worker_image=""
web_image=""
output_dir=""
created_at=""
schema_compatibility="unknown"
ci_run_id="${GITHUB_RUN_ID:-local-verification}"
ci_workflow="${GITHUB_WORKFLOW:-local-release-verification}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --git-sha) git_sha="${2:-}"; shift 2 ;;
    --api-image) api_image="${2:-}"; shift 2 ;;
    --worker-image) worker_image="${2:-}"; shift 2 ;;
    --web-image) web_image="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --created-at) created_at="${2:-}"; shift 2 ;;
    --schema-compatibility) schema_compatibility="${2:-}"; shift 2 ;;
    --ci-run-id) ci_run_id="${2:-}"; shift 2 ;;
    --ci-workflow) ci_workflow="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$git_sha" =~ ^[0-9a-f]{40}$ ]] || fail "--git-sha must be a full lowercase Git SHA"
[[ -n "$api_image" && -n "$worker_image" && -n "$web_image" ]] || fail "all image references are required"
[[ -n "$output_dir" ]] || fail "--output-dir is required"
[[ -x "$MANIFEST_TOOL" ]] || fail "manifest tool is missing or not executable: $MANIFEST_TOOL"
[[ "$(git -C "$ROOT_DIR" rev-parse HEAD)" == "$git_sha" ]] || fail "HEAD does not match --git-sha"
[[ -z "$(git -C "$ROOT_DIR" status --porcelain)" ]] || fail "source checkout must be clean"
git -C "$ROOT_DIR" cat-file -e "${git_sha}^{commit}" || fail "Git revision is not a commit"
[[ ! -e "$output_dir" ]] || fail "output directory already exists: $output_dir"

if [[ -z "$created_at" ]]; then
  # The commit timestamp makes the default release identity deterministic for a
  # given Git SHA. A rerun may get a different Actions run ID, but it cannot
  # silently create a second timestamp-derived release identity.
  commit_epoch="$(git -C "$ROOT_DIR" show -s --format=%ct "$git_sha")"
  if created_at="$(date -u -d "@$commit_epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"; then
    :
  else
    created_at="$(date -u -r "$commit_epoch" +%Y-%m-%dT%H:%M:%SZ)"
  fi
fi
release_stamp="$(printf '%s' "$created_at" | tr -d ':-' | sed 's/\.000000//; s/\.000//')"
[[ "$release_stamp" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || fail "--created-at must be second-precision RFC3339 UTC"
release_id="${release_stamp}-${git_sha:0:12}"

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/strayhub-release.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT
payload_dir="$work_dir/payload"
mkdir -p "$payload_dir" "$output_dir"

git -C "$ROOT_DIR" archive "$git_sha" \
  infra/gce/docker-compose.production.yml \
  infra/gce/docker-compose.acceptance.yml \
  infra/gce/.env.acceptance.template \
  infra/gce/postgres/init-runtime-role.sh \
  infra/gce/scripts \
  infra/gce/secrets/production-secret-map.tsv \
  infra/gce/secrets/acceptance-secret-map.tsv \
  infra/gce/systemd \
  docs/deployment/acceptance-isolation.md \
  docs/deployment/acceptance-bootstrap.md \
  scripts/verify_acceptance_live.py \
  scripts/production_config_sync.py \
  scripts/line_menu_manifest.py \
  scripts/line_rollout_config.py \
  scripts/line_menu_rollout.py \
  scripts/line_online_operator.py \
  scripts/manual_release_gate.py \
  scripts/release_head_gate.py | tar -x -C "$payload_dir"

printf '%s\n' "$git_sha" >"$payload_dir/revision"
printf 'STRAYHUB_API_IMAGE=%s\n' "$api_image" >"$payload_dir/image-digests.env"
printf 'STRAYHUB_WORKER_IMAGE=%s\n' "$worker_image" >>"$payload_dir/image-digests.env"
printf 'STRAYHUB_WEB_IMAGE=%s\n' "$web_image" >>"$payload_dir/image-digests.env"

migration_revision="$("$MANIFEST_TOOL" migration-head --source-root "$ROOT_DIR")"
"$MANIFEST_TOOL" create-bundle \
  --payload-dir "$payload_dir" \
  --output "$output_dir/deployment-bundle.tar"
"$MANIFEST_TOOL" create-manifest \
  --output "$output_dir/release-manifest.json" \
  --release-id "$release_id" \
  --git-sha "$git_sha" \
  --created-at "$created_at" \
  --api-image "$api_image" \
  --worker-image "$worker_image" \
  --web-image "$web_image" \
  --migration-revision "$migration_revision" \
  --schema-compatibility "$schema_compatibility" \
  --compose "$payload_dir/infra/gce/docker-compose.production.yml" \
  --bundle "$output_dir/deployment-bundle.tar" \
  --ci-run-id "$ci_run_id" \
  --ci-workflow "$ci_workflow"
"$MANIFEST_TOOL" write-checksums --artifact-dir "$output_dir"
"$MANIFEST_TOOL" validate-artifact --artifact-dir "$output_dir"

printf '[Release bundle] PASS: %s\n' "$release_id"
