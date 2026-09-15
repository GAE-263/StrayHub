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
MinIO server and bootstrap use official Quay images pinned to amd64 manifest digests; the
former Docker Hub tags are no longer pullable.
The existing lack of Docker healthchecks for the database Worker and Beat is preserved rather
than inventing an HTTP health endpoint. Phase 4 must verify their running state and task imports.

## Environment differences

| Contract | Local runtime | Staging | Production |
| --- | --- | --- | --- |
| Application graph, commands, dependencies, healthchecks | Shared base | Shared base plus a constrained ingress-only edge | Shared base |
| Images | Same Dockerfiles; local build or selected digest | Required release digests, no build | Release digest env, existing no-build deploy |
| API / Web host ports | Loopback 18081 / 13001 | Loopback 18082 / 13002 | Existing edge-facing configured ports |
| PostgreSQL / MinIO / Redis | Loopback debug ports 65433 / 19000 / 16379 | Internal network only | Internal network only |
| Volumes and network | `strayhub-local-runtime` project | Isolated `strayhub-staging` project; applications stay on an internal network, while a secret-free edge alone joins the ingress network | `strayhub-production` project |
| Config / secrets | Dedicated local env and generated local JWT files | Dedicated local JWT/AES keys; mock AI; `APP_ENV=local` | Existing protected production generations |
| HTTPS / nginx | Optional external ngrok/nginx; direct local ports are HTTP | Local HTTP; cloud HTTPS checks remain pending | Existing managed nginx edge |
| LINE / data | Local/test channel and fictional data | Disabled outbound LINE; fictional data only | Production channel and records |
| Deployment lifecycle | Compose wrapper, explicit migration then startup | Immutable artifact validation, migration, live acceptance and one fail-closed receipt | Existing manifest/preflight/migration/systemd/receipt lifecycle |

The Staging-only TCP edge contains no runtime environment, secrets or storage mounts. It is
read-only, drops all Linux capabilities, enables `no-new-privileges`, uses the exact API release
image, and publishes only `127.0.0.1:18082` and `127.0.0.1:13002`. API and Web publish no ports
directly and remain unable to reach external networks. This proves local ingress availability,
not parity with the production HTTPS/nginx routing and upload/security policy.

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
healthchecks, environment key sets (with explicit local AES config additions), mount contracts
and network membership. It permits only the exact constrained Staging edge described above and
rejects other graph additions, shared production resources, public ports, mutable Staging image
references and Staging build definitions. Rendered secrets are never printed by the checker.

Run `uv run pytest tests/contract/test_runtime_parity.py`. The fixture uses synthetic config
and digest values; mutation tests prove contract drift is rejected. These are Compose model
checks, not proof that containers, cloud access, LINE or HTTPS work.

## Phase 4: local Docker decision

The read-only inventory on 2026-09-15 found `strayhub-gce`, `nginx-20260820-033352` and
`rrapi-20260813`, with no named StrayHub staging VM. The temporary acceptance stack is a
separate existing workflow and is not silently repurposed as persistent Staging.

The user chose local Docker instead of provisioning a paid GCP Staging VM. See
[local staging operations](local-staging.md). This changes Phase 4 from automatic cloud staging
to a manually initiated local release rehearsal. No VM, DNS, self-hosted runner or production
deployment is created. Release images remain immutable `linux/amd64` images, including on Macs.

The local runner reuses artifact checksum/manifest/extraction validation and the canonical
Compose bundle. It does not invoke production-only systemd/deploy scripts. The receipt binds the
local runner and overlay hashes separately from the selected artifact identity. Local-only AES
configuration, synthetic data and internal networking are intentional differences.

The local Phase 4 scope now performs exact Alembic revision readback, guarded deterministic
synthetic bootstrap, authenticated login/API/QR/care-report flows, positive tenant-A access,
negative tenant-B access, cross-shelter denial, runtime-role `BYPASSRLS`/superuser checks, RLS
inventory, container image/health checks and both loopback probes. Bootstrap cancels unfinished
drafts only for the exact synthetic tenant/volunteer, and report idempotency is bound to the new
draft, so an interrupted attempt can be safely rerun against retained volumes.

The successful immutable artifact for code acceptance was publisher run `34971497626`, Git SHA
`e77a1745f81a9e80e28717b8984715bd5be9aa47`, release artifact digest
`sha256:0b8cb3ebe463f955b27c33a304bbacd86ee947c0ab3e69c6549c0dba048f81cf`.
Fresh attempts `attempt-006` and `attempt-007` both passed against the same artifact and retained
volumes. Their protected local receipt SHA-256 values are respectively
`59cd57c751d2a72daaeed7b331dfe3abfd0fcab2fdfec4107d726e7679a893e8` and
`634c87adf0d35f88998347f624ad02d0b7398588ae2fb88102945ba6e6ad20f1`.

This completes the user-selected **local Docker** Phase 4 scope. It does not claim GCP Staging
equivalence: WIF/IAP/IAM/KMS, public HTTPS/nginx, systemd/reboot and live LINE resources are not
applicable to this local environment. Worker and Beat running state is checked, but successful
background task execution is not claimed. Every local receipt records cloud checks as
`NOT_APPLICABLE_LOCAL` and `production_promotion_approved: false`; it cannot authorize production.

## Revert

Revert the added overrides, wrapper, parity checker and tests plus their bundle entries.
Existing production Compose/systemd and legacy local volumes are unchanged. Previously
published bundles retain their original contents and checksums.
