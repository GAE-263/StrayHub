#!/usr/bin/env bash

GCS_BACKUP_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-lib.sh
source "$GCS_BACKUP_SCRIPT_DIR/backup-lib.sh"

GCS_DEFAULT_PREFIX="strayhub-backups"

gcs_validate_bucket() {
  [[ "$1" =~ ^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$ ]] ||
    backup_fail "invalid GCS backup bucket name"
}

gcs_validate_prefix() {
  local prefix="$1"
  [[ -n "$prefix" && ${#prefix} -le 128 ]] || backup_fail "invalid GCS backup prefix"
  [[ "$prefix" != /* && "$prefix" != */ && "$prefix" != *//* ]] ||
    backup_fail "GCS backup prefix must be a non-root normalized path"
  [[ "$prefix" != *".."* && "$prefix" != *"*"* && "$prefix" != *"?"* ]] ||
    backup_fail "GCS backup prefix contains unsafe path syntax"
  [[ "$prefix" =~ ^[a-z0-9][a-z0-9._/-]*[a-z0-9]$ ]] ||
    backup_fail "invalid GCS backup prefix"
}

gcs_require_cli() {
  command -v "$GCS_CLI" >/dev/null 2>&1 || backup_fail "gcloud storage CLI is required"
  "$GCS_CLI" storage --help >/dev/null 2>&1 || backup_fail "gcloud storage is unavailable"
}

gcs_require_adc_only() {
  [[ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ]] ||
    backup_fail "GOOGLE_APPLICATION_CREDENTIALS JSON paths are forbidden; use ADC from VM identity"
}

gcs_remote_uri() {
  printf 'gs://%s/%s/%s/%s' "$GCS_BUCKET" "$GCS_PREFIX" "$BACKUP_ENVIRONMENT" "$BACKUP_ID"
}

gcs_validate_backup_directory() {
  local requested="$1"
  local expected_environment="$2"
  BACKUP_DIR="$(backup_existing_directory "$requested")"
  local manifest
  manifest="$(backup_existing_file "$BACKUP_DIR/manifest.json")"
  python3 "$BACKUP_METADATA_HELPER" verify-manifest --manifest "$manifest" >/dev/null
  BACKUP_ID="$(python3 "$BACKUP_METADATA_HELPER" field --input "$manifest" --path backup_id)"
  backup_validate_id "$BACKUP_ID"
  [[ "$(basename "$BACKUP_DIR")" == "$BACKUP_ID" ]] ||
    backup_fail "backup directory name does not match manifest backup ID"
  local manifest_environment
  manifest_environment="$(
    python3 "$BACKUP_METADATA_HELPER" field --input "$manifest" --path environment
  )"
  [[ "$manifest_environment" == "$expected_environment" ]] ||
    backup_fail "manifest environment does not match requested environment"
  [[ ! -e "$BACKUP_DIR/_COMPLETE" ]] ||
    backup_fail "local backup must not contain a transport completion marker before upload"
}

gcs_validate_common() {
  backup_require_command python3
  [[ -x "$BACKUP_METADATA_HELPER" ]] || backup_fail "metadata helper is missing"
  backup_validate_environment "$BACKUP_ENVIRONMENT"
  gcs_validate_bucket "$GCS_BUCKET"
  gcs_validate_prefix "$GCS_PREFIX"
  gcs_require_adc_only
  gcs_require_cli
}
