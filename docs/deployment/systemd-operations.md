# GCE systemd Operational Supervision

Status: Phase E3 accepted; Phase E5 restart/reboot acceptance passed with noted failure-injection boundary

## Scope and paths

The canonical deployment checkout is `/opt/strayhub/current`. Unit source files live in
`infra/gce/systemd/` and are installed root-owned at mode `0644` under `/etc/systemd/system` by
`install-systemd-units.sh`; operators do not maintain hand-edited copies. The runtime user is
`strayhub`, with its explicitly accepted root-equivalent Docker group membership.

The non-secret config directory is `root:strayhub` mode `0750`, and
`/etc/strayhub/production.env` is `root:strayhub` mode `0640`. Secret generations and local backups remain `strayhub:strayhub` beneath
`/var/lib/strayhub/{secrets,backups}` at mode `0700`; staged files remain `0600`. Unit files contain
paths and resource names only, never passwords, tokens, JWT bodies, or service-account JSON.

Migration, runtime, health, and backup orchestration run as `strayhub`. The secret-fetch oneshot is
the sole root unit because the host-packaged `gcloud` is snap-confined and rejects the bootstrap
user's `/opt/strayhub` home. It performs only the existing read-only atomic fetch, then explicitly
hands the protected staging tree back to `strayhub`; no other unit duplicates secret access. This
unit retains `PrivateTmp` and `UMask=0077`, but cannot use `NoNewPrivileges` because that blocks the
snap-confine transition required to launch the host `gcloud`. All non-root orchestration units keep
`NoNewPrivileges=true`.

## Unit topology and startup order

The boot transaction is deliberately linear:

```text
network-online + docker
  -> strayhub-secrets.service
  -> strayhub-migrate.service (production preflight, then existing Compose migration)
  -> strayhub.service (Compose runtime, then bounded local health verification)

strayhub-backup.timer
  -> strayhub-backup.service (existing B3 backup + D3 GCS upload)
```

`strayhub-secrets.service` is a `Type=oneshot` unit that invokes only `fetch-secrets.sh`. Its atomic
`current` replacement and previous-generation preservation remain unchanged. If secret fetch fails,
the migration dependency fails and the application transaction does not start.

`strayhub-migrate.service` is another oneshot. Its `ExecStartPre` runs the production preflight after
secret staging. Its only migration path is the existing Compose `tools` profile and `migration`
service, which waits for healthy PostgreSQL and runs Alembic upgrade head. MinIO is not an Alembic
dependency. If preflight or migration fails, `strayhub.service` is blocked; there is no second
migration command or restart loop.

`strayhub.service` starts the canonical application services: PostgreSQL, MinIO and its idempotent
bucket bootstrap, API, Worker, and Web. Public nginx is intentionally absent from this VM; the
existing edge at `34.10.249.63` is the sole TLS and routing owner. Compose dependency health gates
remain authoritative.
Long-running services retain `restart: unless-stopped`; migration and minio-bootstrap retain
`restart: "no"`.

## Start, stop, restart, and health

Normal operator commands are:

```bash
sudo systemctl start strayhub
sudo systemctl stop strayhub
sudo systemctl restart strayhub
sudo systemctl status strayhub strayhub-secrets strayhub-migrate
```

Start uses `docker compose up -d` with the protected non-secret and staged secret env files. Stop
uses bounded `docker compose stop`; it never invokes `docker compose down -v` and therefore does not
delete the named PostgreSQL or MinIO volumes. A normal restart does not rerun an already-active
migration oneshot. At a new boot, Alembic upgrade head is safely idempotent and completes before the
application unit.

`verify-systemd-runtime.sh` waits at most 180 seconds. It requires healthy PostgreSQL, MinIO, API,
and Web containers, a running Worker, direct local HTTP responses on the source-restricted Web/API
host ports, the public structural API and volunteer route, and the expected GET 405 at the LINE
webhook path. A timeout fails startup visibly rather than accepting a degraded runtime.

The application VM neither mounts nor issues a TLS certificate. DNS and the existing Let's Encrypt
certificate remain unchanged on the old edge. The hostname `strayhub.enadv.quest` and LINE/LIFF
endpoints are unchanged.

Docker's published Web/API ports require host IPv4 forwarding. The repo-owned
`infra/gce/systemd/99-strayhub-network.conf` persists `net.ipv4.ip_forward=1` through reboot, and
the systemd installer loads it before enabling the runtime. GCE firewall policy remains the ingress
boundary: forwarding does not make an unallowed port or source reachable.

## Failure recovery and reboot

Docker restart policies recover an unexpectedly crashed non-stateful container without requiring
systemd to poll containers. The accepted API failure recovery drill sends `SIGKILL` to only the
API container's host PID, waits for Docker to restart it, and reruns the bounded health verifier.
Do not use an administrative `docker stop` or `docker kill` for this drill: Docker may treat that as
an intentional stop and suppress `unless-stopped` recovery. PostgreSQL and MinIO are not killed for
failure injection.

`strayhub.service` and `strayhub-backup.timer` are enabled. After a reboot, systemd waits for network
and Docker, stages a fresh atomic secret generation, safely checks migration head through the
existing migration service, starts Compose, and runs local health verification. The static IP and
named volume identities must remain unchanged.

Failure gates are proven without damaging live state: contract tests establish that a failed secret
oneshot blocks migration/application, and a failed migration oneshot blocks the main unit. Secret
failure tests use an isolated bad source/map and preserve the previous generation; migration failure
is not injected into the live database.

## Backup timer and concurrency

`strayhub-backup.timer` runs once per day at `03:00 UTC`, adds up to 15 minutes of randomized delay,
and uses `Persistent=true`, so a missed run is triggered after downtime. This is one daily PoC
backup, not exact seven-daily/four-weekly selection. The accepted GCS 35-day lifecycle and unlocked
7-day retention remain the current retention mechanism.

`strayhub-backup.service` uses the current protected scalar environment, takes the existing B3
PostgreSQL/MinIO backup, validates it, and invokes the existing D3 upload that writes `_COMPLETE`
last. `flock` rejects overlap. Any backup, validation, or upload failure exits non-zero and leaves
the local artifact for diagnosis; it does not delete local backups or GCS objects.

The backup unit keeps its non-root `strayhub` identity and places the snap package's native Cloud
SDK entrypoint (`/snap/google-cloud-cli/current/bin`) first in its fixed `PATH`. This avoids the snap
launcher rejecting the system user's `/opt/strayhub` home while preserving VM ADC and the unit's
least-privilege boundary; it does not install credentials or a service-account key file.

GCS does not preserve an empty `minio/objects/` directory. Upload and download verification recreate
that canonical empty directory before manifest validation. An expected non-empty inventory still
fails if any object is missing, and `_COMPLETE` remains the last write.

Manual acceptance and timer inspection use:

```bash
sudo systemctl start strayhub-backup.service
sudo systemctl status strayhub-backup.service strayhub-backup.timer
sudo systemctl list-timers strayhub-backup.timer
```

## Phase E3 live acceptance evidence

The 2026-08-30 controlled acceptance used project `canvas-primacy-502703-k1`, VM
`strayhub-gce`, static IP `34.81.77.204`, and VM ADC service account
`strayhub-gce-sa@canvas-primacy-502703-k1.iam.gserviceaccount.com`. The original synthetic database
URLs used the bootstrap login instead of the canonical role split. Exactly one new enabled version
was added to each existing database URL secret: runtime now uses `strayhub_app`, while migration
uses `strayhub_migration`. No secret resource or old version was deleted, and the runtime role
remained non-superuser, non-role-creating, non-database-creating, and without `BYPASSRLS`.

Fresh secret staging, production preflight, migration, and local runtime health passed; Alembic
remained at `0037_animal_external_sources` with 37 RLS-enabled tables and 40 policies. A normal
systemd restart preserved the PostgreSQL and MinIO named volumes and did not rerun the active
migration oneshot. The API-only process crash recovered to healthy with Docker restart count 1.
One controlled reboot produced a fresh immutable secret generation, reran migration safely, and
recovered all services with the same volumes, static IP, ADC identity, and migration head.

Manual backup `20260830T033225Z-e3daily6182` passed local integrity checks, GCS upload/download
verification, and `_COMPLETE` validation in the private backup bucket. A controlled held-lock test
rejected overlap before backup work began. The timer is enabled and active with `Persistent=true`;
its first observed next run was 2026-08-31 03:02:17 UTC. At acceptance, 2.9 GiB of 3.8 GiB memory
was available and the 29 GiB root filesystem was 32% used. Journals contained no secret values.
DNS, trusted certificate issuance, LINE/LIFF endpoints, public cutover, IAM, KMS, GCS policy, and
legacy infrastructure were unchanged.

## Logs and troubleshooting

Systemd orchestration is visible in journald, while application output remains in Docker logs:

```bash
sudo journalctl -u strayhub-secrets -u strayhub-migrate -u strayhub --since today
sudo journalctl -u strayhub-backup --since today
sudo -u strayhub docker compose --project-name strayhub-production \
  --file /opt/strayhub/current/infra/gce/docker-compose.production.yml \
  --env-file /etc/strayhub/production.env \
  --env-file /var/lib/strayhub/secrets/current/runtime.env ps
sudo -u strayhub docker logs --tail 100 strayhub-production-api-1
```

Do not print the rendered Compose model or staged env file. Neither unit invokes shell tracing or
logs secret values. On failure, inspect unit status, bounded journal output, Compose `ps`, and the
specific container log without dumping environments.

To stop operations without deleting data:

```bash
sudo systemctl disable --now strayhub-backup.timer
sudo systemctl stop strayhub
```

Rollback installs a reviewed previous repo version and its repo-owned unit files, runs daemon-reload,
then starts the unit again. Do not use volume deletion, revoke live IAM, alter DNS, or delete legacy
infrastructure as an operational rollback.

## Phase E5 operational acceptance

Phase E5 repeated a normal `systemctl restart` and exactly one controlled VM reboot. Both preserved
`strayhub-production_postgres_data` and `strayhub-production_minio_data`, Alembic head
`0037_animal_external_sources`, a synthetic MinIO persistence marker, public routing, and the
enabled/active backup timer. The reboot changed boot ID, retained `net.ipv4.ip_forward=1`, and
recovered OS Login/IAP/rose access plus all runtime containers. The marker was removed after proof.

An operator `docker kill` correctly produced a public 502 but, by Docker design, counted as an
explicit operator stop under `unless-stopped`; systemd recovered the runtime. A host-PID SIGKILL
proposal was rejected because PID reuse could target an unrelated process. Automatic crash-policy
re-verification is therefore deferred instead of using an unsafe injection. The earlier E3 crash
evidence remains historical; E5 does not overwrite it.

The release inventory also found only `/opt/strayhub/releases/e702d7d-e3`, with no previous
immutable artifact or revision marker. E5 performed the required documented rollback dry run but no
live release switch. See `docs/deployment/full-acceptance.md` for the evidence and hard gate.

## Deferred boundary

Phase E4 accepted the single-edge live routing and firewall boundary; DNS, existing TLS ownership,
and LINE/LIFF endpoint values remain unchanged. Scheduling alert delivery, centralized logging, exact tiered retention, remote Terraform
state ownership, deployment CI replacement, and Phase F legacy removal also remain deferred.

## SSH administration

The VM keeps project OS Login as its single SSH identity mechanism: `enable-oslogin=TRUE` and
`block-project-ssh-keys=TRUE`. SSH ingress remains restricted to IAP TCP forwarding from
`35.235.240.0/20`; no world-open TCP 22 rule is permitted. The intended Linux user is
`b97502027_gmail_com`.

The approved `rose` public key was added to the operator's OS Login profile on 2026-08-30 and has
fingerprint
`SHA256:1pQPrAV7PeZS7v9Jue457oP9HW9KtADYkAnGsfkaGec`. OS Login profile keys are intentionally
operator-managed outside Terraform so Terraform cannot overwrite unrelated access.
The matching operator-held private key authenticated successfully through IAP before firewall
tightening, after tightening, and after the accepted reboot. No private key is stored in the repo or
uploaded to GCP.
