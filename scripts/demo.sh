#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-serve}"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/strayhub-uv-cache}"
export UV_CACHE_DIR
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub}"
export STRAYHUB_TEST_DATABASE_URL="${STRAYHUB_TEST_DATABASE_URL:-postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub}"
export API_HOST="${API_HOST:-127.0.0.1}"
export API_PORT="${API_PORT:-8000}"
export WEB_HOST="${WEB_HOST:-127.0.0.1}"
export WEB_PORT="${WEB_PORT:-3000}"

case "$MODE" in
  check|serve) ;;
  *)
    echo "用法：$0 [check|serve]" >&2
    exit 2
    ;;
esac

require_command() {
  command -v "$1" >/dev/null || {
    echo "缺少必要命令：$1" >&2
    exit 1
  }
}

require_command uv
require_command npm

if [[ -z "${AUTH_JWT_ACTIVE_PRIVATE_KEY:-}" || -z "${AUTH_JWT_ACTIVE_PUBLIC_KEY:-}" ]]; then
  require_command openssl
  key_dir="$(mktemp -d)"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$key_dir/private.pem" \
    >/dev/null 2>&1
  openssl pkey -in "$key_dir/private.pem" -pubout -out "$key_dir/public.pem" \
    >/dev/null 2>&1
  export AUTH_JWT_ACTIVE_PRIVATE_KEY="$(<"$key_dir/private.pem")"
  export AUTH_JWT_ACTIVE_PUBLIC_KEY="$(<"$key_dir/public.pem")"
  rm -rf "$key_dir"
fi

if [[ "${DEMO_SKIP_DOCKER:-0}" != "1" ]]; then
  require_command docker
  docker compose -f infra/local/docker-compose.yml up -d postgres minio
fi

echo "[Demo] Migration"
uv run alembic upgrade head

echo "[Demo] Fictional ORG-A／ORG-B seed"
uv run python -m scripts.seed_local

echo "[Demo] US0～US3 and AI failure degradation smoke"
uv run pytest \
  tests/e2e/test_us0_shelter_isolation.py \
  tests/e2e/test_us1_animal_selection.py \
  tests/e2e/test_us2_line_bot_report.py \
  tests/e2e/test_us3_animal_timeline.py \
  tests/integration/test_ai_failure_timeline_status.py \
  -q

echo "[Demo] PASS"
echo "Staff A:      local-staff-a / local-only-password"
echo "Volunteer A:  local-volunteer-a / local-only-password"
echo "Staff B:      local-staff-b / local-only-password"
echo "Platform:     local-platform-admin / local-only-password"
echo "API:          http://${API_HOST}:${API_PORT}/healthz"
echo "Web:          http://${WEB_HOST}:${WEB_PORT}"

if [[ "$MODE" == "check" ]]; then
  exit 0
fi

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "[Demo] Starting FastAPI／Next.js／Worker; press Ctrl-C to stop"
uv run python -m uvicorn services.api.app.main:app \
  --host "$API_HOST" --port "$API_PORT" &
pids+=("$!")
npm --prefix apps/web run dev -- --hostname "$WEB_HOST" --port "$WEB_PORT" &
pids+=("$!")
uv run python services/worker/worker.py &
pids+=("$!")

wait "${pids[0]}" "${pids[1]}" "${pids[2]}"
