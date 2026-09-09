#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CONFIG_ENV=""
RUNTIME_ENV=""
IMAGE_ENV=""
CONFIRM=""
DOCKER_BIN="${STRAYHUB_DOCKER_BIN:-docker}"

fail() { echo "[Acceptance cleanup] FAIL: $*" >&2; exit 1; }
while (($#)); do
  case "$1" in
    --config-env) CONFIG_ENV="${2:-}"; shift 2 ;;
    --runtime-env) RUNTIME_ENV="${2:-}"; shift 2 ;;
    --image-env) IMAGE_ENV="${2:-}"; shift 2 ;;
    --confirm) CONFIRM="${2:-}"; shift 2 ;;
    *) fail "unknown or incomplete argument: $1" ;;
  esac
done

[[ "$CONFIRM" == "CLEAN_STRAYHUB_ACCEPTANCE" ]] || fail "explicit acceptance confirmation is required"
for file in "$CONFIG_ENV" "$RUNTIME_ENV" "$IMAGE_ENV"; do [[ -f "$file" ]] || fail "required env file is missing"; done

command -v "$DOCKER_BIN" >/dev/null || fail "docker is required"
compose_environment=(env -i "PATH=$PATH" "HOME=${HOME:-/root}")
[[ -z "${DOCKER_HOST:-}" ]] || compose_environment+=("DOCKER_HOST=$DOCKER_HOST")
[[ -z "${DOCKER_CONFIG:-}" ]] || compose_environment+=("DOCKER_CONFIG=$DOCKER_CONFIG")
compose=("${compose_environment[@]}" "$DOCKER_BIN" compose --project-name strayhub-acceptance --profile tools --env-file "$CONFIG_ENV" --env-file "$RUNTIME_ENV" --env-file "$IMAGE_ENV" --file "$ROOT_DIR/infra/gce/docker-compose.production.yml" --file "$ROOT_DIR/infra/gce/docker-compose.acceptance.yml")
"${compose[@]}" down --volumes --remove-orphans

container_ids="$("$DOCKER_BIN" ps -aq --filter label=com.docker.compose.project=strayhub-acceptance)" ||
  fail "cannot inspect acceptance containers"
volume_ids="$("$DOCKER_BIN" volume ls -q --filter label=com.docker.compose.project=strayhub-acceptance)" ||
  fail "cannot inspect acceptance volumes"
network_ids="$("$DOCKER_BIN" network ls -q --filter label=com.docker.compose.project=strayhub-acceptance)" ||
  fail "cannot inspect acceptance networks"
[[ -z "$container_ids" ]] || fail "acceptance containers remain"
[[ -z "$volume_ids" ]] || fail "acceptance volumes remain"
[[ -z "$network_ids" ]] || fail "acceptance networks remain"
echo "[Acceptance cleanup] PASS"
