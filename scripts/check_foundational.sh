#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
export STRAYHUB_TEST_DATABASE_URL="${STRAYHUB_TEST_DATABASE_URL:-postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test}"
export DATABASE_URL="${STRAYHUB_TEST_DATABASE_URL/postgresql:\/\//postgresql+asyncpg:\/\/}"
uv run python -c 'from scripts.test_database import require_test_database; require_test_database()'

echo "[foundational] checking migration files"
test -f services/api/migrations/versions/0003_tenant_rls.py
test -f services/api/migrations/versions/0007_ai_jobs.py
uv run alembic -c services/api/alembic.ini upgrade head

echo "[foundational] checking contract and security tests"
uv run pytest \
  tests/contract/test_authentication_contract.py \
  tests/contract/test_authentication_adapters.py \
  tests/contract/test_authentication_adapters_extra.py \
  tests/integration/test_database_scope_setter.py \
  tests/integration/test_authentication_session.py \
  tests/integration/test_observation_vocabulary_foundation.py \
  tests/integration/test_ai_job_persistence_foundation.py \
  tests/integration/test_audit_service.py \
  tests/security/test_unauthenticated_internal_data.py \
  tests/isolation/test_foundational_tenant_matrix.py

echo "[foundational] checking Python quality"
uv run ruff check services scripts tests
uv run ruff format --check services scripts tests

echo "[foundational] checking repository gates"
uv run alembic history >/dev/null
uv run pytest
npm --prefix apps/web run typecheck
npm --prefix apps/web test
npm --prefix packages/contracts run check

echo "[foundational] PASS"
