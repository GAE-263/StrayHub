#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT_DIR"
COMPOSE_FILE="$ROOT_DIR/infra/gce/docker-compose.production.yml"
CONFIG_ENV="/etc/strayhub/production.env"
SECRETS_ENV="/var/lib/strayhub/secrets/current/runtime.env"
TIMEOUT=180

fail() {
  printf '[Systemd runtime health] FAIL: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --config-env) CONFIG_ENV="${2:-}"; shift 2 ;;
    --secrets-env) SECRETS_ENV="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT="${2:-}"; shift 2 ;;
    *) fail "unknown or incomplete argument: $1" ;;
  esac
done

[[ -f "$CONFIG_ENV" ]] || fail "production config is missing"
[[ -f "$SECRETS_ENV" ]] || fail "staged runtime environment is missing"
[[ "$TIMEOUT" =~ ^[1-9][0-9]{0,3}$ ]] || fail "timeout must be 1-9999 seconds"
command -v docker >/dev/null || fail "docker is required"
command -v curl >/dev/null || fail "curl is required"

env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found = 1} END {exit !found}' \
    "$CONFIG_ENV"
}

canonical_hostname="$(env_value E4_CANONICAL_HOSTNAME 2>/dev/null || true)"
web_port="$(env_value E4_WEB_UPSTREAM_HOST_PORT 2>/dev/null || true)"
api_port="$(env_value E4_API_UPSTREAM_HOST_PORT 2>/dev/null || true)"
[[ "$canonical_hostname" == "strayhub.enadv.quest" ]] || fail "canonical hostname is invalid"
[[ "$web_port" == "3000" ]] || fail "Web upstream host port must be 3000"
[[ "$api_port" == "8080" ]] || fail "API upstream host port must be 8080"

compose=(
  docker compose
  --project-name strayhub-production
  --file "$COMPOSE_FILE"
  --env-file "$CONFIG_ENV"
  --env-file "$SECRETS_ENV"
)

container_ready() {
  local service="$1"
  local require_health="$2"
  local container_id state health
  container_id="$("${compose[@]}" ps -q "$service")"
  [[ -n "$container_id" ]] || return 1
  state="$(docker inspect --format '{{.State.Status}}' "$container_id")"
  [[ "$state" == "running" ]] || return 1
  if [[ "$require_health" == true ]]; then
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container_id")"
    [[ "$health" == "healthy" ]] || return 1
  fi
}

endpoint_code() {
  local port="$1"
  local path="$2"
  curl --silent --show-error --output /dev/null --max-time 5 \
    --header "Host: $canonical_hostname" --write-out '%{http_code}' \
    "http://127.0.0.1:$port$path" 2>/dev/null || true
}

runtime_ready() {
  container_ready postgres true || return 1
  container_ready minio true || return 1
  container_ready api true || return 1
  container_ready web true || return 1
  container_ready worker false || return 1
  [[ "$(endpoint_code "$api_port" /healthz)" == "200" ]] || return 1
  [[ "$(endpoint_code "$web_port" /)" == "200" ]] || return 1
  [[ "$(endpoint_code "$api_port" /v1/public/volunteer-organizations)" == "200" ]] || return 1
  [[ "$(endpoint_code "$web_port" /volunteer-application)" == "200" ]] || return 1
  [[ "$(endpoint_code "$api_port" /v1/line/webhook)" == "405" ]] || return 1
}

deadline=$((SECONDS + TIMEOUT))
until runtime_ready; do
  ((SECONDS < deadline)) || {
    "${compose[@]}" ps >&2 || true
    fail "runtime did not become healthy within ${TIMEOUT}s"
  }
  sleep 3
done

printf '[Systemd runtime health] PASS: direct API/Web upstreams, Worker, PostgreSQL, and MinIO\n'
