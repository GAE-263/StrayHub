# Phase 7: checkpoint, resume and rollback protection

Status: base Phase 7 implementation merged in PR #42. Production activation and a controlled
recovery/rollback drill have been authorized, but are not yet performed. The follow-up compatibility
binding must pass review, CI and hosted staging before proceeding.
The currently deployed Phase 5 artifact predates these protections; do not mutate its immutable
directory or claim that its old scripts now provide checkpoint/resume support.

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

`infra/gce/release-compatibility.json` is versioned review input, not a manual workflow override.
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

This review permits only the current accepted `7bb29ea…` predecessor and tooling-only successors.
It does not authorize other pairs or relax tenant/authentication behavior. The first Phase 7
artifact (`f70f9b5…`) remains `unknown` and will not be used for the live rollback drill.

## Acceptance and remaining live work

Local tests execute deployment shell with a temporary-only toolchain and injected failures, and
exercise real durable-state/receipt code. Coverage includes before/after pointer replacement,
migration ambiguity, receipt write/link interruptions, repeat resume, identity drift, multiple DB
heads, secret-free diagnostics, and shared-lock placement. No production outage is induced.

Before declaring live Phase 7 acceptance, merge through CI, build and stage an exact artifact
containing these tools, then separately authorize deployment and a controlled recovery/rollback
drill with a fresh backup and an explicitly compatible known-good release pair. Existing Phase 5
production success and older F5b drills do not replace this acceptance.
