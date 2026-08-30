# Phase F1 Legacy / Terraform Ownership Inventory

Status: **READY** (F1 inventory; supplemented by F2)

Migration: **NONE**

Infrastructure mutation: **NONE**

Terraform mutation: **NONE**
Inventory date: 2026-08-31

This is a read-only ownership record. It does not authorize deletion, state migration, API
disablement, IAM changes, or production traffic changes. `SAFE TO DELETE` is deliberately not a
classification in this inventory.

## Accepted E5 checkpoint

```text
a065366837f4fe44e52a067c0a191fc61e1fc702
feat(deploy): add guarded acceptance identity bootstrap
```

The repository was clean at that checkpoint before this document was added.

## Current accepted architecture

```text
Internet -> strayhub.enadv.quest -> nginx VM 34.10.249.63 :80/:443
                                      |-> strayhub-gce 34.81.77.204:3000 -> Web
                                      `-> strayhub-gce 34.81.77.204:8080 -> API

strayhub-gce private Compose network
  -> Worker
  -> PostgreSQL 16 on a named volume
  -> MinIO runtime media on a named volume
```

The public A record resolves to `34.10.249.63`. The edge VM
`nginx-20260820-033352`, its static address `rrapi-nginx`, nginx configuration, and Let's Encrypt
certificate are manually managed and remain part of the accepted architecture. The application VM,
reserved address, dedicated network/subnet, two ingress rules, and VM service account are in the
isolated `infra/gce/terraform` local state. Application release installation, Compose, systemd,
Secret Manager grants, KMS grant, GCS bucket/grants, public edge, DNS, and TLS are not owned by that
state.

The canonical checkout is `/opt/strayhub/current`; the accepted release inventory contained
`/opt/strayhub/releases/e702d7d-e3`. Runtime supervision is owned by `strayhub-secrets.service`,
`strayhub-migrate.service`, and `strayhub.service`. Backups are owned by
`strayhub-backup.service` and `strayhub-backup.timer`.

## Removal classification

| Resource or boundary | Management owner | Classification | Removal prerequisite / evidence |
| --- | --- | --- | --- |
| `strayhub-gce` VM and boot disk | Current GCE Terraform | `KEEP_CURRENT` | Accepted application host; never a legacy cleanup target |
| `strayhub-gce-ip` (`34.81.77.204`) | Current GCE Terraform | `KEEP_CURRENT` | Edge upstream and accepted static application address |
| `strayhub-gce-vpc` and `strayhub-gce-subnet` | Current GCE Terraform | `KEEP_CURRENT` | Canonical VM network |
| `strayhub-gce-allow-edge-upstreams` and `strayhub-gce-allow-iap-ssh` | Current GCE Terraform | `KEEP_CURRENT` | Canonical source-restricted Web/API and IAP SSH ingress |
| `strayhub-gce-sa` | Current GCE Terraform; grants manual | `KEEP_CURRENT` | VM ADC identity for all accepted managed-service access |
| Compose, named PostgreSQL/MinIO volumes, Worker, systemd units, release paths | Repo/operator managed on VM | `KEEP_CURRENT` | Accepted runtime and persistent data |
| `nginx-20260820-033352` and address `rrapi-nginx` (`34.10.249.63`) | Manual, outside repo Terraform | `KEEP_CURRENT` | Sole public DNS/TLS/routing edge; its name is not evidence of legacy status |
| `strayhub.enadv.quest` DNS and edge certificate | Manual/external DNS and edge Certbot | `KEEP_CURRENT` | Live traffic and trusted TLS depend on them; Cloud DNS API is disabled in this project |
| Eleven `strayhub-prod-*` Secret Manager secrets | Manual managed-service setup | `KEEP_SHARED` | Current VM has resource-level Secret Accessor on each; secrets and values are never deletion candidates |
| `strayhub-pii/pii-encryption` KMS key | Manual managed-service setup | `KEEP_SHARED` | Current VM has key-scoped Encrypter/Decrypter; live PII path depends on it |
| `strayhub-backups-canvas-primacy-502703-k1` | Manual managed-service setup | `KEEP_SHARED` | Current backup target; current VM has objectCreator/objectViewer |
| Default VPC, default firewall rules, and default Compute service account | GCP default/manual | `HOLD_NEEDS_VERIFICATION` | Current edge and unrelated workloads use this boundary; ownership is mixed |
| `infra/gcp-demo` Cloud Run services/job and public invoker IAM declarations | Legacy Terraform source | `LEGACY_CANDIDATE` | No matching live StrayHub Cloud Run service was found; still require remote-state proof and reviewed plan |
| `infra/gcp-demo` Cloud SQL, database/users, demo VPC and private-service-access declarations | Legacy Terraform source | `LEGACY_CANDIDATE` | Canonical DB is local PostgreSQL; Cloud SQL API is disabled, so remote-state/live ownership must still be proven |
| `infra/gcp-demo` runtime GCS bucket/IAM/signed-URL declarations | Legacy Terraform source | `LEGACY_CANDIDATE` | Canonical media is MinIO and backup bucket is different; prove remote state cannot affect retained bucket/IAM |
| Legacy Cloud Run service accounts and their project/Secret/KMS IAM declarations | Legacy Terraform source | `LEGACY_CANDIDATE` | Matching service accounts were not found live; prove state and remove only bindings for retired principals |
| Legacy GitHub WIF pool/provider and Artifact Registry writer | Legacy Terraform source | `LEGACY_CANDIDATE` | No matching pool or `strayhub-demo` repository was found; replacement delivery gate must exist first |
| Legacy `strayhub-demo` Artifact Registry, logging bucket, and Cloud Run error metric declarations | Legacy Terraform source | `LEGACY_CANDIDATE` | Matching resources were not found; verify remote state and replacement observability/image ownership |
| Legacy `google_project_service.required` addresses | Legacy Terraform source | `HOLD_NEEDS_VERIFICATION` | APIs are project-shared; `disable_on_destroy=false`, but service ownership must not be treated as legacy-exclusive |
| Legacy Secret Manager data sources | External references from legacy Terraform | `KEEP_SHARED` | Data sources do not create secrets; never delete referenced secrets as legacy cleanup |
| Legacy KMS key variable/binding | Existing key plus legacy-principal binding | `KEEP_SHARED` | Retain key; only a proven retired principal's binding can become a candidate |
| Legacy GCS backend and `strayhub/gcp-demo` prefix | Bucket identity absent from repo | `HOLD_NEEDS_VERIFICATION` | Locate backend configuration and inspect state metadata before changing source or state |
| `.github/workflows/demo-build.yml`, legacy deploy scripts, and GCP-demo IaC contracts | Repository CI/operations | `LEGACY_CANDIDATE` | Replace current validation/image gate and disable mutation paths before removal |
| `rrapi-20260813`, `rr-test`, `rr-api-firewall`, `rrbot`, `rrbot-9527`, and `car-930` identity | Other live workloads | `UNKNOWN` | Names and live presence do not prove StrayHub ownership; exclude from every Phase F deletion plan |

## Terraform ownership

### Current GCE state

`infra/gce/terraform/versions.tf` uses a local backend at `terraform.tfstate`. The state and plan
artifacts are Git-ignored. The existing saved `e1c-final.tfplan` reports `No changes`; it was read,
not regenerated or applied. The checked state contains exactly:

| Terraform address | GCP resource | Purpose | Classification | Safe to remove later? |
| --- | --- | --- | --- | --- |
| `data.google_compute_image.ubuntu_lts` | Ubuntu image lookup | Boot image selection | `KEEP_CURRENT` | No |
| `google_compute_address.gce` | `strayhub-gce-ip` | Static application address | `KEEP_CURRENT` | No |
| `google_compute_firewall.edge_upstreams` | Edge-only TCP 3000/8080 | Public-edge upstream | `KEEP_CURRENT` | No |
| `google_compute_firewall.iap_ssh` | IAP TCP 22 | Administrative access | `KEEP_CURRENT` | No |
| `google_compute_instance.gce` | `strayhub-gce` | Application host | `KEEP_CURRENT` | No |
| `google_compute_network.gce` | `strayhub-gce-vpc` | Dedicated network | `KEEP_CURRENT` | No |
| `google_compute_subnetwork.gce` | `strayhub-gce-subnet` | `10.42.0.0/24` subnet | `KEEP_CURRENT` | No |
| `google_service_account.runtime` | `strayhub-gce-sa` | VM ADC identity | `KEEP_CURRENT` | No |

The VM resource has a lifecycle precondition for IAP compatibility, but neither Terraform tree has
`prevent_destroy`. The current state does not own the edge, DNS/TLS, Secret Manager secrets or
grants, KMS key or grant, backup bucket or grants, application release, Compose data, or systemd.

### Legacy GCP-demo Terraform

`infra/gcp-demo/terraform` declares a GCS backend prefix `strayhub/gcp-demo`, but the backend bucket
is intentionally supplied outside the repository. Repository gates initialize it with
`-backend=false`; no local legacy state is present. Consequently the following are declarations,
not proof that the resources exist in the active project or are present in a reachable state:

| Terraform address/group | Declared GCP purpose | Classification |
| --- | --- | --- |
| `google_project_service.required[*]` | Eleven project APIs | `HOLD_NEEDS_VERIFICATION` |
| `data.google_secret_manager_secret.runtime[*]` | Existing runtime secrets | `KEEP_SHARED` |
| `google_cloud_run_v2_service.{web,api,worker}` | Legacy runtime | `LEGACY_CANDIDATE` |
| `google_cloud_run_v2_job.migration` | Legacy Alembic job | `LEGACY_CANDIDATE` |
| `google_cloud_run_v2_service_iam_member.*` | Legacy public ingress | `LEGACY_CANDIDATE` |
| `google_compute_network.demo`, `google_compute_global_address.private_service_access`, `google_service_networking_connection.private_service_access` | Legacy Cloud SQL network path | `LEGACY_CANDIDATE` |
| `google_sql_database_instance.demo`, `google_sql_database.crm`, `google_sql_user.{runtime,migration}` | Legacy database | `LEGACY_CANDIDATE` |
| `google_storage_bucket.private`, bucket/runtime IAM, signed-URL IAM | Legacy runtime media | `LEGACY_CANDIDATE` |
| `google_service_account.runtime[*]` and project IAM groups | Legacy runtime identities | `LEGACY_CANDIDATE` |
| `google_kms_crypto_key_iam_member.api_volunteer_pii` | Binding on an existing/shared key | `KEEP_SHARED` key; candidate binding only after principal proof |
| `google_secret_manager_secret_iam_member.runtime[*]` | Bindings on existing/shared secrets | `KEEP_SHARED` secrets; candidate bindings only after principal proof |
| `google_iam_workload_identity_pool.github`, provider, and writer IAM | Legacy GitHub delivery identity | `LEGACY_CANDIDATE` after CI replacement |
| `google_artifact_registry_repository.containers` | Legacy image repository | `LEGACY_CANDIDATE` after image provenance review |
| `google_logging_project_bucket_config.demo`, `google_logging_metric.cloud_run_errors` | Legacy observability | `LEGACY_CANDIDATE` after logging review |

There are no modules or workspace selection in either tree. Both pin Google provider `~> 6.0` and
Terraform `>= 1.6.0, < 2.0.0`.

## Read-only live inventory evidence

The active project is `canvas-primacy-502703-k1`.

- Current: `strayhub-gce` is running at `34.81.77.204`; its dedicated address, VPC/subnet,
  firewall rules, and service account match the current state.
- Current manual edge: `nginx-20260820-033352` is running at `34.10.249.63`, and public DNS resolves
  there.
- Managed services: exactly eleven named `strayhub-prod-*` secrets, KMS key
  `strayhub-pii/pii-encryption`, and backup bucket
  `strayhub-backups-canvas-primacy-502703-k1` were found. The VM identity has only the documented
  resource-level Secret Accessor, KMS Encrypter/Decrypter, and bucket objectCreator/objectViewer
  grants; it has no project-level role from these checks.
- Legacy names absent: no `strayhub-demo-*` Cloud Run service/job, service account, Artifact
  Registry, WIF pool, logging bucket, error metric, load-balancer backend, URL map, forwarding rule,
  target proxy, or Compute SSL certificate was found.
- Cloud SQL and Cloud DNS APIs are disabled. They were not enabled for inventory. This prevents a
  complete API-level absence proof and leaves remote-state/DNS ownership on hold.
- The only Artifact Registry found was `rrbot-9527`; the only Cloud Run service found was `rrbot`.
  Other `rr*` compute/network resources and `car-930` are classified `UNKNOWN`, not legacy.

Live absence is not deletion authorization. A resource may exist in another project/region or in a
remote state whose backend bucket is not recorded here.

## CI and deployment ownership

`.github/workflows/demo-build.yml` does not deploy: it formats and validates legacy Terraform with
the backend disabled, scans `infra/gcp-demo`, builds its API/Worker/Web images locally, and uploads
metadata. It neither authenticates to GCP nor pushes images. `.github/workflows/ci.yml` is the
primary test/quality gate and still runs contracts that require the legacy IaC shape.

No workflow deploys the accepted GCE architecture. The accepted host is released manually through
repo-owned scripts, Compose, and systemd. `infra/gcp-demo/apply.sh` remains a manual production
mutation path guarded by `GCP_DEMO_APPLY=1`; its migration, seed, and LINE sync helpers target the
legacy Cloud Run design. Therefore legacy CI/files cannot be removed until a GCE build/release gate
exists, while the legacy manual mutation path must be retired or made uncallable before cleanup.
The live `rrbot-9527` repository is unrelated/unknown and is not a StrayHub replacement registry.

## Terraform state risks

1. The current local state is clear but narrow: it owns only the GCE host foundation.
2. F2 found no legacy backend bucket or state in repository history, local metadata, or the accepted
   project. The sole project bucket has no `strayhub/gcp-demo` prefix. An external/other-project
   backend remains excluded and unknown; if produced later, it may mix legacy-exclusive resources
   with shared Secret/KMS IAM and project APIs.
3. Removing legacy source and later applying its state could destroy legacy resources, remove IAM
   from shared resources, or leave orphaned objects. Source deletion must follow—not precede—a state
   disposition plan.
4. Current live resources absent from current Terraform include the public edge/address, DNS/TLS,
   Secret/KMS/GCS resources and IAM, systemd, releases, and runtime data.
5. Several legacy declarations do not correspond to resources visible in the active project, but
   that does not prove the remote state is empty, uses this project, or is authoritative.
6. F2 proposes a separate platform Terraform owner and future imports for manually retained Secret
   Manager, KMS, GCS, and resource-IAM objects. If legacy state is later discovered with retained
   addresses, the decision changes to a state split. No state action is authorized yet.

Ownership is clear enough to implement F3 release gates, but not to run a destructive plan. Cloud
SQL remains `UNKNOWN` because both Cloud SQL and Cloud Asset APIs are disabled and were not enabled
for discovery. See [`phase-f-release-and-state-plan.md`](phase-f-release-and-state-plan.md).

## Phase F2 outcome and Phase F3 prerequisites

F2 remained non-destructive and produced the ownership and release design linked above. F3 should:

1. implement the replacement GCE build/release gate with immutable image and release provenance;
2. create a reproducible deployment and schema-compatible rollback/roll-forward artifact pair;
3. provision a dedicated registry and short-lived CI identity only after separate review;
4. keep Cloud SQL and all unrelated resources explicitly held;
5. make no legacy state or deletion change; and
6. leave candidate deletion planning for a separately reviewed later task.

No destructive Phase F task should begin because F1/F2 are `READY`.

## Phase F deletion hard gates

- [ ] replacement GCE CI deployment gate exists
- [ ] production GCE deployment can be reproduced
- [ ] Terraform state ownership reviewed
- [ ] shared resources identified and protected
- [ ] rollback owner recorded
- [ ] rollback artifact/release strategy exists
- [x] legacy deployment no longer receives production traffic
- [ ] legacy CI cannot redeploy unexpectedly
- [ ] candidate deletion plan reviewed
- [ ] terraform plan shows no unintended retained-resource changes
- [x] backup/restore evidence remains valid

The traffic gate is supported by DNS resolving to the accepted edge, its upstream configuration
targeting `strayhub-gce`, and the absence of any StrayHub Cloud Run service in the active project.
The backup/restore gate is supported by the accepted E5 checkpoint. All unchecked gates remain
blocking for deletion.
