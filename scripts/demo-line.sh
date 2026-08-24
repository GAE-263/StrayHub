#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

read_dotenv_value() {
  local name="$1"
  [[ -f .env ]] || return 0
  python - "$name" <<'PY'
from pathlib import Path
import ast
import sys

name = sys.argv[1]
prefix = f"{name}="
for raw_line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or not line.startswith(prefix):
        continue
    value = line[len(prefix):].strip()
    if value[:1] in {"'", '"'}:
        try:
            value = str(ast.literal_eval(value))
        except (SyntaxError, ValueError):
            pass
    print(value)
    break
PY
}

load_dotenv_value() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    printf -v "$name" '%s' "$(read_dotenv_value "$name")"
  fi
}

for dotenv_name in TUNNEL_PROVIDER API_HOST API_PORT WEB_HOST WEB_PORT START_WORKER LIFF_ID SHELTER_ENTRY_REFERENCE; do
  load_dotenv_value "$dotenv_name"
done

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

wait_for_tunnel_http() {
  local label="$1"
  local url="$2"
  local path="$3"
  local host="${url#https://}"
  local public_ip=""
  host="${host%%/*}"
  for _ in $(seq 1 45); do
    if curl --max-time 5 -fsS "${url}${path}" >/dev/null 2>&1; then
      return 0
    fi
    if [[ -z "$public_ip" ]] && command -v dig >/dev/null 2>&1; then
      public_ip="$(dig +short @1.1.1.1 A "$host" | sed -nE '/^[0-9]+(\.[0-9]+){3}$/p' | head -n 1)"
    fi
    if [[ -n "$public_ip" ]] && curl --max-time 5 -fsS \
      --resolve "${host}:443:${public_ip}" "${url}${path}" >/dev/null 2>&1; then
      echo "[Line Demo] ${label} tunnel reachable via public DNS fallback"
      return 0
    fi
    sleep 1
  done
  echo "Could not reach tunnel ${label}: ${url}${path}" >&2
  return 1
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
  TUNNEL_URL="$url"
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
  if curl --max-time 1 -fsS "http://${API_HOST}:${API_PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl --max-time 5 -fsS "http://${API_HOST}:${API_PORT}/healthz" >/dev/null || {
  echo "FastAPI health check failed" >&2
  exit 1
}

# Next.js proxies /v1 server-side, so FastAPI stays private on the same host.
API_BASE_URL="http://${API_HOST}:${API_PORT}"
echo "[Line Demo] Starting Next.js with local API proxy"
API_BASE_URL="$API_BASE_URL" LIFF_ID="$LIFF_ID" \
  npm --prefix apps/web run dev -- --hostname "$WEB_HOST" --port "$WEB_PORT" &
pids+=("$!")

for _ in $(seq 1 30); do
  if curl --max-time 1 -fsS "http://${WEB_HOST}:${WEB_PORT}/volunteer-entry" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl --max-time 5 -fsS "http://${WEB_HOST}:${WEB_PORT}/volunteer-entry" >/dev/null || {
  echo "Next.js volunteer entry check failed" >&2
  exit 1
}

echo "[Line Demo] Starting Web tunnel (${TUNNEL_PROVIDER})"
start_tunnel "Web" "$WEB_PORT" "$log_dir/web.log"
WEB_TUNNEL_URL="$TUNNEL_URL"
echo "[Line Demo] Web tunnel health check"
wait_for_tunnel_http "Web" "$WEB_TUNNEL_URL" "/volunteer-entry"

if [[ "$START_WORKER" == "1" ]]; then
  echo "[Line Demo] Starting worker"
  uv run python -m services.worker.worker &
  pids+=("$!")
fi

LIFF_URL="https://liff.line.me/${LIFF_ID}/volunteer-entry?entry=${SHELTER_ENTRY_REFERENCE}"

echo
echo "[Line Demo] PASS"
echo "Local API:        ${API_BASE_URL}"
echo "Web tunnel:       ${WEB_TUNNEL_URL}"
echo "LIFF Endpoint:    ${WEB_TUNNEL_URL}/volunteer-entry"
echo "手機 LINE 入口:   ${LIFF_URL}"
echo
echo "請在 LINE Developers Console 設定 LIFF Endpoint URL："
echo "  ${WEB_TUNNEL_URL}/volunteer-entry"
echo "按 Ctrl-C 會停止本腳本啟動的 API、Web、tunnel 與 worker。"

wait "${pids[0]}"
