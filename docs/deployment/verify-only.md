# Phase 6: independent production verification

Status at the 2026-09-15 acceptance checkpoint: PR #40 is merged, the workflow is active on
`release`, and independent production verification passed. No production deployment was performed.
See the [acceptance record](cicd-phase-5-6-acceptance.md) for exact targets, runs and branch backup.

## Manual operation

Run `GCE Immutable Release` (`gce-release.yml`) from the protected `release` branch:

- `operation`: `verify`
- `git_sha`: full lowercase SHA of the expected **currently deployed** release
- `confirmation`: `VERIFY PRODUCTION <full-SHA> <release-ID>`

The release ID has the form `YYYYMMDDTHHMMSSZ-<first-12-SHA-characters>`. Obtain both
identities from the last successful deployment record, not from the newest main commit.
The deployed SHA need not equal workflow/release HEAD. Other publication/deployment inputs
are unused; leave them empty/default. The existing confirmation field carries the release
ID to remain within the workflow's ten dispatch inputs.

Verification executes trusted workflow-revision code checked out at `github.sha`, never the
caller-supplied target SHA. Target validation and the existing actor/triggering-actor/first-attempt
gate run before WIF credentials. Existing production WIF and IAP routes are unchanged. Use a
fresh dispatch to retry; GitHub rerun attempts remain disallowed by the existing policy.

## Scope and results

The same job performs standalone and post-deployment verification. In deploy mode it additionally
binds the target to that run's deployment outputs and reports a superseded release branch.
Standalone verify skips the full CI/build gate, publication and deployment jobs; explicit job-level
status handling lets verification run even though its deployment dependency was skipped.

The remote read-only verifier checks the current release pointer, validates release files and
manifest SHA, requires a matching successful receipt, and compares running API/Web/Worker images
against immutable image references. It checks container health and local endpoints. It does not
rewrite the deployment receipt. Public root and `/healthz` probes run separately after the SSH
probe succeeds, even if remote runtime verification fails.

The job summary distinguishes:

- SSH probe outcome (only public-key propagation failures receive bounded probe retries).
- `PASS`, `SSH_TRANSPORT_FAILURE` (255), `REMOTE_VERIFICATION_FAILURE` (mapped remote exit 40),
  or `TRANSPORT_OR_EXECUTION_FAILURE` (other gcloud failures).
- Independent public HTTP health outcome.

`REMOTE_VERIFICATION_FAILURE` is not proof of application illness: it also includes receipt,
identity, missing script and sudo failures. Inspect the failed remote step for the specific cause.
Skipped checks are not passes. Remote verification itself is not retried. The job is bounded
to 15 minutes and retains the existing per-branch serialization with deployments.

No build, publish, migration, restart, secret materialization or redeploy is invoked. WIF still
uses the existing deployer identity (not a newly least-privileged verifier); gcloud can register
an ephemeral OS Login SSH key. Read-only refers to application/deployment state, not zero cloud
authentication side effects. No authenticated synthetic production writes are performed.

## Acceptance and activation

Local verification passed 128 relevant tests plus Ruff, actionlint and `git diff --check`.
PR CI, main CI and release-push CI passed. Following explicit merge and branch-transition
authorization, [run 34986498828](https://github.com/GAE-263/StrayHub/actions/runs/34986498828)
passed target validation, WIF, SSH transport, exact receipt/runtime and public health checks.
The full quality gate, publication, deployment and write-authorization jobs were skipped.

The workflow SHA was `2e121a644ff79f290d2d390b6ea4bb49442c947c`; the deployed target was
`f07c643d63f92a2cf7fdc19078c4ea5418aac539`, release `20260915T055145Z-f07c643d63f9`.
This demonstrates independent verification of an older deployed SHA without deploying workflow
HEAD. Phase 6 cloud acceptance is complete. Failure classification was tested locally with
simulated failures; no SSH outage or unhealthy state was deliberately induced in production.
