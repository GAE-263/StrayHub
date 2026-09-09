#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT_DIR"
COMPOSE_FILE="$ROOT_DIR/infra/gce/docker-compose.production.yml"
CONFIG_ENV=""
SECRETS_ROOT="/var/lib/strayhub/secrets"
PROJECT_NAME="strayhub-d1-preflight-$$"
IMAGE_ENV=""

usage() {
  echo "Usage: $0 --config-env PATH [--secrets-root PATH] [--project-name NAME] [--image-env PATH]" >&2
}

fail() {
  echo "[Production secret preflight] FAIL: $*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --config-env) CONFIG_ENV="${2:-}"; shift 2 ;;
    --secrets-root) SECRETS_ROOT="${2:-}"; shift 2 ;;
    --project-name) PROJECT_NAME="${2:-}"; shift 2 ;;
    --image-env) IMAGE_ENV="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; fail "unknown or incomplete argument: $1" ;;
  esac
done

command -v docker >/dev/null || fail "docker is required"
command -v openssl >/dev/null || fail "openssl is required"
[[ "$PROJECT_NAME" =~ ^strayhub-d1-preflight-[a-z0-9_-]{1,40}$ ]] ||
  fail "--project-name must use the isolated strayhub-d1-preflight-* prefix"
[[ -f "$CONFIG_ENV" ]] || fail "--config-env must name a protected non-secret config file"
if [[ -n "$IMAGE_ENV" ]]; then
  [[ -f "$IMAGE_ENV" ]] || fail "--image-env must name an immutable image reference file"
  for image_key in STRAYHUB_API_IMAGE STRAYHUB_WORKER_IMAGE STRAYHUB_WEB_IMAGE; do
    image_value="$(awk -F= -v key="$image_key" '$1 == key {sub(/^[^=]*=/, ""); print; found = 1} END {exit !found}' "$IMAGE_ENV" 2>/dev/null || true)"
    [[ "$image_value" =~ ^[a-z0-9][a-z0-9._/-]*[a-z0-9]@sha256:[0-9a-f]{64}$ ]] ||
      fail "$image_key must use an exact repository@sha256 digest"
  done
fi
[[ -d "$SECRETS_ROOT" ]] || fail "secret staging root does not exist"
SECRETS_ROOT="$(cd "$SECRETS_ROOT" && pwd -P)"
current="$SECRETS_ROOT/current"
[[ -L "$current" ]] || fail "current secret generation symlink is missing"
generation="$(cd "$current" && pwd -P)"
case "$generation" in
  "$SECRETS_ROOT/generations/"*) ;;
  *) fail "current secret generation escapes the staging root" ;;
esac

mode_of() {
  stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"
}

[[ "$(mode_of "$SECRETS_ROOT")" == "700" ]] || fail "secret staging root mode must be 0700"
runtime_env="$current/runtime.env"
private_key="$current/jwt-private.pem"
public_key="$current/jwt-public.pem"
for secret_file in "$runtime_env" "$private_key" "$public_key"; do
  [[ -s "$secret_file" ]] || fail "required staged secret file is missing or empty"
  [[ "$(mode_of "$secret_file")" == "600" ]] || fail "staged secret file mode must be 0600"
done

env_value() {
  local file="$1"
  local key="$2"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found = 1} END {exit !found}' \
    "$file"
}

[[ "$(env_value "$CONFIG_ENV" B1_VERIFICATION_ONLY 2>/dev/null || true)" == "false" ]] ||
  fail "B1_VERIFICATION_ONLY must be false in production"
if grep -Eq 'verification/generated|SYNTHETIC VERIFICATION ONLY|NOT FOR REAL DEPLOYMENT' "$CONFIG_ENV"; then
  fail "production config references verification-only material"
fi

required_config=(
  APP_ENV POSTGRES_DB POSTGRES_USER POSTGRES_RUNTIME_USER MINIO_ENDPOINT MINIO_BUCKET
  LINE_CHANNEL_ID LIFF_ID AUTH_JWT_ISSUER AUTH_JWT_AUDIENCE
  LINE_ROLE_MENU_FEATURES_ENABLED
  REDIS_MAXMEMORY CELERY_AI_ENABLED CELERY_QUEUE_AI CELERY_QUEUE_SYSTEM
  CELERY_TASK_SOFT_TIME_LIMIT CELERY_TASK_TIME_LIMIT CELERY_VISIBILITY_TIMEOUT
  CELERY_MAX_RETRIES CELERY_RETRY_BACKOFF_MAX CELERY_RECONCILE_INTERVAL_SECONDS
  CELERY_WORKER_CONCURRENCY
  AUTH_JWT_ACTIVE_PRIVATE_KEY_REFERENCE AUTH_JWT_ACTIVE_PUBLIC_KEY_REFERENCE
  AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE
  PII_ENCRYPTION_PROVIDER PII_KMS_KEY_NAME AI_PROVIDER
  E4_CANONICAL_HOSTNAME E4_WEB_UPSTREAM_HOST_PORT E4_API_UPSTREAM_HOST_PORT
)
for key in "${required_config[@]}"; do
  value="$(env_value "$CONFIG_ENV" "$key" 2>/dev/null || true)"
  [[ -n "$value" ]] || fail "$key is missing or empty"
  [[ ! "$value" =~ (CHANGE|PLACEHOLDER|PROJECT_ID|example\.com) ]] || fail "$key is unresolved"
done
[[ "$(env_value "$CONFIG_ENV" APP_ENV)" == "production" ]] || fail "APP_ENV must be production"
[[ "$(env_value "$CONFIG_ENV" PII_ENCRYPTION_PROVIDER)" == "gcp-kms" ]] ||
  fail "PII_ENCRYPTION_PROVIDER must remain gcp-kms"
[[ "$(env_value "$CONFIG_ENV" E4_CANONICAL_HOSTNAME)" == "strayhub.enadv.quest" ]] ||
  fail "E4_CANONICAL_HOSTNAME must be strayhub.enadv.quest"
[[ "$(env_value "$CONFIG_ENV" E4_WEB_UPSTREAM_HOST_PORT)" == "3000" ]] ||
  fail "E4_WEB_UPSTREAM_HOST_PORT must be 3000"
[[ "$(env_value "$CONFIG_ENV" E4_API_UPSTREAM_HOST_PORT)" == "8080" ]] ||
  fail "E4_API_UPSTREAM_HOST_PORT must be 8080"

celery_ai_enabled="$(env_value "$CONFIG_ENV" CELERY_AI_ENABLED)"
[[ "$celery_ai_enabled" == "true" || "$celery_ai_enabled" == "false" ]] ||
  fail "CELERY_AI_ENABLED must be exactly true or false"
[[ "$(env_value "$CONFIG_ENV" REDIS_MAXMEMORY)" =~ ^[1-9][0-9]*(mb|gb)$ ]] ||
  fail "REDIS_MAXMEMORY must be a positive mb/gb value"
for numeric_key in CELERY_TASK_SOFT_TIME_LIMIT CELERY_TASK_TIME_LIMIT \
  CELERY_VISIBILITY_TIMEOUT CELERY_RECONCILE_INTERVAL_SECONDS CELERY_WORKER_CONCURRENCY; do
  [[ "$(env_value "$CONFIG_ENV" "$numeric_key")" =~ ^[1-9][0-9]*$ ]] ||
    fail "$numeric_key must be a positive integer"
done
[[ "$(env_value "$CONFIG_ENV" CELERY_MAX_RETRIES)" =~ ^[0-9]+$ ]] ||
  fail "CELERY_MAX_RETRIES must be a non-negative integer"
soft_limit="$(env_value "$CONFIG_ENV" CELERY_TASK_SOFT_TIME_LIMIT)"
hard_limit="$(env_value "$CONFIG_ENV" CELERY_TASK_TIME_LIMIT)"
((soft_limit < hard_limit)) || fail "CELERY_TASK_SOFT_TIME_LIMIT must be below CELERY_TASK_TIME_LIMIT"

line_features_enabled="$(env_value "$CONFIG_ENV" LINE_ROLE_MENU_FEATURES_ENABLED)"
[[ "$line_features_enabled" == "true" || "$line_features_enabled" == "false" ]] ||
  fail "LINE_ROLE_MENU_FEATURES_ENABLED must be exactly true or false"
if [[ "$line_features_enabled" == "true" ]]; then
  required_line_config=(
    WEB_PUBLIC_BASE_URL LINE_RICH_MENU_DEFAULT_ID LINE_RICH_MENU_VOLUNTEER_ID
    LINE_RICH_MENU_STAFF_ID LINE_STAFF_LIFF_ID LINE_ROLE_MENU_SMOKE_EVIDENCE
  )
  for key in "${required_line_config[@]}"; do
    value="$(env_value "$CONFIG_ENV" "$key" 2>/dev/null || true)"
    [[ -n "$value" ]] || fail "$key is required when LINE role-menu features are enabled"
    [[ ! "$value" =~ (CHANGE|PLACEHOLDER|PROJECT_ID|\.example(\.(com|net|org))?|\.invalid|\.test|fake-|local-only-) ]] ||
      fail "$key is unresolved"
  done
  public_url="$(env_value "$CONFIG_ENV" WEB_PUBLIC_BASE_URL)"
  [[ "$public_url" =~ ^https://[^/[:space:]]+(/.*)?$ ]] ||
    fail "WEB_PUBLIC_BASE_URL must be an absolute HTTPS URL"
  smoke_evidence="$(env_value "$CONFIG_ENV" LINE_ROLE_MENU_SMOKE_EVIDENCE)"
  [[ "$smoke_evidence" =~ ^verified-[0-9]{8}-[0-9a-f]{40}$ ]] ||
    fail "LINE_ROLE_MENU_SMOKE_EVIDENCE must identify the date and exact tested commit"
fi
kms_key_name="$(env_value "$CONFIG_ENV" PII_KMS_KEY_NAME)"
[[ "$kms_key_name" =~ ^projects/[^/[:space:]]+/locations/[^/[:space:]]+/keyRings/[^/[:space:]]+/cryptoKeys/[^/[:space:]]+$ ]] ||
  fail "PII_KMS_KEY_NAME must be a full Cloud KMS CryptoKey resource name"
configured_private="$(env_value "$CONFIG_ENV" AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE)"
configured_public="$(env_value "$CONFIG_ENV" AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE)"
[[ -f "$configured_private" && -f "$configured_public" ]] ||
  fail "configured production JWT files do not exist"
configured_private="$(cd "$(dirname "$configured_private")" && pwd -P)/$(basename "$configured_private")"
configured_public="$(cd "$(dirname "$configured_public")" && pwd -P)/$(basename "$configured_public")"
private_key="$(cd "$(dirname "$private_key")" && pwd -P)/$(basename "$private_key")"
public_key="$(cd "$(dirname "$public_key")" && pwd -P)/$(basename "$public_key")"
[[ "$configured_private" == "$private_key" ]] || fail "production JWT private path is not staged"
[[ "$configured_public" == "$public_key" ]] || fail "production JWT public path is not staged"

required_runtime=(
  POSTGRES_PASSWORD POSTGRES_RUNTIME_PASSWORD DATABASE_URL DATABASE_MIGRATION_URL
  MINIO_ACCESS_KEY MINIO_SECRET_KEY LINE_CHANNEL_SECRET LINE_CHANNEL_ACCESS_TOKEN
  ANIMAL_CONFIRMATION_SECRET LOGIN_ABUSE_HMAC_SECRET REDIS_PASSWORD CELERY_BROKER_URL
)
for key in "${required_runtime[@]}"; do
  value="$(env_value "$runtime_env" "$key" 2>/dev/null || true)"
  [[ -n "$value" && "$value" != "''" ]] || fail "$key is missing or empty from runtime.env"
done
broker_url="$(env_value "$runtime_env" CELERY_BROKER_URL)"
[[ "$broker_url" != *localhost* && "$broker_url" != *127.0.0.1* ]] ||
  fail "CELERY_BROKER_URL must not use a loopback host"
[[ "$broker_url" == *"redis://:"*"@redis:6379/"* ]] ||
  fail "CELERY_BROKER_URL must use authenticated private Redis DNS"
if [[ "$celery_ai_enabled" == "true" ]]; then
  gemini_key="$(env_value "$runtime_env" GEMINI_API_KEY 2>/dev/null || true)"
  gemini_path="$(env_value "$CONFIG_ENV" GEMINI_SERVICE_ACCOUNT_PATH 2>/dev/null || true)"
  [[ -n "$gemini_key" || -n "$gemini_path" ]] ||
    fail "CELERY_AI_ENABLED=true requires GEMINI_API_KEY or GEMINI_SERVICE_ACCOUNT_PATH"
fi

derived_public="$(mktemp "${TMPDIR:-/tmp}/strayhub-d1-public.XXXXXX")"
compose=(docker compose --project-name "$PROJECT_NAME" --env-file "$CONFIG_ENV" \
  --env-file "$runtime_env")
if [[ -n "$IMAGE_ENV" ]]; then
  compose+=(--env-file "$IMAGE_ENV")
fi
compose+=(-f "$COMPOSE_FILE")
cleanup() {
  rm -f "$derived_public"
  "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT
openssl pkey -in "$private_key" -pubout -out "$derived_public" >/dev/null 2>&1 ||
  fail "staged JWT private key is invalid"
cmp -s "$derived_public" "$public_key" || fail "staged JWT active pair does not match"

"${compose[@]}" config --quiet
"${compose[@]}" config --format json | python3 -c '
import json, sys
from urllib.parse import unquote, urlsplit
services = json.load(sys.stdin)["services"]
# Legacy worker is a database-backed process, validated separately below.
environments = [services[name]["environment"] for name in ("api", "celery-worker", "celery-beat")]
for key in ("CELERY_BROKER_URL", "CELERY_AI_ENABLED"):
    values = [env.get(key) for env in environments]
    if not values[0] or any(value != values[0] for value in values):
        sys.exit("[Production secret preflight] FAIL: inconsistent " + key)
try:
    broker = urlsplit(environments[0]["CELERY_BROKER_URL"])
    valid = (broker.scheme == "redis" and broker.hostname == "redis"
             and broker.port == 6379 and broker.password
             and unquote(broker.password) == services["redis"]["environment"]["REDIS_PASSWORD"])
except (ValueError, KeyError):
    valid = False
if not valid:
    sys.exit("[Production secret preflight] FAIL: Redis credential/origin mismatch")
'
"${compose[@]}" run --rm --no-deps --entrypoint /bin/sh api -ec '
  export AUTH_JWT_ACTIVE_PRIVATE_KEY="$(cat /run/secrets/runtime_jwt_private_key)"
  export AUTH_JWT_ACTIVE_PUBLIC_KEY="$(cat /run/secrets/runtime_jwt_public_key)"
  python -c "from services.api.app.config.settings import Settings; Settings().validate_runtime_safety(process=\"api\")"
' >/dev/null
"${compose[@]}" run --rm --no-deps --entrypoint python worker -c \
  'from services.api.app.config.settings import Settings; Settings().validate_runtime_safety(process="worker")' \
  >/dev/null
"${compose[@]}" run --rm --no-deps --entrypoint python celery-worker -c \
  'from services.api.app.config.settings import Settings; Settings().validate_runtime_safety(process="worker")' \
  >/dev/null
"${compose[@]}" run --rm --no-deps --entrypoint python celery-beat -c \
  'from services.api.app.config.settings import Settings; Settings().validate_runtime_safety(process="worker")' \
  >/dev/null
"${compose[@]}" --profile tools run --rm --no-deps --entrypoint python migration -c \
  'from services.api.app.config.settings import Settings; Settings().validate_runtime_safety(process="migration")' \
  >/dev/null

echo "[Production secret preflight] PASS"
