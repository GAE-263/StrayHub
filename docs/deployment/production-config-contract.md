# Production Runtime Configuration Contract

Status: Phase B1 production-like verification contract
Canonical Compose: `infra/gce/docker-compose.production.yml`
Canonical non-local verification environment: `APP_ENV=gcp-demo`

This contract covers the GCE single-VM runtime: Next.js, FastAPI, Worker, PostgreSQL, and MinIO on
one private Compose network. The checked-in environment is synthetic verification configuration;
preflight generates the JWT material after checkout under an ignored directory. Neither is a
production credential source, and neither may be copied into a real deployment.

Phase B1 does not fetch Secret Manager values or exercise Cloud KMS. The future sources below define
the ownership boundary for those later integrations without implementing them now.

## Application configuration

| Field | Required by | Classification | Phase B1 source | Future production source |
| --- | --- | --- | --- | --- |
| `APP_ENV` | API, Worker, Alembic | Non-secret | Verification env; fixed to `gcp-demo` | Compose non-secret env/config |
| `DATABASE_URL` | API, Worker | Secret | Synthetic restricted-runtime login; internal `postgres:5432` URL | Secret Manager |
| `DATABASE_MIGRATION_URL` | Alembic | Secret | Synthetic bootstrap/migration login; internal `postgres:5432` URL | Secret Manager |
| `MINIO_ENDPOINT` | API | Non-secret | Verification env; internal `http://minio:9000` | Compose non-secret env/config |
| `MINIO_ACCESS_KEY` | API, MinIO, bucket bootstrap | Secret | Synthetic verification env | Secret Manager |
| `MINIO_SECRET_KEY` | API, MinIO, bucket bootstrap | Secret | Synthetic verification env | Secret Manager |
| `MINIO_BUCKET` | API, bucket bootstrap | Non-secret | Verification env | Compose non-secret env/config |
| `LINE_CHANNEL_ID` | API | Non-secret | Synthetic verification env | Compose non-secret env/config |
| `LINE_CHANNEL_SECRET` | API | Secret | Synthetic verification env | Secret Manager |
| `LINE_CHANNEL_ACCESS_TOKEN` | API | Secret | Synthetic verification env | Secret Manager |
| `LIFF_ID` | API, Web | Non-secret | Synthetic verification env | Compose non-secret env/config |
| `ANIMAL_CONFIRMATION_SECRET` | API | Secret | Synthetic verification env | Secret Manager |
| `AUTH_JWT_ISSUER` | API | Non-secret | Verification env | Compose non-secret env/config |
| `AUTH_JWT_AUDIENCE` | API | Non-secret | Verification env | Compose non-secret env/config |
| `AUTH_JWT_ACTIVE_PRIVATE_KEY_REFERENCE` | API | Non-secret | Verification env identifier | Compose non-secret env/config |
| `AUTH_JWT_ACTIVE_PUBLIC_KEY_REFERENCE` | API | Non-secret | Verification env identifier | Compose non-secret env/config |
| `AUTH_JWT_ACTIVE_PRIVATE_KEY` | API | Secret | Runtime-generated, ignored Compose file secret | Secret Manager |
| `AUTH_JWT_ACTIVE_PUBLIC_KEY` | API | Secret | Runtime-generated, ignored Compose file secret | Secret Manager |
| `PII_ENCRYPTION_PROVIDER` | API | Non-secret | Verification env; `gcp-kms` | Compose non-secret env/config |
| `PII_KMS_KEY_NAME` | API | Non-secret resource identifier | Structurally valid synthetic resource name | KMS resource reference |
| `AI_PROVIDER` | API | Non-secret | Verification env; `mock` | Compose non-secret env/config |
| `AI_API_KEY` | API when external AI is selected | Secret | Not set because Phase B1 uses mock AI | Secret Manager |

Optional previous JWT key material and its reference follow the same Secret Manager/non-secret
identifier split when rotation enables them. External AI endpoint/model fields become Compose
non-secret env/config when an external provider is selected; the existing fail-fast policy then also
requires `AI_API_KEY`.

## Service bootstrap and verification-only configuration

| Field | Required by | Classification | Phase B1 source | Future production source |
| --- | --- | --- | --- | --- |
| `POSTGRES_DB` | PostgreSQL | Non-secret | Verification env | Compose non-secret env/config |
| `POSTGRES_USER` | PostgreSQL | Non-secret | Verification env | Compose non-secret env/config |
| `POSTGRES_PASSWORD` | PostgreSQL | Secret | Synthetic verification env | Secret Manager |
| `POSTGRES_RUNTIME_USER` | PostgreSQL init, API, Worker | Non-secret | Verification env | Compose non-secret env/config |
| `POSTGRES_RUNTIME_PASSWORD` | PostgreSQL init, API, Worker | Secret | Synthetic verification env | Secret Manager |
| `API_BASE_URL` | Web server | Non-secret | Compose; internal `http://api:8080` | Compose non-secret env/config |
| `B1_VERIFICATION_ONLY` | B1 preflight | Non-secret safety marker | Verification env; must be `true` | Not used in real deployment |
| `AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE` | Compose secret transport | Sensitive path, not key material | Ignored generated-file path | Protected staged file populated from Secret Manager |
| `AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE` | Compose secret transport | Non-secret/sensitive path | Ignored generated-file path | Protected staged file populated from Secret Manager |
| `B1_API_HOST_PORT` | Local verifier only | Non-secret | Verification env | Not used after nginx owns ingress |
| `B1_WEB_HOST_PORT` | Local verifier only | Non-secret | Verification env | Not used after nginx owns ingress |

`POSTGRES_PASSWORD` belongs to the bootstrap/migration login and matches `DATABASE_MIGRATION_URL`.
`POSTGRES_RUNTIME_PASSWORD` belongs to the non-superuser application login and matches
`DATABASE_URL`. The initialization script makes that login a member of the migration-managed
`strayhub_runtime` role, preserving RLS enforcement while keeping schema ownership with the migration
principal. It establishes the same runtime default table privileges before the first migration, so
tables created before migration `0003` do not miss the repository's expected runtime ACL. MinIO
server root credentials and the API's MinIO credentials are the same synthetic pair in Phase B1;
Phase D must design least-privilege credentials and rotation before real deployment.

Preflight generates an RSA 2048 verification pair under the Git-ignored
`infra/gce/verification/generated/` directory. It reuses a valid matching pair or replaces a missing
or invalid pair; `--force` explicitly rotates it. Compose mounts the generated files as read-only file
secrets, and the API startup command exports their contents only inside the API process. Deleting the
generated directory is safe because the next preflight regenerates it. No verification PEM is
committed, accepted as a staging/shared-demo credential, or uploaded to Secret Manager.

The B1 env template alone points `AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE` and
`AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE` at ignored generated paths. The canonical Compose remains
parameterized and does not hard-code either verification or production paths. Real GCE must stage JWT
values from Secret Manager at protected, non-repository paths and provide those paths to Compose.

`B1_VERIFICATION_ONLY=true` marks the synthetic template and is enforced by the B1 preflight. It is
not a real deployment mode or production gate. See `infra/gce/verification/README.md` for generation,
rotation, cleanup, and forbidden-use rules.

## Canonical commands

All commands use the isolated project name `strayhub-b1-verify`; they do not address the normal local
demo stack.

Set the shared arguments for readability:

```bash
COMPOSE_FILE=infra/gce/docker-compose.production.yml
ENV_FILE=infra/gce/.env.production.example
PROJECT=strayhub-b1-verify
```

Preflight and render the resolved model:

```bash
infra/gce/scripts/preflight.sh "$ENV_FILE"
docker compose --project-name "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config
```

Build the three application images:

```bash
docker compose --project-name "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
  build api worker web
```

Run the canonical one-shot migration before starting the long-running application processes:

```bash
docker compose --project-name "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
  run --rm migration
```

The `migration` profile reuses the API image and its Compose command is
`alembic -c services/api/alembic.ini upgrade head`. It receives only `APP_ENV=gcp-demo` and the
internal bootstrap `DATABASE_MIGRATION_URL`, returns non-zero on failure, and exits after Alembic
completes. It is never included in the normal `up`; Phase B1 adds no schema migration.

Start the runtime:

```bash
docker compose --project-name "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
```

Verify API health and Web-to-API network reachability:

```bash
curl --fail http://127.0.0.1:18080/healthz
docker compose --project-name "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
  exec -T web wget -qO- http://api:8080/healthz
```

The API and Web loopback bindings exist only for Phase B1 local verification. PostgreSQL, MinIO, and
the MinIO console have no host port. Phase B2 will add nginx and own public routing.

Stop the isolated stack while preserving named volumes:

```bash
docker compose --project-name "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down
```

`docker compose down` retains the named PostgreSQL and MinIO data volumes. Only an intentional:

```bash
docker compose --project-name "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down -v
```

destroys them. In other words, `docker compose down -v` destroys verification data and must not be
used as the normal stop command.

## Phase B1 verification boundary

Included: Compose parsing, operator preflight, PostgreSQL/MinIO health, bucket bootstrap, one-shot
Alembic, API fail-fast/startup/health, long-running Worker, Web startup, internal Web-to-API reach,
safe MinIO write/read, and persistence across a normal down/up cycle.

Deferred to Phase B2 or later: nginx, TLS, real GCE provisioning, systemd, live Secret Manager
injection, functional KMS/PII verification, real LINE/LIFF calls, GCS backup, backup/restore scripts,
legacy CI replacement, Terraform state migration, and removal of Cloud Run/Cloud SQL/runtime-GCS
assets. GCS is backup-only in the target design and is not a dependency of this Compose runtime.
