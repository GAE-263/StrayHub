#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-lib.sh
source "$SCRIPT_DIR/backup-lib.sh"

BACKUP_PROJECT=""
BACKUP_ENV_FILE="$BACKUP_DEFAULT_ENV_FILE"
BACKUP_FILE=""
TARGET_DATABASE=""
CONFIRMED=false

while (($#)); do
  case "$1" in
    --project-name) BACKUP_PROJECT="${2:-}"; shift 2 ;;
    --env-file) BACKUP_ENV_FILE="${2:-}"; shift 2 ;;
    --backup-file) BACKUP_FILE="${2:-}"; shift 2 ;;
    --target-database) TARGET_DATABASE="${2:-}"; shift 2 ;;
    --confirm-isolated-restore) CONFIRMED=true; shift ;;
    *) backup_fail "unknown or incomplete argument: $1" ;;
  esac
done

backup_require_base
[[ "$CONFIRMED" == true ]] || backup_fail "--confirm-isolated-restore is required"
backup_validate_restore_database "$TARGET_DATABASE"
BACKUP_FILE="$(backup_existing_file "$BACKUP_FILE")"
[[ "$BACKUP_FILE" == *.dump ]] || backup_fail "PostgreSQL backup must be a .dump file"
metadata_file="$(dirname "$BACKUP_FILE")/metadata.json"
metadata_file="$(backup_existing_file "$metadata_file")"
expected_head="$(python3 "$BACKUP_METADATA_HELPER" field --input "$metadata_file" --path migration_head)"
expected_checksum="$(python3 "$BACKUP_METADATA_HELPER" field --input "$metadata_file" --path sha256)"
actual_checksum="$(python3 -c '
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
' "$BACKUP_FILE")"
[[ "$actual_checksum" == "$expected_checksum" ]] || backup_fail "PostgreSQL backup checksum mismatch"

container_dump="/tmp/strayhub-b3-restore-${TARGET_DATABASE}.dump"
trap 'backup_compose exec -T postgres rm -f -- "$container_dump" >/dev/null 2>&1 || true' EXIT
backup_compose cp "$BACKUP_FILE" "postgres:$container_dump" >/dev/null
backup_compose exec -T postgres pg_restore --list "$container_dump" >/dev/null

backup_compose exec -T postgres sh -ec '
  target="$1"
  dropdb --username "$POSTGRES_USER" --if-exists --force "$target"
  createdb --username "$POSTGRES_USER" --template=template0 "$target"
  pg_restore --username "$POSTGRES_USER" --dbname "$target" --no-owner --exit-on-error "$2"
' sh "$TARGET_DATABASE" "$container_dump"

restored_head="$(
  backup_compose exec -T postgres sh -ec \
    'psql --username "$POSTGRES_USER" --dbname "$1" --tuples-only --no-align --command "SELECT version_num FROM alembic_version"' \
    sh "$TARGET_DATABASE" | tr -d '[:space:]'
)"
[[ "$restored_head" == "$expected_head" ]] || backup_fail "restored Alembic head mismatch"

runtime_role="$(backup_compose exec -T postgres printenv POSTGRES_RUNTIME_USER | tr -d '\r\n')"
[[ "$runtime_role" =~ ^[A-Za-z0-9_]+$ ]] || backup_fail "unsafe runtime role name"
role_flags="$(
  backup_compose exec -T postgres sh -ec \
    'psql --username "$POSTGRES_USER" --dbname "$1" --tuples-only --no-align --command "SELECT rolsuper::text || chr(58) || rolbypassrls::text FROM pg_roles WHERE rolname = '\''$2'\''"' \
    sh "$TARGET_DATABASE" "$runtime_role" | tr -d '[:space:]'
)"
[[ "$role_flags" == "false:false" ]] || backup_fail "runtime role safety flags changed"

rls_state="$(
  backup_compose exec -T postgres sh -ec \
    'psql --username "$POSTGRES_USER" --dbname "$1" --tuples-only --no-align --command "SELECT (SELECT count(*) FROM pg_class WHERE relrowsecurity)::text || chr(58) || (SELECT count(*) FROM pg_policies)::text || chr(58) || has_table_privilege('\''$2'\'', '\''organizations'\'', '\''SELECT'\'')::text"' \
    sh "$TARGET_DATABASE" "$runtime_role" | tr -d '[:space:]'
)"
IFS=: read -r rls_table_count policy_count runtime_select <<<"$rls_state"
[[ "$rls_table_count" =~ ^[1-9][0-9]*$ ]] || backup_fail "restored database has no RLS-enabled tables"
[[ "$policy_count" =~ ^[1-9][0-9]*$ ]] || backup_fail "restored database has no RLS policies"
[[ "$runtime_select" == "true" ]] || backup_fail "runtime role table privileges were not restored"

printf '[PostgreSQL restore] PASS: database=%s migration_head=%s\n' \
  "$TARGET_DATABASE" "$restored_head"
