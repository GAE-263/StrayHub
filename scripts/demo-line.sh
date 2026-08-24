#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Load local operator configuration without printing it.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

TUNNEL_PROVIDER="${TUNNEL_PROVIDER:-cloudflared}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8001}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-3001}"
START_WORKER="${START_WORKER:-1}"
LIFF_ID="${LIFF_ID:-}"
SHELTER_ENTRY_REFERENCE="${SHELTER_ENTRY_REFERENCE:-}"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少必要命令：$1" >&2
    exit 1
  }
}

require_value() {
  local name="$1"
  [[ -n "${!name:-}" ]] || {
    echo "請在 .env 或 shell environment 設定 ${name}" >&2
    exit 2
  }
}

require_port_available() {
  local label="$1"
  local port="$2"
  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "${label} port ${port} 已被使用，請先停止舊服務。" >&2
    exit 1
  fi
}

extract_tunnel_url() {
  local log_file="$1"
  case "$TUNNEL_PROVIDER" in
    cloudflared)
      sed -nE 's#.*(https://[A-Za-z0-9.-]+\.trycloudflare\.com).*#\1#p' "$log_file" | head -n 1
      ;;
    ngrok)
      sed -nE 's#.*Forwarding[[:space:]]+(https://[^[:space:]]+).*#\1#p' "$log_file" | head -n 1
      ;;
  esac
}

start_tunnel() {
  local label="$1"
  local port="$2"
  local log_file="$3"
  case "$TUNNEL_PROVIDER" in
    cloudflared)
      cloudflared tunnel --url "http://127.0.0.1:${port}" >"$log_file" 2>&1 &
      ;;
    ngrok)
      ngrok http "$port" --log=stdout >"$log_file" 2>&1 &
      ;;
    *)
      echo "TUNNEL_PROVIDER 必須是 cloudflared 或 ngrok" >&2
      exit 2
      ;;
  esac
  pids+=("$!")
  local url=""
  for _ in $(seq 1 30); do
    url="$(extract_tunnel_url "$log_file" || true)"
    [[ -n "$url" ]] && break
    sleep 1
  done
  if [[ -z "$url" ]]; then
    echo "${label} tunnel 未產生 HTTPS URL；log: ${log_file}" >&2
    sed -n '1,80p' "$log_file" >&2 || true
    exit 1
  fi
  printf '%s\n' "$url"
}

require_value LIFF_ID
require_value SHELTER_ENTRY_REFERENCE
require_command uv
require_command npm
require_command curl
case "$TUNNEL_PROVIDER" in
  cloudflared) require_command cloudflared ;;
  ngrok) require_command ngrok ;;
  *) echo "TUNNEL_PROVIDER 必須是 cloudflared 或 ngrok" >&2; exit 2 ;;
esac
require_port_available "API" "$API_PORT"
require_port_available "Web" "$WEB_PORT"

pids=()
log_dir="$(mktemp -d "${TMPDIR:-/tmp}/strayhub-line.XXXXXX")"
cleanup() {
  local pid
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  rm -rf "$log_dir"
}
trap cleanup EXIT INT TERM

echo "[Line Demo] Starting FastAPI on ${API_HOST}:${API_PORT}"
uv run python -m uvicorn services.api.app.main:app \
  --host "$API_HOST" --port "$API_PORT" &
pids+=("$!")

for _ in $(seq 1 30); do
  if curl --max-time 1 -fsS "http://${API_HOST}:${API_PORT}/healthz" >/dev/null; then
    break
  fi
  sleep 1
done
curl --max-time 5 -fsS "http://${API_HOST}:${API_PORT}/healthz" >/dev/null || {
  echo "FastAPI health check failed" >&2
  exit 1
}

echo "[Line Demo] Starting API tunnel (${TUNNEL_PROVIDER})"
API_TUNNEL_URL="$(start_tunnel "API" "$API_PORT" "$log_dir/api.log")"
curl --max-time 10 -fsS "${API_TUNNEL_URL}/healthz" >/dev/null || {
  echo "API tunnel health check failed: ${API_TUNNEL_URL}/healthz" >&2
  exit 1
}

# API_BASE_URL is a Next.js server-runtime value. It must be set before Next.js starts.
echo "[Line Demo] Starting Next.js with API_BASE_URL=${API_TUNNEL_URL}"
API_BASE_URL="$API_TUNNEL_URL" LIFF_ID="$LIFF_ID" \
  npm --prefix apps/web run dev -- --hostname "$WEB_HOST" --port "$WEB_PORT" &
pids+=("$!")

for _ in $(seq 1 30); do
  if curl --max-time 1 -fsS "http://${WEB_HOST}:${WEB_PORT}/volunteer-entry" >/dev/null; then
    break
  fi
  sleep 1
done
curl --max-time 5 -fsS "http://${WEB_HOST}:${WEB_PORT}/volunteer-entry" >/dev/null || {
  echo "Next.js volunteer entry check failed" >&2
  exit 1
}

echo "[Line Demo] Starting Web tunnel (${TUNNEL_PROVIDER})"
WEB_TUNNEL_URL="$(start_tunnel "Web" "$WEB_PORT" "$log_dir/web.log")"
curl --max-time 10 -fsS "${WEB_TUNNEL_URL}/volunteer-entry" >/dev/null || {
  echo "Web tunnel check failed: ${WEB_TUNNEL_URL}/volunteer-entry" >&2
  exit 1
}

if [[ "$START_WORKER" == "1" ]]; then
  echo "[Line Demo] Starting worker"
  uv run python -m services.worker.worker &
  pids+=("$!")
fi

LIFF_URL="https://liff.line.me/${LIFF_ID}/volunteer-entry?entry=${SHELTER_ENTRY_REFERENCE}"

echo
echo "[Line Demo] PASS"
echo "API tunnel:       ${API_TUNNEL_URL}"
echo "Web tunnel:       ${WEB_TUNNEL_URL}"
echo "LIFF Endpoint:    ${WEB_TUNNEL_URL}/volunteer-entry"
echo "手機 LINE 入口:   ${LIFF_URL}"
echo
echo "請在 LINE Developers Console 設定 LIFF Endpoint URL："
echo "  ${WEB_TUNNEL_URL}/volunteer-entry"
echo "按 Ctrl-C 會停止本腳本啟動的 API、Web、tunnel 與 worker。"

wait "${pids[0]}"
