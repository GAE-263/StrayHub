#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-lib.sh
source "$SCRIPT_DIR/backup-lib.sh"

BACKUP_PROJECT=""
BACKUP_ENV_FILE="$BACKUP_DEFAULT_ENV_FILE"
BACKUP_OBJECTS_DIR=""
TARGET_BUCKET=""
CONFIRMED=false

while (($#)); do
  case "$1" in
    --project-name) BACKUP_PROJECT="${2:-}"; shift 2 ;;
    --env-file) BACKUP_ENV_FILE="${2:-}"; shift 2 ;;
    --backup-objects-dir) BACKUP_OBJECTS_DIR="${2:-}"; shift 2 ;;
    --target-bucket) TARGET_BUCKET="${2:-}"; shift 2 ;;
    --confirm-isolated-restore) CONFIRMED=true; shift ;;
    *) backup_fail "unknown or incomplete argument: $1" ;;
  esac
done

backup_require_base
[[ "$CONFIRMED" == true ]] || backup_fail "--confirm-isolated-restore is required"
backup_validate_restore_bucket "$TARGET_BUCKET"
BACKUP_OBJECTS_DIR="$(backup_existing_directory "$BACKUP_OBJECTS_DIR")"
inventory_file="$(backup_existing_file "$(dirname "$BACKUP_OBJECTS_DIR")/inventory.json")"
python3 "$BACKUP_METADATA_HELPER" verify-minio \
  --objects-dir "$BACKUP_OBJECTS_DIR" \
  --inventory "$inventory_file" >/dev/null

backup_compose run --rm --no-deps \
  --env "TARGET_BUCKET=$TARGET_BUCKET" \
  --volume "$(dirname "$BACKUP_OBJECTS_DIR"):/backup:ro" \
  --entrypoint /bin/sh \
  minio-bootstrap -ec '
    mc alias set runtime http://minio:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" >/dev/null
    mc mb --ignore-existing "runtime/$TARGET_BUCKET" >/dev/null
    mc rm --recursive --force "runtime/$TARGET_BUCKET" >/dev/null
    mc mirror --overwrite /backup/objects "runtime/$TARGET_BUCKET" >/dev/null
    mc anonymous set none "runtime/$TARGET_BUCKET" >/dev/null
  '

verification_dir="$(mktemp -d "${TMPDIR:-/tmp}/strayhub-b3-minio-verify.XXXXXX")"
trap 'rm -rf -- "$verification_dir"' EXIT
mkdir -p "$verification_dir/objects"
host_uid="$(id -u)"
host_gid="$(id -g)"
backup_compose run --rm --no-deps \
  --user "$host_uid:$host_gid" \
  --env "TARGET_BUCKET=$TARGET_BUCKET" \
  --volume "$verification_dir:/verify" \
  --entrypoint /bin/sh \
  minio-bootstrap -ec '
    export MC_CONFIG_DIR=/tmp/.mc
    mkdir -p "$MC_CONFIG_DIR"
    mc alias set runtime http://minio:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" >/dev/null
    mc mirror --overwrite "runtime/$TARGET_BUCKET" /verify/objects >/dev/null
  '

python3 "$BACKUP_METADATA_HELPER" verify-minio \
  --objects-dir "$verification_dir/objects" \
  --inventory "$inventory_file"
printf '[MinIO restore] PASS: bucket=%s\n' "$TARGET_BUCKET"
