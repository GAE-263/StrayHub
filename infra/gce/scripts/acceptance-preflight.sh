#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BASE_COMPOSE="$ROOT_DIR/infra/gce/docker-compose.production.yml"
ACCEPTANCE_COMPOSE="$ROOT_DIR/infra/gce/docker-compose.acceptance.yml"
POLICY="$ROOT_DIR/infra/gce/scripts/acceptance-compose-policy.py"
CONFIG_ENV=""
IMAGE_ENV=""
SECRETS_ROOT="/var/lib/strayhub/acceptance/secrets"
DOCKER_BIN="${STRAYHUB_DOCKER_BIN:-docker}"

fail() { echo "[Acceptance preflight] FAIL: $*" >&2; exit 1; }
usage() {
  echo "Usage: $0 --config-env PATH --image-env PATH [--secrets-root PATH]" >&2
}

while (($#)); do
  case "$1" in
    --config-env) CONFIG_ENV="${2:-}"; shift 2 ;;
    --image-env) IMAGE_ENV="${2:-}"; shift 2 ;;
    --secrets-root) SECRETS_ROOT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; fail "unknown or incomplete argument: $1" ;;
  esac
done

command -v "$DOCKER_BIN" >/dev/null || fail "docker is required"
command -v python3 >/dev/null || fail "python3 is required"
command -v openssl >/dev/null || fail "openssl is required"
[[ -f "$CONFIG_ENV" ]] || fail "--config-env must name the protected acceptance config"
[[ -f "$IMAGE_ENV" ]] || fail "--image-env must name immutable release images"
[[ -d "$SECRETS_ROOT" ]] || fail "acceptance secret staging root does not exist"
[[ -f "$ROOT_DIR/infra/gce/postgres/init-runtime-role.sh" ]] ||
  fail "PostgreSQL runtime-role initializer is missing from the release"
[[ -x "$ROOT_DIR/infra/gce/postgres/init-runtime-role.sh" ]] ||
  fail "PostgreSQL runtime-role initializer is not executable"

mode_of() { stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"; }
owner_of() { stat -c '%u' "$1" 2>/dev/null || stat -f '%u' "$1"; }
env_value() {
  local file="$1" key="$2"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); gsub(/^\047|\047$/, ""); print; found = 1} END {exit !found}' "$file"
}

SECRETS_ROOT="$(cd "$SECRETS_ROOT" && pwd -P)"
case "$SECRETS_ROOT" in
  /var/lib/strayhub/acceptance/secrets|/tmp/strayhub-acceptance-*|/private/tmp/strayhub-acceptance-*) ;;
  *) fail "secret root must use the acceptance boundary" ;;
esac
[[ "$(mode_of "$SECRETS_ROOT")" == "700" ]] || fail "secret root mode must be 0700"
current="$SECRETS_ROOT/current"
[[ -L "$current" ]] || fail "current acceptance secret generation is missing"
generation="$(cd "$current" && pwd -P)"
case "$generation" in "$SECRETS_ROOT/generations/"*) ;; *) fail "current generation escapes acceptance root" ;; esac

runtime_env="$current/runtime.env"
private_key="$current/jwt-private.pem"
public_key="$current/jwt-public.pem"
bootstrap_password="$current/acceptance-bootstrap-password"
for file in "$runtime_env" "$private_key" "$public_key" "$bootstrap_password"; do
  [[ -s "$file" ]] || fail "required staged secret file is missing"
  [[ "$(mode_of "$file")" == "600" ]] || fail "staged secret file mode must be 0600"
done
openssl pkey -in "$private_key" -noout >/dev/null 2>&1 || fail "JWT private key is invalid"
openssl pkey -pubin -in "$public_key" -noout >/dev/null 2>&1 || fail "JWT public key is invalid"

[[ "$(mode_of "$CONFIG_ENV")" == "600" ]] || fail "acceptance config mode must be 0600"
[[ "$(env_value "$CONFIG_ENV" APP_ENV)" == "acceptance" ]] || fail "APP_ENV must be acceptance"
[[ "$(env_value "$CONFIG_ENV" ACCEPTANCE_BIND_HOST)" == "127.0.0.1" ]] || fail "ports must bind loopback"
[[ "$(env_value "$CONFIG_ENV" ACCEPTANCE_WEB_HOST_PORT)" == "13000" ]] || fail "web port must be 13000"
[[ "$(env_value "$CONFIG_ENV" ACCEPTANCE_API_HOST_PORT)" == "18080" ]] || fail "API port must be 18080"
[[ "$(env_value "$CONFIG_ENV" ACCEPTANCE_INGRESS_MODE)" == "external-https-to-loopback-web" ]] || fail "acceptance ingress mode is invalid"
[[ "$(env_value "$CONFIG_ENV" ACCEPTANCE_INGRESS_UPSTREAM)" == "http://127.0.0.1:13000" ]] || fail "acceptance ingress must terminate at loopback Web"
[[ "$(env_value "$CONFIG_ENV" CELERY_AI_ENABLED)" == "false" ]] || fail "CELERY_AI_ENABLED must be false"
[[ "$(env_value "$CONFIG_ENV" CELERY_WORKER_CONCURRENCY)" == "1" ]] || fail "worker concurrency must be 1"
[[ -z "$(env_value "$CONFIG_ENV" GEMINI_SERVICE_ACCOUNT_PATH 2>/dev/null || true)" ]] || fail "service-account JSON keys are forbidden"
[[ "$(env_value "$CONFIG_ENV" PII_ENCRYPTION_PROVIDER)" == "gcp-kms" ]] || fail "PII provider must be gcp-kms"
kms_key="$(env_value "$CONFIG_ENV" PII_KMS_KEY_NAME)"
[[ "$kms_key" =~ ^projects/[^/[:space:]]+/locations/[^/[:space:]]+/keyRings/strayhub-acceptance/cryptoKeys/[^/[:space:]]+$ ]] || fail "PII KMS key must use the acceptance key ring"

line_channel_id="$(env_value "$CONFIG_ENV" LINE_CHANNEL_ID)"
production_line_channel_id="$(env_value "$CONFIG_ENV" PRODUCTION_LINE_CHANNEL_ID_FOR_ISOLATION_CHECK)"
line_login_channel_id="$(env_value "$CONFIG_ENV" LINE_LOGIN_CHANNEL_ID)"
liff_id="$(env_value "$CONFIG_ENV" LIFF_ID)"
[[ "$line_channel_id" =~ ^[0-9]+$ && "$production_line_channel_id" =~ ^[0-9]+$ ]] || fail "LINE channel IDs must be numeric"
[[ "$line_channel_id" != "$production_line_channel_id" ]] || fail "acceptance LINE channel must differ from production"
[[ "$line_login_channel_id" =~ ^[0-9]+$ && "$line_login_channel_id" != "$line_channel_id" ]] || fail "acceptance LINE Login channel must be dedicated"
[[ "$liff_id" == "$line_login_channel_id-"* ]] || fail "LIFF ID must belong to the acceptance LINE Login channel"

[[ "$(env_value "$CONFIG_ENV" LINE_ROLE_MENU_FEATURES_ENABLED)" == "true" ]] ||
  fail "LINE role-menu features must be enabled for acceptance"
[[ "$(env_value "$CONFIG_ENV" LINE_STAFF_MENU_ENABLED)" == "false" ]] ||
  fail "LINE staff menu must remain disabled for adopter/volunteer acceptance"
required_line_menu_config=(
  LINE_RICH_MENU_DEFAULT_ID LINE_RICH_MENU_VOLUNTEER_ID LINE_RICH_MENU_ADOPTION_HUB_ID
  LINE_ROLE_MENU_SMOKE_EVIDENCE LINE_ROLE_MENU_REPORT_PATH LINE_ROLE_MENU_REPORT_SHA256
  LINE_ROLE_MENU_RESOURCES_PATH LINE_ROLE_MENU_RELEASE_MANIFEST
)
for key in "${required_line_menu_config[@]}"; do
  [[ -n "$(env_value "$CONFIG_ENV" "$key" 2>/dev/null || true)" ]] ||
    fail "$key is required for acceptance role-menu verification"
done
role_menu_evidence="$(env_value "$CONFIG_ENV" LINE_ROLE_MENU_SMOKE_EVIDENCE)"
[[ "$role_menu_evidence" =~ ^verified-[0-9]{8}-[0-9a-f]{40}$ ]] ||
  fail "LINE_ROLE_MENU_SMOKE_EVIDENCE must identify the date and exact tested commit"

report_path="$(env_value "$CONFIG_ENV" LINE_ROLE_MENU_REPORT_PATH)"
resources_path="$(env_value "$CONFIG_ENV" LINE_ROLE_MENU_RESOURCES_PATH)"
release_path="$(env_value "$CONFIG_ENV" LINE_ROLE_MENU_RELEASE_MANIFEST)"
for protected_path in "$report_path" "$resources_path" "$release_path"; do
  [[ "$protected_path" != "/dev/null" && -s "$protected_path" ]] ||
    fail "protected LINE role-menu evidence file is unavailable"
  case "$(mode_of "$protected_path")" in
    400|440|444|600|640|644) ;;
    *) fail "protected LINE role-menu evidence file mode is unsafe" ;;
  esac
  owner_id="$(owner_of "$protected_path")"
  [[ "$owner_id" == "0" || "$owner_id" == "$EUID" ]] ||
    fail "protected LINE role-menu evidence file owner is unsafe"
done
report_sha256="$(openssl dgst -sha256 "$report_path" | awk '{print $NF}')"
[[ "$report_sha256" == "$(env_value "$CONFIG_ENV" LINE_ROLE_MENU_REPORT_SHA256)" ]] ||
  fail "LINE role-menu report checksum mismatch"
python3 - "$report_path" <<'PY' || fail "LINE role-menu report must be real production-like evidence"
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    report = json.load(stream)
if report.get("kind") != "real-line" or report.get("environment") != "production-like":
    raise SystemExit(1)
PY

public_url="$(env_value "$CONFIG_ENV" WEB_PUBLIC_BASE_URL)"
[[ "$public_url" =~ ^https://[^/[:space:]]+(/.*)?$ ]] || fail "WEB_PUBLIC_BASE_URL must be dedicated HTTPS"
[[ "$public_url" != *strayhub.enadv.quest* ]] || fail "production ingress is forbidden"
[[ "$public_url" != *".example"* && "$public_url" != *".invalid"* && "$public_url" != *localhost* ]] || fail "WEB_PUBLIC_BASE_URL is unresolved"
allowlist="$(env_value "$CONFIG_ENV" LINE_NOTIFICATION_RECIPIENT_ALLOWLIST_SHA256)"
[[ "$allowlist" =~ ^[0-9a-f]{64},[0-9a-f]{64}(,[0-9a-f]{64})*$ ]] || fail "LINE allowlist needs at least two SHA-256 identities"

for image_key in STRAYHUB_API_IMAGE STRAYHUB_WORKER_IMAGE STRAYHUB_WEB_IMAGE; do
  image_value="$(env_value "$IMAGE_ENV" "$image_key" 2>/dev/null || true)"
  [[ "$image_value" =~ ^[a-z0-9][a-z0-9._/-]*[a-z0-9]@sha256:[0-9a-f]{64}$ ]] ||
    fail "$image_key must be an immutable digest"
done

required_runtime=(POSTGRES_PASSWORD POSTGRES_RUNTIME_PASSWORD DATABASE_URL DATABASE_MIGRATION_URL MINIO_ACCESS_KEY MINIO_SECRET_KEY LINE_CHANNEL_SECRET LINE_CHANNEL_ACCESS_TOKEN ANIMAL_CONFIRMATION_SECRET LOGIN_ABUSE_HMAC_SECRET REDIS_PASSWORD CELERY_BROKER_URL)
for key in "${required_runtime[@]}"; do
  [[ -n "$(env_value "$runtime_env" "$key" 2>/dev/null || true)" ]] || fail "$key is missing"
done
[[ "$(env_value "$runtime_env" DATABASE_URL)" == *"@postgres:5432/strayhub_acceptance"* ]] || fail "runtime database is not isolated"
[[ "$(env_value "$runtime_env" DATABASE_MIGRATION_URL)" == *"@postgres:5432/strayhub_acceptance"* ]] || fail "migration database is not isolated"
[[ "$(env_value "$runtime_env" CELERY_BROKER_URL)" == redis://:*@redis:6379/* ]] || fail "broker is not acceptance-internal"

container_ids="$("$DOCKER_BIN" ps -aq --filter label=com.docker.compose.project=strayhub-acceptance)" ||
  fail "cannot inspect acceptance containers"
volume_ids="$("$DOCKER_BIN" volume ls -q --filter label=com.docker.compose.project=strayhub-acceptance)" ||
  fail "cannot inspect acceptance volumes"
network_ids="$("$DOCKER_BIN" network ls -q --filter label=com.docker.compose.project=strayhub-acceptance)" ||
  fail "cannot inspect acceptance networks"
[[ -z "$container_ids" ]] || fail "acceptance containers already exist before Gate 3"
[[ -z "$volume_ids" ]] || fail "acceptance volumes already exist before Gate 3"
[[ -z "$network_ids" ]] || fail "acceptance networks already exist before Gate 3"

compose_environment=(env -i "PATH=$PATH" "HOME=${HOME:-/root}")
[[ -z "${DOCKER_HOST:-}" ]] || compose_environment+=("DOCKER_HOST=$DOCKER_HOST")
[[ -z "${DOCKER_CONFIG:-}" ]] || compose_environment+=("DOCKER_CONFIG=$DOCKER_CONFIG")
compose=("${compose_environment[@]}" "$DOCKER_BIN" compose --project-name strayhub-acceptance --profile tools --env-file "$CONFIG_ENV" --env-file "$runtime_env" --env-file "$IMAGE_ENV" --file "$BASE_COMPOSE" --file "$ACCEPTANCE_COMPOSE")
"${compose[@]}" config --quiet
"${compose[@]}" config --format json | "$POLICY"
echo "[Acceptance preflight] PASS (static only; no runtime started)"
