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
component_dir="$(backup_prepare_directory "$BACKUP_DIR/postgres")"
dump_path="$component_dir/postgres.dump"
temporary_dump="$component_dir/postgres.dump.tmp"
[[ ! -e "$dump_path" && ! -e "$temporary_dump" ]] || backup_fail "PostgreSQL artifact already exists"

database="$(backup_compose exec -T postgres printenv POSTGRES_DB | tr -d '\r\n')"
[[ "$database" =~ ^[A-Za-z0-9_]+$ ]] || backup_fail "unsafe PostgreSQL database name"
migration_head="$(
  backup_compose exec -T postgres sh -ec \
    'psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --tuples-only --no-align --command "SELECT version_num FROM alembic_version"' |
    tr -d '[:space:]'
)"
[[ "$migration_head" =~ ^[A-Za-z0-9_]+$ ]] || backup_fail "unable to read Alembic migration head"
pg_dump_version="$(backup_compose exec -T postgres pg_dump --version | tr -d '\r\n')"
timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

trap 'rm -f -- "$temporary_dump"' EXIT
backup_compose exec -T postgres sh -ec \
  'pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom --no-owner' \
  >"$temporary_dump"
[[ -s "$temporary_dump" ]] || backup_fail "pg_dump produced an empty artifact"
mv "$temporary_dump" "$dump_path"
chmod 600 "$dump_path"

python3 "$BACKUP_METADATA_HELPER" postgres-metadata \
  --backup-id "$BACKUP_ID" \
  --timestamp "$timestamp" \
  --database "$database" \
  --dump "$dump_path" \
  --migration-head "$migration_head" \
  --pg-dump-version "$pg_dump_version" \
  --output "$component_dir/metadata.json"

printf '[PostgreSQL backup] PASS: %s\n' "$dump_path"
