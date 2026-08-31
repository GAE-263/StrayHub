#!/bin/sh
set -eu

private_key_file=/run/secrets/runtime_jwt_private_key
public_key_file=/run/secrets/runtime_jwt_public_key

if [ ! -r "$private_key_file" ] || [ ! -r "$public_key_file" ]; then
  echo "acceptance verification requires the existing read-only runtime JWT mounts" >&2
  exit 1
fi

export AUTH_JWT_ACTIVE_PRIVATE_KEY="$(cat "$private_key_file")"
export AUTH_JWT_ACTIVE_PUBLIC_KEY="$(cat "$public_key_file")"

exec python -m scripts.verify_acceptance_live "$@"
