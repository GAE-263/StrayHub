#!/usr/bin/env bash

BACKUP_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_ROOT_DIR="$(cd "$BACKUP_LIB_DIR/../../.." && pwd)"
BACKUP_COMPOSE_FILE="$BACKUP_ROOT_DIR/infra/gce/docker-compose.production.yml"
BACKUP_DEFAULT_ENV_FILE="$BACKUP_ROOT_DIR/infra/gce/.env.production.example"
BACKUP_DEFAULT_OUTPUT_ROOT="$BACKUP_ROOT_DIR/infra/gce/backup/generated"
BACKUP_METADATA_HELPER="$BACKUP_LIB_DIR/backup-metadata.py"

backup_fail() {
  printf '[Backup/restore] FAIL: %s\n' "$*" >&2
  exit 1
}

backup_require_command() {
  command -v "$1" >/dev/null 2>&1 || backup_fail "required command is missing: $1"
}

backup_validate_project() {
  [[ "$1" =~ ^[a-z0-9][a-z0-9_-]{2,62}$ ]] || backup_fail "invalid Compose project name"
}

backup_validate_id() {
  [[ "$1" =~ ^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9_-]{2,31}$ ]] || \
    backup_fail "backup ID must be UTC timestamp plus a safe suffix"
}

backup_validate_environment() {
  [[ "$1" =~ ^[a-z0-9][a-z0-9_-]{1,31}$ ]] || backup_fail "invalid environment label"
}

backup_validate_restore_database() {
  [[ "$1" =~ ^strayhub_b3_restore_[a-z0-9_]{3,40}$ ]] || \
    backup_fail "restore database must use the isolated strayhub_b3_restore_ prefix"
}

backup_validate_restore_bucket() {
  [[ "$1" =~ ^strayhub-b3-restore-[a-z0-9][a-z0-9-]{2,40}$ ]] || \
    backup_fail "restore bucket must use the isolated strayhub-b3-restore- prefix"
}

backup_prepare_directory() {
  local requested="$1"
  [[ -n "$requested" && "$requested" != "/" ]] || backup_fail "unsafe empty or root directory"
  [[ ! -L "$requested" ]] || backup_fail "backup directory must not be a symlink"
  local existed=false
  [[ -e "$requested" ]] && existed=true
  mkdir -p -- "$requested"
  local resolved
  resolved="$(cd "$requested" && pwd -P)"
  case "$resolved" in
    /|/tmp|/private/tmp|/var|/var/tmp|/private/var|/private/var/tmp|/Users|/home|/root|\
      "$BACKUP_ROOT_DIR"|"$BACKUP_ROOT_DIR/infra"|"$BACKUP_ROOT_DIR/infra/gce")
      backup_fail "refusing broad repository or filesystem backup directory"
      ;;
  esac
  if [[ "$existed" == false ]]; then
    chmod 700 "$resolved"
  fi
  [[ -w "$resolved" ]] || backup_fail "backup directory is not writable"
  printf '%s\n' "$resolved"
}

backup_existing_file() {
  local requested="$1"
  [[ -f "$requested" && ! -L "$requested" ]] || backup_fail "file is missing or unsafe: $requested"
  local directory basename
  directory="$(cd "$(dirname "$requested")" && pwd -P)"
  basename="$(basename "$requested")"
  printf '%s/%s\n' "$directory" "$basename"
}

backup_existing_directory() {
  local requested="$1"
  [[ -d "$requested" && ! -L "$requested" ]] || \
    backup_fail "directory is missing or unsafe: $requested"
  (cd "$requested" && pwd -P)
}

backup_compose() {
  docker compose \
    --project-name "$BACKUP_PROJECT" \
    --file "$BACKUP_COMPOSE_FILE" \
    --env-file "$BACKUP_ENV_FILE" \
    "$@"
}

backup_require_base() {
  backup_require_command docker
  backup_require_command python3
  [[ -f "$BACKUP_COMPOSE_FILE" ]] || backup_fail "canonical Compose file is missing"
  [[ -f "$BACKUP_ENV_FILE" ]] || backup_fail "environment file is missing"
  [[ -x "$BACKUP_METADATA_HELPER" ]] || backup_fail "metadata helper is missing or not executable"
  backup_validate_project "$BACKUP_PROJECT"
}
