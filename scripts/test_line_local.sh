#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DIR="${TMPDIR:-/tmp}/strayhub-line-local-test"
NGROK_PID_FILE="$RUNTIME_DIR/ngrok.pid"
NGROK_CONFIG_FILE="$RUNTIME_DIR/ngrok.yml"
NGROK_LOG_FILE="$RUNTIME_DIR/ngrok.log"
NGINX_PREFIX="$RUNTIME_DIR/nginx"
NGINX_PID_FILE="$NGINX_PREFIX/nginx.pid"
NGINX_CONFIG_FILE="$NGINX_PREFIX/line-local.conf"
NGINX_TEMPLATE="infra/local/nginx/line-local.conf.template"
INSPECTION_URL="http://127.0.0.1:4040/api/tunnels"
MODE="${1:-run}"
NGROK_PID=""
NGINX_PID=""
NGINX_BIN="${NGINX_BIN:-nginx}"

pass() { printf '[PASS] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }
fail() { printf '[FAIL] %s\n' "$*" >&2; }
die() {
  fail "$1"
  exit "${2:-1}"
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/test_line_local.sh
  ./scripts/test_line_local.sh --no-tunnel
  ./scripts/test_line_local.sh --print-env
  ./scripts/test_line_local.sh stop

The helper validates an existing ./scripts/demo.sh stack, starts its own local
nginx proxy, and optionally exposes that one origin through one ngrok tunnel.
It never publishes a Rich Menu, modifies .env, or changes LINE Developers.
EOF
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command is missing: $1"
}

read_dotenv_value() {
  local name="$1"
  [[ -f .env ]] || return 0
  python3 - "$name" <<'PY'
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

resolve_demo_port() {
  python3 - "$1" <<'PY'
from pathlib import Path
import re
import sys

name = sys.argv[1]
source = Path("scripts/demo.sh").read_text(encoding="utf-8")
pattern = re.compile(rf'export {re.escape(name)}="\$\{{{re.escape(name)}:-([0-9]+)\}}"')
values = sorted(set(pattern.findall(source)))
if len(values) != 1:
    print(f"ambiguous_{name.lower()}", file=sys.stderr)
    raise SystemExit(2)
print(values[0])
PY
}

resolve_routes_and_env() {
  python3 <<'PY'
from pathlib import Path
import re

webhook_source = Path("services/api/app/api/line_webhook.py").read_text(encoding="utf-8")
main_source = Path("services/api/app/main.py").read_text(encoding="utf-8")
if "app.include_router(line_webhook_router)" not in main_source:
    raise SystemExit("LINE webhook router is not registered")
prefixes = set(re.findall(r'APIRouter\(prefix="([^"]+)"', webhook_source))
routes = set(re.findall(r'@router\.post\("([^"]+)"[^\n]*\)\s*\nasync def webhook', webhook_source))
if len(prefixes) != 1 or len(routes) != 1:
    raise SystemExit("LINE webhook route is ambiguous")

liff_pages = [
    path
    for path in Path("apps/web/app").rglob("page.tsx")
    if "VolunteerApplicationClient" in path.read_text(encoding="utf-8")
]
if len(liff_pages) != 1 or liff_pages[0].parent.name != "volunteer-application":
    raise SystemExit("Volunteer LIFF route is ambiguous")

proxy_source = Path("apps/web/app/v1/[...path]/route.ts").read_text(encoding="utf-8")
liff_source = liff_pages[0].read_text(encoding="utf-8")
next_source = Path("apps/web/next.config.ts").read_text(encoding="utf-8")

def one(pattern: str, source: str, label: str) -> str:
    values = sorted(set(re.findall(pattern, source)))
    if len(values) != 1:
        raise SystemExit(f"{label} is ambiguous")
    return values[0]

print(prefixes.pop() + routes.pop())
print("/volunteer-application")
print(one(r'process\.env\.([A-Z][A-Z0-9_]*)\?\.replace', proxy_source, "frontend API env"))
print(one(r'process\.env\.([A-Z][A-Z0-9_]*)\s*\?\?', liff_source, "LIFF ID env"))
print(one(r'process\.env\.([A-Z][A-Z0-9_]*)\?\.trim', next_source, "dev origin env"))
PY
}

pid_is_owned_ngrok() {
  local pid="$1"
  local command_line=""
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$command_line" == *ngrok*start* && "$command_line" == *"$NGROK_CONFIG_FILE"* ]]
}

pid_is_owned_nginx() {
  local pid="$1"
  local command_line=""
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$command_line" == *nginx*"$NGINX_PREFIX"*"$NGINX_CONFIG_FILE"* ]]
}

stop_owned_ngrok() {
  local pid=""
  [[ -f "$NGROK_PID_FILE" ]] || return 0
  pid="$(sed -n '1p' "$NGROK_PID_FILE" 2>/dev/null || true)"
  if pid_is_owned_ngrok "$pid"; then
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    pass "Stopped helper-owned ngrok process $pid"
  else
    warn "Stored ngrok PID is not an active process owned by this helper; nothing killed"
  fi
  rm -f "$NGROK_PID_FILE"
}

stop_owned_nginx() {
  local pid=""
  [[ -f "$NGINX_PID_FILE" ]] || return 0
  pid="$(sed -n '1p' "$NGINX_PID_FILE" 2>/dev/null || true)"
  if pid_is_owned_nginx "$pid"; then
    kill -QUIT "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    pass "Stopped helper-owned nginx process $pid"
  else
    warn "Stored nginx PID is not an active process owned by this helper; nothing killed"
  fi
  rm -f "$NGINX_PID_FILE"
}

remove_runtime_files() {
  rm -f "$NGROK_PID_FILE" "$NGROK_CONFIG_FILE" "$NGROK_LOG_FILE"
  rm -f "$NGINX_CONFIG_FILE" "$NGINX_PREFIX/logs/access.log" "$NGINX_PREFIX/logs/error.log"
  rmdir "$NGINX_PREFIX/logs" 2>/dev/null || true
  rmdir "$NGINX_PREFIX" 2>/dev/null || true
  rmdir "$RUNTIME_DIR" 2>/dev/null || true
}

cleanup() {
  if [[ -n "$NGROK_PID" ]] && pid_is_owned_ngrok "$NGROK_PID"; then
    kill "$NGROK_PID" 2>/dev/null || true
    wait "$NGROK_PID" 2>/dev/null || true
  fi
  if [[ -n "$NGINX_PID" ]] && pid_is_owned_nginx "$NGINX_PID"; then
    kill -QUIT "$NGINX_PID" 2>/dev/null || true
  fi
  remove_runtime_files
}

if [[ "$MODE" == "--help" || "$MODE" == "-h" ]]; then
  usage
  exit 0
fi
if [[ "$MODE" == "stop" ]]; then
  stop_owned_ngrok
  stop_owned_nginx
  remove_runtime_files
  exit 0
fi
if [[ "$MODE" != "run" && "$MODE" != "--no-tunnel" && "$MODE" != "--print-env" ]]; then
  usage >&2
  exit 2
fi

require_command python3

if [[ -n "${API_PORT:-}" ]]; then
  API_LOCAL_PORT="$API_PORT"
else
  API_LOCAL_PORT="$(resolve_demo_port API_PORT)" || die \
    "Could not resolve one API port from scripts/demo.sh; explicitly set API_PORT after resolving the conflict."
fi
if [[ -n "${WEB_PORT:-}" ]]; then
  WEB_LOCAL_PORT="$WEB_PORT"
else
  WEB_LOCAL_PORT="$(resolve_demo_port WEB_PORT)" || die \
    "Could not resolve one Web port from scripts/demo.sh; explicitly set WEB_PORT after resolving the conflict."
fi
NGINX_LOCAL_PORT="${NGINX_PORT:-8082}"
for port_name in API_LOCAL_PORT WEB_LOCAL_PORT NGINX_LOCAL_PORT; do
  port_value="${!port_name}"
  [[ "$port_value" =~ ^[0-9]+$ && "$port_value" -ge 1 && "$port_value" -le 65535 ]] || \
    die "$port_name must be an integer from 1 to 65535"
done

resolved="$(resolve_routes_and_env)" || die "Could not resolve current LINE/LIFF routes or environment variables"
LINE_WEBHOOK_ROUTE="$(printf '%s\n' "$resolved" | sed -n '1p')"
LIFF_ROUTE="$(printf '%s\n' "$resolved" | sed -n '2p')"
FRONTEND_API_ENV="$(printf '%s\n' "$resolved" | sed -n '3p')"
LIFF_ID_ENV="$(printf '%s\n' "$resolved" | sed -n '4p')"
ORIGIN_ENV="$(printf '%s\n' "$resolved" | sed -n '5p')"

for dotenv_name in LINE_CHANNEL_SECRET LINE_CHANNEL_ACCESS_TOKEN LINE_LOGIN_CHANNEL_ID LIFF_ID LIFF_HANDOFF_E2E_MOCK; do
  load_dotenv_value "$dotenv_name"
done

if [[ "$MODE" == "--print-env" ]]; then
  cat <<EOF
API_LOCAL_PORT=$API_LOCAL_PORT
WEB_LOCAL_PORT=$WEB_LOCAL_PORT
NGINX_LOCAL_PORT=$NGINX_LOCAL_PORT
LINE_WEBHOOK_ROUTE=$LINE_WEBHOOK_ROUTE
LIFF_ROUTE=$LIFF_ROUTE
FRONTEND_API_ENV=$FRONTEND_API_ENV
LIFF_ID_ENV=$LIFF_ID_ENV
ALLOWED_DEV_ORIGIN_ENV=$ORIGIN_ENV
NGINX_TEMPLATE=$NGINX_TEMPLATE
LIFF_ID=${LIFF_ID:-<unset>}
EOF
  exit 0
fi

required_env_failed=0
check_line_env() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "$value" ]]; then
    fail "$name is not set; configure it in the repository-root .env or shell environment"
    required_env_failed=1
  elif [[ "$value" == fake-* ]]; then
    fail "$name uses the repository fake value; real-device LINE testing requires a controlled real value"
    required_env_failed=1
  else
    pass "$name is set"
  fi
}

check_line_env LINE_CHANNEL_SECRET
check_line_env LINE_CHANNEL_ACCESS_TOKEN
check_line_env LINE_LOGIN_CHANNEL_ID
check_line_env LIFF_ID

if [[ "${LIFF_HANDOFF_E2E_MOCK:-0}" == "1" ]]; then
  fail "LIFF_HANDOFF_E2E_MOCK=1 is enabled; real LINE LIFF identity would be replaced by the E2E mock"
  required_env_failed=1
else
  pass "LIFF E2E mock identity is disabled"
fi
if [[ "${LIFF_ID:-}" == fake-* ]]; then
  fail "Volunteer LIFF would use the local fake identity path"
  required_env_failed=1
else
  pass "Volunteer LIFF is configured for real LINE identity"
fi

require_command curl
if curl --max-time 3 -fsS "http://127.0.0.1:${API_LOCAL_PORT}/healthz" >/dev/null 2>&1; then
  pass "API reachable at http://127.0.0.1:${API_LOCAL_PORT}"
else
  die "API is not reachable at http://127.0.0.1:${API_LOCAL_PORT}/healthz; run ./scripts/demo.sh first"
fi
if curl --max-time 5 -fsS "http://127.0.0.1:${WEB_LOCAL_PORT}${LIFF_ROUTE}" >/dev/null 2>&1; then
  pass "Web reachable at http://127.0.0.1:${WEB_LOCAL_PORT}${LIFF_ROUTE}"
else
  die "Web is not reachable at http://127.0.0.1:${WEB_LOCAL_PORT}${LIFF_ROUTE}; run ./scripts/demo.sh first"
fi

if ! python3 - <<'PY'
from pathlib import Path
import sys

text = Path("infra/local/line-rich-menu.yaml").read_text(encoding="utf-8")
required = """  - label: 志工報名
    type: uri
    uri: ${LIFF_BASE_URL}"""
if required not in text or "organization_id=" in text:
    sys.exit(1)
PY
then
  warn "Local Rich Menu does not match the shared general Volunteer LIFF architecture"
else
  pass "Local Rich Menu 志工報名 opens the shared LIFF without a shelter target"
fi

if [[ "$required_env_failed" -ne 0 ]]; then
  die "Required real LINE/LIFF environment is incomplete; nginx and tunnel were not started" 2
fi

require_command "$NGINX_BIN"
mkdir -p "$NGINX_PREFIX/logs"
python3 - "$NGINX_TEMPLATE" "$NGINX_CONFIG_FILE" \
  "$API_LOCAL_PORT" "$WEB_LOCAL_PORT" "$NGINX_LOCAL_PORT" <<'PY'
from pathlib import Path
import sys

template_path, output_path, api_port, web_port, nginx_port = sys.argv[1:]
text = Path(template_path).read_text(encoding="utf-8")
replacements = {
    "__API_PORT__": api_port,
    "__WEB_PORT__": web_port,
    "__NGINX_PORT__": nginx_port,
}
for key, value in replacements.items():
    text = text.replace(key, value)
if "__" in text:
    raise SystemExit("unresolved nginx template placeholder")
Path(output_path).write_text(text, encoding="utf-8")
PY

trap cleanup EXIT INT TERM
"$NGINX_BIN" -p "$NGINX_PREFIX/" -c "$NGINX_CONFIG_FILE" -t
"$NGINX_BIN" -p "$NGINX_PREFIX/" -c "$NGINX_CONFIG_FILE"
for _ in 1 2 3 4 5; do
  [[ -f "$NGINX_PID_FILE" ]] && break
  sleep 0.2
done
[[ -f "$NGINX_PID_FILE" ]] || die "nginx did not create its helper-owned PID file"
NGINX_PID="$(sed -n '1p' "$NGINX_PID_FILE")"
pid_is_owned_nginx "$NGINX_PID" || die "nginx process ownership could not be verified"

PROXY_LOCAL_URL="http://127.0.0.1:${NGINX_LOCAL_PORT}"
if curl --max-time 5 -fsS "$PROXY_LOCAL_URL/v1/public/volunteer-organizations" >/dev/null; then
  pass "nginx → API /v1"
else
  die "nginx did not preserve /v1/public/volunteer-organizations"
fi
if curl --max-time 5 -fsS "$PROXY_LOCAL_URL${LIFF_ROUTE}" >/dev/null; then
  pass "nginx → Web"
else
  die "nginx did not route ${LIFF_ROUTE} to Next.js"
fi

for denied_path in /login /v1/management/dashboard /v1/not-allowlisted; do
  denied_status="$(curl --max-time 3 -sS -o /dev/null -w '%{http_code}' \
    "$PROXY_LOCAL_URL${denied_path}")"
  [[ "$denied_status" == "404" ]] || die \
    "public gateway must deny ${denied_path}; received HTTP ${denied_status}"
done
pass "nginx default-deny boundary"

hmr_headers="$(curl --http1.1 --max-time 2 -sS -D - -o /dev/null \
  -H 'Connection: Upgrade' \
  -H 'Upgrade: websocket' \
  -H 'Sec-WebSocket-Version: 13' \
  -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  "$PROXY_LOCAL_URL/_next/webpack-hmr" 2>/dev/null || true)"
if [[ "$hmr_headers" == *" 101 "* ]]; then
  pass "nginx → Web HMR WebSocket"
elif [[ "$hmr_headers" == *" 403 "* ]]; then
  die "HMR WebSocket was rejected; verify that /_next never reaches FastAPI"
else
  warn "HMR endpoint did not return 101 in this Next.js process; deterministic nginx routing checks still apply"
fi

if [[ "$MODE" == "--no-tunnel" ]]; then
  cat <<EOF

Resolved local single-origin configuration
API:   http://127.0.0.1:${API_LOCAL_PORT}
Web:   http://127.0.0.1:${WEB_LOCAL_PORT}
Proxy: ${PROXY_LOCAL_URL}
Webhook route: ${LINE_WEBHOOK_ROUTE}
LIFF route: ${LIFF_ROUTE}
Rich Menu LIFF URI: https://liff.line.me/${LIFF_ID}
Optional signature test: uv run pytest tests/security/test_line_webhook_signature.py
EOF
  exit 0
fi

require_command ngrok
if ! ngrok config check >/dev/null 2>&1; then
  die "ngrok configuration/authentication is not ready; run 'ngrok config add-authtoken <token>'"
fi
if curl --max-time 1 -fsS "$INSPECTION_URL" >/dev/null 2>&1; then
  die "ngrok inspection API port 4040 is already in use; stop or reconfigure the unrelated ngrok agent first"
fi

mkdir -p "$RUNTIME_DIR"
if [[ -f "$NGROK_PID_FILE" ]]; then
  existing_pid="$(sed -n '1p' "$NGROK_PID_FILE" 2>/dev/null || true)"
  if pid_is_owned_ngrok "$existing_pid"; then
    die "This helper already owns ngrok process $existing_pid; run '$0 stop' first"
  fi
  rm -f "$NGROK_PID_FILE"
fi

cat >"$NGROK_CONFIG_FILE" <<EOF
version: "3"
tunnels:
  strayhub-single-origin:
    proto: http
    addr: 127.0.0.1:${NGINX_LOCAL_PORT}
EOF
if ! ngrok config check --config "$NGROK_CONFIG_FILE" >/dev/null 2>&1; then
  die "Generated ngrok v3 configuration is not supported by the installed ngrok CLI"
fi

ngrok_config_args=()
if [[ -n "${NGROK_CONFIG:-}" && -f "${NGROK_CONFIG}" ]]; then
  ngrok_config_args+=(--config "$NGROK_CONFIG")
elif [[ -n "${HOME:-}" && -f "$HOME/Library/Application Support/ngrok/ngrok.yml" ]]; then
  ngrok_config_args+=(--config "$HOME/Library/Application Support/ngrok/ngrok.yml")
elif [[ -n "${HOME:-}" && -f "$HOME/.config/ngrok/ngrok.yml" ]]; then
  ngrok_config_args+=(--config "$HOME/.config/ngrok/ngrok.yml")
elif [[ -n "${HOME:-}" && -f "$HOME/.ngrok2/ngrok.yml" ]]; then
  ngrok_config_args+=(--config "$HOME/.ngrok2/ngrok.yml")
elif [[ -z "${NGROK_AUTHTOKEN:-}" ]]; then
  die "Could not locate ngrok config; set NGROK_CONFIG or NGROK_AUTHTOKEN"
fi
ngrok_config_args+=(--config "$NGROK_CONFIG_FILE")

ngrok start strayhub-single-origin "${ngrok_config_args[@]}" \
  --log "$NGROK_LOG_FILE" --log-format logfmt &
NGROK_PID="$!"
printf '%s\n' "$NGROK_PID" >"$NGROK_PID_FILE"

PUBLIC_URL=""
for ((attempt = 1; attempt <= 20; attempt += 1)); do
  if ! kill -0 "$NGROK_PID" 2>/dev/null; then
    fail "ngrok exited before the single-origin tunnel was available"
    sed -n '1,80p' "$NGROK_LOG_FILE" >&2 || true
    exit 1
  fi
  tunnel_json="$(curl --max-time 2 -fsS "$INSPECTION_URL" 2>/dev/null || true)"
  if [[ -n "$tunnel_json" ]]; then
    PUBLIC_URL="$(printf '%s' "$tunnel_json" | python3 -c '
import json, sys
try:
    tunnels = json.load(sys.stdin).get("tunnels", [])
except (json.JSONDecodeError, AttributeError):
    raise SystemExit(0)
by_name = {item.get("name"): item.get("public_url", "") for item in tunnels}
value = by_name.get("strayhub-single-origin", "")
print(value if value.startswith("https://") else "")
')"
    [[ -n "$PUBLIC_URL" ]] && break
  fi
  sleep 1
done

[[ -n "$PUBLIC_URL" ]] || die "Could not discover the single HTTPS tunnel by name"
PUBLIC_HOST="${PUBLIC_URL#https://}"
PUBLIC_HOST="${PUBLIC_HOST%%/*}"

cat <<EOF

============================================================
StrayHub Local LINE Test
============================================================

Local direct
API:   http://127.0.0.1:${API_LOCAL_PORT}
Web:   http://127.0.0.1:${WEB_LOCAL_PORT}

Local nginx
Proxy: ${PROXY_LOCAL_URL}

Public
URL:   ${PUBLIC_URL}

LINE Developers

Webhook URL:
${PUBLIC_URL}${LINE_WEBHOOK_ROUTE}

LIFF Endpoint URL:
${PUBLIC_URL}${LIFF_ROUTE}

Rich Menu LIFF URI:
https://liff.line.me/${LIFF_ID}

Frontend API base:
${FRONTEND_API_ENV}=${PUBLIC_URL}

Next.js allowed dev origin:
${ORIGIN_ENV}=${PUBLIC_HOST}
============================================================

[WARN] ${LIFF_ID_ENV}, ${FRONTEND_API_ENV}, and ${ORIGIN_ENV} are read when
Next.js starts. If their current values differ, restart only the Web process with:

${FRONTEND_API_ENV}="${PUBLIC_URL}" ${LIFF_ID_ENV}="${LIFF_ID}" \
${ORIGIN_ENV}="${PUBLIC_HOST}" \
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port ${WEB_LOCAL_PORT}

Browser API calls use relative /v1 paths and nginx sends them directly to FastAPI.
No wildcard CORS or second public API tunnel is required.

LINE Platform must send a request with a valid X-Line-Signature; GET/curl is not
a complete signature test. Optional local check:
uv run pytest tests/security/test_line_webhook_signature.py

nginx and ngrok remain active until Ctrl-C or: ./scripts/test_line_local.sh stop
EOF

wait "$NGROK_PID"
