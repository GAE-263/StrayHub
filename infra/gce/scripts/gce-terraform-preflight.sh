#!/usr/bin/env bash
set -euo pipefail

EXPECTED_ACCOUNT=""
EXPECTED_PROJECT=""
EXPECTED_REGION=""
EXPECTED_ZONE=""

fail() {
  printf '[E1 Terraform preflight] FAIL: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --account) EXPECTED_ACCOUNT="${2:-}"; shift 2 ;;
    --project) EXPECTED_PROJECT="${2:-}"; shift 2 ;;
    --region) EXPECTED_REGION="${2:-}"; shift 2 ;;
    --zone) EXPECTED_ZONE="${2:-}"; shift 2 ;;
    *) fail "unknown or incomplete argument: $1" ;;
  esac
done

command -v gcloud >/dev/null 2>&1 || fail "gcloud is required"
for value in "$EXPECTED_ACCOUNT" "$EXPECTED_PROJECT" "$EXPECTED_REGION" "$EXPECTED_ZONE"; do
  [[ -n "$value" ]] || fail "account, project, region, and zone are all required"
done
[[ "$EXPECTED_ACCOUNT" =~ ^[^[:space:]@]+@[^[:space:]@]+$ ]] || fail "invalid account"
[[ "$EXPECTED_PROJECT" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || fail "invalid project"
[[ "$EXPECTED_REGION" =~ ^[a-z]+-[a-z]+[0-9]$ ]] || fail "invalid region"
[[ "$EXPECTED_ZONE" == "$EXPECTED_REGION-"? ]] || fail "zone must belong to region"

active_account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)')"
active_project="$(gcloud config get-value project 2>/dev/null)"
[[ "$active_account" == "$EXPECTED_ACCOUNT" ]] || fail "active gcloud account mismatch"
[[ "$active_project" == "$EXPECTED_PROJECT" ]] || fail "active gcloud project mismatch"

[[ "$(gcloud compute regions describe "$EXPECTED_REGION" --project "$EXPECTED_PROJECT" --format='value(status)')" == "UP" ]] ||
  fail "region is not UP"
[[ "$(gcloud compute zones describe "$EXPECTED_ZONE" --project "$EXPECTED_PROJECT" --format='value(status)')" == "UP" ]] ||
  fail "zone is not UP"

enabled_services="$(gcloud services list --enabled --project "$EXPECTED_PROJECT" --format='value(config.name)')"
grep -qx compute.googleapis.com <<<"$enabled_services" || fail "Compute Engine API is not enabled"

collision="$(
  {
    gcloud compute instances list --project "$EXPECTED_PROJECT" --format='value(name)' |
      grep -Fx strayhub-gce || true
    gcloud compute addresses list --project "$EXPECTED_PROJECT" --format='value(name)' |
      grep -Fx strayhub-gce-ip || true
    gcloud compute networks list --project "$EXPECTED_PROJECT" --format='value(name)' |
      grep -Fx strayhub-gce-vpc || true
    gcloud compute networks subnets list --project "$EXPECTED_PROJECT" --regions "$EXPECTED_REGION" --format='value(name)' |
      grep -Fx strayhub-gce-subnet || true
    gcloud compute firewall-rules list --project "$EXPECTED_PROJECT" --format='value(name)' |
      grep -E '^strayhub-gce-allow-(web|iap-ssh)$' || true
    gcloud iam service-accounts list --project "$EXPECTED_PROJECT" --format='value(email)' |
      grep -Fx "strayhub-gce-sa@$EXPECTED_PROJECT.iam.gserviceaccount.com" || true
  } | sed '/^[[:space:]]*$/d'
)"
[[ -z "$collision" ]] || fail "target resource name collision detected"

printf '[E1 Terraform preflight] PASS: account=%s project=%s region=%s zone=%s\n' \
  "$active_account" "$active_project" "$EXPECTED_REGION" "$EXPECTED_ZONE"
