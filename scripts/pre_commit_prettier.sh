#!/usr/bin/env bash
# Run Prettier from apps/web so .prettierignore and config match CI's `prettier --check .`.
set -euo pipefail
cd "$(dirname "$0")/../apps/web"
files=()
for path in "$@"; do
  files+=("${path#apps/web/}")
done
[ "${#files[@]}" -gt 0 ] || exit 0
exec npx --no-install prettier --write --ignore-unknown "${files[@]}"
