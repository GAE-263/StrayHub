#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=gcs-backup-lib.sh
source "$SCRIPT_DIR/gcs-backup-lib.sh"

BACKUP_DIR=""
GCS_BUCKET=""
GCS_PREFIX="$GCS_DEFAULT_PREFIX"
BACKUP_ENVIRONMENT=""
GCS_CLI="${STRAYHUB_GCLOUD_BIN:-gcloud}"

while (($#)); do
  case "$1" in
    --backup-dir) BACKUP_DIR="${2:-}"; shift 2 ;;
    --bucket) GCS_BUCKET="${2:-}"; shift 2 ;;
    --prefix) GCS_PREFIX="${2:-}"; shift 2 ;;
    --environment) BACKUP_ENVIRONMENT="${2:-}"; shift 2 ;;
    --gcloud-bin) GCS_CLI="${2:-}"; shift 2 ;;
    *) backup_fail "unknown or incomplete argument: $1" ;;
  esac
done

gcs_validate_common
[[ -n "$BACKUP_DIR" ]] || backup_fail "--backup-dir is required"
gcs_validate_backup_directory "$BACKUP_DIR" "$BACKUP_ENVIRONMENT"

printf '[GCS backup preflight] PASS: backup_id=%s\n' "$BACKUP_ID"
