#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/strayhub-uv-cache}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub}"
export STRAYHUB_TEST_DATABASE_URL="${STRAYHUB_TEST_DATABASE_URL:-postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub}"
TF_DIR="$ROOT_DIR/infra/gcp-demo/terraform"
TERRAFORM_BIN="${TERRAFORM_BIN:-terraform}"

require_command() {
  command -v "$1" >/dev/null || {
    echo "缺少必要命令：$1" >&2
    exit 1
  }
}

require_command uv
require_command npm
require_command docker
require_command "$TERRAFORM_BIN"

echo "[T237] Migration and fictional Seed"
uv run alembic upgrade head
uv run python -m scripts.seed_local >/tmp/strayhub-gcp-demo-seed.json

echo "[T237] Python quality and full local regression"
uv run ruff check .
uv run ruff format --check .
uv run pytest -q -p no:warnings

echo "[T237] Frontend and generated contracts"
npm --prefix apps/web run quality
npm --prefix packages/contracts run check

echo "[T237] Migration／Isolation／Storage／LINE contract boundaries"
uv run pytest \
  tests/integration/test_empty_database_bootstrap.py \
  tests/integration/test_database_scope_setter.py \
  tests/isolation/test_full_cross_tenant_matrix.py \
  tests/contract/test_storage_adapter_contract.py \
  tests/contract/test_storage_vendor_contract.py \
  tests/contract/test_line_adapter_contract.py \
  tests/contract/test_all_adapters.py \
  -q -p no:warnings

echo "[T237] Terraform format／init／validate"
"$TERRAFORM_BIN" fmt -check -recursive "$TF_DIR"
"$TERRAFORM_BIN" -chdir="$TF_DIR" init -backend=false -input=false
"$TERRAFORM_BIN" -chdir="$TF_DIR" validate

echo "[T237] Secret scan"
if rg -n --hidden \
  --glob '!.git/**' \
  --glob '!node_modules/**' \
  --glob '!**/.venv/**' \
  --glob '!**/.terraform/**' \
  --glob '!**/*.lock' \
  '(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC )?PRIVATE KEY-----|LINE_CHANNEL_ACCESS_[T]OKEN=)' \
  infra/gcp-demo; then
  echo "Secret scan failed: credential-shaped material detected" >&2
  exit 1
fi

echo "[T237] Docker build"
docker info >/dev/null
docker build -f infra/gcp-demo/Dockerfile.api -t strayhub-demo-api:gate .
docker build -f infra/gcp-demo/Dockerfile.worker -t strayhub-demo-worker:gate .
docker build -f infra/gcp-demo/Dockerfile.web -t strayhub-demo-web:gate .

echo "Deployment Gate passed. No Terraform apply was executed."
