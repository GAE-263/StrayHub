#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

read_dotenv_value() {
  local name="$1"
  local python_bin="python"
  [[ -f .env ]] || return 0
  if ! command -v "$python_bin" >/dev/null 2>&1; then
    python_bin="python3"
  fi
  "$python_bin" - "$name" <<'PY'
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

for dotenv_name in NGROK_URL API_HOST API_PORT WEB_HOST WEB_PORT START_WORKER LIFF_ID LINE_LOGIN_CHANNEL_ID SHELTER_ENTRY_REFERENCE PII_LOCAL_KEY_BASE64; do
  load_dotenv_value "$dotenv_name"
done

NGROK_URL="${NGROK_URL:-}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8001}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-3001}"
START_WORKER="${START_WORKER:-1}"
LIFF_ID="${LIFF_ID:-}"
LINE_LOGIN_CHANNEL_ID="${LINE_LOGIN_CHANNEL_ID:-}"
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

listeners_on_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | sort -u
  elif command -v ss >/dev/null 2>&1; then
    ss -tlnpH "sport = :${port}" 2>/dev/null \
      | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
  fi
}

# Set DEMO_KILL_STALE=1 to reclaim a port from a Ctrl-C'd previous run.
require_port_available() {
  local label="$1"
  local port="$2"
  local pids
  pids="$(listeners_on_port "$port" | tr '\n' ' ')"
  [[ -z "${pids// /}" ]] && return 0

  if [[ "${DEMO_KILL_STALE:-0}" == "1" ]]; then
    echo "[Line Demo] ${label} port ${port} 佔用中 (PID ${pids})，清除中" >&2
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
  echo "  停止舊服務：  kill ${pids}" >&2
  echo "  或自動清除：  DEMO_KILL_STALE=1 ./scripts/demo-line.sh" >&2
  exit 1
}

extract_tunnel_url() {
  local log_file="$1"
  sed -nE \
    -e 's#.*url=(https://[^[:space:]]+).*#\1#p' \
    -e 's#.*Forwarding[[:space:]]+(https://[^[:space:]]+).*#\1#p' \
    "$log_file" | head -n 1
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
  ngrok http "$port" --url "$NGROK_URL" --log=stdout --log-format=logfmt \
    >"$log_file" 2>&1 &
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
  if [[ "$url" != "$NGROK_URL" ]]; then
    echo "${label} tunnel URL 與 NGROK_URL 不一致：${url}" >&2
    exit 1
  fi
  TUNNEL_URL="$url"
}

require_value LIFF_ID
require_value SHELTER_ENTRY_REFERENCE
require_value NGROK_URL
NGROK_URL="${NGROK_URL%/}"
if [[ ! "$NGROK_URL" =~ ^https:// ]]; then
  echo "NGROK_URL 必須是 HTTPS 保留網址，例如 https://your-domain.ngrok.app" >&2
  exit 2
fi
require_command uv
require_command npm
require_command curl
if [[ "$LIFF_ID" != fake-* ]] && {
  [[ -z "$LINE_LOGIN_CHANNEL_ID" ]] || [[ "$LINE_LOGIN_CHANNEL_ID" == fake-* ]];
}; then
  echo "真實 LIFF_ID 必須搭配 LINE_LOGIN_CHANNEL_ID（LINE Login Channel 的 Channel ID）" >&2
  exit 2
fi
export LINE_LOGIN_CHANNEL_ID
require_command ngrok
require_port_available "API" "$API_PORT"
require_port_available "Web" "$WEB_PORT"

if [[ -z "${AUTH_JWT_ACTIVE_PRIVATE_KEY:-}" || -z "${AUTH_JWT_ACTIVE_PUBLIC_KEY:-}" ]]; then
  require_command openssl
  key_dir="$(mktemp -d "${TMPDIR:-/tmp}/strayhub-line-keys.XXXXXX")"
  # Keep stderr visible: a silent failure here surfaces later as an opaque
  # HTTP 503 (authentication_not_configured) from /v1/auth/login.
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
    -out "$key_dir/private.pem" >/dev/null
  openssl pkey -in "$key_dir/private.pem" -pubout \
    -out "$key_dir/public.pem" >/dev/null
  export AUTH_JWT_ACTIVE_PRIVATE_KEY="$(<"$key_dir/private.pem")"
  export AUTH_JWT_ACTIVE_PUBLIC_KEY="$(<"$key_dir/public.pem")"
  rm -rf "$key_dir"
  if [[ -z "$AUTH_JWT_ACTIVE_PRIVATE_KEY" || -z "$AUTH_JWT_ACTIVE_PUBLIC_KEY" ]]; then
    echo "openssl 未產生 JWT 金鑰；請確認 openssl 可用後重試。" >&2
    exit 1
  fi
fi

export PII_ALLOW_LOCAL_PROVIDER=true
if [[ -z "${PII_LOCAL_KEY_BASE64:-}" ]]; then
  require_command openssl
  export PII_LOCAL_KEY_BASE64="$(openssl rand -base64 32)"
fi

pids=()
log_dir="$(mktemp -d "${TMPDIR:-/tmp}/strayhub-line.XXXXXX")"
cleanup() {
  local pid port pids_on
  # Kill each child and its descendants (npm -> node -> next-server would
  # otherwise linger and hold WEB_PORT, causing EADDRINUSE next run).
  for pid in "${pids[@]:-}"; do
    [[ -z "$pid" ]] && continue
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill -TERM "$pid" 2>/dev/null || true
  done
  for port in "$API_PORT" "$WEB_PORT"; do
    pids_on="$(listeners_on_port "$port" | tr '\n' ' ')"
    # shellcheck disable=SC2086
    [[ -n "${pids_on// /}" ]] && kill -TERM $pids_on 2>/dev/null || true
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

echo "[Line Demo] Starting Web tunnel (ngrok: ${NGROK_URL})"
start_tunnel "Web" "$WEB_PORT" "$log_dir/web.log"
WEB_TUNNEL_URL="$TUNNEL_URL"
WEB_TUNNEL_HOST="${WEB_TUNNEL_URL#https://}"

# Next.js proxies /v1 server-side, so FastAPI stays private on the same host.
API_BASE_URL="http://${API_HOST}:${API_PORT}"
echo "[Line Demo] Starting Next.js with local API proxy"
API_BASE_URL="$API_BASE_URL" LIFF_ID="$LIFF_ID" \
  LINE_DEMO_WEB_ORIGIN_HOST="$WEB_TUNNEL_HOST" \
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

echo "[Line Demo] Web tunnel health check"
wait_for_tunnel_http "Web" "$WEB_TUNNEL_URL" "/volunteer-entry"

if [[ "$START_WORKER" == "1" ]]; then
  echo "[Line Demo] Starting worker"
  uv run python -m services.worker.worker &
  pids+=("$!")
fi

LIFF_ENDPOINT_URL="${WEB_TUNNEL_URL}/volunteer-entry?entry=${SHELTER_ENTRY_REFERENCE}"
LIFF_URL="https://liff.line.me/${LIFF_ID}"

echo
echo "[Line Demo] PASS"
echo "Local API:        ${API_BASE_URL}"
echo "Web tunnel:       ${WEB_TUNNEL_URL}"
echo "LIFF Endpoint:    ${LIFF_ENDPOINT_URL}"
echo "手機 LINE 入口:   ${LIFF_URL}"
echo
echo "請在 LINE Developers Console 設定 LIFF Endpoint URL："
echo "  ${LIFF_ENDPOINT_URL}"
echo "按 Ctrl-C 會停止本腳本啟動的 API、Web、tunnel 與 worker。"

wait "${pids[0]}"
