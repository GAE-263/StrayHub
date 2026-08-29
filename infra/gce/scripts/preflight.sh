#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/infra/gce/docker-compose.production.yml"
ENV_FILE="${1:-$ROOT_DIR/infra/gce/.env.production.example}"
KEY_GENERATOR="$ROOT_DIR/infra/gce/scripts/generate-verification-jwt-keys.sh"
TLS_GENERATOR="$ROOT_DIR/infra/gce/scripts/generate-verification-tls-cert.sh"
NGINX_CONFIG="$ROOT_DIR/infra/gce/nginx/strayhub.conf"

fail() {
  echo "[Phase B4 preflight] FAIL: $*" >&2
  exit 1
}

command -v docker >/dev/null || fail "docker is required"
[[ -f "$COMPOSE_FILE" ]] || fail "Compose file not found: $COMPOSE_FILE"
[[ -f "$ENV_FILE" ]] || fail "environment file not found: $ENV_FILE"
[[ -f "$NGINX_CONFIG" ]] || fail "nginx config not found: $NGINX_CONFIG"
[[ -x "$KEY_GENERATOR" ]] || fail "verification JWT key generator is missing or not executable"
[[ -x "$TLS_GENERATOR" ]] || fail "verification TLS generator is missing or not executable"

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
  B4_HTTP_HOST_PORT
  B4_HTTPS_HOST_PORT
  B4_LETSENCRYPT_DIR
  B4_ACME_WEBROOT
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
"$TLS_GENERATOR" || fail "verification TLS certificate generation failed"

for key_file_var in AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE; do
  key_file="$(env_value "$key_file_var")"
  [[ -f "$ROOT_DIR/infra/gce/${key_file#./}" ]] || fail "$key_file_var does not exist"
done

[[ "$(env_value B4_LETSENCRYPT_DIR)" == "./verification/generated/tls" ]] || \
  fail "B4_LETSENCRYPT_DIR must use the ignored Phase B4 generated path"
[[ "$(env_value B4_ACME_WEBROOT)" == "./verification/generated/acme-webroot" ]] || \
  fail "B4_ACME_WEBROOT must use the ignored Phase B4 generated path"
tls_private="$ROOT_DIR/infra/gce/verification/generated/tls/live/strayhub/privkey.pem"
tls_certificate="$ROOT_DIR/infra/gce/verification/generated/tls/live/strayhub/fullchain.pem"
acme_webroot="$ROOT_DIR/infra/gce/verification/generated/acme-webroot"
[[ -f "$tls_private" && -f "$tls_certificate" ]] || fail "verification TLS files do not exist"
git -C "$ROOT_DIR" check-ignore -q "infra/gce/verification/generated/tls/live/strayhub/privkey.pem" || \
  fail "verification TLS private key is not ignored by Git"
if git -C "$ROOT_DIR" ls-files --error-unmatch \
  "infra/gce/verification/generated/tls/live/strayhub/privkey.pem" >/dev/null 2>&1; then
  fail "verification TLS private key is tracked by Git"
fi

assigned_values="$(awk '!/^[[:space:]]*(#|$)/ {sub(/^[^=]*=/, ""); print}' "$ENV_FILE")"
if grep -Eiq 'localhost|127\.0\.0\.1|strayhub:strayhub|(^|[^[:alnum:]])(changeme|dummy|placeholder|minioadmin)([^[:alnum:]]|$)|(^|[^[:alnum:]])(fake-|local-only-)' \
  <<<"$assigned_values"; then
  fail "environment file contains a loopback or blocked verification value"
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet
nginx_image="$(
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --images |
    awk '/^nginx:/ {print; exit}'
)"
[[ -n "$nginx_image" ]] || fail "nginx image is missing from the rendered Compose model"

docker run --rm \
  --add-host api:127.0.0.1 \
  --add-host web:127.0.0.1 \
  --volume "$NGINX_CONFIG:/etc/nginx/conf.d/default.conf:ro" \
  --volume "$ROOT_DIR/infra/gce/verification/generated/tls:/etc/letsencrypt:ro" \
  --volume "$acme_webroot:/var/www/certbot:ro" \
  "$nginx_image" nginx -t >/dev/null || fail "nginx syntax validation failed"

echo "[Phase B4 preflight] PASS"
