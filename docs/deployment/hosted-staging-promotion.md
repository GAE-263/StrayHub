# Phase 5: hosted Docker staging and production promotion

Implementation is ready for review. Hosted execution and production promotion still need live
acceptance after this change reaches the protected branches. No new GCP VM is required.

## Step 1: hosted staging evidence

`build-release.yml` retains its main-only publisher and adds the dependent `Hosted Docker Staging`
job on `ubuntu-24.04`. The publisher passes the exact OCI release reference to the job. Staging
pulls it and runs `scripts.local_staging` with the existing canonical Compose, isolated internal
network, synthetic credentials, migration readback, runtime checks, authenticated API/QR/report
flows, tenant denial checks and loopback ingress probes. No application image is rebuilt.

Each hosted runner has disposable Docker data. Credentials and the attempt directory are created
under `RUNNER_TEMP`; only `staging-attestation.json` is uploaded. The local receipt remains
`production_promotion_approved: false`. The hosted wrapper adds repository, workflow, workflow SHA,
run ID and attempt identity. The artifact name includes source SHA and attempt; uploads never
overwrite earlier evidence. It is retained for 30 days. After expiry, dispatch fresh acceptance
for the same current main SHA to reuse its existing OCI artifact.

The job uses the already approved `main + build-release.yml + release-publication` WIF route and
publisher service account solely for registry pulls. This account has publisher privileges, not
reader-only privileges; no IAM change is included here. A future dedicated reader identity would
require a separately reviewed WIF/IAM change. Runtime containers receive neither this access token
nor a cloud credential file. Docker login stores the short-lived token only on the hosted runner.

Live WIF currently allows only `run_attempt=1`. A fresh workflow dispatch is the retry mechanism;
the immutable builder reuses the same image/artifact identities. Historical SHA builds may still
be requested, but only a source SHA equal to the workflow's own main SHA issues hosted evidence.

## Step 2: production consumes exact evidence

The existing `gce-release.yml` manual deploy retains operator, confirmation, first-attempt,
release freshness, publication receipt, preflight, migration and IAP controls. Two new inputs are
required for deployment:

- `staging_run_id`: the successful build-and-staging run ID.
- `staging_artifact_identity`: `<artifact-id>:<64-character-archive-sha256>`, printed in the staging
  job summary. This is the uploaded ZIP digest, distinct from the OCI release digest.

Before obtaining deployer WIF credentials, the gate reads GitHub run/artifact metadata and checks:

1. The run belongs to `GAE-263/StrayHub`, used `build-release.yml` on main, has the selected SHA,
   is complete and successful, and came from push or manual dispatch.
2. The artifact belongs to that run and latest attempt, is not expired, and matches its supplied
   ID, name and SHA-256. The downloaded bytes must match the same digest.
3. The archive contains exactly one bounded JSON file. Duplicate JSON keys, extra files and paths
   are rejected; the archive is never extracted to the filesystem.
4. The attestation's workflow/run/attempt/SHA match GitHub metadata. Its complete acceptance results,
   migration revision, runtime role and runner/overlay hashes pass validation.
5. The OCI reference, source SHA, release ID, bundle checksum, manifest checksum, migration revision
   and all three image references match the previously validated publication bundle.

The attestation is GitHub run-bound evidence, not an independently signed offline document.
A local JSON file alone cannot authorize deployment. Missing, mixed, failed or expired evidence
stops the workflow before deployer authentication. Publication still adds only its existing
receipt; application images and the deployment bundle remain unchanged.

## Branch transition and activation

The existing production WIF route still requires `gce-release.yml@refs/heads/release` and exact
release HEAD. To promote a tested main SHA, `release` must select that exact commit through a
reviewed fast-forward; a new main-to-release merge commit has a different identity and is rejected.
Do not bypass freshness or rebuild a release-only merge SHA. Retiring this branch is Phase 8 work.
Older workflow code on `release` will not contain the new gate until this reviewed transition is
performed. Treat Phase 5 as unactivated until both branches have the gated workflow and live hosted
acceptance has passed. No production dispatch should occur before that point.

GitHub Environment names remain OIDC namespaces. The current independent reviewer protection is
absent; the existing single-operator manual confirmation remains the approval mechanism.

## Acceptance boundaries and verification

This validates Linux Docker runtime with mock external services and synthetic data. Cloud KMS,
Secret Manager materialization, public nginx/HTTPS, systemd/reboot and real LINE remain outside
the staging evidence. Worker/Beat checks establish running state, not successful task execution.
Production retains its existing cloud preflight and receipt/runtime verification.

Run the focused attestation, local staging, runtime parity, immutable release, manual gate and
release workflow tests. The first live run must show publisher reuse/build PASS, hosted acceptance
PASS, and one attestation archive. A production activation must show evidence validation before
the deployer auth step, then read back the exact deployed images and receipt. Existing production
remains in place until a separately authorized manual deployment.

## Reversal

If hosted acceptance fails, publication artifacts remain reusable and production receives no
passing evidence. Fix acceptance and dispatch a fresh run. Removing the dependent staging job
alone keeps production fail-closed because its evidence gate remains mandatory. Reverting the
production gate would reopen the former path and requires explicit review.
