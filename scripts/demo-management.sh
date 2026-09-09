#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/demo-management.sh --profile shared-demo-production --activation-evidence FILE
  ./scripts/demo-management.sh --profile shared-demo-dev --activation-evidence FILE

Management exposure is never the default. This wrapper accepts only an explicit
shared profile and delegates lifecycle/cleanup to demo-line.sh.
EOF
}

if [[ $# -ne 4 || "$1" != "--profile" || "$3" != "--activation-evidence" ]]; then
  usage >&2
  exit 2
fi
case "$2" in
  shared-demo-production|shared-demo-dev) ;;
  *) usage >&2; exit 2 ;;
esac

echo "[Management Demo] Explicit shared public profile requested: $2"
exec "$ROOT_DIR/scripts/demo-line.sh" --profile "$2" --activation-evidence "$4"
