# Phase F5 Legacy Deletion Readiness and F6 Removal Plan

Status: **READY FOR SEPARATELY AUTHORIZED F6 REPOSITORY CLEANUP**

Inventory date: 2026-08-31

Infrastructure mutation: **NONE**

Legacy deletion: **NOT PERFORMED**

This document is a non-destructive review and a proposed sequence for a separately authorized
Phase F6. It is not deletion authority. No `apply`, `destroy`, state operation, import, IAM change,
API change, traffic change, or resource deletion was performed for F5.

## Accepted production checkpoint

| Field | Verified value |
| --- | --- |
| F4 provenance commit | `a6f39ea0a42987b00c882edd8bad63155e0308e8` |
| Release | `20260831T034951Z-38ab34dc6aaf` |
| Source | `38ab34dc6aaff78e0f3a9f20dbf954a071fb355a` |
| API image | `sha256:febfd99365a536c4063b0b6d1351cd3ea984118fb1f067899c1e1223170dad83` |
| Worker image | `sha256:9234c5d4dda3c53f59bb6af15fee957fdb6cbced490a8074318feca71872ad4f` |
| Web image | `sha256:56ee756e8cab60d0afe6f87248a8273b78ecaae0221d2b117bae1bd83cd68203` |
| Migration | `0037_animal_external_sources` |
| Runtime role / DB host | `strayhub_app` / Compose `postgres` |
| Public hostname / edge | `strayhub.enadv.quest` / `34.10.249.63` |
| Application host | `strayhub-gce` / `34.81.77.204` |

The active release pointer, non-secret receipt, image environment, and running API/Worker/Web
containers matched the release above. `strayhub.service` and `strayhub-backup.timer` were active,
and the bounded runtime verifier passed API, Web, Worker, PostgreSQL, and MinIO.

## Blocking decisions

| Gate | Result | Reason |
| --- | --- | --- |
| Cloud SQL | `ABSENT_PROVEN` | F5d resolved the historical operator scope: the complete two-project organization and all other projects visible to the sole configured account contain no legacy Cloud SQL activity or identity. |
| Legacy production traffic | `NONE` | DNS resolves to the retained nginx edge; live nginx sends Web/API traffic only to `34.81.77.204:3000/8080`; public Web, health, volunteer route and LINE webhook structural checks reached that path. |
| Legacy CI/operator redeploy risk | `NO` | Default-branch commit `f4237bd7e312927ea683a4e73ea32c17f797e95c` removes OIDC from the legacy validation workflow and makes all four legacy mutation helpers unconditional fail-closed stubs. |
| Shared-resource ownership | `PASS` | `PLATFORM_TERRAFORM` owns 29 retained Secret Manager/KMS/GCS/IAM addresses with a final no-change plan and no secret values or versions in state. |
| Terraform state ownership | `PASS` | Current GCE and platform state are known; F5d proves no legacy backend bucket or state object was created in the resolved historical scope. |
| State migration | `NOT_REQUIRED` | Retained shared ownership is adopted safely and there is no legacy state to split or migrate. |
| Destroy-plan review | `NOT_REQUIRED` | No legacy state or live legacy resource exists. F6 must not manufacture a destroy plan from the source declarations. |
| N/N-1 | `PASS` | N `20260831T060436Z-5f0664f0a639` and N-1 `20260831T034951Z-38ab34dc6aaf` are genuine immutable releases; rollback/roll-forward and authenticated acceptance passed. |
| Backup/restore | `PASS` | PostgreSQL/MinIO restore evidence remains valid; fresh backup `20260831T062155Z-e3daily2165` passed manifest/checksum, GCS upload and `_COMPLETE`. |

F5d resolves Cloud SQL, the legacy backend/state bucket, and legacy runtime GCS as
`ABSENT_PROVEN`. Deletion safety and F6 entry are **READY** only for the separately reviewed
repository-source cleanup boundary documented below; the live GCP deletion manifest is empty.

### F5b ownership update

`PLATFORM_TERRAFORM` now owns the retained Secret Manager/KMS/backup GCS/exact IAM set plus its
dedicated state bucket. All 29 addresses were imported without live-resource change and the final
plan is `No changes`. The platform ownership gate is resolved; see
[`platform-terraform.md`](platform-terraform.md).

The F5b source branch and default-branch commit
`f4237bd7e312927ea683a4e73ea32c17f797e95c` fail-close all four legacy mutation helpers and harden
the legacy workflow to validation-only without OIDC. The final redeploy risk is `NO`. F5b also
established the genuine N/N-1 pair recorded above; F5d resolves the later historical identity
questions.

## Evidence-backed resource inventory

An absent expected name is evidence that there is currently no matching deletion target in the
active project; it is not evidence about an unknown external project or backend.

| Resource | Actual GCP identity | Current use | Future use | Classification | Evidence | Proposed F6 action |
| --- | --- | --- | --- | --- | --- | --- |
| Application VM | `projects/canvas-primacy-502703-k1/zones/asia-east1-b/instances/strayhub-gce` | Canonical runtime | Canonical runtime | `KEEP_CURRENT` | Running, healthy, current release active | Never delete in legacy cleanup |
| Application IP | `regions/asia-east1/addresses/strayhub-gce-ip` (`34.81.77.204`) | Edge upstream | Stable application address | `KEEP_CURRENT` | In use by current VM and nginx | Never delete |
| Application network | `strayhub-gce-vpc`, `strayhub-gce-subnet` | Canonical isolated network | GCE runtime | `KEEP_CURRENT` | Known current Terraform addresses | Never delete |
| Application firewall | `strayhub-gce-allow-edge-upstreams`, `strayhub-gce-allow-iap-ssh` | Edge-only upstream and IAP SSH | GCE runtime/admin | `KEEP_CURRENT` | Exact source ranges and current state verified | Never delete |
| Runtime identity | `strayhub-gce-sa@canvas-primacy-502703-k1.iam.gserviceaccount.com` | VM ADC | GCE runtime | `KEEP_CURRENT` | VM attachment plus resource-level grants | Never delete or weaken |
| Public edge | `nginx-20260820-033352`, `rrapi-nginx` (`34.10.249.63`) | Sole DNS/TLS edge | Manual retained edge | `KEEP_CURRENT` | DNS and live nginx upstream evidence | Never delete in Phase F |
| DNS/TLS | `strayhub.enadv.quest`, edge certificate/config | Public traffic, LINE/LIFF | `MANUAL_RETAIN` | `KEEP_CURRENT` | Public HTTPS healthy; Cloud DNS API is disabled and ownership stays manual/external | Retain unchanged |
| Immutable release | release directory, receipt, manifest and three digest images for `20260831T034951Z-38ab34dc6aaf` | Current N | Roll-forward and audit | `KEEP_CURRENT` | Runtime digests match manifest | Retain; add genuine compatible N-1 |
| Current registry | `asia-east1/strayhub` | API/Worker/Web immutable images | Canonical release registry | `KEEP_CURRENT` | Repository IAM is publisher writer/runtime reader | Never delete |
| Current WIF | pool `github-strayhub`, provider `github` | GitHub OIDC | Canonical release auth | `KEEP_CURRENT` | Active, repository/ref/environment restricted | Never delete or broaden |
| Publisher identity | `strayhub-artifact-publisher@...` | Immutable publication | Canonical publisher | `KEEP_CURRENT` | WIF impersonation and repository writer | Never delete |
| Deployer identity | `strayhub-gce-deployer@...` | Reserved production environment identity | Canonical deployment boundary | `KEEP_CURRENT` | Separate WIF binding; no broad project role observed | Retain pending deployment design |
| Production secrets | Eleven `strayhub-prod-*` secrets | Atomic runtime staging | `PLATFORM_TERRAFORM` | `KEEP_SHARED` | Each has exact runtime accessor binding | Import metadata/IAM later; never import values or delete versions |
| PII KMS | `asia-east1/strayhub-pii/pii-encryption` | Runtime encrypt/decrypt | `PLATFORM_TERRAFORM` | `KEEP_SHARED` | Enabled key, exact runtime grant | Import key/IAM later; never delete key material |
| Backup GCS | `strayhub-backups-canvas-primacy-502703-k1` | Off-VM backup/restore | `PLATFORM_TERRAFORM` | `KEEP_SHARED` | Private, uniform, retention/lifecycle, runtime creator/viewer | Import bucket/IAM later; never delete backup objects in legacy cleanup |
| Project APIs | Enabled shared project services | Current GCE and unrelated workloads | Platform/project boundary | `HOLD` | Services are not legacy-exclusive; legacy Terraform uses `disable_on_destroy=false` | Do not disable in Phase F without separate consumer proof |
| Default network/firewalls/default Compute SA | Project defaults | Edge and unrelated workloads | External/shared | `HOLD` | Ownership is mixed; edge uses default network and SA | Exclude from automated cleanup |
| Legacy Cloud Run services | Expected `strayhub-demo-{web,api,worker}`; no matching live identity | None found | None | `LEGACY_SAFE_CANDIDATE` (source only) | Active project lists only unrelated `rrbot` | No cloud delete now; remove declarations only after all gates and a final absence check |
| Legacy Cloud Run migration job | Expected `strayhub-demo-migration`; no matching live identity | None found | None | `LEGACY_SAFE_CANDIDATE` (source only) | No Cloud Run jobs listed | No cloud delete now; retire helper/declaration after gates |
| Legacy service accounts/IAM | Expected `strayhub-demo-{api,next,worker,migration}`; none found | None found | None | `LEGACY_SAFE_CANDIDATE` (source only) | SA inventory contains only current and unrelated identities | Remove source only after final policy diff; never remove current grants |
| Legacy WIF | Expected `strayhub-demo-github`; none found | None found | None | `LEGACY_SAFE_CANDIDATE` (source only) | Only `github-strayhub` exists | Remove source only; do not touch current pool/provider |
| Legacy Artifact Registry | Expected `asia-east1/strayhub-demo`; none found | None found | None | `LEGACY_SAFE_CANDIDATE` (source only) | Only current `strayhub` and unrelated `rrbot-9527` exist | Remove source only after final registry inventory |
| Legacy observability | Expected `strayhub-demo-logs` and `strayhub-demo-cloud-run-errors`; none found | None found | None | `LEGACY_SAFE_CANDIDATE` (source only) | Only standard logging buckets; no custom metric found | Remove source only after final logging inventory |
| Legacy network/private service access | Expected `strayhub-demo-vpc` and address/peering; none found | None found | None | `LEGACY_SAFE_CANDIDATE` (source only) | Network/global-address/peering inventory has no match | Remove source only; do not touch current/default networks |
| Cloud SQL/database/users | No historical project contains a matching instance | None | None | `LEGACY_SAFE_CANDIDATE` (source only) | F5d organization/project lifetime audit, service, IAM and network correlation prove the declaration was never applied | Remove source only; no cloud deletion command |
| Legacy runtime GCS | No historical project contains a legacy runtime bucket | None | None | `LEGACY_SAFE_CANDIDATE` (source only) | F5d complete bucket/lifetime activity inventory plus absent operator input and pending deployment evidence | Remove source only; never touch backup/platform buckets |
| Legacy backend/state | No bucket or state object; historical prefix `strayhub/gcp-demo` was never initialized remotely | None | None | `LEGACY_SAFE_CANDIDATE` (source only) | CI and helper used `-backend=false`; no backend input, object, local metadata or historical operator command exists | Remove source only; do not initialize or plan the legacy root |
| Legacy repo CI/operator paths | `demo-build.yml`, fail-closed `infra/gcp-demo` helpers and IaC | Validation only | None | `LEGACY_SAFE_CANDIDATE` (source only) | Default branch has no OIDC and every legacy mutation helper exits unconditionally | Remove obsolete workflow/source/contracts in separately reviewed F6 repository cleanup |
| Unrelated resources | `rrapi-20260813`, `rr-test`, `rr-api-firewall`, `rrbot`, `rrbot-9527`, `car-930` | Other workloads/ownership unknown | Outside StrayHub | `EXCLUDED` | Live identities do not establish StrayHub ownership | Never include in Phase F commands |

There are no proven live GCP legacy deletion candidates today. The `LEGACY_SAFE_CANDIDATE` rows are
repository-source retirement candidates only. A later appearance of a matching live resource moves
that row back to `HOLD` until ownership and data-retention evidence are reviewed.

## Shared-resource ownership transition

| Resource | Current owner | Current consumer | Future owner | Terraform import required? | Safe to remove from legacy ownership? |
| --- | --- | --- | --- | --- | --- |
| Secrets and secret IAM | Manual/operator | `strayhub-gce-sa` | `PLATFORM_TERRAFORM` | Yes, metadata and exact IAM only | Only after zero-change adoption; never remove secret/value |
| KMS keyring/key/IAM | Manual/operator | API through `strayhub-gce-sa` | `PLATFORM_TERRAFORM` | Yes | Only exact retired-principal bindings after policy comparison |
| Backup bucket/IAM | Manual/operator | Backup service through `strayhub-gce-sa` | `PLATFORM_TERRAFORM` | Yes | Only after zero-change adoption; bucket/data remain retained |
| GCE host foundation | Local GCE Terraform | Canonical VM | `GCE_TERRAFORM` | No current import; remote backend later | Not part of legacy ownership |
| Edge/DNS/TLS | Manual/external | Public users, LINE and LIFF | `MANUAL_RETAIN` | No current plan | No; retain unchanged |

Conceptual state sequence: declare exact live configuration in an isolated platform root; select a
reviewed remote backend; import one resource or exact IAM member at a time; require a zero-change
plan after every adoption; prove the legacy root no longer references retained resources; only then
retire legacy source. If a legacy state is discovered, stop and redesign this as an explicit state
split. F5 performs none of these operations.

## DO NOT DELETE

- `strayhub-gce`, its boot disk, `strayhub-gce-ip`, `strayhub-gce-vpc`,
  `strayhub-gce-subnet`, current firewall rules, and `strayhub-gce-sa`.
- The `strayhub` Artifact Registry, `github-strayhub` pool/provider,
  `strayhub-artifact-publisher`, and `strayhub-gce-deployer`.
- All eleven `strayhub-prod-*` secrets, versions, access bindings, KMS keyring/key/versions, backup
  bucket, backup objects, retention/lifecycle, and current runtime IAM.
- `nginx-20260820-033352`, `rrapi-nginx`, public DNS, trusted TLS material, and nginx configuration.
- PostgreSQL and MinIO named volumes, immutable release directories, receipts, manifests, current
  systemd units, and backup timer.
- `rrapi-20260813`, `rr-test`, `rr-api-firewall`, `rrbot`, `rrbot-9527`, and `car-930`.
- Default project network, firewall rules, Compute service account, and shared project APIs without
  a separately reviewed ownership/consumer decision.

## Proposed F6 sequence — do not execute in F5

Every step is fail-closed. Steps containing an unresolved placeholder are not executable until a
reviewed, exact resource manifest replaces it.

1. **Close every F5 blocker.** Precondition: Cloud SQL is `PRESENT` or `ABSENT_PROVEN`, backend/state
   identity is resolved, platform imports have zero-change plans, and a genuine compatible N-1 is
   accepted. Action: documentation/review only. Verification: all F6 gates below are checked.
   Stop condition: any result remains `UNKNOWN`, `PARTIAL`, or failed.
2. **Retire legacy redeploy paths on the default branch.** Precondition: current release workflow
   and replacement contracts pass. Action: separately reviewed repository commit that removes or
   permanently fail-closes `infra/gcp-demo/apply.sh` and the three legacy job helpers, then replaces
   `demo-build.yml` and legacy-shape CI assertions. Verification: default branch no longer has a
   callable legacy apply/job execution path; current release workflow still passes. Rollback:
   revert only the repository commit; do not recreate cloud resources.
3. **Establish N/N-1.** Precondition: a second immutable release has reviewed schema compatibility.
   Action: publish/deploy through canonical OIDC/WIF and exact-digest tooling. Verification: both
   manifests, receipts, images and rollback dry run pass. Stop: no genuine compatible pair.
4. **Capture fresh recovery evidence.** Precondition: stable current runtime. Action: invoke the
   existing systemd backup service, verify local manifest/checksums, GCS `_COMPLETE`, and the latest
   accepted isolated restore procedure/evidence. Verification: PostgreSQL head/RLS/runtime role and
   MinIO inventory pass. Stop: any backup, upload, marker or restore failure.
5. **Freeze the exact deletion manifest.** Precondition: fresh read-only GCP inventory and policy
   exports. Action: record full resource names/regions and exact IAM members only for proven legacy
   resources. Verification: two-person comparison against this KEEP/HOLD/EXCLUDED list and current
   Terraform no-change plan. Stop: a current/shared/unrelated resource appears.
6. **Remove legacy traffic bindings, if any.** Precondition: exact candidate exists and traffic/log
   evidence remains zero. Action class: remove only the candidate Cloud Run invoker/domain/traffic
   binding named in the frozen manifest. Verification: public traffic and current GCE acceptance
   remain healthy. Stop/rollback: restore the saved exact binding if current traffic regresses.
   Current inventory makes this a no-op.
7. **Remove legacy Cloud Run services and job, if any.** Precondition: exact service/job identities
   are in the frozen manifest and no traffic/schedule/caller exists. Action class: individual
   `gcloud run services delete` / `gcloud run jobs delete`; never wildcard. Verification: each exact
   identity is absent and current routes pass. Stop: any dependency or unexpected identity.
   Current inventory makes this a no-op.
8. **Resolve and disposition Cloud SQL.** Precondition: status is no longer unknown. If absent,
   perform no action. If present, require exact instance identity, ownership, retention/export,
   backup verification, connection audit and explicit separate deletion approval before an
   individual `gcloud sql instances delete`. Verification: approved export/retention evidence and
   current local PostgreSQL acceptance. Stop: any data, owner, state or rollback uncertainty.
9. **Resolve and disposition legacy runtime GCS.** Precondition: exact bucket is proven legacy-only,
   its state and contents have an approved retention disposition, and it is not the backup bucket.
   Action class: delete reviewed objects/bucket only under separate authorization. Verification:
   exact bucket absence plus MinIO/GCS-backup acceptance. Stop: unknown data or owner, shared IAM,
   or any name equal to the protected backup bucket.
10. **Remove legacy-exclusive IAM identities and bindings.** Precondition: principals are absent from
    every current consumer and are listed exactly. Action class: remove each legacy-only IAM member,
    then service account; never edit a whole policy. Verification: policy diff contains only named
    retired principals; current VM, publisher and deployer access still pass. Stop/rollback: restore
    the saved exact member if a current check fails.
11. **Remove legacy WIF and registry/observability, if present.** Precondition: exact resources are
    proven legacy-only and no artifact/identity retention requirement exists. Action class:
    individual provider, pool, repository, logging metric/bucket deletion from the frozen manifest.
    Verification: current `github-strayhub`, `strayhub` repository and release digests remain.
    Stop: any current provenance or shared consumer reference.
12. **Remove legacy-exclusive networking, if present.** Precondition: Cloud SQL/runtime resources
    are gone, exact network/address/peering has no consumer, and it is neither current nor default.
    Action class: dependency-ordered individual peering/address/network deletion. Verification:
    current GCE network/firewalls and edge path pass. Stop: shared peering/route or unknown owner.
13. **Review project APIs last.** Precondition: project-wide consumer inventory proves an API is
    legacy-exclusive. Action: separate approval for a single named service disablement. Verification:
    current and unrelated workloads pass. Default F6 action is retain; never infer exclusivity from
    legacy Terraform.
14. **Retire legacy IaC/docs only after cloud/state disposition.** Precondition: no state can later
    apply the old source and every historical record has a superseding pointer. Action: reviewed
    repository removal/archive commit. Verification: current contracts, release build and docs pass.
    Stop: source is still required to explain unresolved state/resources.
15. **Run post-removal acceptance.** Precondition: all authorized steps succeeded. Action: no new
    mutation; run public routes, authenticated tenant/RLS/volunteer checks, systemd/runtime health,
    managed-service access, backup timer, secret scan and current Terraform plan. Rollback/stop:
    stop further removal immediately and restore only the exact last reversible binding/config;
    use immutable N/N-1 or roll-forward according to the accepted release procedure.

A broad `terraform destroy` is prohibited: no trustworthy legacy state exists, and the source mixes
legacy resources with shared secrets, KMS IAM and project APIs.

## F6 hard gates

- [x] current immutable runtime digest matches manifest
- [x] Cloud SQL status resolved
- [x] production traffic uses only current GCE path
- [x] current Artifact Registry/WIF/IAM explicitly protected
- [x] shared Secret/KMS/GCS/IAM ownership adopted and zero-change
- [x] legacy CI/operator redeploy path identified
- [x] legacy redeploy path retired on the default branch
- [x] legacy Terraform/backend state risk fully resolved
- [x] genuine compatible immutable N/N-1 exists
- [x] no current/shared resource appears in the proposed deletion plan
- [x] unrelated resources are excluded
- [x] backup/restore readiness confirmed
- [x] fresh pre-removal backup `20260831T062155Z-e3daily2165` completed
- [x] dependency-ordered removal and stop conditions are defined
- [x] post-removal acceptance plan is defined

Only evidence-backed gates are checked. Phase F6 entry is **READY** for a separately authorized
repository-only cleanup; it does not authorize any live GCP deletion.

F5b passed the genuine N -> N-1 -> N drill with exact running digests and authenticated
tenant/RLS/volunteer acceptance at each switched state. The roll-forward used the recorded newer
release only, required equal migration revision, and performed no migration or database downgrade.
These results do not weaken the three unresolved identity gates: Cloud SQL, the legacy Terraform
backend/state bucket, and legacy runtime GCS all remain `UNKNOWN`.

## Phase F5c discovery result

F5c performed a final read-only correlation of repository history, local Terraform metadata,
accepted-project inventory, bucket object names, IAM/network evidence, and Admin Activity logs. It
made no infrastructure or Terraform mutation.

The accepted project was created on 2026-07-17, and its full-lifetime Admin Activity evidence shows
no Cloud SQL event, no Cloud SQL API enablement, and no `strayhub-demo-postgres` reference. Cloud
SQL Admin, Cloud Asset, and Service Networking remain disabled; no Cloud SQL service-agent binding,
private-service address, peering, peering route, or canonical runtime consumer exists. A legacy
Cloud SQL declaration targeted at this project is `DECLARED_BUT_ABSENT`.

The same full-lifetime Storage Admin Activity inventory records only the protected backup and
platform-state bucket creations. They are the only current buckets, and neither contains the
historical `strayhub/gcp-demo` prefix. The only template-like concrete runtime name,
`strayhub-demo-private`, does not exist. Repository and Git history contain no tracked legacy state,
tfvars, backend config, backend bucket value, runtime bucket value, or production project value;
both the original workflow and historical helper initialized the legacy root with the backend
disabled.

These facts prove absence only in the accepted project. Because the legacy `project_id`,
`name_prefix`, backend bucket, and runtime bucket were all external inputs, neither the repository
nor the single currently authenticated account proves that an inaccessible historical
project/account was never used. The F5c cross-project result is therefore:

| Gate | F5c result | Removal consequence |
| --- | --- | --- |
| Cloud SQL | `CLOUD_SQL_UNKNOWN` | no SQL deletion target; stop until historical project binding or organization-wide absence is proven |
| Legacy backend/state | `UNKNOWN`; no state object found | never initialize against a guessed bucket and never run a destroy plan |
| Legacy runtime GCS | `UNKNOWN`; no data-bearing bucket found | no bucket/object deletion; require exact historical input and retention disposition |

There are no new live `LEGACY_SAFE_CANDIDATE` resources and no newly discovered
`LEGACY_DATA_HOLD`; the unknown identities themselves remain hard holds. All `KEEP_CURRENT`,
`KEEP_SHARED`, and `EXCLUDED` rows remain unchanged. Deletion safety and F6 entry remain
**BLOCKED**.

## Phase F5d historical inventory result

F5d resolved the external-input uncertainty using the historical operator and organization scope.
The sole configured gcloud account is an administrator of organization `710298876843`; complete
project enumeration shows two active organization projects and no folders. One additional visible
project is labeled and enabled only for the Gemini API and has no repository, operator, service, or
resource correlation to StrayHub.

The accepted project and the second organization project were both created on 2026-07-17. Their
full-lifetime Admin Activity contains no `strayhub-demo` event, Cloud SQL event, or Cloud SQL API
enablement. The second project has no relevant API or bucket; the accepted project contains only
the canonical resources already protected by this plan. Cloud Asset organization search was not
available because its API remains disabled, and F5d did not enable it. Organization-admin project
enumeration, per-project service/resource inventory, and full-project-lifetime audit evidence were
used instead.

Repository and complete Git history contain no production legacy project, tfvars, backend config,
backend bucket, runtime bucket, state, successful T239 evidence, or `GCP_DEMO_APPLY=1` execution.
The original workflow and the historical operator helper both initialized with `-backend=false`.
The local shell history contains only the accepted project selection and no legacy Terraform input
or apply command. Local gcloud logs begin on 2026-08-29; their relevant StrayHub-demo matches are
only current F5 discovery operations. The versioned deployment evidence has remained pending since
its creation.

This combined evidence resolves the historical deployment identity as **NONE USED**: the legacy
Terraform stack was designed and validated but never applied. Therefore:

| Boundary | F5d result |
| --- | --- |
| Historical project identity | `RESOLVED` — no project was used for the legacy deployment |
| Cloud SQL | `ABSENT_PROVEN` |
| Legacy backend/state | `ABSENT_PROVEN` |
| Legacy runtime GCS | `ABSENT_PROVEN` |

No live legacy resource or data-bearing hold exists. The F6 cloud deletion manifest is empty. The
only new `LEGACY_SAFE_CANDIDATE` scope is repository source: fail-closed `infra/gcp-demo` helpers,
legacy Terraform declarations, the validation-only legacy workflow, obsolete shape contracts, and
transitional documentation. F6 must be a separately reviewed repository cleanup that preserves
historical evidence and all current/shared/excluded resources. A broad `terraform destroy`, guessed
backend initialization, API disablement, IAM change, or live resource deletion remains prohibited.

## Phase F6 execution record

F6 executed the repository-only portion of this plan: obsolete declarative/callable legacy source,
its validation workflow, and legacy-only contracts were removed. Current image definitions and the
LINE Rich Menu input were moved to `infra/gce/`, current workflows/contracts were updated, and an
explicit historical record was added. The cloud deletion manifest was empty, so no Terraform
destroy/apply, backend initialization, API/IAM mutation, or live resource deletion occurred.
