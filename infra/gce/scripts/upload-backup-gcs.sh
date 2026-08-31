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
remote_uri="$(gcs_remote_uri)"

if "$GCS_CLI" storage ls "$remote_uri/_COMPLETE" >/dev/null 2>&1; then
  backup_fail "backup ID is already complete in GCS"
fi

verification_root="$(mktemp -d "${TMPDIR:-/tmp}/strayhub-d3-upload-verify.XXXXXX")"
marker="$verification_root/_COMPLETE"
cleanup() {
  rm -rf -- "$verification_root"
}
trap cleanup EXIT

"$GCS_CLI" storage rsync --recursive "$BACKUP_DIR" "$remote_uri" >/dev/null
mkdir -p "$verification_root/backup"
"$GCS_CLI" storage rsync --recursive "$remote_uri" "$verification_root/backup" >/dev/null
# Object stores do not preserve an empty directory. Recreate the canonical
# layout before validation; a non-empty expected inventory still fails if any
# object is absent.
mkdir -p "$verification_root/backup/minio/objects"
python3 "$BACKUP_METADATA_HELPER" verify-manifest \
  --manifest "$verification_root/backup/manifest.json" >/dev/null
[[ "$(python3 "$BACKUP_METADATA_HELPER" field \
  --input "$verification_root/backup/manifest.json" --path backup_id)" == "$BACKUP_ID" ]] ||
  backup_fail "uploaded backup ID mismatch"

printf '%s\n' "$BACKUP_ID" >"$marker"
chmod 600 "$marker"
"$GCS_CLI" storage cp "$marker" "$remote_uri/_COMPLETE" >/dev/null
"$GCS_CLI" storage cp "$remote_uri/_COMPLETE" "$verification_root/activated" >/dev/null
cmp -s "$marker" "$verification_root/activated" || backup_fail "completion marker mismatch"

printf '[GCS backup upload] PASS: %s\n' "$remote_uri"
