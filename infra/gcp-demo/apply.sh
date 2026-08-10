#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_DIR="$ROOT_DIR/infra/gcp-demo/terraform"
EVIDENCE_FILE="$ROOT_DIR/infra/gcp-demo/gate-evidence.md"
TERRAFORM_BIN="${TERRAFORM_BIN:-terraform}"
PLAN_FILE="${PLAN_FILE:-$ROOT_DIR/infra/gcp-demo/terraform/demo.tfplan}"

if ! rg -q 'T238 PASS|Deployment Gate passed' "$EVIDENCE_FILE"; then
  echo "T239 blocked: T238 deployment gate evidence is not passing" >&2
  exit 1
fi
if [[ -z "${TF_VAR_project_id:-}" || -z "${TF_VAR_region:-}" ]]; then
  echo "T239 requires TF_VAR_project_id and TF_VAR_region" >&2
  exit 1
fi

"$TERRAFORM_BIN" -chdir="$TF_DIR" init -backend=false -input=false
"$TERRAFORM_BIN" -chdir="$TF_DIR" plan -input=false -out="$PLAN_FILE"
echo "Terraform plan written to $PLAN_FILE. Review it before apply."

if [[ "${GCP_DEMO_APPLY:-0}" != "1" ]]; then
  echo "No apply executed. Set GCP_DEMO_APPLY=1 only after human review of the plan."
  exit 0
fi

"$TERRAFORM_BIN" -chdir="$TF_DIR" apply -input=false "$PLAN_FILE"
echo "T239 apply completed; continue with migrate.sh, seed-demo.sh and sync-line.sh."
