# PostgreSQL and MinIO Backup / Restore

Status: Phase E2 live GCS transport and isolated restore-from-GCS accepted with synthetic data

## Backup model and boundary

The canonical backup captures two components sequentially under one UTC-stamped backup ID:

1. PostgreSQL logical custom-format output from `pg_dump -Fc`.
2. MinIO object bytes and keys copied with the pinned `minio/mc` image.
3. A manifest that binds component timestamps, Alembic head, counts, and SHA-256 integrity values.

The default B3 staging root is the Git-ignored `infra/gce/backup/generated/`. This is local disk on
the same development machine and is **not an off-VM or durable production backup**. The layout is
uploaded beneath `strayhub-backups/<environment>/<backup-id>/` in a private, IAM-restricted GCS
bucket by the D3 transport scripts. Simulated upload/download and integrity checks pass, but live
bucket/IAM/lifecycle and restore acceptance remain required before production readiness.

Production dumps and object copies may contain sensitive shelter data and PII. Store them with
owner-only permissions, never commit them, never serve them through nginx, and never put them on an
uncontrolled developer workstation. The JSON metadata contains no passwords, tokens, access keys,
or private keys.

## Prerequisites and combined backup

The scripts require Docker Compose, Python 3, the canonical Compose/env files, and a running isolated
stack. They use containerized PostgreSQL and MinIO clients, so no host PostgreSQL or `mc` install is
required. Run the non-destructive backup preflight first:

```bash
infra/gce/scripts/backup-preflight.sh strayhub-b3-verify
```

Create one combined backup:

```bash
infra/gce/scripts/backup-all.sh \
  --project-name strayhub-b3-verify \
  --environment gcp-demo
```

An explicit `--output-root /protected/external/path` is supported for operator-selected staging.
The script rejects broad filesystem/repository roots and symlink roots. It refuses an existing
backup ID instead of overwriting it. A generation is complete only when its top-level
`manifest.json` exists and passes `verify-manifest`; a partial directory from a failed capture must
never be uploaded or treated as restorable evidence.

## PostgreSQL backup and restore

`backup-postgres.sh` executes `pg_dump` inside the Compose PostgreSQL service using the
schema-owning migration credential already present in the container. It never emits a password. The
artifact is `postgres/postgres.dump` in custom format; `postgres/metadata.json` records its SHA-256,
source database, capture timestamp, PostgreSQL tool version, and Alembic migration head.

Restore requires an explicit file, an isolated target database name, and a confirmation flag:

```bash
infra/gce/scripts/restore-postgres.sh \
  --project-name strayhub-b3-verify \
  --backup-file infra/gce/backup/generated/gcp-demo/<backup-id>/postgres/postgres.dump \
  --target-database strayhub_b3_restore_drill \
  --confirm-isolated-restore
```

Only names beginning `strayhub_b3_restore_` are accepted. After checksum and `pg_restore --list`
validation, the script recreates only that isolated database, restores with `pg_restore`, verifies
the Alembic head, and confirms the runtime role remains neither superuser nor `BYPASSRLS`. It cannot
target the canonical, local demo, or arbitrary database. Production restore will require a separate
maintenance/traffic decision and must never be triggered casually.

## MinIO backup and restore

`backup-minio.sh` copies the private runtime bucket to `minio/objects/` with original keys and bytes.
`minio/inventory.json` records every relative key, size, SHA-256, total object count, and a canonical
inventory hash. It does not change bucket policy or expose the bucket.

Restore likewise requires an explicit object directory, an isolated bucket, and confirmation:

```bash
infra/gce/scripts/restore-minio.sh \
  --project-name strayhub-b3-verify \
  --backup-objects-dir infra/gce/backup/generated/gcp-demo/<backup-id>/minio/objects \
  --target-bucket strayhub-b3-restore-drill \
  --confirm-isolated-restore
```

Only bucket names beginning `strayhub-b3-restore-` are accepted. The script validates the staged
inventory before upload, clears only that isolated target, keeps anonymous access disabled, copies
it back to a temporary verification directory, and compares every key, byte count, and checksum.

## Manifest and consistency limitation

`manifest.json` contains the backup ID, UTC timestamp, environment, script version, source Git SHA,
component timestamps/tool versions, PostgreSQL artifact/checksum/Alembic head, MinIO bucket/object
count/inventory checksum, and an explicit `transactionally_atomic: false` declaration. Run:

```bash
python3 infra/gce/scripts/backup-metadata.py verify-manifest \
  --manifest infra/gce/backup/generated/gcp-demo/<backup-id>/manifest.json
```

PostgreSQL and MinIO are captured sequentially, not as a distributed snapshot. The common ID and
short time gap aid correlation but do not guarantee cross-system atomicity. Before production, decide
whether writes must be paused or coordinated during backup and define a measured recovery point.

## Retention and GCS transport

The D3 bucket proposal uses a 7-day unlocked retention policy and a 35-day age-based lifecycle. This
is a rolling age window, not the earlier seven-daily/four-weekly selection proposal. GCS lifecycle
cannot choose weekly generations without scheduler or metadata logic, so exact weekly/monthly
retention remains deferred. The VM has no delete permission and D3 adds no pruning command.

`gcs-backup-preflight.sh`, `upload-backup-gcs.sh`, and `download-backup-gcs.sh` reuse this manifest.
Upload verifies locally, transfers with `gcloud storage`, re-downloads and verifies, then writes
`_COMPLETE` last. Download requires that marker, uses a fresh isolated destination, and revalidates
all hashes before the existing restore scripts may run. See `docs/deployment/gcs-backup.md`.

## B3 recovery drill

Use only the isolated Compose project `strayhub-b3-verify`. Run migration, insert one synthetic
database probe row, upload synthetic MinIO objects, create a combined backup, restore to the strict
isolated database/bucket names, and verify the row, Alembic head, keys, and hashes. Stop only that
project afterward and remove its verification volumes/artifacts. Do not seed real user, shelter, or
PII data.

The completed B3 drill restored `postgres.dump` into `strayhub_b3_restore_drill`, recovered the
synthetic probe row, matched Alembic head `0037_animal_external_sources`, retained 37 RLS-enabled
tables and 40 policies, and confirmed the restricted runtime role ACL. Two synthetic MinIO objects
were restored to `strayhub-b3-restore-drill`; object count and the canonical inventory SHA-256
matched. The manifest revalidated all component hashes. The isolated stack, volumes, and generated
artifacts were removed after verification.

The D3 drill repeated the restore boundary after a simulated GCS round trip: upload with `_COMPLETE`
last, removal of local staging, download to a fresh directory, and full manifest verification. The
downloaded PostgreSQL dump restored its synthetic probe row, migration head, RLS/runtime-role
checks; the downloaded MinIO artifact restored its synthetic key and exact bytes/checksum. Live GCS
was not part of that D3 drill.

Phase E2 repeated the drill through the dedicated private live bucket using VM ADC and restored the
fresh download into isolated PostgreSQL/MinIO targets. Deferred: backup scheduling, exact
daily/weekly/monthly selection, production maintenance mode, systemd, CI replacement, Terraform
state migration, and legacy deletion.
