#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/strayhub-uv-cache}"
export STRAYHUB_TEST_DATABASE_URL="${STRAYHUB_TEST_DATABASE_URL:-postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test}"
export DATABASE_URL="postgresql+asyncpg://${STRAYHUB_TEST_DATABASE_URL#postgresql://}"
uv run python -c 'from scripts.test_database import require_test_database; require_test_database()'

COMPOSE_FILE="infra/local/docker-compose.yml"

if [[ "${VERIFY_LOCAL_SKIP_DOCKER:-0}" != "1" ]]; then
  command -v docker >/dev/null
  echo "[T224] Docker Compose PostgreSQL／MinIO"
  docker compose -f "$COMPOSE_FILE" up -d postgres minio
  docker compose -f "$COMPOSE_FILE" ps
fi

echo "[T224] Migration"
uv run alembic upgrade head
uv run python -m scripts.configure_runtime_role --apply

echo "[T224] Empty database bootstrap／reversible migration"
uv run pytest tests/integration/test_empty_database_bootstrap.py -q

echo "[T224] Fictional seed"
uv run python -m scripts.seed_test_fixtures

echo "[T218-T221] Full local flow／isolation／failure／adapter contracts"
uv run pytest \
  tests/e2e/test_full_local_flow.py \
  tests/isolation/test_full_cross_tenant_matrix.py \
  tests/integration/test_full_local_failure_matrix.py \
  tests/contract/test_all_adapters.py \
  tests/contract/test_contract_documents.py \
  tests/contract/test_generated_contract_types.py \
  -q

echo "[T224] Full Python test suite"
uv run pytest -q

echo "[T245] Python lint, formatting and type check"
uv run ruff check services scripts tests
uv run ruff format --check services scripts tests
uv run mypy

echo "[T247] Frontend quality／build"
npm --prefix apps/web run quality
npm --prefix apps/web run build

echo "[T224] Generated OpenAPI contract types"
npm --prefix packages/contracts run check

echo "[T224] MinIO／GCS adapter contracts"
uv run pytest tests/contract/test_storage_adapter_contract.py tests/contract/test_storage_vendor_contract.py -q

echo "[T224] Secret scan"
if rg -n --hidden \
  --glob '!.git/**' \
  --glob '!node_modules/**' \
  --glob '!**/.venv/**' \
  --glob '!**/.next/**' \
  --glob '!**/*.lock' \
  '(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC )?PRIVATE KEY-----)' \
  .; then
  echo "Secret scan failed: credential-shaped material detected" >&2
  exit 1
fi

echo "[T224] Docker Build"
dockerfiles="$(rg --files -g 'Dockerfile*' || true)"
if [[ -z "$dockerfiles" ]]; then
  echo "Docker build skipped: no Dockerfiles configured"
else
  while IFS= read -r dockerfile; do
    [[ -z "$dockerfile" ]] && continue
    image_tag="strayhub-local:$(echo "$dockerfile" | tr '/: ' '---')"
    docker build -f "$dockerfile" -t "$image_tag" .
  done <<< "$dockerfiles"
fi

echo "Local verification passed. ORG-A／ORG-B are test fixtures only; normal demo uses demo.sh."
