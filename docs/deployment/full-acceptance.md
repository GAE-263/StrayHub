# Full GCE Deployment Acceptance

Status: Phase E5 authenticated acceptance **READY**
Acceptance date: 2026-08-30
Canonical hostname: `strayhub.enadv.quest`
Repository checkpoint at start: `71dbc14`
Active runtime path: `/opt/strayhub/releases/e702d7d-e3`
Migration: **NONE**

Phase E5 validated the accepted single-edge deployment without redesigning it. The existing nginx
VM at `34.10.249.63` remains the sole public DNS/TLS edge and proxies only to Web TCP 3000 and API
TCP 8080 on `strayhub-gce` (`34.81.77.204`). E5 changed no DNS, certificate, LINE/LIFF URL,
application or tenant behavior, database schema, managed-service IAM, Terraform state, CI, or legacy
infrastructure.

## Acceptance matrix

| Domain | Result | Evidence and boundary |
| --- | --- | --- |
| PUBLIC_EDGE | PASS | Trusted Let's Encrypt TLS; Web/API/volunteer/LINE routes passed before and after restart/reboot |
| WEB | PASS | Root, login, volunteer, animal-confirmation, care-report, and production static asset returned 200; no HMR marker |
| API | PASS | Normal password login issued a deployed session/JWT; authenticated Tenant A animal access and care-report APIs passed |
| AUTH | PASS | Missing auth returned 401; the guarded synthetic volunteer used normal Argon2 verification, session creation, and server-side JWT issuance |
| TENANT_ISOLATION | PASS | Tenant A positive access passed; the same volunteer's Tenant B context switch returned 404 and no Tenant B animal leaked |
| VOLUNTEER_FLOW | PASS | Tenant A grant, QR-first resolution, animal confirmation, and care-report submission passed; Tenant B QR candidate access returned 403 |
| LINE_WEBHOOK | PASS | GET 405, invalid signature 401, and an empty valid HMAC-signed event set 200 without exporting the secret |
| LIFF | PASS | Canonical HTTPS volunteer route passed; real-device LINE embedded-browser verification remains deferred |
| DATABASE | PASS | Healthy PostgreSQL, head `0037_animal_external_sources`, role split, and named-volume persistence |
| RLS | PASS | 37 RLS-enabled tables, 40 policies, runtime role non-superuser/non-BYPASSRLS, focused cross-tenant tests passed |
| MINIO | PASS | Private synthetic object write/read, backup, restart/reboot persistence, exact cleanup, and no public port |
| WORKER | PASS | Running after restart/reboot with no crash markers or privilege change |
| SECRET_MANAGER | PASS | All 11 exact secrets fetched to discarded stdout via VM metadata ADC; current target 0700 and files 0600; no values logged |
| KMS | PASS | Live synthetic encrypt/decrypt exact round trip and malformed-ciphertext fail-closed through the configured CryptoKey |
| BACKUP | PASS | `20260830T125231Z-e3daily8453`: PostgreSQL, nested MinIO object, manifest, checksum, GCS upload, and `_COMPLETE` |
| RESTORE | PASS | Fresh GCS download restored isolated PostgreSQL head/RLS/role and one MinIO object with exact inventory SHA |
| SYSTEMD | PASS | Secret, migration, runtime, and backup timer units active; no failed units |
| RESTART | PASS | Controlled `systemctl restart` recovered all services and preserved DB/MinIO volumes |
| FAILURE_RECOVERY | DEFERRED | Operator container kill produced 502 and systemd recovery passed; unsafe host-PID SIGKILL was rejected, so automatic crash-policy recovery was not repeated |
| REBOOT | PASS | Exactly one reboot changed boot ID and recovered IAP, forwarding, units, containers, public routes, volumes, and timer |
| SSH | PASS | OS Login, IAP-only ingress, rose login, password auth disabled, no public TCP 22 |
| FIREWALL | PASS | Edge reached 3000/8080; unrelated source could not reach 80/443/3000/8080/5432/9000/9001 |
| ROLLBACK | PASS | Evidence-backed dry run only: no previous release artifact exists, so the schema-compatibility hard gate correctly prevented a live switch |

## Public, runtime, and security evidence

- Public `/`, `/healthz`, `/volunteer-application`, and the public organizations API returned 200;
  LINE webhook GET returned the expected 405. The public certificate subject is
  `strayhub.enadv.quest`, issued by Let's Encrypt, and was not replaced.
- Web/API upstreams remained reachable only from `34.10.249.63/32`. IAP SSH remained
  `35.235.240.0/20` to TCP 22. New-GCE public 80, 443, 3000, 8080, 5432, 9000, and 9001 were blocked.
- The VM service account has exact-secret accessor on the 11 declared secrets, key-scoped KMS
  Encrypter/Decrypter, and bucket-scoped GCS Object Creator/Viewer. It has no user-managed key.
  The backup bucket remains uniform-access, public-access-prevention enforced, with the accepted
  unlocked 604800-second retention and 35-day age lifecycle.
- Secret/current target permissions resolved to 0700 and `runtime.env` to 0600. Journals, API,
  Worker, and edge logs had zero secret-pattern hits; API/Worker logs had zero plaintext-PII-pattern
  hits and no recurring crash loop.
- After reboot, memory available was 3.0 GiB of 3.8 GiB, root disk use was 32% of 29 GiB, swap use
  was zero, and no container showed runaway memory or CPU.

The initial authenticated-resume inventory found an empty live database and correctly blocked
direct inserts or an authentication bypass. E5b subsequently added the reviewed server-side
`scripts/bootstrap_acceptance.py` operator command described in
`docs/deployment/acceptance-bootstrap.md`. It requires an allowed demo/acceptance environment,
explicit allow flag, explicit confirmation, and a protected runtime password source before opening
a database connection. Fixture creation uses canonical services, repositories, Argon2 hashing,
tenant context, domain validation, audit records, and one transaction through the existing
migration credential. API and Worker runtime privileges remain unchanged.

The dry run rolled back successfully. The first live run created exactly the deterministic Tenant
A/B fixture set; the identical second run reported every fixture `reused` with the same UUIDs and no
duplicates. No real PII, plaintext password, password hash, JWT, raw QR token, or signing key was
printed or committed. The protected 0600 password file remains outside the release tree under
operator ownership.

The guarded live verifier then used the public hostname and normal `/v1/auth/login` path. Missing
auth returned 401, valid synthetic volunteer login passed, Tenant A context and authenticated animal
access passed, and a Tenant B context switch returned 404. QR-first resolution and confirmation for
Animal A passed; care report `1b3d5c88-3430-46dc-a2b5-8c29b57b04e8` was stored in Tenant A with
synthetic content. The same volunteer's Tenant B QR candidate request returned 403. Live metadata
remained 37 RLS-enabled tables; runtime role `strayhub_app` remained non-superuser and
non-BYPASSRLS.

## Backup and restore findings

The first non-empty E5 backup exposed that the MinIO mirror container wrote root-owned nested files
to a host bind mount. The host-side `strayhub` process then correctly failed rather than silently
publishing an incomplete backup. `backup-minio.sh` now runs the mirror with the caller UID:GID and a
writable temporary mc configuration directory. The same ownership issue was found in the isolated
restore verification cleanup and fixed in `restore-minio.sh`. Focused contracts cover both rules.

After the fixes, backup `20260830T125231Z-e3daily8453` uploaded the PostgreSQL dump, one nested
synthetic MinIO object, metadata, manifest, and `_COMPLETE` to the private bucket. A fresh protected
download restored PostgreSQL into `strayhub_b3_restore_e5_125231` at the current Alembic head with
RLS/runtime-role checks, and restored MinIO into `strayhub-b3-restore-e5-125231` with object count 1
and exact inventory SHA-256. The disposable DB, bucket, restore staging, incomplete local backup,
and failed verification temporary directory were removed after evidence capture. The successful
local/GCS backup remains governed by existing retention.

One verification command initially used `gcloud --out-file=/dev/null`; gcloud preserved the 1:3
character device but changed its mode to 0600. E5 immediately restored standard mode 0666 and
confirmed the runtime remained active. Subsequent exact-secret checks used ordinary stdout
redirection and all passed without printing values.

## Restart, failure, and reboot

`systemctl restart strayhub` recovered Web, API, Worker, PostgreSQL, and MinIO; the two named volumes,
Alembic head, public routes, and synthetic MinIO marker persisted. An operator `docker kill` produced
the expected public 502, but Docker treats that command as an explicit operator stop under
`unless-stopped`; systemd restored the service and PostgreSQL/MinIO remained healthy. A proposed
host-PID SIGKILL was rejected because PID reuse could target an unrelated host process. E5 records
automatic crash-policy re-verification as deferred instead of bypassing that safety decision.

Exactly one controlled VM reboot changed boot ID from
`20f62fc0-b0b6-46c4-bda0-bdf91674e04d` to
`1ebb98d0-ad45-4737-bc31-9152bc0e1c8b`. Public health transitioned through 502/connection failure
and recovered to 200. OS Login/IAP/rose, `net.ipv4.ip_forward=1`, all systemd units and containers,
the enabled/active backup timer, named volumes, Alembic head, and the MinIO marker recovered. The
marker was then removed exactly and verified absent.

## Rollback dry run

The active pointer resolves to `/opt/strayhub/releases/e702d7d-e3`, but that directory is the only
entry under `/opt/strayhub/releases/` and contains no Git revision marker. E4 and the two E5 script
fixes were installed into that active directory. The edge has one active config
`/etc/nginx/sites-enabled/rr.conf`, whose SHA-256 matches the repository source, but no previous
edge-config copy. Consequently there is no immediately previous artifact whose completeness and
schema compatibility can be proven. E5 correctly did **not** switch the release pointer or nginx
config and did not perform a fake roll-forward.

A future live rollback may proceed only after deployment creates immutable release directories with
an explicit revision marker and retains a reviewed prior edge config. The deterministic sequence is:

1. Verify the previous directory and revision marker, image availability, production config, and
   migration head compatibility with the current database.
2. Preserve the current pointer, secret generation, nginx config, and named-volume identifiers.
3. Stop only `strayhub.service`, atomically switch `/opt/strayhub/current` to the verified previous
   release, and start/health-check locally and publicly. Never restore or downgrade the database and
   never use `docker compose down -v`.
4. Atomically switch back to the recorded current release, restart, and require all local/public,
   volume, timer, and migration-head checks to pass.

Until those artifacts exist, rollback status is `DOCUMENTED/DRY-RUN PASS`; live rollback is unsafe.

## Verification summary

- GCE deployment/managed-service contracts: 82 passed on the authenticated-resume run.
- Updated backup/GCS focused contracts: 15 passed; updated restore contract: 7 passed.
- Final E5b auth/tenant/RLS/volunteer/QR/care-report/bootstrap suite: 67 passed on a clean migrated
  local database.
- Critical Playwright: confirmation run 20 passed; initial run had two context-switch timing failures.
- Terraform fmt/validate/plan and repository quality/security results are recorded in `review.md`.
- The reviewed local E5 commits were authorized; no push was performed. Phase F was not started.

## Remaining deferred

- Real-device LINE/LIFF embedded-browser acceptance.
- A safe, repeatable non-operator API crash harness.
- Immutable versioned release packaging, previous edge-config retention, and a genuine
  schema-compatible rollback/roll-forward artifact pair.
- Remote Terraform state and retained-resource ownership, replacement deployment CI, centralized
  logs/alerts, exact tiered backup retention, and all Phase F legacy cleanup.

Phase F remains **NOT STARTED**. Perform the E5 final review and safe local commit before separately
authorizing any Phase F work.
