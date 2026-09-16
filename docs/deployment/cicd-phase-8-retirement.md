# Phase 8: retire duplicate workflow entry points

Implementation checkpoint: [PR #44](https://github.com/GAE-263/StrayHub/pull/44).
Remote activation/publication acceptance is pending at this source checkpoint; the PR timeline
records the subsequent exact merge SHA, CI/staging/publication runs and final activation result.
Production remains the Phase 7 accepted `4a476159…` release. This change performs no deployment,
registry deletion, branch deletion, environment deletion, LINE operation or IAM/WIF mutation.

## Decision and trigger contract

Retain `release` as an exact-main-artifact selector and the existing production WIF/LINE ref.
Removing that ref would require a separate trust and LINE transition. It must advance by reviewed
fast-forward to an already tested main SHA, never a release-only merge commit or rebuild.

| Trigger | Work permitted |
| --- | --- |
| PR | One full CI suite, no cloud credentials or formal image publication |
| main push | Full CI plus immutable build/reuse and hosted staging |
| release push | None after this workflow version is activated |
| Manual publish from release | Exact main CI readback, immutable OCI reuse, publication receipt |
| Manual deploy from release | Exact main CI + publication + staging evidence; then existing deploy |
| Manual verify | Existing target-bound read-only verification; no CI/build/publication/deploy |
| Resume / rollback | Existing explicitly reviewed host tools and compatibility checks |
| LINE manual operations | Unchanged separate workflows, confirmations and release/WIF gates |

`ci.yml` no longer exposes `workflow_call`; `gce-release.yml` no longer has a push trigger or a
reusable full-quality job. No required check is removed: `python`, `Frontend Quality`, `Contracts`,
`Critical E2E`, and `GCE Release Static Contracts` remain the five main ruleset checks.
The obsolete manual `schema_compatibility` input is removed: reuse-only publication cannot change
compatibility already bound into an immutable manifest. Existing CLI builders/recovery tools remain.

`scripts.main_ci_gate` reads only GitHub Actions metadata. It requires the newest main **push** CI
run for the exact SHA, correct repository/workflow, completed success, and all five jobs succeeding
in that exact run attempt. Missing/queued/failed/skipped, wrong SHA/ref/workflow, partial job sets and
attempt changes fail closed. It does not fall back to older success. Checks occur in manual
authorization and again before each publisher/deployer authentication. Existing actor, confirmation,
freshness, first-attempt, exact publication/staging identity and transport controls remain intact.

## Read-only inventory (2026-09-16)

- GitHub lists exactly five active workflows, matching the five versioned workflow files: CI,
  Build Immutable Release, GCE Immutable Release and the two manual LINE workflows. No orphan
  registered workflow was found in that inventory.
- Both environments are used: `release-publication` by build/staging/publication and `production`
  by deploy/verify/LINE. They have no independent reviewer protection; manual operator gates remain
  the existing approval model. Do not delete them or claim that they enforce independent approval.
- Ruleset `23427159` is active on main, with the five matching check names, no bypass actors and
  required PRs. No stale required check was found; no ruleset change is needed.
- `codex/release-backup-20260915-f07c643` preserves explicitly retained historical release history.
  Feature/review branches and open PR #29 are not automatically disposable and are not deleted or
  closed. Old source history can still contain old workflow definitions; current ref/actor/WIF gates
  remain essential. This is not a claim that historical Git objects have been erased.
- Published OCI artifacts, deployed/previous release directories, receipts and GCS backups are
  recovery evidence, not disposable orphans. GitHub downloads have 30-day retention; OCI is canonical.
  No artifact storage is swept, and this inventory is not a complete registry retention audit.

The Phase 7 one-pair compatibility declaration is removed from **new source** because the Phase 8
workflow changes are outside its reviewed runtime-tree allowlist. New artifacts revert to `unknown`
unless separately reviewed; the existing accepted rollback pair and immutable evidence stay intact.

## Activation and acceptance

1. Review and merge this change only after all five PR checks pass. Include the pending Phase 7
   acceptance documentation without changing its recorded artifact identities.
2. Require merged main CI and hosted staging PASS. Confirm build reuse remains digest-stable.
3. With explicit git/publication authorization, fast-forward release to that exact main SHA and
   read back refs. Confirm no new release-push run is created; do not trigger production deployment.
4. A separately authorized manual publication can prove the readback gate replaces duplicate CI;
   verify there are no full-suite jobs and no image rebuilds. Production activation is not needed
   for repository workflow retirement and must not be inferred from this cleanup.

Local acceptance includes negative gate tests, workflow wiring tests, immutable builder reuse and
default-unknown tests, and read-only gate validation against successful main CI run `35039483033`.
Complete local suite: **2,782 passed, two data-dependent skips**, with access to the existing
dedicated test PostgreSQL and backend-disabled Terraform provider initialization. The initial
sandboxed run could not open local database sockets or resolve the Terraform registry; those were
environmental failures, not waived tests. Two offline authorization fixtures were updated to supply
the new CI metadata. The subsequently expanded gate suite passed all 23 tests (including two added
after full-suite collection). Ruff, format, actionlint and diff checks passed. No application/API
or tenant authorization implementation changed.
At this source checkpoint, remote merge/activation and publication acceptance remain pending;
do not report Phase 8 fully live until the PR timeline records those run identities and evidence.

Stop if required checks drift, main CI evidence is absent, freshness fails, an existing PR overlaps,
or remote refs diverge. Do not restore functionality by bypassing gates. Reversal is a reviewed
workflow change on main; never force-reset release or mutate a published manifest. No production
data or current pointer changes are needed to reverse this repository-only phase.
