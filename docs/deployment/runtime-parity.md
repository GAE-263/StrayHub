# Phase 3: shared runtime contract

## Source of truth

`infra/gce/docker-compose.production.yml` remains the canonical service definition.
Its historical filename is retained because release manifests, installed systemd units,
preflight, rollback and acceptance tools already use it. Local and Staging layer overrides
over that same file; they do not copy application definitions. Production remains byte-for-byte
unchanged by this phase.

The full graph is PostgreSQL, MinIO, MinIO bootstrap, Redis, API, migration (tools profile),
database-polling Worker, Celery Worker, Celery Beat and Web. The legacy database Worker and
Celery Worker execute different queues; neither replaces the other. Beat is the scheduler.
The existing lack of Docker healthchecks for the database Worker and Beat is preserved rather
than inventing an HTTP health endpoint. Phase 4 must verify their running state and task imports.

## Environment differences

| Contract | Local runtime | Staging | Production |
| --- | --- | --- | --- |
| Application graph, commands, dependencies, healthchecks | Shared base | Shared base | Shared base |
| Images | Same Dockerfiles; local build or selected digest | Required release digests, no build | Release digest env, existing no-build deploy |
| API / Web host ports | Loopback 18081 / 13001 | Loopback 18082 / 13002 | Existing edge-facing configured ports |
| PostgreSQL / MinIO / Redis | Loopback debug ports 65433 / 19000 / 16379 | Internal network only | Internal network only |
| Volumes and network | `strayhub-local-runtime` project | `strayhub-staging` project, dedicated VM | `strayhub-production` project |
| Config / secrets | Dedicated local env and generated local JWT files | Dedicated protected staging env, JWT, KMS and LINE identity | Existing protected production generations |
| HTTPS / nginx | Optional external ngrok/nginx; direct local ports are HTTP | Dedicated HTTPS edge upstreams | Existing managed nginx edge |
| LINE / data | Local/test channel and fictional data | Dedicated test channel, allowlisted users, fictional data | Production channel and records |
| Deployment lifecycle | Compose wrapper, explicit migration then startup | Phase 4 must share deployment lifecycle implementation | Existing manifest/preflight/migration/systemd/receipt lifecycle |

Ingress lives outside the application Compose graph today. Adding a new nginx service only
to Staging would conceal that difference. Phase 4 must verify the actual staging HTTPS edge,
its routing and upload/security rules; a passing Compose comparison alone is not ingress parity.

The old `infra/local/docker-compose.yml` stays available as an **infrastructure-only test
fixture** for existing host-run unit/integration tests and their data volumes. It is not the
full runtime parity path. No existing developer data is migrated or removed.

## Run the full local runtime

Prepare a dedicated env file using the required fields in `infra/gce/.env.production.template`:
set `APP_ENV=local`, local database/storage/Redis credentials, matching database URLs pointing
at `postgres:5432`, JWT file paths, local/test LINE values and mock AI. Never copy production
secrets. Supply the base Compose's required port variables; the override replaces their bindings.
Paths for JWT files must be absolute or relative to `infra/gce`, the first Compose file.

```bash
bash scripts/runtime-compose.sh /absolute/path/local.env config --quiet
bash scripts/runtime-compose.sh /absolute/path/local.env build api worker web
bash scripts/runtime-compose.sh /absolute/path/local.env up -d postgres minio minio-bootstrap redis
bash scripts/runtime-compose.sh /absolute/path/local.env run --rm migration
bash scripts/runtime-compose.sh /absolute/path/local.env up -d api worker celery-worker celery-beat web
```

## Automated evidence

`scripts/check_runtime_parity.py` renders all three models with every profile enabled, including
migration. It compares service membership, images, commands, entrypoints, dependencies,
healthchecks, environment key sets, mount contracts and network membership. It rejects shared
production resource names, public local/staging ports, mutable staging image references and
staging build definitions. Rendered secrets are never printed by the checker.

Run `uv run pytest tests/contract/test_runtime_parity.py`. The fixture uses synthetic config
and digest values; mutation tests prove contract drift is rejected. These are Compose model
checks, not proof that containers, cloud access, LINE or HTTPS work.

## Phase 4 activation prerequisites

The read-only inventory on 2026-09-15 found `strayhub-gce`, `nginx-20260820-033352` and
`rrapi-20260813`, with no named StrayHub staging VM. The temporary acceptance stack is a
separate existing workflow and is not silently repurposed as persistent Staging.

Before live promotion, establish a dedicated staging VM and hostname, protected configuration,
secrets/test LINE identities, publisher/deployer WIF trust and successful Phase 2 build/rerun
evidence. Reuse the production deployment lifecycle through an explicit environment contract;
do not run the production-only `deploy-release.sh` against staging or duplicate its lifecycle.
Then test migration, image/runtime identity, HTTPS and authenticated multi-shelter E2E before
issuing a SHA/digest-bound staging PASS receipt. No Phase 4 PASS is claimed by this change.

## Revert

Revert the added overrides, wrapper, parity checker and tests plus their bundle entries.
Existing production Compose/systemd and legacy local volumes are unchanged. Previously
published bundles retain their original contents and checksums.
