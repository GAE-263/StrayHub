#!/usr/bin/env sh
set -eu

test -f apps/web/package.json
test -f pyproject.toml
test -f services/api/app/main.py
test -f services/worker/worker.py
test -f services/api/migrations/versions/0001_bootstrap.py
printf '%s\n' "setup files are present"

