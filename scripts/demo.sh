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
export API_PORT="${API_PORT:-8001}"
export API_BASE_URL="${API_BASE_URL:-http://${API_HOST}:${API_PORT}}"
export WEB_HOST="${WEB_HOST:-127.0.0.1}"
export WEB_PORT="${WEB_PORT:-3001}"

case "$MODE" in
  check|serve) ;;
  --help|-h)
    echo "用法：$0 [check|serve]"
    echo "正常 demo：FurKids 5、新店犬最多 60、五股犬最多 60；不建立 ORG-A／ORG-B。"
    echo "check 只 bootstrap/驗證；serve（預設）另啟動 FastAPI／Next.js／Worker。"
    echo "舊 fixtures 請先預覽：uv run python -m scripts.cleanup_legacy_demo_fixtures；--yes 才刪除。"
    echo "測試 fixtures 請使用獨立 DB：uv run python -m scripts.seed_test_fixtures"
    exit 0
    ;;
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

require_port_available() {
  local label="$1"
  local port="$2"
  if command -v lsof >/dev/null && lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "${label} port ${port} 已被使用，請先停止舊服務後再執行 demo.sh。" >&2
    exit 1
  fi
}

require_command uv
require_command npm

# Check .env-aware settings before migrations, grants, data or storage writes.
uv run python -m scripts.local_demo

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

export PII_ALLOW_LOCAL_PROVIDER=true
if [[ -z "${PII_LOCAL_KEY_BASE64:-}" ]]; then
  require_command openssl
  export PII_LOCAL_KEY_BASE64="$(openssl rand -base64 32)"
fi

if [[ "${DEMO_SKIP_DOCKER:-0}" != "1" ]]; then
  require_command docker
  docker compose -f infra/local/docker-compose.yml up -d postgres minio
fi

echo "[Demo] Migration"
uv run alembic upgrade head
uv run python -m scripts.configure_runtime_role --apply

echo "[Demo] Three-shelter data bootstrap (no test fixtures)"
uv run python -m scripts.bootstrap_demo

echo "[Demo] PASS"
echo "Three-shelter manager: demo-furkids-admin / local-only-password"
echo "Platform: demo-platform-admin / local-only-password"
echo "FurKids volunteer: demo-furkids-volunteer / local-only-password"
echo "Xindian volunteer: demo-xindian-volunteer / local-only-password"
echo "Wugu volunteer: demo-wugu-volunteer / local-only-password"
echo "API:          http://${API_HOST}:${API_PORT}/healthz"
echo "Web:          http://${WEB_HOST}:${WEB_PORT}"

if [[ "$MODE" == "check" ]]; then
  exit 0
fi

require_port_available "API" "$API_PORT"
require_port_available "Web" "$WEB_PORT"

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
uv run python -m services.worker.worker &
pids+=("$!")

wait "${pids[0]}" "${pids[1]}" "${pids[2]}"
