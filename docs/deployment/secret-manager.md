# Secret Manager Runtime Staging

Status: Phase D1 local staging and consumption verified; live GCP validation deferred

## Boundary and secret inventory

The canonical production flow is centralized at the GCE host boundary:

```text
GCP Secret Manager
  -> one read-only fetch-secrets.sh invocation on the VM
  -> immutable protected generation under /var/lib/strayhub/secrets
  -> atomic current symlink
  -> runtime.env plus JWT files
  -> Docker Compose services
```

The fetcher reads the declarative `infra/gce/secrets/production-secret-map.tsv`. Secret IDs follow
`<prefix>-<environment>-<suffix>`; the defaults form names such as
`strayhub-prod-database-url`. The GCP project ID is always an explicit command input and is never
committed. The canonical required inventory is:

| Staged value | Transport | Consumers |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | Protected `runtime.env` | PostgreSQL bootstrap/migration owner |
| `POSTGRES_RUNTIME_PASSWORD` | Protected `runtime.env` | PostgreSQL restricted runtime role |
| `DATABASE_URL` | Protected `runtime.env` | API, Worker |
| `DATABASE_MIGRATION_URL` | Protected `runtime.env` | one-shot migration |
| `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | Protected `runtime.env` | MinIO, bootstrap, API |
| `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN` | Protected `runtime.env` | API |
| `ANIMAL_CONFIRMATION_SECRET` | Protected `runtime.env` | API |
| active JWT private/public pair | `jwt-private.pem`, `jwt-public.pem` | API only, read-only |
| `AI_API_KEY` | Optional protected `runtime.env` entry | API only when external AI is selected |

`LINE_CHANNEL_ID`, `LIFF_ID`, JWT issuer/audience/references, storage endpoint/bucket, KMS resource
name, and AI provider/endpoint/model are non-secret configuration. The current runtime does not use a
LINE Login channel secret. Existing application settings remain compatible with a previous JWT
public key, but enabling that rotation input requires a separately reviewed optional Compose file
mount; D1 does not redesign JWT rotation or make a previous key mandatory.

## Fetch and atomic staging

On the future VM, an operator runs an explicit read-only fetch:

```bash
infra/gce/scripts/fetch-secrets.sh \
  --project <approved-project-id> \
  --environment prod \
  --output-root /var/lib/strayhub/secrets
```

The script uses only `gcloud secrets versions access latest`; it does not create or mutate secrets,
versions, or IAM. It fetches only mapped IDs, redirects bodies straight into private staging files,
never passes values as command arguments, and never prints them. A missing/empty required value or
invalid/mismatched JWT pair aborts before activation.

Each successful fetch creates an immutable `generations/<UTC-id>/` directory and atomically replaces
the `current` symlink. This switches `runtime.env` and both active JWT files as one generation. The
staging root and generation directories use directory mode `0700`; every secret uses file mode `0600`.
Ownership belongs to the future deployment/runtime administrator selected in Phase E; D1
does not assume a Linux username. Old generations are not automatically deleted in D1.

## Production and verification separation

`infra/gce/.env.production.template` is non-secret and intentionally incomplete. Copy it to a
protected host config path, fill only non-secret fields, and keep `B1_VERIFICATION_ONLY=false`.
Production Compose combines it with `/var/lib/strayhub/secrets/current/runtime.env` and selects JWT
files below that same external root.

The historical B1 verifier remains separate: `.env.production.example` has
`B1_VERIFICATION_ONLY=true`, synthetic scalar values, and runtime-generated verification JWT files
under the ignored repository path. Production preflight rejects that marker and any
`verification/generated` path. Production never silently falls back to B1 values.

`runtime.env` is an explicit host-trust tradeoff. Scalar secrets become container environment
variables and can be visible to sufficiently privileged host users through Docker inspection. They
are not cryptographically hidden. JWT values use Compose file secrets so multiline key bodies do
not appear in rendered Compose output or process arguments. Do not run shell tracing, print the
secret env, paste full `docker compose config`, or include the staging tree in backups/manifests.

## Production preflight and runtime consumption

Run the deliberate staging step first, then:

```bash
infra/gce/scripts/production-preflight.sh \
  --config-env /etc/strayhub/production.env \
  --secrets-root /var/lib/strayhub/secrets
```

The production preflight verifies mode separation, paths, permissions, the active JWT pair, required
non-secret/scalar inputs, and `docker compose config --quiet`. It then runs dependency-free API,
Worker, and Migration settings checks in their existing images. Those checks exercise the same
non-local fail-fast policy and service-specific database inputs without contacting PostgreSQL,
MinIO, LINE, KMS, or any external provider. They use an isolated `strayhub-d1-preflight-*` Compose
project and remove its empty network/volumes on exit.

Normal production Compose commands supply both env inputs in order:

```bash
docker compose \
  --env-file /etc/strayhub/production.env \
  --env-file /var/lib/strayhub/secrets/current/runtime.env \
  -f infra/gce/docker-compose.production.yml up -d
```

Do not print the rendered model because scalar env transport is visible by design.

## IAM and legacy mismatch

The future GCE VM service account is the staging principal. Grant only
`roles/secretmanager.secretAccessor`, preferably with secret-level IAM on the declared inventory.
Do not grant project Editor/Owner or let every container authenticate to GCP independently. D1 makes
no live IAM change.

Legacy Terraform grants Secret Accessor to several Cloud Run-specific service accounts and combines
it with unrelated Cloud SQL, storage, and logging roles. That wiring remains transitional and is not
the canonical GCE pattern. Retained IAM/state changes require later review; no legacy Terraform is
modified here.

## Rotation, failure, and local simulation

Rotation is: add a Secret Manager version, run the fetcher, validate the new atomic generation, then
restart affected containers. JWT private/public values must be published and fetched as a matching
pair. Automated scheduling and rollback/pruning policy are deferred to Phase E.

For credential-free D1 verification, `--source-dir` reads synthetic files named with the same secret
IDs and exercises identical validation, staging, permissions, generation switching, and Compose
consumption. It is verification-only and cannot be an implicit production fallback. No approved test
GCP project is configured, so live Secret Manager validation is deferred to Phase E/D acceptance.

The completed local D1 drill staged all 11 required values, left optional `AI_API_KEY` absent for
`AI_PROVIDER=mock`, verified 0700/0600 modes, rejected a missing required secret without changing
`current`, and rotated to a new coherent generation. Production preflight rendered Compose and
passed API, Worker, and Migration fail-fast checks. A separate isolated API container started in
production mode and returned `{"status":"ok"}` from its internal health endpoint. All temporary
Docker and synthetic staging resources were removed afterward.

Deferred: Phase D2 Cloud KMS functional encrypt/decrypt and IAM; Phase D3 private GCS backup upload,
lifecycle, and restore-from-GCS; Phase E real VM identity, ownership, systemd, rotation scheduling,
and live Secret Manager validation; Phase F legacy cleanup and deployment CI replacement.
