#!/usr/bin/env sh
set -eu

mc alias set local http://localhost:9000 local-access-key local-secret-key
mc mb --ignore-existing local/strayhub-private
mc anonymous set none local/strayhub-private
mc ilm rule add --expire-days 1 local/strayhub-private --prefix temporary/ 2>/dev/null || true

