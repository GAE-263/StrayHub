# Production Runtime Configuration Contract

Status: Phase B1-B4/D1-D3 contracts plus Phase E2-E4 live runtime access accepted
Canonical Compose: `infra/gce/docker-compose.production.yml`
Canonical non-local verification environment: `APP_ENV=gcp-demo`

This contract covers the GCE single-VM runtime: Next.js, FastAPI, legacy Worker, Celery Worker,
singleton Celery Beat, PostgreSQL, Redis, and MinIO on one private Compose network. The checked-in environment is synthetic verification configuration;
preflight generates the JWT material after checkout under an ignored directory. Neither is a
production credential source, and neither may be copied into a real deployment.

Phase D1 defines protected Secret Manager staging, D2 retains the existing Cloud KMS PII adapter,
and D3 keeps GCS backup-only. Phase E2 verifies all three through the real GCE VM metadata identity
without introducing a service-account JSON or application-side GCS dependency.

## Application configuration

| Field | Required by | Classification | Phase B1 source | Future production source |
| --- | --- | --- | --- | --- |
| `APP_ENV` | API, Worker, Alembic | Non-secret | Verification env; fixed to `gcp-demo` | Compose non-secret env/config |
| `DATABASE_URL` | API, Worker | Secret | Synthetic restricted-runtime login; internal `postgres:5432` URL | Secret Manager → staged `runtime.env` |
| `DATABASE_MIGRATION_URL` | Alembic | Secret | Synthetic bootstrap/migration login; internal `postgres:5432` URL | Secret Manager → staged `runtime.env` |
| `MINIO_ENDPOINT` | API | Non-secret | Verification env; internal `http://minio:9000` | Compose non-secret env/config |
| `MINIO_ACCESS_KEY` | API, MinIO, bucket bootstrap | Secret | Synthetic verification env | Secret Manager → staged `runtime.env` |
| `MINIO_SECRET_KEY` | API, MinIO, bucket bootstrap | Secret | Synthetic verification env | Secret Manager → staged `runtime.env` |
| `MINIO_BUCKET` | API, bucket bootstrap | Non-secret | Verification env | Compose non-secret env/config |
| `LINE_CHANNEL_ID` | API | Non-secret | Synthetic verification env | Compose non-secret env/config |
| `LINE_CHANNEL_SECRET` | API | Secret | Synthetic verification env | Secret Manager → staged `runtime.env` |
| `LINE_CHANNEL_ACCESS_TOKEN` | API | Secret | Synthetic verification env | Secret Manager → staged `runtime.env` |
| `LIFF_ID` | API, Web | Non-secret | Synthetic verification env | Compose non-secret env/config |
| `ANIMAL_CONFIRMATION_SECRET` | API | Secret | Synthetic verification env | Secret Manager → staged `runtime.env` |
| `LOGIN_ABUSE_HMAC_SECRET` | API | Secret | Synthetic verification env | Secret Manager → staged `runtime.env` |
| `AUTH_JWT_ISSUER` | API | Non-secret | Verification env | Compose non-secret env/config |
| `AUTH_JWT_AUDIENCE` | API | Non-secret | Verification env | Compose non-secret env/config |
| `AUTH_JWT_ACTIVE_PRIVATE_KEY_REFERENCE` | API | Non-secret | Verification env identifier | Compose non-secret env/config |
| `AUTH_JWT_ACTIVE_PUBLIC_KEY_REFERENCE` | API | Non-secret | Verification env identifier | Compose non-secret env/config |
| `AUTH_JWT_ACTIVE_PRIVATE_KEY` | API | Secret | Runtime-generated, ignored Compose file secret | Secret Manager → staged private file |
| `AUTH_JWT_ACTIVE_PUBLIC_KEY` | API | Secret | Runtime-generated, ignored Compose file secret | Secret Manager → staged public file |
| `PII_ENCRYPTION_PROVIDER` | API | Non-secret | Verification env; `gcp-kms` | Compose non-secret env/config; fixed to `gcp-kms` |
| `PII_KMS_KEY_NAME` | API | Non-secret resource identifier | Structurally valid synthetic resource name | Full environment-specific CryptoKey resource name |
| `AI_PROVIDER` | API | Non-secret | Verification env; `mock` | Compose non-secret env/config |
| `AI_API_KEY` | API when external AI is selected | Secret | Not set because Phase B1 uses mock AI | Secret Manager → optional staged `runtime.env` entry |
| `REDIS_MAXMEMORY` | Redis | Non-secret capacity limit | `256mb` | Compose non-secret env/config |
| `REDIS_PASSWORD` | Redis | Secret | Synthetic verification value | Secret Manager → staged `runtime.env` |
| `CELERY_BROKER_URL` | API, Celery Worker, Beat | Secret URL containing Redis password | Internal authenticated Redis URL | Secret Manager → staged `runtime.env` |
| `CELERY_AI_ENABLED` | API, Celery Worker, Beat | Non-secret feature flag | `false` | Enable only after smoke evidence |
| `CELERY_QUEUE_AI`, `CELERY_QUEUE_SYSTEM` | API, Celery Worker, Beat | Non-secret queue names | `ai`, `system` | Compose non-secret env/config; must match on every process |
| `CELERY_TASK_SOFT_TIME_LIMIT`, `CELERY_TASK_TIME_LIMIT` | Celery Worker | Non-secret limits | `45`, `60` | Compose non-secret env/config |
| `CELERY_VISIBILITY_TIMEOUT`, `CELERY_MAX_RETRIES`, `CELERY_RETRY_BACKOFF_MAX` | Celery Worker | Non-secret recovery policy | bounded verification values | Compose non-secret env/config |
| `CELERY_RECONCILE_INTERVAL_SECONDS` | Beat | Non-secret schedule | `30` | Compose non-secret env/config |
| `CELERY_WORKER_CONCURRENCY` | Celery Worker | Non-secret capacity | `2` | Compose non-secret env/config |
| `GEMINI_API_KEY` | API synchronous adoption/diary; Celery Worker when AI flag is enabled | Secret | Unset while disabled | Secret Manager → optional staged `runtime.env`; required before enablement |
| `GEMINI_MODEL_NAME`, `GEMINI_VERTEX_LOCATION` | Model: API/Celery; Vertex location: Celery | Non-secret | checked-in defaults | Compose non-secret env/config |
| `STOOL_API_URL`, `STOOL_TIMEOUT_SECONDS` | Legacy Worker | Non-secret optional provider config | unset / bounded default | Compose non-secret env/config |
| `STOOL_API_KEY` | Legacy Worker when stool provider is enabled | Secret | unset | Secret Manager → optional staged `runtime.env` |

### LINE role-menu release gate

The existing LINE webhook credentials remain required because they also serve the pre-existing care
workflow. The integrated role-menu, adoption-conversation, and staff-menu behavior has a separate
fail-closed release gate. `LINE_ROLE_MENU_FEATURES_ENABLED` defaults to `false` in both checked-in
GCE environments. Local/test runtimes may exercise the integration without changing that production
default. Non-local role-menu access requires global enablement or a valid bounded test scope;
neither mode grants business or tenant permissions.

The current release scope is adoption, growth diary, and volunteer features. Staff use the
Google-authenticated Web interface and submit shelter join requests for administrator approval.
Keep `LINE_STAFF_MENU_ENABLED=false`; Staff LINE resources, LIFF, and staff smoke evidence are
deferred and are not prerequisites for this scope. See [staff access governance](../staff-access-governance.md).

| Field | Consumer | Classification | Local default | Production rule / source |
| --- | --- | --- | --- | --- |
| `LINE_ROLE_MENU_FEATURES_ENABLED` | API, Worker | Non-secret boolean | `false`; local/test behavior remains available | Compose config; must be exactly `true` or `false`, default `false` |
| `LINE_STAFF_MENU_ENABLED` | API, Worker | Non-secret boolean | `false` | Independent opt-in for the optional staff LINE surface; requires role-menu global/test mode plus staff menu and LIFF configuration |
| `LINE_CHANNEL_ID` | API | Non-secret channel identifier | Synthetic/fake local ID | Existing required Compose config; non-placeholder |
| `LINE_CHANNEL_SECRET` | API | Secret | Synthetic/fake local secret | Existing required Secret Manager key `line-channel-secret` |
| `LINE_CHANNEL_ACCESS_TOKEN` | API, Worker | Secret | Synthetic/fake local token | Existing required Secret Manager key `line-channel-access-token`; Worker receives it only for post-commit menu switching |
| `LIFF_ID` | API, Web | Non-secret volunteer LIFF ID | Synthetic/fake local ID | Existing required Compose config; non-placeholder |
| `WEB_PUBLIC_BASE_URL` | API / release preflight | Non-secret public origin for LINE entry and short-lived adoption-photo URLs | Empty; local proxied webhook may derive its HTTPS origin | Required only when enabled; absolute HTTPS, non-loopback, reviewed origin |
| `LINE_RICH_MENU_DEFAULT_ID` | API, Worker | Non-secret LINE resource ID | Empty/no-op | Required only when enabled; Compose config, non-placeholder |
| `LINE_RICH_MENU_VOLUNTEER_ID` | API, Worker | Non-secret LINE resource ID | Empty/no-op | Required only when enabled; Compose config, non-placeholder |
| `LINE_RICH_MENU_STAFF_ID` | API, Worker | Non-secret LINE resource ID | Empty/no-op | Required only when `LINE_STAFF_MENU_ENABLED=true`; otherwise staged values are not routed |
| `LINE_RICH_MENU_ADOPTION_HUB_ID` | API | Non-secret LINE resource ID | Empty/no-op | Required only when enabled; verified hub resource; not needed by Legacy Worker/Celery |
| `LINE_STAFF_LIFF_ID` | API / release preflight | Non-secret staff LIFF ID | Empty | Required only when `LINE_STAFF_MENU_ENABLED=true`; the normal staff surface is Google-authenticated Web management |
| `LINE_ROLE_MENU_SMOKE_EVIDENCE` | API | Legacy compatibility label | Empty | `verified-YYYYMMDD-<40-char-tested-git-sha>` alone no longer authorizes enablement |
| `LINE_ROLE_MENU_TEST_ENABLED` | API / Legacy Worker | Protected operator config | false | Explicit bounded account mode; never enables all users |
| `LINE_ROLE_MENU_TEST_CHANNEL_ID`, `LINE_ROLE_MENU_BOT_SHA256` | API / Legacy Worker | Protected verified identity | Empty | Channel equals configured Messaging Channel; signed webhook destination matches Bot hash |
| `LINE_ROLE_MENU_TEST_USER_SHA256`, `LINE_ROLE_MENU_TEST_EXPIRES_AT` | API / Legacy Worker | Protected scope, no raw UID | Empty | 1–10 unique hashes, no wildcard; timezone-aware expiry within 7 days |
| `LINE_ROLE_MENU_REPORT_PATH`, `LINE_ROLE_MENU_REPORT_SHA256`, `LINE_ROLE_MENU_RESOURCES_PATH` | API / preflight | Protected readonly evidence | /dev/null, empty, /dev/null | Global enablement requires real-line report, current immutable identity and resource readback; mock rejected |
| `LINE_ROLE_MENU_RELEASE_MANIFEST` | API / preflight | Actual verified release manifest | /dev/null | Global mode requires `/opt/strayhub/current/release-manifest.json`; preflight substitutes candidate bundle manifest before switch |

The bounded mode retains production HTTPS and resource gates; staff LIFF/resource/evidence become
part of the contract only when the independent staff LINE capability is enabled. Neither mode grants
business/tenant access. Staff management remains available through the Google-authenticated Web flow
while `LINE_STAFF_MENU_ENABLED=false`.
See [executable operator sequence and invalidation rules](../line-rich-menu-safe-publication.md).
Legacy label-only global deployments must migrate their evidence before their next startup; both flags
false remain compatible without evidence. No Rich Menu settings are added to Celery Worker/Beat.

`LINE_RICH_MENU_ADOPTER_ID` is intentionally not a production requirement: the approved public
menu enters the adoption conversation directly, and there is no completed-adoption lifecycle that
authorizes switching to a persistent adopter menu yet. Adding that lifecycle requires a separate
review. Enabling the gate requires all existing LINE credentials plus every conditional field above;
application startup and production preflight reject a partial configuration.

The repository's `line-liff/adopter/index.html` is a local mock only. The former
`apps/web/public/adoption-entry/index.html` route and `_adoption_entry_message` placeholder were
removed when the real conversation was integrated. The GCE Web image and release bundle do not copy
`line-liff/`, and nginx/systemd define no alias for `line-liff/serve-demo.sh` or either mock page.
If the independent staff LINE gate is enabled, its LIFF ID must point at a separately reviewed
production artifact under `WEB_PUBLIC_BASE_URL`, and the exact release commit must additionally pass
the staff real-LINE smoke cases. With that gate false, adopter/volunteer enablement does not depend
on a Staff LIFF.

Optional previous JWT key material and its reference follow the same Secret Manager/non-secret
identifier split when rotation enables them. External AI endpoint/model fields become Compose
non-secret env/config when an external provider is selected; the existing fail-fast policy then also
requires `AI_API_KEY`.

## Service bootstrap and verification-only configuration

| Field | Required by | Classification | Phase B1 source | Future production source |
| --- | --- | --- | --- | --- |
| `POSTGRES_DB` | PostgreSQL | Non-secret | Verification env | Compose non-secret env/config |
| `POSTGRES_USER` | PostgreSQL | Non-secret | Verification env | Compose non-secret env/config |
| `POSTGRES_PASSWORD` | PostgreSQL | Secret | Synthetic verification env | Secret Manager → staged `runtime.env` |
| `POSTGRES_RUNTIME_USER` | PostgreSQL init, API, Worker | Non-secret | Verification env | Compose non-secret env/config |
| `POSTGRES_RUNTIME_PASSWORD` | PostgreSQL init, API, Worker | Secret | Synthetic verification env | Secret Manager → staged `runtime.env` |
| `API_BASE_URL` | Web server | Non-secret | Compose; internal `http://api:8080` | Compose non-secret env/config |
| `B1_VERIFICATION_ONLY` | B1 preflight | Non-secret safety marker | Verification env; must be `true` | Not used in real deployment |
| `AUTH_JWT_ACTIVE_PRIVATE_KEY_FILE` | Compose secret transport | Sensitive path, not key material | Ignored generated-file path | Protected staged file populated from Secret Manager |
| `AUTH_JWT_ACTIVE_PUBLIC_KEY_FILE` | Compose secret transport | Non-secret/sensitive path | Ignored generated-file path | Protected staged file populated from Secret Manager |
| `E4_CANONICAL_HOSTNAME` | Runtime health and edge contract | Non-secret | `strayhub.enadv.quest` | Same canonical hostname |
| `E4_WEB_UPSTREAM_HOST_PORT` | Old-edge Web upstream | Non-secret | `3000` | Source-restricted host port `3000` |
| `E4_API_UPSTREAM_HOST_PORT` | Old-edge API upstream | Non-secret | `8080` | Source-restricted host port `8080` |
| `GCS_BACKUP_BUCKET` | Host backup scripts only | Non-secret resource name | Explicit fake transport input | Private backup-only bucket name |
| `GCS_BACKUP_PREFIX` | Host backup scripts only | Non-secret object prefix | `strayhub-backups` | `strayhub-backups` |
| `BACKUP_ENVIRONMENT` | Host backup scripts only | Non-secret path segment | `gcp-demo` | `production` or approved environment |

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

The historical `strayhub-b2-verify` B2 and B4 ingress drills used isolated Compose nginx. The selected E4 architecture runs
no nginx on the application VM; the existing edge VM owns public TLS and proxies to the direct
source-restricted Web/API host ports.

Set the shared arguments for readability:

```bash
COMPOSE_FILE=infra/gce/docker-compose.production.yml
ENV_FILE=infra/gce/.env.production.example
PROJECT=strayhub-e4-verify
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

Verify API health and the Web root directly on the local application VM:

```bash
curl --head -H 'Host: strayhub.enadv.quest' http://127.0.0.1:3000/
curl --fail -H 'Host: strayhub.enadv.quest' http://127.0.0.1:8080/healthz
```

Only API and Web publish source-restricted upstream ports. PostgreSQL, Redis, MinIO, both workers,
Celery Beat, and the MinIO
console have no host port. See `infra/edge-nginx/strayhub.enadv.quest.conf` for the selected public
routing policy.

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

## Historical Phase B1-B4 verification boundary

Included: Compose parsing, operator preflight, PostgreSQL/MinIO health, bucket bootstrap, one-shot
Alembic, API fail-fast/startup/health, long-running Worker, Web startup, internal Web-to-API reach,
safe MinIO write/read, and persistence across a normal down/up cycle.

Phase B2 adds nginx single-origin routing and Phase B4 adds the TLS-ready edge without changing
application behavior. B4 only documents DNS/firewall/static-IP requirements. D1 verifies local
Secret Manager staging and D2 verifies the existing KMS adapter, provider selection, failure policy,
and configuration contracts with an injected client. E1 accepted the GCE host foundation, and E2
accepted live Secret Manager, KMS, and GCS backup access. E3 later accepted systemd supervision and
E4 selected the existing external nginx edge without changing DNS, certificate ownership, or
LINE/LIFF URLs. Legacy CI replacement, Terraform state migration, and removal of Cloud Run/Cloud
SQL/runtime-GCS assets remain deferred. GCS is backup-only in the target design and is not a
dependency of this Compose runtime.

## Phase B3 backup / restore contract

Backups are one-shot operator scripts, not long-running Compose services. The canonical local staging
root is the Git-ignored `infra/gce/backup/generated/`, or an explicitly selected protected external
root. A shared UTC backup ID groups `postgres/postgres.dump`, PostgreSQL metadata,
`minio/objects/`, the MinIO inventory, and `manifest.json`. All artifacts use owner-only permissions.

PostgreSQL backup uses the schema-owning migration credential inside the PostgreSQL container and
custom-format `pg_dump`; restore accepts only an explicit artifact, confirmation flag, and an
isolated `strayhub_b3_restore_*` target. MinIO uses the pinned `minio/mc` image and accepts restore
only into a confirmed `strayhub-b3-restore-*` bucket. No backup path is mounted into nginx, Web, API,
or any long-running service.

Phase B3 proves local data correctness only. PostgreSQL and MinIO captures are sequential and not
transactionally atomic. D3 adds host-only `gcloud storage` upload/download with pre/post-transfer
manifest validation and `_COMPLETE` activation. No GCS setting enters Compose or the application.
Live bucket/IAM/lifecycle acceptance passed in Phase E2; scheduling remains deferred. See
`docs/deployment/backup-restore.md` and `docs/deployment/gcs-backup.md`.

## Historical Phase B4 TLS edge contract

The isolated B4 Compose nginx was the only service with host-published HTTP/HTTPS ports. It served only the HTTP-01 challenge
over plaintext, redirects every other HTTP request with 308, and terminates TLS before applying the
unchanged B2 routing table. Verification uses runtime-generated ignored self-signed material;
production used host-level Certbot/Let's Encrypt state mounted read-only. The selected live E4
architecture supersedes that verification topology: TLS remains on the existing external edge and
the GCE application Compose contains no nginx. No private TLS key belongs in Git or a container
image. See `docs/deployment/tls-dns-firewall.md` for the accepted live contract.

## Phase D1 Secret Manager runtime contract

Production secrets are fetched once at the VM boundary into protected immutable generations under
`/var/lib/strayhub/secrets`. Scalar values are transported in mode-`0600` `runtime.env`; the active
JWT pair remains file-based and is mounted read-only into API only. The atomic `current` symlink
switches the env and pair together. Compose stays canonical and selects either B1 verification files
or D1 production staging through explicit env-file inputs.

The committed `.env.production.template` contains non-secret configuration and external staged
paths only. Production preflight rejects `B1_VERIFICATION_ONLY=true`, repository-generated paths,
missing fields, unsafe permissions, and invalid JWT pairs, then performs API/Worker/Migration
fail-fast checks. See `docs/deployment/secret-manager.md` for inventory, naming, IAM, rotation,
container-env risk, simulation, and commands.

## Phase D2 Cloud KMS runtime contract

Every non-local API selects the existing `gcp-kms` PII adapter. `PII_KMS_KEY_NAME` is a non-secret
full CryptoKey resource name; Settings, the adapter, and production preflight reject malformed
references. Compose supplies these two values only to API and contains no credential or key
material. Worker, Migration, Web, nginx, PostgreSQL, and MinIO do not receive KMS configuration.

The GCE VM service account authenticates through Application Default Credentials and holds
`roles/cloudkms.cryptoKeyEncrypterDecrypter` on the specific PII CryptoKey where practical. D2 makes
no IAM or live KMS call. Mock-client tests verify authenticated encrypt/decrypt, returned key-version
metadata, safe failures, and no non-local fallback. See `docs/deployment/cloud-kms.md` for the full
resource, IAM, ADC, rotation, failure, and deferred live-acceptance contract.

## Phase D3 GCS backup transport contract

GCS is backup-only; MinIO remains runtime media. The production template exposes only host-side
bucket, prefix, and environment identifiers. `gcloud storage` authenticates through the future GCE
VM service account's ADC and never uses JSON/HMAC credentials. Upload revalidates B3 artifacts before
and after transfer and writes `_COMPLETE` last; download rejects incomplete/corrupt sets and never
auto-restores.

The future VM receives bucket-level `roles/storage.objectCreator` plus
`roles/storage.objectViewer`; lifecycle, not the VM, owns expiration. The proposed 35-day age rule is
explicitly not seven-daily/four-weekly selection. Local fake-CLI verification does not prove live GCS
or IAM. See `docs/deployment/gcs-backup.md`.

Schema 2 protected approvals bind the exact release, resource identities and AI configuration. Historical test-scope expiry does not invalidate an approved unchanged release at restart. Bounded test access still expires; schema 1 retains its original seven-day limit. A revoked/missing/mismatched approval fails startup validation. See the schema-2 operator contract in the LINE publication runbook.
