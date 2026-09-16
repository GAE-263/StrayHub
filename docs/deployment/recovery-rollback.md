# Phase 7: checkpoint, resume and rollback protection

Status: Phase 7 implementation and exact-predecessor binding merged in PRs #42 and #43. Production
deployment, same-artifact verify-only resume, controlled rollback and roll-forward, and final
independent verification passed on 2026-09-16. Production finishes on `4a476159…`; see the
[live acceptance record](cicd-phase-7-acceptance.md) for exact identities and evidence.
The retained Phase 5 predecessor predates these protections; do not mutate its immutable directory
or invoke its old scripts as though they provide checkpoint/resume and shared-lock support.

## Boundaries

Deploy, rollback and roll-forward share `/var/lib/strayhub/releases/.operation.lock` with
nonblocking `flock`. The lock lasts for the entire host operation and is released on process exit.
GitHub concurrency is still retained; it is not a substitute for this host lock. Operators must
use the new canonical scripts, not older retained scripts that predate the lock. Direct Docker,
systemctl, database or old-script invocations are outside the lock and must not run concurrently.

A normal deployment writes a root-owned 0600 `<release-id>.checkpoint.json` atomically, with fsync,
before each stage. It binds the exact manifest SHA-256 (which includes bundle/image identity),
original previous release, and attempted stage. `active-deployment.json` blocks a different
deployment or rollback until the attempt is reconciled. Checkpoints are acknowledgements and
intent records, not proof of actual database/runtime state; SIGKILL or SSH loss can happen after
an operation took effect but before its acknowledgement.

The exit trap still only reports failure. It never starts services, retries migrations, changes
pointers, writes success receipts, or initiates rollback. Do not delete checkpoint/active markers
to make a failed deployment appear clean. Partial release trees or unknown state require review.

## Read-only inspection

Use the approved root-owned, validated candidate tooling and exact manifest; paths below are
placeholders, not commands to paste without resolving the retained artifact first:

```bash
sudo python3 /PATH/TO/VALIDATED/CANDIDATE/infra/gce/scripts/deployment-state.py status \
  --manifest /PATH/TO/VALIDATED/ARTIFACT/release-manifest.json \
  --state-dir /var/lib/strayhub/releases \
  --current-link /opt/strayhub/current
```

`deployed_without_receipt=true` means current points at the target while its successful receipt
does not match. This is not proof of health. Compare pointer, immutable files, DB revision, live
digests, unit status and public health. `status` creates no files and does not acquire credentials.

## Explicit same-artifact resume

After operator review, retain the original validated artifact/bootstrap and use the candidate's
script through the approved IAP/OS Login path, with the normal production confirmation plus
`--resume`. Never source recovery code from an unvalidated writable upload directory.

```bash
sudo /PATH/TO/VALIDATED/CANDIDATE/infra/gce/scripts/deploy-release.sh \
  --artifact-dir /PATH/TO/VALIDATED/ARTIFACT \
  --deployment-role 'Reviewed production recovery operator' \
  --confirm-production DEPLOY_STRAYHUB_PRODUCTION \
  --resume
```

| Observed state and checkpoint | Allowed behavior |
| --- | --- |
| Original previous pointer; checkpoint strictly before migration starts | Revalidate exact artifact/existing release and prior receipt; repeat secret materialization, pull and preflight before normal deployment. A previously acknowledged stop may repeat. |
| Migration started or head/pointer transition uncertain while still on previous pointer | Refuse. No automatic upgrade replay, downgrade or rollback; investigate actual DB and runtime with a separately reviewed recovery plan. |
| Target pointer; checkpoint at pointer switch or later | Read DB head without upgrading, then verify runtime/public health and complete receipt. No pull, materialization, unit install, restart, or migration upgrade is replayed. If runtime is not healthy, stop for operator review. |
| Target pointer and complete matching receipt | Reverify and reuse the receipt; do not overwrite immutable evidence or redeploy. |
| Missing checkpoint, changed manifest, partial/corrupt release, foreign pointer or another active attempt | Refuse. Legacy pre-Phase-7 releases are not implicitly adopted into this recovery model. |

The original previous-release identity is retained even when current already points at the target.
An existing receipt must match SHA, images, migration revision and original previous release.
Receipt creation uses create-only atomic publication, not overwrite. A matching temporary receipt
symlink can be completed after interruption; a conflicting path is refused. The active marker is
cleared only after the successful receipt/current pointer are verified and checkpoint is complete.

There is deliberately no new GitHub `resume` operation in this change. A failed deploy must not be
retried with GitHub's rerun button or fresh `deploy` dispatch as a substitute for reviewed host
recovery. Existing WIF, staging evidence gates and normal publication/deploy workflow are unchanged.

## Rollback and roll-forward

Existing explicit confirmations and canonical scripts remain required. Both tools now:

- Hold the shared host lock and refuse an unresolved deployment marker.
- Validate current and target immutable files plus both successful receipts, including exact
  SHA/image/migration identity. An arbitrary retained directory is not a known-good rollback target.
- Retain recorded previous-release binding and the existing rollback compatibility declaration.
- Refuse differing migration revisions, even with a compatibility declaration. Read back exactly
  one expected live DB head before touching runtime; no downgrade or upgrade is run.
- Require secrets/migration dependency units already active before restart, to avoid implicitly
  starting their mutation commands through systemd dependencies.
- Pull original digests and pass target preflight before stopping current runtime. Existing
  explicit rollback/roll-forward failure restoration behavior remains separate from deploy resume.

This is intentionally stricter than the earlier rollback implementation. An `unknown` or
`forward-only` compatibility declaration still blocks rollback even when migrations happen to
match. Never edit a published manifest to change that declaration. A future schema-changing
rollback requires a separately designed and reviewed compatibility procedure.

### Reviewed exact predecessor declaration

An optional `infra/gce/release-compatibility.json` is versioned review input, not a manual workflow override.
Its `unchanged-runtime` mode binds the previous full SHA, release ID, manifest SHA-256 and migration
revision. Before declaring backward compatibility, the builder compares tracked Git blob identities
between that predecessor and HEAD. Only docs, tests and an explicit deployment-tooling file list
may differ. Application, migrations, dependencies, Compose, secret maps, image Dockerfiles and any
other non-allowlisted file must be unchanged. Missing Git history or runtime drift fails closed.
Remove or renew the declaration through a reviewed PR for later application changes.

The builder embeds `rollback_predecessor` into a NEW immutable manifest before checksums and OCI
publication. Existing artifacts remain unchanged; `--reuse-only` does not change their metadata.
Normal deployment validates the actual current manifest against this binding before any runtime
change. Rollback and roll-forward validate the same exact pair, in addition to receipts, live DB
head, preflight and the existing compatibility flag. A matching migration revision alone does not
grant compatibility. The older predecessor's own `unknown` flag does not prevent returning from
the newly reviewed compatible successor; it still prevents an unrelated further rollback.

The Phase 7 review permitted only the accepted `7bb29ea…` predecessor and tooling-only successors.
It does not authorize other pairs or relax tenant/authentication behavior. The first Phase 7
artifact (`f70f9b5…`) remains `unknown` and will not be used for the live rollback drill.

Phase 8 removes that single-pair declaration from new source because CI/workflow changes fall outside
its reviewed allowlist. Without a new reviewed declaration, future artifacts default to `unknown`.
Published Phase 7 artifacts retain their original binding and remain usable for the accepted pair;
removing the source declaration never edits their manifest or receipt.

## Acceptance and remaining live work

Local tests execute deployment shell with a temporary-only toolchain and injected failures, and
exercise real durable-state/receipt code. Coverage includes before/after pointer replacement,
migration ambiguity, receipt write/link interruptions, repeat resume, identity drift, multiple DB
heads, secret-free diagnostics, and shared-lock placement. No production outage is induced.

The first live Phase 7 acceptance completed those gates with a fresh verified GCS backup and the
explicitly reviewed `7bb29ea…` / `4a476159…` pair. Its resume drill proved completed-release
verification without changing container start times, unit execution timestamps or the original
receipt. No production crash, uncertain migration or data restore was induced. Existing isolated
failure tests cover those conservative refusal/recovery branches; the live drill does not claim
to exercise them in production. Future deployments still require their own CI, exact-artifact
staging, authorization and compatible-pair review.
