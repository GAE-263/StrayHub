# MinIO server upgrade runbook (2024-12-18 → pgsty 2026-08-04)

Upstream `minio/minio` stopped publishing container images and the repository was archived, so
production Compose now pins the community-maintained fork `pgsty/minio` (and its `pgsty/mc` client)
by amd64 manifest digest (PR #54). Production data was written by `RELEASE.2024-12-18T13-15-44Z`.
This runbook records the upgrade rehearsal and the procedure for the real cutover.

## What the rehearsal proved (synthetic data, amd64)

| Check | Result |
| --- | --- |
| In-place start of `pgsty/minio` on a volume written by 2024-12-18 | healthy in ~6 s, no startup errors |
| 52 objects (two organizations, CJK / special / deep / 0-byte / 6 MB keys) | size, SHA-256, ETag, Content-Type and user metadata identical before and after |
| Bucket stays private (no policy, anonymous GET → 403) | unchanged |
| App `MinioStorageAdapter` put / get / presigned URL / delete | pass |
| `backup-minio.sh` and `restore-minio.sh` with `pgsty/mc` | PASS; backup SHA-256 inventory matches the pre-upgrade baseline |
| Post-upgrade writes survive a restart | yes |
| **Old image on a post-upgrade volume** | **fails**: `Unknown xl meta version 3`, GetObject → `InternalError` |
| Roll back by restoring the pre-upgrade volume tar + old image | identical to the pre-upgrade baseline; post-cutover writes are lost |

**Consequence: the upgrade cannot be undone by switching the image back.** Rollback is only
possible from a physical copy of the volume taken *before* the upgrade, and anything written to
MinIO after that copy is lost.

Not covered by the rehearsal: real production data volume and object count (upgrade time), the
production VM (3.8 GiB RAM, 29 GiB disk), production credentials.

## Assets to have before the cutover

- Old server image, in case Quay no longer serves it: `quay.io/minio/minio@sha256:34c8e2f5…`
  (amd64, `RELEASE.2024-12-18T13-15-44Z`). Keep a `docker save` copy off the VM.
- New images are pinned in `infra/gce/docker-compose.production.yml`; keep a `docker save` copy too.
  A loaded image does **not** resolve an `@sha256:` reference, so a restore from such a copy needs
  the Compose `image:` lines pointed at the loaded tags (or a registry you control).

## Rehearse locally (never with production data)

```bash
export REHEARSAL_ENDPOINT=http://127.0.0.1:29000 REHEARSAL_BUCKET=strayhub-rehearsal \
       REHEARSAL_ACCESS_KEY=<synthetic> REHEARSAL_SECRET_KEY=<synthetic>
uv run python -m scripts.minio_upgrade_rehearsal seed
uv run python -m scripts.minio_upgrade_rehearsal snapshot before.json
# stop the old MinIO, tar its volume (rollback copy), start pgsty/minio on the same volume
uv run python -m scripts.minio_upgrade_rehearsal snapshot after.json
uv run python -m scripts.minio_upgrade_rehearsal compare before.json after.json
uv run python -m scripts.minio_upgrade_rehearsal probe
```

The tool refuses a non-loopback endpoint. Run Compose with a clean environment
(`env -i PATH=… HOME=… docker compose …`): variables exported in your shell, including
`MINIO_*`, **override** `--env-file`. Use `uv run python -m scripts.staging_attestation prepare
--directory <dir>` for a disposable synthetic env file and a unique `--project-name`.

## Production procedure

All commands run on the VM. Define the same Compose invocation the systemd units use:

```bash
dc() { sudo -u strayhub docker compose --project-name strayhub-production \
  --file /opt/strayhub/current/infra/gce/docker-compose.production.yml \
  --env-file /etc/strayhub/production.env \
  --env-file /var/lib/strayhub/secrets/current/runtime.env \
  --env-file /opt/strayhub/current/image-digests.env "$@"; }
```

### 0. Read-only facts

- Running MinIO image and version: `dc ps minio`, `sudo -u strayhub docker exec strayhub-production-minio-1 minio --version`
- Volume size and free disk: `sudo docker system df -v | grep minio_data`, `df -h /var/lib/strayhub`
  (the tar needs roughly the volume's size; the VM root disk is small).
- Object count and size from the latest backup `minio/inventory.json`; the daily backup timer
  (`strayhub-backup.timer`, 03:00 UTC) must have a recent successful, uploaded generation.

### 1. Backups (before the maintenance window ends)

1. Logical backup with its SHA-256 inventory: `infra/gce/scripts/backup-all.sh` (see
   [backup-restore.md](backup-restore.md)); verify the manifest and confirm the GCS upload wrote
   `_COMPLETE`.
2. Quiesce the volume with the unit that owns the runtime (`Type=oneshot`, `RemainAfterExit=yes`, so
   stopping containers by hand would leave the unit "active" and a later `start` would do nothing):
   `sudo systemctl stop strayhub.service`. This stops writers and MinIO, like the deploy does.
3. Physical copy of the volume, with a checksum, stored off the VM:

   ```bash
   sudo docker run --rm -v strayhub-production_minio_data:/data:ro \
     -v /var/lib/strayhub/backups:/backup postgres:16-alpine \
     tar czf /backup/minio-data-pre-pgsty.tgz -C /data .
   sha256sum /var/lib/strayhub/backups/minio-data-pre-pgsty.tgz
   ```

### 2. Cutover

What `deploy-release.sh` actually does (read from the script, not assumed):

1. `compose pull api worker web` and the production preflight run **first**. MinIO and
   `minio-bootstrap` are **not** in that pull. The `pgsty` images would only be pulled implicitly by
   `systemctl restart strayhub.service` (`compose up`) *after* the runtime is stopped. If Docker Hub
   is unreachable at that moment the stack is down and the deploy fails after `release_preparation`
   (recoverable only by the manual `--resume` on the VM, see the release notes). **Pre-pull both
   images on the VM before starting the deploy:**

   ```bash
   sudo docker pull pgsty/minio@sha256:2b36182f3479c58b5cba920f20479738ee85ce218de0596a244f9a1368268db9
   sudo docker pull pgsty/mc@sha256:8ac3333f012adb27c406df77c7cae6ce700892cc44ee489036404e3fc356e9ea
   ```

2. `systemctl stop strayhub.service` stops the **whole** runtime (writers and MinIO), then
   migration, pointer switch and unit install. There is no hook between stop and start, so the
   physical volume copy of step 1 must already exist; the script never takes one.
3. `systemctl restart strayhub.service` starts the upgraded MinIO **and** the writers together.
   `verify-systemd-runtime.sh` and the public `/healthz` checks run after that, and they do not
   inspect MinIO data. Traffic from the existing edge can reach the writers as soon as they are up,
   so a failed step 3 below can lose objects written in that window.

Sequence: step 1 (stop writers and MinIO, tar, then **start the current release again** with
`sudo systemctl start strayhub.service`, whose `ExecStartPost` re-runs the runtime verification, so
production is not left down), pre-pull, then run the
canonical deploy. Skipping the restart and deploying while stopped is faster but unverified (the
preflight's behavior with a stopped runtime was not checked), so it is not the default.

### 3. Verify (all must pass before leaving the window)

- `dc ps` shows `minio` healthy and `minio-bootstrap` exited 0; bucket still private.
- Compare the object count and total size with the step 0 / step 1 inventory.
- Run the logical backup again and compare its `inventory.json` SHA-256 entries with the pre-upgrade
  generation (the same keys must hash identically).
- One real flow end to end: a LINE diary photo is stored, shown in the history carousel, and the
  presigned/public photo URL loads. API and worker logs show no S3 errors.

### 4. Rollback (any failed check)

**Do not use `rollback-release.sh` on its own.** It pulls only `api worker web` of release N-1 and
restarts N-1's Compose, which still pins the *old* `quay.io/minio/...` images. Those would start on
the already-upgraded volume and fail (`Unknown xl meta version 3`), and the old image may no longer
be pullable. It is also refused unless release N records backward compatibility; that claim does
not cover the MinIO data format and must not be written to make a MinIO rollback pass.
Restore the data explicitly first:

1. `sudo systemctl stop strayhub.service`, then remove the MinIO container
   (`dc rm -f minio`).
2. Replace the volume contents with the pre-upgrade tar (verify its checksum first):
   `docker run --rm -v strayhub-production_minio_data:/data -v …:/backup postgres:16-alpine sh -c
   'find /data -mindepth 1 -delete && tar xzf /backup/minio-data-pre-pgsty.tgz -C /data'`.
3. Make sure the old server image is present on the VM (load the saved copy if Quay no longer
   serves it), then run the application rollback entrypoint to N-1, whose Compose pins that image.
   Repeat the step 3 checks against the pre-upgrade inventory.
4. Anything written after the tar was taken must be re-created from other sources or accepted as lost.

## Follow-ups

- `pgsty` is a third-party fork (AGPLv3, not affiliated with MinIO, Inc.). Mirror both images into a
  registry the project controls so a removal cannot break deploys again.
- Upstream is archived: plan for a maintained object store or the GCS storage adapter
  (`services/api/app/infrastructure/storage/gcs.py`) rather than relying on this fork long term.
