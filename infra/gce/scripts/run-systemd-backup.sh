#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCRIPT_DIR="$ROOT_DIR/infra/gce/scripts"
CONFIG_ENV="/etc/strayhub/production.env"
OUTPUT_ROOT="/var/lib/strayhub/backups"
PROJECT_NAME="strayhub-production"
LOCK_FILE="/run/lock/strayhub-backup.lock"

fail() {
  printf '[Systemd backup] FAIL: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --config-env) CONFIG_ENV="${2:-}"; shift 2 ;;
    --output-root) OUTPUT_ROOT="${2:-}"; shift 2 ;;
    --project-name) PROJECT_NAME="${2:-}"; shift 2 ;;
    --lock-file) LOCK_FILE="${2:-}"; shift 2 ;;
    *) fail "unknown or incomplete argument: $1" ;;
  esac
done

[[ -f "$CONFIG_ENV" ]] || fail "production config is missing"
[[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9_-]{2,62}$ ]] || fail "invalid Compose project name"
[[ -n "$OUTPUT_ROOT" && "$OUTPUT_ROOT" != "/" ]] || fail "unsafe backup output root"
[[ "$LOCK_FILE" == /run/lock/* && "$LOCK_FILE" != "/run/lock/" ]] || fail "unsafe lock path"
command -v flock >/dev/null || fail "flock is required"

for required_name in POSTGRES_PASSWORD POSTGRES_RUNTIME_PASSWORD DATABASE_URL \
  DATABASE_MIGRATION_URL MINIO_ACCESS_KEY MINIO_SECRET_KEY; do
  [[ -n "${!required_name:-}" ]] || fail "required staged environment is unavailable"
done

env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; found = 1} END {exit !found}' \
    "$CONFIG_ENV"
}

bucket="$(env_value GCS_BACKUP_BUCKET 2>/dev/null || true)"
prefix="$(env_value GCS_BACKUP_PREFIX 2>/dev/null || true)"
environment="$(env_value BACKUP_ENVIRONMENT 2>/dev/null || true)"
[[ -n "$bucket" && -n "$prefix" && -n "$environment" ]] ||
  fail "GCS backup configuration is incomplete"

mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
flock -n 9 || fail "another backup is already running"

backup_id="$(date -u +%Y%m%dT%H%M%SZ)-e3daily$RANDOM"
"$SCRIPT_DIR/backup-all.sh" \
  --project-name "$PROJECT_NAME" \
  --env-file "$CONFIG_ENV" \
  --output-root "$OUTPUT_ROOT" \
  --environment "$environment" \
  --backup-id "$backup_id"
backup_dir="$OUTPUT_ROOT/$environment/$backup_id"
"$SCRIPT_DIR/gcs-backup-preflight.sh" \
  --backup-dir "$backup_dir" \
  --bucket "$bucket" \
  --prefix "$prefix" \
  --environment "$environment"
"$SCRIPT_DIR/upload-backup-gcs.sh" \
  --backup-dir "$backup_dir" \
  --bucket "$bucket" \
  --prefix "$prefix" \
  --environment "$environment"

printf '[Systemd backup] PASS: backup_id=%s\n' "$backup_id"
