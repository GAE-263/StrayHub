#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=gcs-backup-lib.sh
source "$SCRIPT_DIR/gcs-backup-lib.sh"

BACKUP_ID=""
DESTINATION_ROOT=""
GCS_BUCKET=""
GCS_PREFIX="$GCS_DEFAULT_PREFIX"
BACKUP_ENVIRONMENT=""
GCS_CLI="${STRAYHUB_GCLOUD_BIN:-gcloud}"

while (($#)); do
  case "$1" in
    --backup-id) BACKUP_ID="${2:-}"; shift 2 ;;
    --destination-root) DESTINATION_ROOT="${2:-}"; shift 2 ;;
    --bucket) GCS_BUCKET="${2:-}"; shift 2 ;;
    --prefix) GCS_PREFIX="${2:-}"; shift 2 ;;
    --environment) BACKUP_ENVIRONMENT="${2:-}"; shift 2 ;;
    --gcloud-bin) GCS_CLI="${2:-}"; shift 2 ;;
    *) backup_fail "unknown or incomplete argument: $1" ;;
  esac
done

gcs_validate_common
backup_validate_id "$BACKUP_ID"
[[ -n "$DESTINATION_ROOT" ]] || backup_fail "--destination-root is required"
DESTINATION_ROOT="$(backup_prepare_directory "$DESTINATION_ROOT")"
environment_dir="$(backup_prepare_directory "$DESTINATION_ROOT/$BACKUP_ENVIRONMENT")"
chmod 700 "$DESTINATION_ROOT" "$environment_dir"
target_dir="$environment_dir/$BACKUP_ID"
[[ ! -e "$target_dir" ]] || backup_fail "download target already exists"
remote_uri="$(gcs_remote_uri)"

temporary_dir="$(mktemp -d "$environment_dir/.download-$BACKUP_ID.XXXXXX")"
chmod 700 "$temporary_dir"
cleanup() {
  rm -rf -- "$temporary_dir"
}
trap cleanup EXIT

"$GCS_CLI" storage cp "$remote_uri/_COMPLETE" "$temporary_dir/expected-complete" >/dev/null ||
  backup_fail "remote backup is incomplete"
[[ "$(tr -d '\r\n' <"$temporary_dir/expected-complete")" == "$BACKUP_ID" ]] ||
  backup_fail "remote completion marker is invalid"

staged_backup="$temporary_dir/backup"
mkdir -p "$staged_backup"
"$GCS_CLI" storage rsync --recursive "$remote_uri" "$staged_backup" >/dev/null
mkdir -p "$staged_backup/minio/objects"
[[ -f "$staged_backup/_COMPLETE" ]] || backup_fail "downloaded backup has no completion marker"
cmp -s "$temporary_dir/expected-complete" "$staged_backup/_COMPLETE" ||
  backup_fail "downloaded completion marker mismatch"
python3 "$BACKUP_METADATA_HELPER" verify-manifest \
  --manifest "$staged_backup/manifest.json" >/dev/null
[[ "$(python3 "$BACKUP_METADATA_HELPER" field \
  --input "$staged_backup/manifest.json" --path backup_id)" == "$BACKUP_ID" ]] ||
  backup_fail "downloaded backup ID mismatch"
[[ "$(python3 "$BACKUP_METADATA_HELPER" field \
  --input "$staged_backup/manifest.json" --path environment)" == "$BACKUP_ENVIRONMENT" ]] ||
  backup_fail "downloaded backup environment mismatch"

chmod -R go-rwx "$staged_backup"
mv "$staged_backup" "$target_dir"
rm -f -- "$temporary_dir/expected-complete"
rmdir "$temporary_dir"
temporary_dir="$environment_dir/.download-complete"

printf '[GCS backup download] PASS: %s\n' "$target_dir"
