#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEFAULT_MAP="$ROOT_DIR/infra/gce/secrets/production-secret-map.tsv"
PROJECT_ID=""
ENVIRONMENT=""
NAME_PREFIX="strayhub"
OUTPUT_ROOT="/var/lib/strayhub/secrets"
SECRET_MAP="$DEFAULT_MAP"
SOURCE_DIR=""
GCLOUD_BIN="${STRAYHUB_GCLOUD_BIN:-gcloud}"

usage() {
  cat >&2 <<'EOF'
Usage: fetch-secrets.sh --environment NAME [--project PROJECT_ID] [options]

Options:
  --output-root PATH   Protected staging root (default: /var/lib/strayhub/secrets)
  --name-prefix NAME   Secret Manager ID prefix (default: strayhub)
  --secret-map PATH    Declarative secret inventory
  --source-dir PATH    Synthetic local source instead of GCP (verification only)
  --gcloud-bin PATH    Explicit gcloud-compatible executable
EOF
}

fail() {
  echo "[Secret staging] FAIL: $*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --project) PROJECT_ID="${2:-}"; shift 2 ;;
    --environment) ENVIRONMENT="${2:-}"; shift 2 ;;
    --name-prefix) NAME_PREFIX="${2:-}"; shift 2 ;;
    --output-root) OUTPUT_ROOT="${2:-}"; shift 2 ;;
    --secret-map) SECRET_MAP="${2:-}"; shift 2 ;;
    --source-dir) SOURCE_DIR="${2:-}"; shift 2 ;;
    --gcloud-bin) GCLOUD_BIN="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; fail "unknown or incomplete argument: $1" ;;
  esac
done

[[ "$ENVIRONMENT" =~ ^[a-z][a-z0-9-]{1,30}$ ]] || fail "invalid --environment"
[[ "$NAME_PREFIX" =~ ^[a-z][a-z0-9-]{1,30}$ ]] || fail "invalid --name-prefix"
[[ -f "$SECRET_MAP" ]] || fail "secret map not found"
command -v python3 >/dev/null || fail "python3 is required for atomic activation"
if [[ -z "$SOURCE_DIR" ]]; then
  [[ "$PROJECT_ID" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || fail "invalid --project"
  command -v "$GCLOUD_BIN" >/dev/null || fail "gcloud is required for live read-only fetch"
else
  [[ -d "$SOURCE_DIR" ]] || fail "synthetic source directory not found"
  SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd -P)"
fi

mkdir -p "$OUTPUT_ROOT"
chmod 700 "$OUTPUT_ROOT"
OUTPUT_ROOT="$(cd "$OUTPUT_ROOT" && pwd -P)"
repo_root="$(cd "$ROOT_DIR" && pwd -P)"
case "$OUTPUT_ROOT" in
  "$repo_root"|"$repo_root"/*)
    allowed_local="$repo_root/infra/gce/verification/generated/d1-secrets"
    [[ "$OUTPUT_ROOT" == "$allowed_local" || "$OUTPUT_ROOT" == "$allowed_local"/* ]] ||
      fail "repository staging is allowed only below ignored verification/generated/d1-secrets"
    ;;
esac

mkdir -p "$OUTPUT_ROOT/generations"
chmod 700 "$OUTPUT_ROOT/generations"
staging_dir="$(mktemp -d "$OUTPUT_ROOT/.staging.XXXXXX")"
chmod 700 "$staging_dir"
cleanup() {
  rm -rf -- "$staging_dir"
}
trap cleanup EXIT

required_count=0
optional_count=0
while IFS='|' read -r transport runtime_name suffix staged_filename requiredness; do
  [[ -n "$transport" && "${transport:0:1}" != "#" ]] || continue
  [[ "$transport" == "env" || "$transport" == "file" ]] || fail "invalid transport in map"
  [[ "$runtime_name" =~ ^[A-Z][A-Z0-9_]+$ ]] || fail "invalid runtime name in map"
  [[ "$suffix" =~ ^[a-z][a-z0-9-]+$ ]] || fail "invalid secret suffix in map"
  [[ "$requiredness" == "required" || "$requiredness" == "optional" ]] ||
    fail "invalid requiredness in map"
  secret_id="$NAME_PREFIX-$ENVIRONMENT-$suffix"
  if [[ "$transport" == "env" ]]; then
    destination="$staging_dir/.scalar-$runtime_name"
  else
    [[ "$staged_filename" =~ ^[a-z][a-z0-9.-]+$ ]] || fail "invalid staged filename"
    destination="$staging_dir/$staged_filename"
  fi
  error_log="$staging_dir/.fetch-error"
  if [[ -n "$SOURCE_DIR" ]]; then
    if [[ -f "$SOURCE_DIR/$secret_id" ]]; then
      cp "$SOURCE_DIR/$secret_id" "$destination"
      fetched=true
    else
      fetched=false
    fi
  elif "$GCLOUD_BIN" secrets versions access latest \
    --project "$PROJECT_ID" --secret "$secret_id" >"$destination" 2>"$error_log"; then
    fetched=true
  else
    fetched=false
  fi
  rm -f "$error_log"
  if [[ "$fetched" != true || ! -s "$destination" ]]; then
    rm -f "$destination"
    [[ "$requiredness" == "optional" ]] && { optional_count=$((optional_count + 1)); continue; }
    fail "required secret is missing or empty: $secret_id"
  fi
  chmod 600 "$destination"
  if [[ "$transport" == "env" ]]; then
    value="$(<"$destination")"
    [[ -n "$value" && "$value" != *$'\n'* && "$value" != *$'\r'* ]] ||
      fail "$secret_id must be a non-empty single-line scalar"
    unset value
  fi
  [[ "$requiredness" == "required" ]] && required_count=$((required_count + 1))
done <"$SECRET_MAP"

private_key="$staging_dir/jwt-private.pem"
public_key="$staging_dir/jwt-public.pem"
openssl pkey -in "$private_key" -noout >/dev/null 2>&1 || fail "staged JWT private key is invalid"
openssl pkey -pubin -in "$public_key" -noout >/dev/null 2>&1 || fail "staged JWT public key is invalid"
derived_public="$staging_dir/.derived-public.pem"
openssl pkey -in "$private_key" -pubout -out "$derived_public" >/dev/null 2>&1
cmp -s "$derived_public" "$public_key" || fail "staged JWT active key pair does not match"
rm -f "$derived_public"

runtime_env="$staging_dir/runtime.env"
: >"$runtime_env"
while IFS='|' read -r transport runtime_name _suffix _staged_filename _requiredness; do
  [[ "$transport" == "env" ]] || continue
  scalar_file="$staging_dir/.scalar-$runtime_name"
  [[ -f "$scalar_file" ]] || continue
  value="$(<"$scalar_file")"
  escaped="${value//\\/\\\\}"
  escaped="${escaped//\'/\\\'}"
  printf "%s='%s'\n" "$runtime_name" "$escaped" >>"$runtime_env"
  unset value escaped
  rm -f "$scalar_file"
done <"$SECRET_MAP"
chmod 600 "$runtime_env" "$private_key" "$public_key"

generation_id="$(date -u +%Y%m%dT%H%M%SZ)-$(openssl rand -hex 4)"
generation_dir="$OUTPUT_ROOT/generations/$generation_id"
[[ ! -e "$generation_dir" ]] || fail "generation already exists"
mv "$staging_dir" "$generation_dir"
staging_dir="$OUTPUT_ROOT/.staging-complete"
next_link="$OUTPUT_ROOT/.current.$$"
ln -s "generations/$generation_id" "$next_link"
python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' \
  "$next_link" "$OUTPUT_ROOT/current"

printf '[Secret staging] PASS: activated generation %s (%d required, %d optional unavailable)\n' \
  "$generation_id" "$required_count" "$optional_count"
