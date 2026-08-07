#!/usr/bin/env sh
set -eu

env UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" uv run alembic history >/dev/null
env UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" uv run ruff check .
env UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" uv run pytest
npm --prefix apps/web run typecheck
npm --prefix apps/web test
npm --prefix packages/contracts run check
