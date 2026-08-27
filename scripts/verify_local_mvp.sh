#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/strayhub-uv-cache}"

if [[ "${VERIFY_LOCAL_MVP_SKIP_DOCKER:-0}" != "1" ]]; then
  command -v docker >/dev/null
  docker compose -f infra/local/docker-compose.yml up -d postgres minio
fi

export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub}"
export STRAYHUB_TEST_DATABASE_URL="${STRAYHUB_TEST_DATABASE_URL:-postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub}"

echo "[MVP] migration"
uv run alembic upgrade head

echo "[MVP] fictional seed"
uv run python -m scripts.seed_test_fixtures

echo "[MVP] PostgreSQL bootstrap／isolation／vertical flow／failure degradation"
uv run pytest \
  tests/integration/test_empty_database_bootstrap.py \
  tests/isolation/test_cross_tenant_resource_matrix.py \
  tests/e2e/test_local_line_bot_vertical_flow.py \
  tests/integration/test_local_failure_degradation.py \
  tests/e2e/test_us3_animal_timeline.py \
  -q

echo "[MVP] contracts and storage adapters"
uv run pytest \
  tests/contract/test_contract_documents.py \
  tests/contract/test_line_adapter_contract.py \
  tests/contract/test_storage_adapter_contract.py \
  tests/contract/test_storage_vendor_contract.py \
  tests/integration/test_media_validation.py \
  -q

echo "[MVP] Python quality"
uv run ruff check services scripts tests
uv run ruff format --check services scripts tests

echo "[MVP] frontend"
npm --prefix apps/web test -- --run
npm --prefix apps/web run typecheck

echo "[MVP] generated contract types"
npm --prefix packages/contracts run check

echo "Local MVP gate passed. ORG-A／ORG-B are test fixtures only; normal demo uses demo.sh."
