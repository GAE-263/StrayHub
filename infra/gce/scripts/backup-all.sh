#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-lib.sh
source "$SCRIPT_DIR/backup-lib.sh"

BACKUP_PROJECT=""
BACKUP_ENV_FILE="$BACKUP_DEFAULT_ENV_FILE"
OUTPUT_ROOT="$BACKUP_DEFAULT_OUTPUT_ROOT"
BACKUP_ENVIRONMENT="gcp-demo"
BACKUP_ID=""

while (($#)); do
  case "$1" in
    --project-name) BACKUP_PROJECT="${2:-}"; shift 2 ;;
    --env-file) BACKUP_ENV_FILE="${2:-}"; shift 2 ;;
    --output-root) OUTPUT_ROOT="${2:-}"; shift 2 ;;
    --environment) BACKUP_ENVIRONMENT="${2:-}"; shift 2 ;;
    --backup-id) BACKUP_ID="${2:-}"; shift 2 ;;
    *) backup_fail "unknown or incomplete argument: $1" ;;
  esac
done

backup_require_base
backup_validate_environment "$BACKUP_ENVIRONMENT"
if [[ -z "$BACKUP_ID" ]]; then
  BACKUP_ID="$(date -u +%Y%m%dT%H%M%SZ)-b3$RANDOM"
fi
backup_validate_id "$BACKUP_ID"
OUTPUT_ROOT="$(backup_prepare_directory "$OUTPUT_ROOT")"
environment_dir="$(backup_prepare_directory "$OUTPUT_ROOT/$BACKUP_ENVIRONMENT")"
backup_dir="$environment_dir/$BACKUP_ID"
[[ ! -e "$backup_dir" ]] || backup_fail "backup ID already exists"
backup_dir="$(backup_prepare_directory "$backup_dir")"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

"$SCRIPT_DIR/backup-postgres.sh" \
  --project-name "$BACKUP_PROJECT" \
  --env-file "$BACKUP_ENV_FILE" \
  --backup-dir "$backup_dir" \
  --backup-id "$BACKUP_ID"
"$SCRIPT_DIR/backup-minio.sh" \
  --project-name "$BACKUP_PROJECT" \
  --env-file "$BACKUP_ENV_FILE" \
  --backup-dir "$backup_dir" \
  --backup-id "$BACKUP_ID"

git_commit="$(git -C "$BACKUP_ROOT_DIR" rev-parse --short HEAD 2>/dev/null || printf unknown)"
python3 "$BACKUP_METADATA_HELPER" manifest \
  --backup-id "$BACKUP_ID" \
  --timestamp "$timestamp" \
  --environment "$BACKUP_ENVIRONMENT" \
  --git-commit "$git_commit" \
  --backup-dir "$backup_dir" \
  --output "$backup_dir/manifest.json"
python3 "$BACKUP_METADATA_HELPER" verify-manifest --manifest "$backup_dir/manifest.json"

printf '[Combined backup] PASS: %s\n' "$backup_dir"
