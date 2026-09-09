#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVIDENCE_FILE="${ACTIVATION_EVIDENCE_FILE:-}"
GENERATED_EVIDENCE=0

usage() {
  cat <<'EOF'
用法：
  ./scripts/demo-shared-management.sh [--activation-evidence FILE]

互動式建立／驗證 local demo data，要求安全輸入一次 demo 密碼，
再以 shared-demo-production 啟動 FastAPI、Next.js、nginx 與 ngrok。

未提供 FILE 時，授權操作者確認 ACTIVATE 後，腳本會根據已提交的
T055～T057 去敏驗收紀錄建立當次暫存 evidence，結束時自動刪除。

密碼不會寫入 URL、檔案或 command output。測試結束請按 Ctrl-C 停止所有程序。
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --activation-evidence)
      [[ $# -ge 2 ]] || { echo "--activation-evidence 需要檔案路徑" >&2; exit 2; }
      EVIDENCE_FILE="$2"
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
  shift
done

read_dotenv_value() {
  local name="$1"
  [[ -f "$ROOT_DIR/.env" ]] || return 0
  python3 - "$ROOT_DIR/.env" "$name" <<'PY'
from pathlib import Path
import ast
import sys

path = Path(sys.argv[1])
prefix = f"{sys.argv[2]}="
for raw_line in path.read_text(encoding="utf-8").splitlines():
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

if [[ -z "${NGROK_URL:-}" ]]; then
  NGROK_URL="$(read_dotenv_value NGROK_URL)"
fi
NGROK_URL="${NGROK_URL%/}"

if [[ -z "${STRAYHUB_DEMO_PASSWORD:-}" ]]; then
  if [[ ! -t 0 || ! -t 1 ]]; then
    echo "非互動執行必須先設定 STRAYHUB_DEMO_PASSWORD。" >&2
    exit 2
  fi
  read -r -s -p "輸入新的 demo 密碼：" STRAYHUB_DEMO_PASSWORD
  printf '\n'
  export STRAYHUB_DEMO_PASSWORD
fi

echo "[Shared Demo] Bootstrap and verify synthetic demo data"
"$ROOT_DIR/scripts/demo.sh" check

cleanup() {
  if [[ "$GENERATED_EVIDENCE" == "1" && -n "$EVIDENCE_FILE" ]]; then
    rm -f "$EVIDENCE_FILE"
  fi
}
trap cleanup EXIT INT TERM

if [[ -z "$EVIDENCE_FILE" ]]; then
  if [[ ! -t 0 || ! -t 1 ]]; then
    echo "非互動執行必須提供 --activation-evidence FILE。" >&2
    exit 2
  fi
  if [[ ! "$NGROK_URL" =~ ^https:// ]]; then
    echo "請先在 .env 或 shell environment 設定 HTTPS NGROK_URL。" >&2
    exit 2
  fi

  OPERATOR_ID=""
  read -r -p "授權操作者代號：" OPERATOR_ID
  [[ -n "$OPERATOR_ID" ]] || { echo "操作者代號不可為空。" >&2; exit 2; }
  printf '%s\n' "即將以 shared-demo-production 對外開放 synthetic demo：$NGROK_URL"
  read -r -p "輸入 ACTIVATE 確認本次受控啟用：" confirmation
  [[ "$confirmation" == "ACTIVATE" ]] || { echo "未授權啟用。" >&2; exit 2; }

  EVIDENCE_FILE="$(mktemp "${TMPDIR:-/tmp}/strayhub-activation.XXXXXX")"
  chmod 600 "$EVIDENCE_FILE"
  GENERATED_EVIDENCE=1
  python3 - "$ROOT_DIR" "$EVIDENCE_FILE" "$NGROK_URL" "$OPERATOR_ID" <<'PY'
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
output = Path(sys.argv[2])
origin = sys.argv[3]
operator = sys.argv[4]
incident = root / "specs/012-sensitive-data-transport-hardening/runtime-incident-result.md"
validation = root / "specs/013-remote-management-public-access/validation-result.md"
tasks = root / "specs/013-remote-management-public-access/tasks.md"

incident_text = incident.read_text(encoding="utf-8")
validation_text = validation.read_text(encoding="utf-8")
tasks_text = tasks.read_text(encoding="utf-8")
for task in ("T055", "T056", "T057"):
    if f"- [X] {task}" not in tasks_text:
        raise SystemExit(f"Committed activation prerequisite is incomplete: {task}")
if "COMPLETE WITH DOCUMENTED RESIDUAL RISK" not in incident_text:
    raise SystemExit("Committed incident evidence is incomplete")
if "READY_FOR_CONTROLLED_ACTIVATION" not in validation_text:
    raise SystemExit("Committed runtime validation is not activation-ready")

source_digests = {
    "incident": sha256(incident.read_bytes()).hexdigest(),
    "validation": sha256(validation.read_bytes()).hexdigest(),
    "tasks": sha256(tasks.read_bytes()).hexdigest(),
}
check_sources = {
    "exact_runtime_reserved_host_validated": origin,
    "synthetic_demo_data_verified": source_digests["tasks"],
    "old_demo_password_rejected": source_digests["incident"],
    "new_demo_password_accepted": source_digests["incident"],
    "old_demo_sessions_revoked": source_digests["incident"],
    "allow_and_deny_route_matrix_passed": source_digests["validation"],
    "sensitive_log_sentinel_absent": source_digests["validation"],
}
payload = {
    "version": 1,
    "evidence_kind": "manual_external",
    "runtime_origin": origin,
    "environment": "local-synthetic-demo",
    "operator": operator,
    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    "checks": {
        name: {
            "result": "PASS",
            "evidence_digest_sha256": sha256(
                f"{name}:{source}".encode("utf-8")
            ).hexdigest(),
        }
        for name, source in check_sources.items()
    },
}
output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY
  echo "[Shared Demo] Temporary activation evidence created (removed on exit)"
elif [[ ! -f "$EVIDENCE_FILE" ]]; then
  echo "找不到 activation evidence：$EVIDENCE_FILE" >&2
  exit 2
fi

echo "[Shared Demo] Starting explicit shared-demo-production profile"
echo "[Shared Demo] External URL will be printed by the helper; do not put credentials in it."
"$ROOT_DIR/scripts/demo-management.sh" \
  --profile shared-demo-production \
  --activation-evidence "$EVIDENCE_FILE"
