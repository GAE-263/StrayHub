#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
REGION="${GCP_REGION:?GCP_REGION is required}"
JOB_NAME="${GCP_SEED_JOB_NAME:-strayhub-demo-seed}"

gcloud run jobs execute "$JOB_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --wait \
  --args="--fictional-only"
echo "T241 fictional Organization A/B seed job completed."
