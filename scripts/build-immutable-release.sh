#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_BUILDER="$ROOT_DIR/scripts/build-release-bundle.sh"
MANIFEST_TOOL="$ROOT_DIR/infra/gce/scripts/release-manifest.py"
ARTIFACT_DOCKERFILE="$ROOT_DIR/infra/gce/images/Dockerfile.release-artifact"

usage() {
  cat <<'EOF'
Usage: build-immutable-release.sh \
  --git-sha FULL_SHA \
  --registry HOST/PROJECT/REPOSITORY \
  --output-dir DIRECTORY \
  [--reuse-only]

The registry tag is the full Git SHA. Existing tags are read back and reused;
an existing release artifact is extracted and validated without rebuilding.
EOF
}

fail() {
  printf '[Immutable release] FAIL: %s\n' "$*" >&2
  exit 1
}

git_sha=""
registry=""
output_dir=""
reuse_only=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --git-sha) git_sha="${2:-}"; shift 2 ;;
    --registry) registry="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    --reuse-only) reuse_only=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$git_sha" =~ ^[0-9a-f]{40}$ ]] || fail "--git-sha must be a full lowercase Git SHA"
[[ "$registry" =~ ^[a-z0-9.-]+-docker\.pkg\.dev/[a-z0-9-]+/[a-z0-9-]+$ ]] || \
  fail "--registry must be a concrete Artifact Registry repository"
[[ -n "$output_dir" ]] || fail "--output-dir is required"
[[ ! -e "$output_dir" ]] || fail "output directory already exists: $output_dir"
[[ -x "$BUNDLE_BUILDER" ]] || fail "bundle builder is missing or not executable"
[[ -x "$MANIFEST_TOOL" ]] || fail "manifest tool is missing or not executable"
[[ -f "$ARTIFACT_DOCKERFILE" ]] || fail "release artifact Dockerfile is missing"
command -v docker >/dev/null || fail "docker is required"
command -v gcloud >/dev/null || fail "gcloud is required"
[[ "$(git -C "$ROOT_DIR" rev-parse HEAD)" == "$git_sha" ]] || fail "HEAD does not match --git-sha"
[[ -z "$(git -C "$ROOT_DIR" status --porcelain)" ]] || fail "source checkout must be clean"

mkdir -p "$output_dir"
cleanup() {
  if [[ -n "${artifact_container:-}" ]]; then
    docker rm "$artifact_container" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

image_digest() {
  local image="$1"
  local digest
  digest="$(gcloud artifacts docker images describe "$image" --format='value(image_summary.digest)' 2>/dev/null || true)"
  if [[ -n "$digest" && ! "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    fail "registry returned an invalid digest for $image"
  fi
  printf '%s' "$digest"
}

build_or_reuse_image() {
  local service="$1"
  local image="$registry/strayhub-$service:$git_sha"
  local digest
  local -a cache_args=()
  if [[ -n "${ACTIONS_CACHE_URL:-}" && -n "${ACTIONS_RUNTIME_TOKEN:-}" ]]; then
    cache_args=(
      --cache-from "type=gha,scope=strayhub-$service"
      --cache-to "type=gha,mode=max,scope=strayhub-$service"
    )
  fi
  digest="$(image_digest "$image")"
  if [[ -z "$digest" ]]; then
    docker buildx build \
      --push \
      --provenance=true \
      --sbom=false \
      "${cache_args[@]}" \
      --label "org.opencontainers.image.revision=$git_sha" \
      --label "org.opencontainers.image.source=${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-GAE-263/StrayHub}" \
      --file "$ROOT_DIR/infra/gce/images/Dockerfile.$service" \
      --tag "$image" \
      "$ROOT_DIR"
    digest="$(image_digest "$image")"
  fi
  [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "image digest readback failed for $image"
  printf '%s@%s' "${image%%:*}" "$digest"
}

artifact_tag="$registry/strayhub-release:$git_sha"
artifact_digest="$(image_digest "$artifact_tag")"
if [[ -n "$artifact_digest" ]]; then
  artifact_container="$(docker create "$artifact_tag")"
  docker cp "$artifact_container:/release-manifest.json" "$output_dir/release-manifest.json"
  docker cp "$artifact_container:/checksums.sha256" "$output_dir/checksums.sha256"
  docker cp "$artifact_container:/deployment-bundle.tar" "$output_dir/deployment-bundle.tar"
  docker cp "$artifact_container:/release-identity.json" "$output_dir/release-identity.json"
  "$MANIFEST_TOOL" validate-artifact --artifact-dir "$output_dir"
  manifest_sha256="$(sha256sum "$output_dir/release-manifest.json" | awk '{print $1}')"
  bundle_sha256="$(sha256sum "$output_dir/deployment-bundle.tar" | awk '{print $1}')"
  python3 - "$output_dir" "$git_sha" "$manifest_sha256" "$bundle_sha256" <<'PY'
import json
import pathlib
import sys

artifact_dir = pathlib.Path(sys.argv[1])
expected_sha, expected_manifest, expected_bundle = sys.argv[2:]
manifest = json.loads((artifact_dir / "release-manifest.json").read_text())
identity = json.loads((artifact_dir / "release-identity.json").read_text())
if manifest["git_sha"] != expected_sha or identity.get("git_sha") != expected_sha:
    raise SystemExit("existing release artifact Git SHA mismatch")
if identity.get("release_id") != manifest["release_id"]:
    raise SystemExit("existing release identity release_id mismatch")
if identity.get("manifest_sha256") != expected_manifest:
    raise SystemExit("existing release identity manifest checksum mismatch")
if identity.get("bundle_sha256") != expected_bundle:
    raise SystemExit("existing release identity bundle checksum mismatch")
for service in ("api", "worker", "web"):
    expected_image = f'{manifest["images"][service]["repository"]}@{manifest["images"][service]["digest"]}'
    if identity.get("images", {}).get(service) != expected_image:
        raise SystemExit(f"existing release identity {service} image mismatch")
PY
  printf '[Immutable release] PASS: reused %s@%s\n' "${artifact_tag%%:*}" "$artifact_digest"
  printf 'artifact_image=%s@%s\n' "${artifact_tag%%:*}" "$artifact_digest" >"$output_dir/artifact-identity.env"
  printf 'manifest_sha256=%s\n' "$manifest_sha256" >>"$output_dir/artifact-identity.env"
  printf 'bundle_sha256=%s\n' "$bundle_sha256" >>"$output_dir/artifact-identity.env"
  exit 0
fi

if [[ "$reuse_only" == true ]]; then
  fail "canonical release artifact does not exist for $git_sha; refusing to build from a non-main workflow"
fi

api_image="$(build_or_reuse_image api)"
worker_image="$(build_or_reuse_image worker)"
web_image="$(build_or_reuse_image web)"

"$BUNDLE_BUILDER" \
  --git-sha "$git_sha" \
  --api-image "$api_image" \
  --worker-image "$worker_image" \
  --web-image "$web_image" \
  --output-dir "$output_dir" \
  --schema-compatibility unknown \
  --ci-run-id "${GITHUB_RUN_ID:-local-verification}" \
  --ci-workflow "${GITHUB_WORKFLOW:-Build Immutable Release}"

manifest_sha256="$(sha256sum "$output_dir/release-manifest.json" | awk '{print $1}')"
bundle_sha256="$(sha256sum "$output_dir/deployment-bundle.tar" | awk '{print $1}')"
release_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["release_id"])' "$output_dir/release-manifest.json")"
cat >"$output_dir/release-identity.json" <<EOF
{
  "schema_version": 1,
  "git_sha": "$git_sha",
  "release_id": "$release_id",
  "images": {
    "api": "$api_image",
    "worker": "$worker_image",
    "web": "$web_image"
  },
  "manifest_sha256": "$manifest_sha256",
  "bundle_sha256": "$bundle_sha256"
}
EOF

docker buildx build \
  --push \
  --provenance=true \
  --sbom=false \
  --label "org.opencontainers.image.revision=$git_sha" \
  --label "org.opencontainers.image.source=${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-GAE-263/StrayHub}" \
  --file "$ARTIFACT_DOCKERFILE" \
  --tag "$artifact_tag" \
  "$output_dir"

artifact_digest="$(image_digest "$artifact_tag")"
[[ "$artifact_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "release artifact digest readback failed"
printf 'artifact_image=%s@%s\n' "${artifact_tag%%:*}" "$artifact_digest" >"$output_dir/artifact-identity.env"
printf 'manifest_sha256=%s\n' "$manifest_sha256" >>"$output_dir/artifact-identity.env"
printf 'bundle_sha256=%s\n' "$bundle_sha256" >>"$output_dir/artifact-identity.env"
printf '[Immutable release] PASS: %s@%s\n' "${artifact_tag%%:*}" "$artifact_digest"
