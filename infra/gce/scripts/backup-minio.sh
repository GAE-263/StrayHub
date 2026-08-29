#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-lib.sh
source "$SCRIPT_DIR/backup-lib.sh"

BACKUP_PROJECT=""
BACKUP_ENV_FILE="$BACKUP_DEFAULT_ENV_FILE"
BACKUP_DIR=""
BACKUP_ID=""

while (($#)); do
  case "$1" in
    --project-name) BACKUP_PROJECT="${2:-}"; shift 2 ;;
    --env-file) BACKUP_ENV_FILE="${2:-}"; shift 2 ;;
    --backup-dir) BACKUP_DIR="${2:-}"; shift 2 ;;
    --backup-id) BACKUP_ID="${2:-}"; shift 2 ;;
    *) backup_fail "unknown or incomplete argument: $1" ;;
  esac
done

backup_require_base
backup_validate_id "$BACKUP_ID"
[[ -n "$BACKUP_DIR" ]] || backup_fail "--backup-dir is required"
BACKUP_DIR="$(backup_prepare_directory "$BACKUP_DIR")"
component_dir="$(backup_prepare_directory "$BACKUP_DIR/minio")"
objects_dir="$component_dir/objects"
[[ ! -e "$objects_dir" ]] || backup_fail "MinIO backup objects directory already exists"
mkdir -p "$objects_dir"
chmod 700 "$objects_dir"

bucket="$(backup_compose run --rm --no-deps --entrypoint /bin/sh minio-bootstrap -ec 'printf %s "$MINIO_BUCKET"' | tr -d '\r\n')"
[[ "$bucket" =~ ^[a-z0-9][a-z0-9.-]{2,62}$ ]] || backup_fail "unsafe MinIO bucket name"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mc_version="$(backup_compose run --rm --no-deps --entrypoint /bin/sh minio-bootstrap -ec 'mc --version | head -1' | tr -d '\r\n')"

backup_compose run --rm --no-deps \
  --volume "$component_dir:/backup" \
  --entrypoint /bin/sh \
  minio-bootstrap -ec '
    mc alias set runtime http://minio:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" >/dev/null
    mc mirror --overwrite "runtime/$MINIO_BUCKET" /backup/objects >/dev/null
  '
chmod -R go-rwx "$component_dir"

python3 "$BACKUP_METADATA_HELPER" minio-inventory \
  --backup-id "$BACKUP_ID" \
  --timestamp "$timestamp" \
  --bucket "$bucket" \
  --objects-dir "$objects_dir" \
  --mc-version "$mc_version" \
  --output "$component_dir/inventory.json"

printf '[MinIO backup] PASS: %s\n' "$objects_dir"
