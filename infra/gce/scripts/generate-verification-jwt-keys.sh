#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEFAULT_OUTPUT_DIR="$ROOT_DIR/infra/gce/verification/generated"
OUTPUT_DIR="${STRAYHUB_VERIFICATION_JWT_DIR:-$DEFAULT_OUTPUT_DIR}"
PRIVATE_KEY="$OUTPUT_DIR/jwt-private.pem"
PUBLIC_KEY="$OUTPUT_DIR/jwt-public.pem"
FORCE=0

usage() {
  echo "Usage: $0 [--force]" >&2
}

case "${1:-}" in
  "") ;;
  --force) FORCE=1 ;;
  *) usage; exit 2 ;;
esac
[[ $# -le 1 ]] || { usage; exit 2; }

command -v openssl >/dev/null || {
  echo "[Verification JWT] FAIL: openssl is required" >&2
  exit 1
}

valid_pair() {
  [[ -f "$PRIVATE_KEY" && -f "$PUBLIC_KEY" ]] || return 1
  openssl pkey -in "$PRIVATE_KEY" -noout >/dev/null 2>&1 || return 1
  openssl rsa -in "$PRIVATE_KEY" -check -noout >/dev/null 2>&1 || return 1
  openssl pkey -pubin -in "$PUBLIC_KEY" -noout >/dev/null 2>&1 || return 1
  openssl pkey -in "$PRIVATE_KEY" -text -noout 2>/dev/null \
    | sed -n '1p' | grep -Eq '\(2048 bit' || return 1

  derived_public="$(mktemp "${TMPDIR:-/tmp}/strayhub-jwt-public.XXXXXX")"
  if ! openssl pkey -in "$PRIVATE_KEY" -pubout -out "$derived_public" >/dev/null 2>&1; then
    rm -f "$derived_public"
    return 1
  fi
  if ! cmp -s "$derived_public" "$PUBLIC_KEY"; then
    rm -f "$derived_public"
    return 1
  fi
  rm -f "$derived_public"
}

mkdir -p "$OUTPUT_DIR"

if [[ "$FORCE" == "0" ]] && valid_pair; then
  chmod 600 "$PRIVATE_KEY"
  chmod 644 "$PUBLIC_KEY"
  echo "[Verification JWT] Reusing valid RSA 2048 keypair in $OUTPUT_DIR"
  exit 0
fi

temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/strayhub-jwt-generate.XXXXXX")"
cleanup() {
  rm -rf "$temporary_dir"
}
trap cleanup EXIT

if ! openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out "$temporary_dir/jwt-private.pem" 2>"$temporary_dir/openssl-error.log"; then
  echo "[Verification JWT] FAIL: OpenSSL could not generate the private key" >&2
  sed -n '1,5p' "$temporary_dir/openssl-error.log" >&2
  exit 1
fi
openssl pkey -in "$temporary_dir/jwt-private.pem" -pubout \
  -out "$temporary_dir/jwt-public.pem" >/dev/null 2>&1
chmod 600 "$temporary_dir/jwt-private.pem"
chmod 644 "$temporary_dir/jwt-public.pem"
mv -f "$temporary_dir/jwt-private.pem" "$PRIVATE_KEY"
mv -f "$temporary_dir/jwt-public.pem" "$PUBLIC_KEY"

valid_pair || {
  echo "[Verification JWT] FAIL: generated keypair validation failed" >&2
  exit 1
}
echo "[Verification JWT] Generated fresh RSA 2048 keypair in $OUTPUT_DIR"
