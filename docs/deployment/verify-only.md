# Phase 6: independent production verification

Implementation is local until reviewed, merged and activated on `release`. No production
verification or deployment has been dispatched as part of this implementation.

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

Run the verify-only, SSH transport, release contract and staging attestation tests plus actionlint.
After separately authorized merge and exact-SHA release activation, dispatch verify against the
existing production release before promoting a new release. Record the run URL, target identities
and all three outcomes. Until that live run passes, Phase 6 cloud acceptance remains pending.
