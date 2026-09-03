#!/usr/bin/env bash
set -euo pipefail

CURRENT_LINK="/opt/strayhub/current"
CONFIG_ENV="/etc/strayhub/production.env"
SECRETS_ENV="/var/lib/strayhub/secrets/current/runtime.env"
STATE_DIR="/var/lib/strayhub/releases"
GIT_SHA=""
RELEASE_ID=""

fail() {
  printf '[GCE release verification] FAIL: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --git-sha) GIT_SHA="${2:-}"; shift 2 ;;
    --release-id) RELEASE_ID="${2:-}"; shift 2 ;;
    *) fail "unknown or incomplete argument: $1" ;;
  esac
done

[[ "${EUID:-$(id -u)}" == "0" ]] || fail "run as root through the approved OS Login/IAP path"
[[ "$GIT_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "invalid expected Git SHA"
[[ "$RELEASE_ID" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] || fail "invalid release ID"
[[ -L "$CURRENT_LINK" ]] || fail "current release pointer is missing"
[[ -L "$STATE_DIR/current.json" ]] || fail "successful current deployment receipt is missing"

current_dir="$(readlink -f "$CURRENT_LINK")"
[[ "$current_dir" == "/opt/strayhub/releases/$RELEASE_ID" ]] ||
  fail "current release pointer does not match expected release"
manifest_tool="$current_dir/infra/gce/scripts/release-manifest.py"
[[ -x "$manifest_tool" ]] || fail "release manifest tool is unavailable"
"$manifest_tool" validate-release-dir --release-dir "$current_dir" >/dev/null
[[ "$("$manifest_tool" show-field --manifest "$current_dir/release-manifest.json" --field git_sha)" == "$GIT_SHA" ]] ||
  fail "current manifest Git SHA does not match expected release"

python3 - "$STATE_DIR/current.json" "$GIT_SHA" "$RELEASE_ID" <<'PY'
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if receipt.get("git_sha") != sys.argv[2]:
    raise SystemExit("current receipt Git SHA mismatch")
if receipt.get("release_id") != sys.argv[3]:
    raise SystemExit("current receipt release ID mismatch")
if receipt.get("verification") != "passed":
    raise SystemExit("current receipt is not verified")
PY

"$current_dir/infra/gce/scripts/verify-systemd-runtime.sh" \
  --config-env "$CONFIG_ENV" \
  --secrets-env "$SECRETS_ENV" \
  --image-env "$current_dir/image-digests.env" \
  --timeout 180

printf '[GCE release verification] PASS: %s at %s\n' "$RELEASE_ID" "$GIT_SHA"
