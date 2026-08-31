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
  check|refresh|serve) ;;
  --help|-h)
    echo "用法：$0 [check|refresh|serve]"
    echo "正常 demo：FurKids 5、新店犬最多 60、五股犬最多 60；不建立 ORG-A／ORG-B。"
    echo "serve（預設）沿用已驗證的 PostgreSQL／MinIO 資料並啟動服務。"
    echo "check 沿用已驗證資料，只 bootstrap／驗證，不啟動服務。"
    echo "refresh 強制同步最新 MOA 資料、驗證後再啟動服務；同步失敗會以非零結束。"
    echo "舊 fixtures 請先預覽：uv run python -m scripts.cleanup_legacy_demo_fixtures；--yes 才刪除。"
    echo "測試 fixtures 請使用獨立 DB：uv run python -m scripts.seed_test_fixtures"
    exit 0
    ;;
  *)
    echo "用法：$0 [check|refresh|serve]" >&2
    exit 2
    ;;
esac

require_command() {
  command -v "$1" >/dev/null || {
    echo "缺少必要命令：$1" >&2
    exit 1
  }
}

# Print the PIDs listening on a TCP port (lsof or ss fallback); empty if none.
listeners_on_port() {
  local port="$1"
  if command -v lsof >/dev/null; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | sort -u
  elif command -v ss >/dev/null; then
    ss -tlnpH "sport = :${port}" 2>/dev/null \
      | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
  fi
}

# Fail fast if a demo port is occupied. Set DEMO_KILL_STALE=1 to reclaim it
# by killing the stale listeners (handy after a Ctrl-C'd previous run).
require_port_available() {
  local label="$1"
  local port="$2"
  local pids
  pids="$(listeners_on_port "$port" | tr '\n' ' ')"
  [[ -z "${pids// /}" ]] && return 0

  if [[ "${DEMO_KILL_STALE:-0}" == "1" ]]; then
    echo "[Demo] ${label} port ${port} 已被 PID ${pids}占用，DEMO_KILL_STALE=1 → 清除中" >&2
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    for _ in $(seq 1 20); do
      [[ -z "$(listeners_on_port "$port")" ]] && return 0
      sleep 0.25
    done
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    sleep 0.5
    [[ -z "$(listeners_on_port "$port")" ]] && return 0
  fi

  echo "${label} port ${port} 已被使用 (PID ${pids})。" >&2
  echo "  先停止舊服務：  kill ${pids}" >&2
  echo "  或自動清除重跑：  DEMO_KILL_STALE=1 ./scripts/demo.sh ${MODE}" >&2
  exit 1
}

require_command uv
require_command npm

# Fail fast on occupied ports before the slow bootstrap so `next dev` /
# uvicorn don't die with EADDRINUSE after several minutes of work.
if [[ "$MODE" != "check" ]]; then
  require_port_available "API" "$API_PORT"
  require_port_available "Web" "$WEB_PORT"
fi

# Check .env-aware settings before migrations, grants, data or storage writes.
uv run python -m scripts.local_demo

if [[ -z "${AUTH_JWT_ACTIVE_PRIVATE_KEY:-}" || -z "${AUTH_JWT_ACTIVE_PUBLIC_KEY:-}" ]]; then
  require_command openssl
  key_dir="$(mktemp -d)"
  # Keep stderr visible: a silent openssl failure here surfaces later as an
  # opaque HTTP 503 (authentication_not_configured) from /v1/auth/login.
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$key_dir/private.pem" >/dev/null
  openssl pkey -in "$key_dir/private.pem" -pubout -out "$key_dir/public.pem" >/dev/null
  export AUTH_JWT_ACTIVE_PRIVATE_KEY="$(<"$key_dir/private.pem")"
  export AUTH_JWT_ACTIVE_PUBLIC_KEY="$(<"$key_dir/public.pem")"
  rm -rf "$key_dir"
  if [[ -z "$AUTH_JWT_ACTIVE_PRIVATE_KEY" || -z "$AUTH_JWT_ACTIVE_PUBLIC_KEY" ]]; then
    echo "openssl 未產生 JWT 金鑰；請確認 openssl 可用後重試。" >&2
    exit 1
  fi
  echo "[Demo] Generated ephemeral RSA JWT signing key (local only, not persisted)"
fi

export PII_ALLOW_LOCAL_PROVIDER=true
if [[ -z "${PII_LOCAL_KEY_BASE64:-}" ]]; then
  require_command openssl
  export PII_LOCAL_KEY_BASE64="$(openssl rand -base64 32)"
fi

if [[ "${DEMO_SKIP_DOCKER:-0}" != "1" ]]; then
  require_command docker
  # --wait blocks until postgres passes its healthcheck; without it a cold
  # start races the migration and asyncpg fails with "Connection reset by peer".
  docker compose -f infra/local/docker-compose.yml up -d --wait --wait-timeout 90 \
    postgres minio
fi

echo "[Demo] Migration"
uv run alembic upgrade head
uv run python -m scripts.configure_runtime_role --apply

echo "[Demo] Three-shelter data bootstrap (no test fixtures)"
if [[ "$MODE" == "refresh" ]]; then
  uv run python -m scripts.bootstrap_demo --refresh
else
  uv run python -m scripts.bootstrap_demo
fi

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

# Re-check in case something grabbed a port during the bootstrap window.
require_port_available "API" "$API_PORT"
require_port_available "Web" "$WEB_PORT"

pids=()
cleanup() {
  local pid port pids_on
  # Kill each child and its descendants (npm -> node -> next-server would
  # otherwise linger and hold WEB_PORT, causing EADDRINUSE next run).
  for pid in "${pids[@]:-}"; do
    [[ -z "$pid" ]] && continue
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
  done
  # Backstop: reclaim the demo ports regardless of process tree shape.
  for port in "$API_PORT" "$WEB_PORT"; do
    pids_on="$(listeners_on_port "$port" | tr '\n' ' ')"
    # shellcheck disable=SC2086
    [[ -n "${pids_on// /}" ]] && kill -TERM $pids_on 2>/dev/null || true
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
