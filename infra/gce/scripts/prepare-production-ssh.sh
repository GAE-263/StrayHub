#!/usr/bin/env bash
set -euo pipefail

# Both production jobs use this probe with their own ephemeral runner key.
# Never source credentials from another job or retry a remote mutation.
[[ "${SSH_INSTANCE:-}" =~ ^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$ ]] || exit 2
[[ "${SSH_PROJECT:-}" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || exit 2
[[ "${SSH_ZONE:-}" =~ ^[a-z]+-[a-z]+[0-9]+-[a-z]$ ]] || exit 2

# New runners have new OS Login keys. Retry only authentication for a
# side-effect-free probe; never retry deployment or receipt verification.
for attempt in 1 2 3; do
  if output="$(gcloud compute ssh "$SSH_INSTANCE" --project "$SSH_PROJECT" --zone "$SSH_ZONE" --tunnel-through-iap --quiet --ssh-flag='-o ConnectTimeout=15' --command true 2>&1)"; then
    break
  else
    status=$?
  fi
  if [[ "$status" != 255 || "$output" != *'Permission denied (publickey)'* || "$attempt" == 3 ]]; then
    printf 'Production SSH transport failed (exit=%s).\n' "$status" >&2
    exit "$status"
  fi
  printf 'Production SSH authentication unavailable; waiting before probe %s/3.\n' "$((attempt + 1))"
  sleep 10
done
