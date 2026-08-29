#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEFAULT_GENERATED_DIR="$ROOT_DIR/infra/gce/verification/generated"
DEFAULT_OUTPUT_DIR="$DEFAULT_GENERATED_DIR/tls"
OUTPUT_DIR="${STRAYHUB_VERIFICATION_TLS_DIR:-$DEFAULT_OUTPUT_DIR}"
ACME_WEBROOT="${STRAYHUB_VERIFICATION_ACME_WEBROOT:-$DEFAULT_GENERATED_DIR/acme-webroot}"
LIVE_DIR="$OUTPUT_DIR/live/strayhub"
PRIVATE_KEY="$LIVE_DIR/privkey.pem"
CERTIFICATE="$LIVE_DIR/fullchain.pem"
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
  echo "[Verification TLS] FAIL: openssl is required" >&2
  exit 1
}

valid_pair() {
  [[ -f "$PRIVATE_KEY" && -f "$CERTIFICATE" ]] || return 1
  openssl pkey -in "$PRIVATE_KEY" -noout >/dev/null 2>&1 || return 1
  openssl x509 -in "$CERTIFICATE" -noout -checkend 86400 >/dev/null 2>&1 || return 1
  openssl x509 -in "$CERTIFICATE" -text -noout 2>/dev/null |
    grep -q 'DNS:localhost' || return 1

  certificate_public="$(mktemp "${TMPDIR:-/tmp}/strayhub-tls-cert-public.XXXXXX")"
  private_public="$(mktemp "${TMPDIR:-/tmp}/strayhub-tls-key-public.XXXXXX")"
  if ! openssl x509 -in "$CERTIFICATE" -pubkey -noout >"$certificate_public" 2>/dev/null ||
    ! openssl pkey -in "$PRIVATE_KEY" -pubout >"$private_public" 2>/dev/null ||
    ! cmp -s "$certificate_public" "$private_public"; then
    rm -f "$certificate_public" "$private_public"
    return 1
  fi
  rm -f "$certificate_public" "$private_public"
}

mkdir -p "$LIVE_DIR" "$ACME_WEBROOT/.well-known/acme-challenge"

if [[ "$FORCE" == "0" ]] && valid_pair; then
  chmod 600 "$PRIVATE_KEY"
  chmod 644 "$CERTIFICATE"
  echo "[Verification TLS] Reusing valid self-signed certificate in $LIVE_DIR"
  exit 0
fi

temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/strayhub-tls-generate.XXXXXX")"
cleanup() {
  rm -rf "$temporary_dir"
}
trap cleanup EXIT

openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 30 \
  -subj '/CN=b4-verification.local' \
  -addext 'subjectAltName=DNS:b4-verification.local,DNS:localhost,IP:127.0.0.1' \
  -keyout "$temporary_dir/privkey.pem" \
  -out "$temporary_dir/fullchain.pem" >/dev/null 2>"$temporary_dir/openssl-error.log" || {
    echo "[Verification TLS] FAIL: OpenSSL could not generate the certificate" >&2
    sed -n '1,5p' "$temporary_dir/openssl-error.log" >&2
    exit 1
  }
chmod 600 "$temporary_dir/privkey.pem"
chmod 644 "$temporary_dir/fullchain.pem"
mv -f "$temporary_dir/privkey.pem" "$PRIVATE_KEY"
mv -f "$temporary_dir/fullchain.pem" "$CERTIFICATE"

valid_pair || {
  echo "[Verification TLS] FAIL: generated certificate validation failed" >&2
  exit 1
}
echo "[Verification TLS] Generated self-signed certificate in $LIVE_DIR"
