#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
REGION="${GCP_REGION:?GCP_REGION is required}"
JOB_NAME="${GCP_LINE_SYNC_JOB_NAME:-strayhub-demo-line-sync}"
SECRET_NAME="${GCP_LINE_SECRET_NAME:?GCP_LINE_SECRET_NAME is required}"

gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null
gcloud run jobs execute "$JOB_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --wait \
  --set-env-vars="LINE_SECRET_REFERENCE=projects/$PROJECT_ID/secrets/$SECRET_NAME"
echo "T242 Rich Menu sync completed without printing token material."
