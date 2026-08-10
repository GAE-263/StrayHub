#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
REGION="${GCP_REGION:?GCP_REGION is required}"
JOB_NAME="${GCP_MIGRATION_JOB_NAME:-strayhub-demo-migration}"

gcloud run jobs execute "$JOB_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --wait

gcloud run jobs describe "$JOB_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(latestCreatedExecution.completionStatus)'
echo "T240 migration job completed."
