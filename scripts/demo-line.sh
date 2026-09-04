#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

reveal_entry_reference=0
for argument in "$@"; do
  case "$argument" in
    --reveal-entry-reference) reveal_entry_reference=1 ;;
    --help|-h)
      echo "用法：$0 [--reveal-entry-reference]"
      echo "預設隱藏 LIFF entry reference；互動確認後可顯示一次完整 Endpoint。"
      exit 0
      ;;
    *)
      echo "用法：$0 [--reveal-entry-reference]" >&2
      exit 2
      ;;
  esac
done

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

for dotenv_name in NGROK_URL API_HOST API_PORT WEB_HOST WEB_PORT NGINX_PORT START_WORKER LIFF_ID LINE_LOGIN_CHANNEL_ID SHELTER_ENTRY_REFERENCE PII_LOCAL_KEY_BASE64; do
  load_dotenv_value "$dotenv_name"
done

NGROK_URL="${NGROK_URL:-}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8001}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-3001}"
NGINX_PORT="${NGINX_PORT:-8082}"
NGINX_BIN="${NGINX_BIN:-nginx}"
NGINX_TEMPLATE="infra/local/nginx/line-local.conf.template"
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
  for _ in $(seq 1 90); do
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
entry_reference_reveal_confirmed=0
if [[ "$reveal_entry_reference" == "1" ]]; then
  if [[ ! -t 0 || ! -t 1 ]]; then
    echo "--reveal-entry-reference 只允許互動式 terminal。" >&2
    exit 2
  fi
  read -r -p "輸入 REVEAL 以顯示一次完整 LIFF Endpoint（注意 terminal capture 風險）：" confirmation
  if [[ "$confirmation" == "REVEAL" ]]; then
    entry_reference_reveal_confirmed=1
  fi
fi
NGROK_URL="${NGROK_URL%/}"
if [[ ! "$NGROK_URL" =~ ^https:// ]]; then
  echo "NGROK_URL 必須是 HTTPS 保留網址，例如 https://your-domain.ngrok.app" >&2
  exit 2
fi
# LINE fetches Flex Message images server-side, so its URL must use the public
# tunnel origin rather than the local FastAPI address inferred behind Next.js.
export WEB_PUBLIC_BASE_URL="$NGROK_URL"
require_command uv
require_command npm
require_command curl
require_command python3
if [[ "$LIFF_ID" != fake-* ]] && {
  [[ -z "$LINE_LOGIN_CHANNEL_ID" ]] || [[ "$LINE_LOGIN_CHANNEL_ID" == fake-* ]];
}; then
  echo "真實 LIFF_ID 必須搭配 LINE_LOGIN_CHANNEL_ID（LINE Login Channel 的 Channel ID）" >&2
  exit 2
fi
export LINE_LOGIN_CHANNEL_ID
require_command ngrok
require_command "$NGINX_BIN"
require_port_available "API" "$API_PORT"
require_port_available "Web" "$WEB_PORT"
require_port_available "Gateway" "$NGINX_PORT"

if [[ -z "${AUTH_JWT_ACTIVE_PRIVATE_KEY:-}" || -z "${AUTH_JWT_ACTIVE_PUBLIC_KEY:-}" ]]; then
  require_command openssl
  key_dir="$(mktemp -d "${TMPDIR:-/tmp}/strayhub-line-keys.XXXXXX")"
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
    -out "$key_dir/private.pem" >/dev/null 2>&1
  openssl pkey -in "$key_dir/private.pem" -pubout \
    -out "$key_dir/public.pem" >/dev/null 2>&1
  export AUTH_JWT_ACTIVE_PRIVATE_KEY="$(<"$key_dir/private.pem")"
  export AUTH_JWT_ACTIVE_PUBLIC_KEY="$(<"$key_dir/public.pem")"
  rm -rf "$key_dir"
fi

export PII_ALLOW_LOCAL_PROVIDER=true
if [[ -z "${PII_LOCAL_KEY_BASE64:-}" ]]; then
  require_command openssl
  export PII_LOCAL_KEY_BASE64="$(openssl rand -base64 32)"
fi

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

for _ in $(seq 1 120); do
  if curl --max-time 1 -fsS "http://${API_HOST}:${API_PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl --max-time 5 -fsS "http://${API_HOST}:${API_PORT}/healthz" >/dev/null || {
  echo "FastAPI health check failed" >&2
  exit 1
}

# FastAPI and Next.js remain private upstreams behind the allowlisted gateway.
API_BASE_URL="http://${API_HOST}:${API_PORT}"
echo "[Line Demo] Starting Next.js with local API proxy"
API_BASE_URL="$API_BASE_URL" LIFF_ID="$LIFF_ID" \
  LINE_DEMO_WEB_ORIGIN_HOST="${NGROK_URL#https://}" \
  npm --prefix apps/web run dev -- --hostname "$WEB_HOST" --port "$WEB_PORT" &
pids+=("$!")

for _ in $(seq 1 240); do
  if curl --max-time 1 -fsS "http://${WEB_HOST}:${WEB_PORT}/volunteer-entry" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl --max-time 5 -fsS "http://${WEB_HOST}:${WEB_PORT}/volunteer-entry" >/dev/null || {
  echo "Next.js volunteer entry check failed" >&2
  exit 1
}

NGINX_PREFIX="$log_dir/nginx"
NGINX_CONFIG_FILE="$NGINX_PREFIX/line-local.conf"
mkdir -p "$NGINX_PREFIX/logs"
python3 - "$NGINX_TEMPLATE" "$NGINX_CONFIG_FILE" \
  "$API_PORT" "$WEB_PORT" "$NGINX_PORT" <<'PY'
from pathlib import Path
import sys

template_path, output_path, api_port, web_port, nginx_port = sys.argv[1:]
text = Path(template_path).read_text(encoding="utf-8")
for key, value in {
    "__API_PORT__": api_port,
    "__WEB_PORT__": web_port,
    "__NGINX_PORT__": nginx_port,
}.items():
    text = text.replace(key, value)
if "__" in text:
    raise SystemExit("unresolved nginx template placeholder")
Path(output_path).write_text(text, encoding="utf-8")
PY
"$NGINX_BIN" -p "$NGINX_PREFIX/" -c "$NGINX_CONFIG_FILE" -t
echo "[Line Demo] Starting default-deny LINE gateway"
"$NGINX_BIN" -p "$NGINX_PREFIX/" -c "$NGINX_CONFIG_FILE" -g "daemon off;" &
pids+=("$!")
for _ in $(seq 1 30); do
  if curl --max-time 1 -fsS "http://127.0.0.1:${NGINX_PORT}/volunteer-entry" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl --max-time 5 -fsS "http://127.0.0.1:${NGINX_PORT}/volunteer-entry" >/dev/null || {
  echo "Default-deny gateway health check failed" >&2
  exit 1
}
for denied_path in /login /v1/management/dashboard /v1/not-allowlisted; do
  denied_status="$(curl --max-time 3 -sS -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:${NGINX_PORT}${denied_path}")"
  if [[ "$denied_status" != "404" ]]; then
    echo "Gateway must deny ${denied_path}; received HTTP ${denied_status}" >&2
    exit 1
  fi
done

echo "[Line Demo] Starting public gateway tunnel (ngrok: ${NGROK_URL})"
start_tunnel "Gateway" "$NGINX_PORT" "$log_dir/gateway.log"
WEB_TUNNEL_URL="$TUNNEL_URL"

echo "[Line Demo] Public gateway health check"
wait_for_tunnel_http "Gateway" "$WEB_TUNNEL_URL" "/volunteer-entry"

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
if [[ "$entry_reference_reveal_confirmed" == "1" ]]; then
  echo "LIFF Endpoint (shown once): ${LIFF_ENDPOINT_URL}"
else
  echo "LIFF Endpoint:    ${WEB_TUNNEL_URL}/volunteer-entry?entry=[REDACTED]"
fi
echo "手機 LINE 入口:   ${LIFF_URL}"
echo
echo "請在 LINE Developers Console 設定完整 LIFF Endpoint URL；需要顯示一次時以 --reveal-entry-reference 互動執行。"
echo "按 Ctrl-C 會停止本腳本啟動的 API、Web、tunnel 與 worker。"

wait "${pids[0]}"
