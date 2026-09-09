#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/strayhub-uv-cache}"
if ! command -v uv >/dev/null 2>&1; then
  echo "缺少 uv，請先安裝 uv 後重新執行。" >&2
  exit 1
fi
exec uv run --locked python -m scripts.dev "$@"
