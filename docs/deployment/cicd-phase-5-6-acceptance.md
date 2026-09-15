# CI/CD Phase 5 and 6 acceptance record

Latest outcome: **Phase 5 first production promotion PASS**, completed 2026-09-15 16:17 UTC
(2026-09-16 00:17 Asia/Taipei). See the final section below. The earlier checkpoint and failed
attempt are retained as history; their pending status is superseded by that successful run.

Checkpoint: 2026-09-15 (run timestamps in UTC). This is a historical acceptance record, not a
claim that these SHAs remain branch HEAD forever or that an artifact remains available forever.
Revalidate current branch heads and artifact expiry before any future operation.

## Outcome and boundaries

- Phase 5 hosted Docker staging: PASS; production evidence gate activated on `release`.
- Phase 5 first end-to-end production promotion: **PENDING**, not dispatched.
- Phase 6 independent production verify-only: **PASS** against the existing deployed release.
- No new GCP VM, IAM/WIF change, production migration, restart or redeployment was performed
  during this Phase 6 activation. Hosted staging runs use disposable Docker infrastructure.
- Phase 7 recovery/checkpoint/resume and current-release rollback acceptance, and Phase 8 legacy
  workflow/branch cleanup remain future work. Historical rollback tools/drills are not Phase 7 sign-off.

## Traceable evidence

| Evidence | Result | Run or review |
| --- | --- | --- |
| Phase 5 implementation | Merged | [PR #39](https://github.com/GAE-263/StrayHub/pull/39) |
| First hosted staging acceptance | PASS at `5c0c9e56ab2af9aba4eea42e96ee3e5c186bbc41` | [34982184945](https://github.com/GAE-263/StrayHub/actions/runs/34982184945) |
| Phase 6 implementation | Merged | [PR #40](https://github.com/GAE-263/StrayHub/pull/40) |
| Phase 6 PR CI | All five checks PASS at `a706897f6dacd95aff56c04cd3956653efaecc9f` | [34984660387](https://github.com/GAE-263/StrayHub/actions/runs/34984660387) |
| Main CI | All five checks PASS at target SHA below | [34985706934](https://github.com/GAE-263/StrayHub/actions/runs/34985706934) |
| Build + Hosted Docker Staging | Both jobs PASS at target SHA below | [34985707262](https://github.com/GAE-263/StrayHub/actions/runs/34985707262) |
| Release push CI | PASS; deployment skipped | [34986467196](https://github.com/GAE-263/StrayHub/actions/runs/34986467196) |
| Independent production verification | PASS; publication/deployment skipped | [34986498828](https://github.com/GAE-263/StrayHub/actions/runs/34986498828) |

The target workflow/main/release SHA for activation was:

```text
2e121a644ff79f290d2d390b6ea4bb49442c947c
```

The five CI checks were Python, Frontend Quality, Contracts, Critical E2E and GCE Release Static
Contracts. Local Phase 6 validation passed 128 relevant tests, Ruff, actionlint and diff checks.

## Hosted attestation identity

For target SHA `2e121a644ff79f290d2d390b6ea4bb49442c947c`:

- Staging run: `34985707262`, attempt `1`.
- Artifact name: `strayhub-staging-2e121a644ff79f290d2d390b6ea4bb49442c947c-attempt-1`.
- Artifact ID: `10402979794`.
- Artifact archive SHA-256: `ca82ac7df74b20a8f7140954a6705c95e8bccbcd8df7631f7c80919b52fa9239`.
- Promotion input identity: `10402979794:ca82ac7df74b20a8f7140954a6705c95e8bccbcd8df7631f7c80919b52fa9239`.

This ZIP checksum is not the OCI artifact digest, bundle checksum or any application image digest.
The successful hosted run creates its attestation only after exact-artifact Docker acceptance.
For a future promotion, obtain and validate the matching canonical publication, bundle checksum
and all three image digests using the production gate; do not substitute an older run's evidence.
GitHub artifacts have 30-day retention. This document is not executable approval or a replacement
for live run/artifact metadata checks. Expired evidence requires fresh eligible hosted acceptance.

The earlier Phase 5 run at `5c0c9e5…` also passed the production evidence verifier locally against
its matching downloaded build artifact. That was not a release-branch publication/deployment run
and does not establish end-to-end production promotion acceptance for either SHA.

## Authorized release-history transition

Before activation, main and release were diverged (33 main-only and seven release-only commits).
All seven release-only commits were historical merge commits; a fast-forward was not possible.
The earlier fast-forward assumption was corrected before any branch update.

With explicit user authorization, the following transition was completed only after target main
CI and hosted staging passed:

1. Preserve old release SHA `f07c643d63f92a2cf7fdc19078c4ea5418aac539` in branch
   `codex/release-backup-20260915-f07c643` and verify its remote ref.
2. Update `release` to `2e121a644ff79f290d2d390b6ea4bb49442c947c` with an explicit lease expecting
   exactly `f07c643d63f92a2cf7fdc19078c4ea5418aac539` as the old remote SHA.
3. Read back both refs; the backup retained the old SHA and release selected the tested SHA.

The backup preserves the old history; it is not an automatic deployment rollback. Restoring the
old branch would restore older workflow code and remove the new gate, so it requires separate
review and authorization. Do not delete the backup or force-update future release heads on the
strength of this one-time authorization. Prefer reviewed exact-SHA fast-forwards thereafter.

## Phase 6 live operation and observations

Run `34986498828` was manually dispatched from `release` with:

```text
operation: verify
git_sha: f07c643d63f92a2cf7fdc19078c4ea5418aac539
confirmation: VERIFY PRODUCTION f07c643d63f92a2cf7fdc19078c4ea5418aac539 20260915T055145Z-f07c643d63f9
```

The workflow revision was `2e121a6…`, deliberately different from the existing deployed target.
It waited for release-push CI under the existing concurrency group. Target validation passed
before WIF. WIF authentication, IAP SSH probe, remote receipt/runtime and public health all passed.
The run skipped the full quality gate, write authorization, publication and deployment jobs.

The remote verifier reported:

```text
[GCE release verification] PASS: 20260915T055145Z-f07c643d63f9 at f07c643d63f92a2cf7fdc19078c4ea5418aac539
```

Runtime verification checks current manifest/receipt identity and actual API/Web/Worker image
references against the deployed release, container health, and local endpoints. Public `/` and
`/healthz` checks passed separately. The application remained on the old release; no new candidate
was promoted. Failure classification was tested with local mocks, not induced production outages.
This verification does not replace authenticated tenant acceptance or a current-release rollback
drill. SSH authentication can register an OS Login key; read-only refers to application/deployment
state, not absence of authentication side effects.

## Remaining acceptance

### First promotion attempt: publication stopped safely

After this checkpoint, the operator authorized the first production promotion of `2e121a6…`.
[Publication run 34988017355](https://github.com/GAE-263/StrayHub/actions/runs/34988017355)
passed all CI checks but failed canonical registry lookup before creating a publication receipt.
It refused to rebuild. No deploy run was dispatched, and production remained on `f07c643…`.

Read-only checks confirmed the VM is in `us-central1-c`, while the retained Docker repository is
in `asia-east1`; the differing resource locations are intentional existing configuration, not
evidence of this failure's cause. The exact OCI artifact exists with digest
`sha256:fd25f1bc7f33bc6a01f7f35c02f06da41e2ff6f810b6b287aa48ebbc85b7a13f`.
Local artifact validation and hosted-evidence verification passed against the downloaded artifact.
The original script suppressed gcloud stderr, so the underlying runner failure remained unknown.
The diagnostic follow-up emits only fixed error categories and exit status, never raw credential
errors. Any new source SHA must pass fresh CI/hosted staging before publication is retried.

### Completion criteria

Before Phase 5 is fully closed, separately authorize and execute a promotion of a currently
eligible exact artifact. Record successful staging evidence validation before deployer WIF,
publication identity, bundle checksum, all three staging/production image digests, resulting
receipt and post-deployment verification. Do not treat branch alignment or the old-release
verify-only success as proof that this deployment has occurred.

## First production promotion completed

[PR #41](https://github.com/GAE-263/StrayHub/pull/41) added safe registry diagnostics and the
earlier acceptance documentation. Its [CI](https://github.com/GAE-263/StrayHub/actions/runs/34989538911)
passed before merge. The merge SHA was `7bb29ea60aeee435b0f05744af969a2ce0542882`.
[Main CI](https://github.com/GAE-263/StrayHub/actions/runs/34990288181) and
[build/hosted staging](https://github.com/GAE-263/StrayHub/actions/runs/34990288178) passed before
release was normally fast-forwarded from `2e121a6…` to this SHA. No additional force update or
IAM/WIF change was required. [Release push CI](https://github.com/GAE-263/StrayHub/actions/runs/34990958333)
also passed.

The previous registry error did not recur. Diagnostics improve future observability but do not
establish the original failure's root cause. No region change or access-policy expansion was made.

| Identity | Accepted value |
| --- | --- |
| Release ID | `20260915T154252Z-7bb29ea60aee` |
| Git SHA | `7bb29ea60aeee435b0f05744af969a2ce0542882` |
| Staging run / attempt | `34990288178` / `1` |
| Staging artifact ID | `10404843625` |
| Staging archive SHA-256 | `68845685854bce71ed210ee9ee6d79b686a65c62946d71af9418ec8e2f024910` |
| Publication run | [34990957571](https://github.com/GAE-263/StrayHub/actions/runs/34990957571) |
| Publication artifact ID | `10405079642` |
| Publication archive SHA-256 | `0d530a7840ea32fc184067c36f4be97a28db773915e91c4adf956970377a8d21` |
| OCI release digest | `sha256:3d8aedecbc117d05067145aa3add1647653541501501dba2aac408bf1db8b51c` |
| Bundle SHA-256 | `da05c899f890df18e45a3ab58f533379fd91b6a236e6f360672ddcdae53e7305` |
| Manifest SHA-256 | `6e7584eebfb08c579f8c944423539684e3144d3c44eeda5ef7877058e07080ff` |
| API image digest | `sha256:f7dfc76f063e183b6a9e771d4eb02e025a565838f451c01a2dc404b5d7785475` |
| Web image digest | `sha256:50356ac34219d538567f6622250590b16f5986a01776559ebb588bd587509e53` |
| Worker image digest | `sha256:c120e4c8887a58160e671f68d73a35bc1ccc905534f734312e32b6931672528e` |

Local validation of the downloaded publication receipt/artifact and hosted evidence passed before
dispatching [deploy run 34992481583](https://github.com/GAE-263/StrayHub/actions/runs/34992481583).
That run's hosted-evidence gate passed at 16:03:20 UTC before its deployer auth step completed at
16:03:21 UTC. It reused the published artifact; publication and full CI jobs were skipped in the
deploy run. No application image was built during publication or deployment.

Production preflight passed, the normal migration/head checks executed, the current pointer was
switched, and the new systemd runtime passed. Both old and new manifests target
`0056_line_webhook_auth_scope`; no downgrade was performed. Unlike Phase 6 verify-only, this
authorized operation did stop/start the application and materialize a new secret generation.

The deployment reported PASS with previous release `20260915T055145Z-f07c643d63f9`. The separate
verification job passed exact receipt/runtime at 16:17:29 UTC and public root/health checks at
16:17:30 UTC. The old release directory and branch backup remain recovery evidence, not blanket
authorization for rollback. Phase 7 recovery/resume and current-pair rollback acceptance, plus
Phase 8 cleanup, remain pending.
