#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' \
  'Legacy Cloud Run seed is retired. Use the guarded GCE acceptance bootstrap when authorized.' >&2
exit 1
