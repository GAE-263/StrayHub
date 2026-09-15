#!/usr/bin/env bash
# Full local runtime; keep infra/local/docker-compose.yml for existing unit tests.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ $# -lt 2 ]]; then
  printf 'Usage: runtime-compose.sh LOCAL_ENV_FILE COMPOSE_COMMAND [ARGS...]\n' >&2
  exit 2
fi
config="$1"
shift
[[ -f "$config" ]] || { printf 'Local config file is missing\n' >&2; exit 1; }
app_env="$(awk -F= '$1 == "APP_ENV" {print $2}' "$config")"
[[ "$app_env" == local ]] || { printf 'Local runtime requires APP_ENV=local\n' >&2; exit 1; }
# Prevent an inherited shell value from overriding the local environment file.
export APP_ENV=local
exec docker compose --project-name strayhub-local-runtime \
  --env-file "$config" \
  -f "$ROOT_DIR/infra/gce/docker-compose.production.yml" \
  -f "$ROOT_DIR/infra/local/docker-compose.runtime.yml" "$@"
