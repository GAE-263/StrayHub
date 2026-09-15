# CI/CD Phase 5 and 6 acceptance record

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
