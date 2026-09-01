#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/gce/docker-compose.production.yml"
ENV_FILE="${1:-$ROOT_DIR/infra/gce/.env.production.example}"
KEY_GENERATOR="$ROOT_DIR/infra/gce/scripts/generate-verification-jwt-keys.sh"

fail() {
  echo "[Single-edge runtime preflight] FAIL: $*" >&2
  exit 1
}

command -v docker >/dev/null || fail "docker is required"
[[ -f "$COMPOSE_FILE" ]] || fail "Compose file not found: $COMPOSE_FILE"
[[ -f "$ENV_FILE" ]] || fail "environment file not found: $ENV_FILE"
[[ -x "$KEY_GENERATOR" ]] || fail "verification JWT key generator is missing or not executable"

required_vars=(
  APP_ENV
  B1_VERIFICATION_ONLY
  POSTGRES_DB
  POSTGRES_USER
  POSTGRES_PASSWORD
  POSTGRES_RUNTIME_USER
  POSTGRES_RUNTIME_PASSWORD
  DATABASE_URL
  DATABASE_MIGRATION_URL
  MINIO_ENDPOINT
  MINIO_ACCESS_KEY
  MINIO_SECRET_KEY
  MINIO_BUCKET
  LINE_CHANNEL_ID
  LINE_CHANNEL_SECRET
  LINE_CHANNEL_ACCESS_TOKEN
  LIFF_ID
  LINE_ROLE_MENU_FEATURES_ENABLED
  ANIMAL_CONFIRMATION_SECRET
  AUTH_JWT_ISSUER
  AUTH_JWT_AUDIENCE
  AUTH_JWT_ACTIVE_PRIVATE_KEY_REFERENCE
  AUTH_JWT_ACTIVE_PUBLIC_KEY_REFERENCE
  AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE
  AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE
  PII_ENCRYPTION_PROVIDER
  PII_KMS_KEY_NAME
  AI_PROVIDER
  E4_CANONICAL_HOSTNAME
  E4_WEB_UPSTREAM_HOST_PORT
  E4_API_UPSTREAM_HOST_PORT
)

env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found = 1} END {exit !found}' \
    "$ENV_FILE"
}

for key in "${required_vars[@]}"; do
  value="$(env_value "$key" 2>/dev/null || true)"
  [[ -n "$value" ]] || fail "$key is missing or empty"
done

app_env="$(env_value APP_ENV)"
normalized_app_env="$(printf '%s' "$app_env" | tr '[:upper:]' '[:lower:]')"
case "$normalized_app_env" in
  local|test|testing) fail "APP_ENV must be non-local" ;;
esac

[[ "$(env_value B1_VERIFICATION_ONLY)" == "true" ]] || \
  fail "B1_VERIFICATION_ONLY must be true; this preflight is not a real deployment gate"

[[ "$(env_value AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE)" == \
  "./verification/generated/jwt-private.pem" ]] || \
  fail "AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE must use the ignored Phase B1 generated path"
[[ "$(env_value AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE)" == \
  "./verification/generated/jwt-public.pem" ]] || \
  fail "AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE must use the ignored Phase B1 generated path"

"$KEY_GENERATOR" || fail "verification JWT key generation failed"

for key_file_var in AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE; do
  key_file="$(env_value "$key_file_var")"
  [[ -f "$ROOT_DIR/infra/gce/${key_file#./}" ]] || fail "$key_file_var does not exist"
done

[[ "$(env_value E4_CANONICAL_HOSTNAME)" == "strayhub.enadv.quest" ]] || \
  fail "E4_CANONICAL_HOSTNAME must be strayhub.enadv.quest"
[[ "$(env_value E4_WEB_UPSTREAM_HOST_PORT)" == "3000" ]] || \
  fail "E4_WEB_UPSTREAM_HOST_PORT must be 3000"
[[ "$(env_value E4_API_UPSTREAM_HOST_PORT)" == "8080" ]] || \
  fail "E4_API_UPSTREAM_HOST_PORT must be 8080"
[[ "$(env_value LINE_ROLE_MENU_FEATURES_ENABLED)" == "false" ]] || \
  fail "LINE_ROLE_MENU_FEATURES_ENABLED must remain false in synthetic verification"

assigned_values="$(awk '!/^[[:space:]]*(#|$)/ {sub(/^[^=]*=/, ""); print}' "$ENV_FILE")"
if grep -Eiq 'localhost|127\.0\.0\.1|strayhub:strayhub|(^|[^[:alnum:]])(changeme|dummy|placeholder|minioadmin)([^[:alnum:]]|$)|(^|[^[:alnum:]])(fake-|local-only-)' \
  <<<"$assigned_values"; then
  fail "environment file contains a loopback or blocked verification value"
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet

echo "[Single-edge runtime preflight] PASS"
