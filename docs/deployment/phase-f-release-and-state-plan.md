# Phase F2 State Ownership and Release Gate Plan

Status: **READY**

Deletion safety: **BLOCKED**

Infrastructure mutation: **NONE**

Terraform mutation: **NONE**

Accepted E5 checkpoint:
`a065366837f4fe44e52a067c0a191fc61e1fc702`

`READY` means F3 may implement the missing release gates. It does not authorize legacy deletion,
state changes, API enablement, or production changes.

## Legacy remote state discovery

| Field | Result |
| --- | --- |
| Backend type | GCS declaration only |
| Bucket | `NOT_CONFIGURED_OR_DISCOVERABLE` |
| Prefix | `strayhub/gcp-demo` |
| State object | `NONE_DISCOVERED` |
| Last modified / generation | Not applicable |
| Ownership confidence | `HIGH` within repository history and the accepted active project; external/other-project state remains excluded and unknown |

Evidence:

- Repository history introduced the backend with a pre-deployment prohibition and never recorded a
  bucket. An operator would have had to supply `-backend-config=bucket=...`.
- The workflow, deploy gate, and `apply.sh` all initialize with `-backend=false`; no matching
  invocation exists in history.
- There is no legacy local state or `.terraform/terraform.tfstate` backend metadata.
- The active project has one bucket,
  `strayhub-backups-canvas-primacy-502703-k1`. Its only top-level prefix is
  `strayhub-backups/`; `strayhub/gcp-demo/**` matches no objects.
- No matching StrayHub Cloud Run service/job, service account, WIF pool, Artifact Registry, logging
  bucket/metric, load balancer, or Compute certificate was found in the active project.
- GitHub variable names could not be queried because `gh` is not installed. The workflow itself has
  no backend input and never authenticates or deploys.

The bounded conclusion is that no legacy state is available in the repository or accepted project,
with strong evidence the proposed demo root was never initialized or applied. This is not authority
to search unrelated projects. If an external backend is later produced, reopen all state conclusions
before any plan.

## Legacy state classification

No legacy state addresses were discovered. These are source declarations, not state contents:

| Classification | Declarations |
| --- | --- |
| `LEGACY_EXCLUSIVE` | Cloud Run services/job/public IAM; Cloud SQL/database/users; demo VPC/private service access; runtime-media GCS; legacy service accounts/WIF/Artifact Registry/observability |
| `SHARED_WITH_GCE` | Secret Manager data/IAM declarations, existing KMS-key IAM declaration, project service declarations |
| `RETAINED_CURRENT` | None owned by a discovered legacy state; accepted GCE/manual resources remain outside it |
| `UNKNOWN` | Any backend/state supplied outside repository history or outside the accepted project |

The legacy root cannot be destroyed safely. Initializing it against an unknown backend or applying
its declarations could create obsolete infrastructure or alter shared IAM.

## Cloud SQL status

Status: **CLOUD_SQL_UNKNOWN**

The canonical runtime uses PostgreSQL on `strayhub-gce`; no legacy state or Cloud Run runtime was
found. However, both Cloud SQL and Cloud Asset APIs are disabled and were not enabled for F2. This
does not prove absence, so Cloud SQL remains held outside every deletion task.

## Shared-resource future ownership

`PLATFORM_TERRAFORM` means a future isolated managed-services root, separate from current GCE host
state and all legacy runtime declarations.

| Resource | Current Terraform owner | Runtime consumer | Future owner | Later state action | Delete? |
| --- | --- | --- | --- | --- | --- |
| 11 `strayhub-prod-*` secrets | None; manual | GCE secret staging | `PLATFORM_TERRAFORM` | Import metadata/IAM; keep values/versions outside state pending design | No |
| Secret-level accessor bindings | None; manual | `strayhub-gce-sa` | `PLATFORM_TERRAFORM` | Exact member import/adoption after policy comparison | No |
| `strayhub-pii` keyring | None; manual | Platform boundary | `PLATFORM_TERRAFORM` | `RESOURCE_IMPORT_REQUIRED` | No |
| `pii-encryption` CryptoKey and binding | None; manual | API through VM ADC | `PLATFORM_TERRAFORM` | Import key and exact member; preserve versions/rotation | No |
| GCS backup bucket and bindings | None; manual | Host backup/restore | `PLATFORM_TERRAFORM` | Import after matching PAP, uniform access, retention, lifecycle and IAM | No |
| DNS | External/manual | Public users and LINE/LIFF | `MANUAL_RETAIN` | None until provider ownership is accepted | No |
| Edge VM/address/nginx/TLS | None; manual | Public routing/TLS | `MANUAL_RETAIN` | Record role ownership and config checksum | No |
| GCE host foundation | Current local GCE state | Canonical runtime | `GCE_TERRAFORM` | Remote backend is a separate decision | No |

F2 performed no import, state movement, IAM change, or Terraform source change.

## Unrelated-resource boundary

`rrapi-20260813`, `rr-test`, `rr-api-firewall`, `rrbot`, `rrbot-9527`, and `car-930` are
`EXCLUDED_FROM_STRAYHUB_DELETION_SCOPE`. The default VPC, default firewalls, and default Compute
service account remain held because current and unrelated workloads share them.

## Current GCE release source of truth

| Release field | Current evidence | Result |
| --- | --- | --- |
| Source commit | Directory suggests `e702d7d`, but contains later E4/E5 changes and no Git/revision marker | `FAIL` provenance |
| Release/active path | Sole directory `/opt/strayhub/releases/e702d7d-e3`; `current` points there | Operationally known |
| Build process | Compose builds three legacy Dockerfiles from the copied checkout | Manual state dependency |
| Registry | No StrayHub registry or pullable fully qualified image reference | `FAIL` |
| Image identity | Mutable `strayhub-{api,worker,web}:b1`; local content IDs exist without Git labels | Not reproducible |
| Compose | Active release copy of `docker-compose.production.yml` | Known, not revision-marked |
| Config/secrets | Protected host config; Secret Manager atomic staging | Accepted |
| Migration | systemd production preflight then one-shot Compose Alembic | Accepted |
| Activation/health | systemd Compose start then bounded local/public verifier | Accepted |
| Acceptance | Contracts and E5 evidence exist but are not linked to a manifest | Partial |

Current GCE release reproducibility is **PARTIAL**. Runtime orchestration is deterministic, but
source, image publication, copy procedure, and release identity are not. The directory name must not
be claimed as the actual Git SHA.

## Immutable release identity

Use `<UTC timestamp>-<12-char Git SHA>` as `release_id`. Identity is the exact Git SHA plus
digest-pinned API/Worker/Web images plus `release-manifest.json`. The non-secret manifest records:

```text
release_id, full git_sha, created_at, build_run
api/worker/web registry@sha256 digests
compose_sha256, deployment_bundle_sha256
migration_revision and reviewed schema compatibility range
expected edge_config_sha256
```

Every `/opt/strayhub/releases/<release-id>/` must be created from a clean commit and contain the
manifest/checksum, a `REVISION` file, exact deployment bundle, and digest-pinned Compose override.
It must contain no env file, secret, credential, private key, backup, or Terraform state. Record
PostgreSQL/MinIO/mc base-image digests too. Release directories become immutable; `current` is the
only mutable pointer. Retain current `N` and compatible `N-1` with both manifests.

## Replacement CI and release gate

### Stage 1: PR build gate

Reuse current CI and add a GCE release-candidate job requiring Python migrations/tests, Ruff,
frontend tests/typecheck/format/build, contract generation, security/tenant/deployment contracts,
critical E2E, repository secret scan, production Compose/preflight with synthetic inputs, and
current-GCE Terraform format/validate without backend mutation. Build all three images from a clean
tree with OCI source/revision/created labels. PR jobs do not authenticate to production or deploy.

### Stage 2: immutable publication

After an accepted protected-branch commit, use GitHub OIDC/WIF—not a JSON key—to push to a dedicated
StrayHub Artifact Registry, resolve all registry digests, create the exact deployment bundle and
manifest, verify checksums, and retain provenance for `N` and `N-1`. `rrbot-9527` is excluded. The
repository and least-privilege publisher identity require separately reviewed F3 infrastructure.

### Stage 3: manually approved production release

Require a protected production-environment approval. Deploy only a previously published manifest,
never rebuild. Use short-lived federation with an approved OS Login/IAP mechanism, or an operator
fetch through IAP; never store SSH private keys in GitHub. A future reviewed repo script must:

1. verify revision, checksums, image digests, configuration references, free space, backup freshness,
   current migration head, and schema compatibility;
2. stage a new release directory and atomically fetch secrets;
3. run production preflight and the existing one-shot migration;
4. atomically switch `current`, install repo units if changed, start and run bounded local/public
   health and smoke tests; and
5. write a non-secret receipt linking approval, manifest, prior release and results.

An ad hoc SSH transcript is not a deployment source. Automatic production deploy is not required;
immutable build/publish, approval, and reproducible operator deployment are.

## Rollback ownership and strategy

```text
ROLLBACK_OWNER: StrayHub production deployment operator role
ROLLBACK_APPROVER: protected production reviewer / incident lead role
ROLLBACK_TRIGGER: failed post-deploy health, critical regression, or approved incident
ROLLBACK_COMMAND_SOURCE: future reviewed GCE release-management script
ROLLBACK_VERIFICATION: manifest/digest/schema gate plus app, Worker, DB, MinIO, timer health
ROLL_FORWARD: publish and deploy a new immutable manifest through the same gate
```

`N` and `N-1` both require Git SHA, registry digests, manifest, deployment bundle, Compose,
migration revision and explicit schema range. If the current DB head is not inside `N-1`'s reviewed
range—or is unknown—STOP and prefer roll-forward. Never run Alembic downgrade, restore DB
automatically, delete volumes, or change DNS/IAM/secrets. Preserve `N`, stop only the app unit,
atomically switch to verified `N-1`, then verify. The edge remains unchanged unless independently
versioned and approved.

## State migration decision

Decision: **RESOURCE_IMPORT_REQUIRED** for retained managed services.

Future sequence: create an isolated platform root/backend; encode exact live configuration and
lifecycle protection; import one resource/IAM group at a time without secret values; require a
zero-change plan after each import; keep GCE host state isolated and never initialize the legacy
root. If legacy remote state appears, stop and redesign as `STATE_SPLIT_REQUIRED`.

## F3 entry gates

- [x] legacy state conclusively unavailable in the bounded source of truth
- [x] retained/shared ownership and proposed adoption understood
- [x] Cloud SQL status explicitly held as `UNKNOWN` and excluded from F3/deletion
- [x] unrelated project resources excluded
- [x] canonical GCE deployment process documented
- [x] immutable artifact design agreed for implementation
- [x] rollback owner role and artifact requirements defined
- [x] replacement CI/release design documented
- [x] no production infrastructure mutation performed

F3 entry is **READY** for release/CI implementation only. Cloud SQL and deletion remain blocked.

## Phase F3 implementation checkpoint

Status: **READY** for review; no production release performed.

F3 implements the design with `release-manifest.py`, `build-release-bundle.sh`, digest-selectable
production Compose, fail-closed production preflight/systemd wiring, canonical deploy and rollback
entrypoints, release contracts, and `.github/workflows/gce-release.yml`. The workflow verifies and
builds on pull requests; immutable publication remains manually dispatched behind the
`release-publication` environment and separately provisioned WIF/registry variables. It contains no
automatic GCE deployment.

The local synthetic bundle drill generated and revalidated a manifest, deterministic bundle, and
checksums with three synthetic registry digests. No release was deployed or published. Full operator
procedure, N/N-1 retention, receipts, rollback refusal, and roll-forward rules are in
[`gce-release-process.md`](gce-release-process.md).

F4 may provision the dedicated registry/WIF/IAM and exercise publication only through a separately
reviewed infrastructure task. Cloud SQL stays `UNKNOWN`; deletion safety stays `BLOCKED`.
