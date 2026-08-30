# GCS Backup Transport Contract

Status: Phase E2 live VM ADC upload/download and isolated restore-from-GCS accepted

## Backup-only boundary

The canonical flow is:

```text
B3 PostgreSQL + MinIO backup directory
  -> local protected staging
  -> gcloud storage over GCE Application Default Credentials
  -> private GCS backup bucket
  -> fresh isolated download staging
  -> manifest and checksum verification
  -> explicit B3 PostgreSQL and MinIO restore commands
```

GCS is an off-VM backup target only. MinIO remains the runtime media backend. No API, Worker, Web,
nginx, PostgreSQL, or MinIO runtime service receives a GCS backup setting or reads backup objects.
The transfer scripts are host-side, explicit operator commands and never run as an application
startup dependency.

`gcloud storage` is the only canonical transfer tool. It already matches the GCP operator tooling,
uses ADC on GCE, supports recursive directory transfer, and needs neither HMAC credentials nor a
separate rclone configuration. D3 does not add an equivalent `gsutil` or rclone path.

## Bucket contract

The production backup bucket name and project remain environment-specific inputs. The accepted E2
bucket is `strayhub-backups-canvas-primacy-502703-k1` in `asia-east1`. The canonical
object root is:

```text
gs://<backup-bucket>/strayhub-backups/<environment>/<backup-id>/
├── manifest.json
├── postgres/
│   ├── metadata.json
│   └── postgres.dump
├── minio/
│   ├── inventory.json
│   └── objects/<original MinIO keys>
└── _COMPLETE
```

Provision the bucket in a region aligned with the GCE deployment where practical, with uniform
bucket-level access, public access prevention enforced, no public IAM, and no website configuration.
The D3 design disables object versioning because backup IDs and objects are immutable and the VM
cannot overwrite completed objects. Default Google-managed encryption is acceptable; a future CMEK
requirement must be separately approved and must not be conflated with field-level PII encryption
through Cloud KMS.

The legacy `infra/gcp-demo` bucket is runtime-media oriented: API/Worker receive Object Admin,
versioning is enabled, and Cloud Run receives its name. It is not the canonical backup bucket and is
not modified by D3. Future ownership should move the approved backup bucket, bucket IAM, and lifecycle
into a managed-service-only Terraform subset after a remote-state review. No Terraform state move,
resource deletion, or live bucket mutation occurs here.

## Authentication and IAM

Canonical authentication is GCE VM service account -> Application Default Credentials ->
`gcloud storage`. Downloaded service-account JSON and HMAC access keys are forbidden.

At the specific backup bucket, grant the GCE VM service account both:

- `roles/storage.objectCreator` to create new immutable backup objects and `_COMPLETE` markers;
- `roles/storage.objectViewer` to list/read objects for verification and restore.

Do not grant `roles/storage.objectAdmin`, project Editor/Owner, or project-wide storage roles. The VM
does not delete objects. Lifecycle performs expiration. A partial prefix cannot be overwritten with
Object Creator; create a new backup ID after a partial failure rather than granting broader access.
D3 performs no live IAM mutation.

## Upload, marker, and download

Run deterministic local validation first:

```bash
infra/gce/scripts/gcs-backup-preflight.sh \
  --backup-dir /protected/backups/production/<backup-id> \
  --bucket <backup-bucket> \
  --prefix strayhub-backups \
  --environment production
```

Upload uses the same explicit inputs:

```bash
infra/gce/scripts/upload-backup-gcs.sh \
  --backup-dir /protected/backups/production/<backup-id> \
  --bucket <backup-bucket> \
  --prefix strayhub-backups \
  --environment production
```

The uploader verifies the B3 manifest and component checksums before transfer, uploads the directory,
downloads it into a temporary verification directory, and revalidates it. Only then does it upload
`_COMPLETE` as the final object and read the marker back. It never deletes the local backup. Transfer
failure exits non-zero and leaves no completion marker.

Download requires an exact backup ID and an unused protected destination:

```bash
infra/gce/scripts/download-backup-gcs.sh \
  --backup-id <backup-id> \
  --destination-root /protected/restore-staging \
  --bucket <backup-bucket> \
  --prefix strayhub-backups \
  --environment production
```

The downloader first requires a matching `_COMPLETE`, downloads into a private temporary directory,
revalidates the manifest, PostgreSQL SHA-256, MinIO inventory, every object size/hash, backup ID, and
environment, then atomically moves the verified directory into place. It refuses an existing target
and never restores automatically. Missing markers, corrupt artifacts, mismatched metadata, unsafe
paths, empty/root prefixes, JSON credential paths, or partial transfers fail closed.

## Restore from downloaded staging

Only after download verification succeeds, run the existing B3 restore tools with explicit isolated
targets:

```bash
infra/gce/scripts/restore-postgres.sh \
  --project-name <isolated-project> \
  --backup-file /protected/restore-staging/production/<backup-id>/postgres/postgres.dump \
  --target-database strayhub_b3_restore_d3 \
  --confirm-isolated-restore

infra/gce/scripts/restore-minio.sh \
  --project-name <isolated-project> \
  --backup-objects-dir /protected/restore-staging/production/<backup-id>/minio/objects \
  --target-bucket strayhub-b3-restore-d3 \
  --confirm-isolated-restore
```

The PostgreSQL restore continues to verify the Alembic head, RLS policy presence, runtime-role
privileges, and non-superuser/non-BYPASSRLS flags. The MinIO restore continues to use an isolated
private bucket and re-download every object for checksum comparison. Production restore still needs
a Phase E maintenance/traffic and recovery-ownership decision.

## Lifecycle and retention

The initial production proposal is a 7-day unlocked bucket retention policy plus a 35-day age-based
lifecycle deletion rule. The retention policy prevents premature deletion during the first week;
the lifecycle removes objects after 35 days without giving the VM delete permission. Do not lock the
retention policy until legal, privacy, recovery, and rollback owners approve the irreversible choice.

A 35-day rolling window is not the same as seven daily plus four weekly generations: it retains all
objects for their age window. GCS lifecycle cannot select weekly generations from the B3 naming
scheme. Exact seven-daily/four-weekly selection needs future scheduler/metadata logic and remains
deferred with monthly retention. D3 does not claim or implement that pruning policy.

## Verification boundary and security

Historical D3 tests inject a fake
`gcloud` executable backed by a temporary filesystem. The same production scripts prove command
shape, ADC-only behavior, pre/post-transfer checksum validation, marker ordering, fresh download,
and rejection of incomplete/corrupt sets. Synthetic stand-ins contain no real PII or production
media, and test cleanup removes only its exact temporary root.

That simulation alone does not prove GCS service behavior, live IAM, bucket policy, lifecycle
enforcement, or real GCE ADC. Phase E2 now supplies that live evidence.

The isolated `strayhub-d3-verify` drill used a real PostgreSQL custom dump and real MinIO object
capture with the filesystem-backed fake CLI transport. After upload, the local backup directory was
removed; a fresh download restored the synthetic database row, Alembic head, RLS/policy and runtime
role checks, plus the MinIO key, bytes, and inventory checksum. The stack, volumes, and temporary
transport root were removed afterward. This is end-to-end local restore evidence, not live GCS
evidence.

## Phase E2 live acceptance

The dedicated bucket has uniform bucket-level access, public access prevention enforced, no public
principal, an unlocked 604800-second retention period, and a 35-day age-based Delete lifecycle rule.
The VM service account has only bucket-scoped `roles/storage.objectCreator` and
`roles/storage.objectViewer`; it has no delete or administrative role and uses no HMAC or JSON key.

Backup `20260830T015218Z-e2live` contains synthetic data only. The canonical uploader validated the
B3 manifest, uploaded six data/metadata objects, downloaded and revalidated them, then wrote and
read `_COMPLETE` last. The original local staging path was moved aside before the canonical
downloader produced a fresh seven-object set from GCS and revalidated all checksums. The downloaded
dump restored the synthetic PostgreSQL row, Alembic head `0037_animal_external_sources`, RLS and
runtime-role safety; MinIO restored two objects with the exact inventory checksum. The isolated
Compose stack, volumes, temporary source, images, and local backup artifacts were removed afterward.

Incomplete/corrupt-set rejection remains covered by the production-script simulated contract tests;
no intentionally incomplete live prefix was retained. MinIO remains runtime media, and no
application service receives this bucket. The completed synthetic GCS set remains governed by the
unlocked 7-day retention and 35-day lifecycle because the VM deliberately lacks delete permission.

The bucket and IAM were created with controlled `gcloud` commands pending a separate canonical IaC
and remote-state ownership review. Legacy runtime-GCS Terraform and resources were not modified.

Deferred: scheduling, maintenance/traffic policy, alerting and recovery ownership, Phase E3
application supervision, and Phase F legacy cleanup/CI replacement. Legacy deletion remains
forbidden.
