#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=backup-lib.sh
source "$SCRIPT_DIR/backup-lib.sh"

BACKUP_PROJECT="${1:-}"
BACKUP_ENV_FILE="${2:-$BACKUP_DEFAULT_ENV_FILE}"
backup_require_base

generated_dir="$(backup_prepare_directory "$BACKUP_DEFAULT_OUTPUT_ROOT")"
git -C "$BACKUP_ROOT_DIR" check-ignore -q \
  "${generated_dir#"$BACKUP_ROOT_DIR/"}/probe" || \
  backup_fail "generated backup directory is not ignored by Git"
[[ -w "$generated_dir" ]] || backup_fail "generated backup directory is not writable"
docker compose --project-name "$BACKUP_PROJECT" --file "$BACKUP_COMPOSE_FILE" \
  --env-file "$BACKUP_ENV_FILE" config --quiet

printf '[Backup preflight] PASS\n'
