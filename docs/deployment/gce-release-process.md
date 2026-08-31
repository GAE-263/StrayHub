# Immutable GCE Release Process

Status: Phase F3 tooling **READY**; no production release performed

Deletion safety: **BLOCKED**

## Release boundary

An immutable release is one clean Git commit, three registry image digests, and one validated
manifest. Mutable tags such as `latest`, `main`, `prod`, or `b1` are never a deployment source.
Application behavior, DNS/TLS, runtime secrets, managed-service IAM, Terraform state, and legacy
resources are outside this release mechanism.

```text
clean Git SHA
  -> API / Worker / Web images
  -> registry@sha256 references
  -> deterministic deployment-bundle.tar
  -> release-manifest.json + checksums.sha256
  -> reviewed production approval
  -> OS Login/IAP operator deployment
```

## Build and publication

`.github/workflows/gce-release.yml` adds a GCE verification gate. Pull requests and matching pushes
run release contracts, Ruff, shell syntax/lint, production Compose/preflight, Terraform validation
without backend access, the repository secret scan, and clean-SHA image builds. The repository's
primary CI remains responsible for the full backend/frontend/contracts/critical-E2E matrix.

Immutable publication is deliberately manual. A `workflow_dispatch` run must set `publish=true`,
pass the `release-publication` environment review, and have all three repository variables:

```text
GCP_WORKLOAD_IDENTITY_PROVIDER
GCP_RELEASE_PUBLISHER_SERVICE_ACCOUNT
GCP_ARTIFACT_REGISTRY
```

The first two identify a separately reviewed short-lived GitHub OIDC/WIF publisher. The registry is
a dedicated StrayHub Artifact Registry path, not `rrbot-9527` and not an implicitly adopted legacy
resource. Until that identity, registry, IAM, variables, and environment reviewers exist, CI
publication is `DESIGNED_ONLY`. No service-account JSON or SSH private key is accepted.

The publish job builds from the full protected-branch SHA, applies OCI source/revision labels,
pushes each image, resolves its registry digest, and runs:

```bash
./scripts/build-release-bundle.sh \
  --git-sha "$FULL_GIT_SHA" \
  --api-image "$API_REPOSITORY@sha256:..." \
  --worker-image "$WORKER_REPOSITORY@sha256:..." \
  --web-image "$WEB_REPOSITORY@sha256:..." \
  --schema-compatibility unknown \
  --ci-run-id "$RUN_ID" \
  --ci-workflow "$WORKFLOW" \
  --output-dir release-bundle
```

The builder refuses a dirty checkout, a SHA other than `HEAD`, mutable/invalid image references,
an existing output directory, multiple Alembic heads, and sensitive/generated payload files.
Schema compatibility defaults to `unknown`; only a separate migration review may select
`backward-compatible-with-previous`.

## Artifact and manifest

The published artifact contains:

```text
release-manifest.json
deployment-bundle.tar
checksums.sha256
```

The deterministic tar contains the exact Compose file, GCE scripts/systemd units, secret map,
acceptance verifier, `revision`, and `image-digests.env`. It contains no production env, secret,
private key, backup, Terraform state, or credential. The manifest records release ID, full Git SHA,
creation time, exact API/Worker/Web repository and digest pairs, Alembic head, reviewed compatibility,
Compose/bundle hashes, and GitHub workflow/run provenance.

Validate before transport or deployment:

```bash
infra/gce/scripts/release-manifest.py validate-artifact \
  --artifact-dir release-bundle
```

Validation checks the JSON contract, checksums, safe tar paths, Compose hash, revision, and exact
agreement between the manifest and `image-digests.env`.

## Production approval and transport

The workflow never deploys to GCE. A reviewed production operator obtains the already-published
artifact and connects through the existing OS Login/IAP boundary. Public TCP 22, static SSH keys,
firewall changes, and production rebuilds are forbidden.

The operator records a role—not credentials—in deployment provenance and runs:

```bash
sudo /PATH/TO/deploy-release.sh \
  --artifact-dir /PATH/TO/VERIFIED/release-bundle \
  --deployment-role "StrayHub production deployment operator" \
  --confirm-production DEPLOY_STRAYHUB_PRODUCTION
```

Before stopping the application, the script validates the full artifact, canonical destination,
new/unused release ID, protected configuration, current secret generation and JWT files. It extracts
the bundle, makes the release root-owned/read-only, refreshes secrets atomically, pulls exact
digests, and runs the accepted production preflight against those digests. Any failure stops before
runtime change.

Only after those gates pass does it stop `strayhub.service`, run the accepted migration container
with migration credentials, and prove the database reached the manifest revision. It never runs a
downgrade. It then atomically changes `/opt/strayhub/current`, installs repo-owned units, starts
through systemd, verifies exact running image references plus API/Web/Worker/PostgreSQL/MinIO, and
checks public Web/API health. A successful deployment writes a non-secret immutable receipt under
`/var/lib/strayhub/releases/` and updates its `current.json` pointer.

The first immutable release has no valid F3 `N-1`; the historical `e702d7d-e3` directory is not
promoted to immutable provenance. Authenticated live acceptance remains an explicitly approved
follow-up using the existing verifier; credentials are never embedded in the generic deploy command.

## Host release layout and retention

```text
/opt/strayhub/releases/<release-id>/
  release-manifest.json
  checksums.sha256
  revision
  image-digests.env
  infra/gce/...
  scripts/verify_acceptance_live.py

/opt/strayhub/current -> /opt/strayhub/releases/<release-id>
/var/lib/strayhub/releases/<release-id>.json
/var/lib/strayhub/releases/current.json -> successful deployment receipt
```

Release directories are never reused or mutated after activation. Keep at least current `N` and its
known-good, schema-compatible `N-1`. F3 performs no automatic cleanup; more releases may be retained.
Runtime secrets remain only under `/var/lib/strayhub/secrets`, non-secret host configuration remains
under `/etc/strayhub`, and PostgreSQL/MinIO named volumes remain unchanged.

## Rollback refusal and roll-forward

A rollback target must be the successful receipt's recorded `N-1`. The current `N` manifest must
explicitly state `backward-compatible-with-previous`; `unknown`, `forward-only`, missing metadata,
checksum drift, or a different target is refused before runtime change.

```bash
sudo /opt/strayhub/current/infra/gce/scripts/rollback-release.sh \
  --target-release "$N_MINUS_ONE_RELEASE_ID" \
  --deployment-role "StrayHub production deployment operator" \
  --confirm-rollback ROLLBACK_STRAYHUB_APPLICATION
```

Rollback validates and pulls `N-1` before stopping the app, never migrates or downgrades the
database, atomically switches only application artifacts, and repeats local/public health checks.
If `N-1` activation fails, the script attempts roll-forward to preserved `N`. A new immutable fixed
release is the preferred recovery whenever schema compatibility is unsafe or unknown.

After a successful rollback, reactivate only the receipt's recorded newer release with:

```bash
sudo /PATH/TO/rollforward-release.sh \
  --target-release "$RECORDED_NEWER_RELEASE_ID" \
  --deployment-role "StrayHub production deployment operator" \
  --confirm-rollforward ROLLFORWARD_STRAYHUB_APPLICATION
```

The roll-forward command requires validated immutable directories, the receipt's exact target, a
strictly newer manifest and the same migration revision. It pulls exact digests and passes isolated
production preflight before stopping the application, performs no migration, switches the pointer
atomically, verifies local/public health, and writes a new receipt. A failed activation restores the
preserved rollback release. Never use it to skip a forward migration or to select an arbitrary
release.

## Failure and security rules

- A migration failure prevents pointer activation; the script attempts to restart the unchanged
  current release without a database downgrade.
- A failure after pointer activation writes no success receipt and requires incident review. The
  deploy script does not silently claim success or invent an automatic schema rollback.
- Normal stop/restart never uses `docker compose down -v`; named volumes and backups remain intact.
- Release files and receipts contain provenance only. Secret values, environment dumps, JWT keys,
  authentication cookies, database URLs, and credentials must never be logged or archived.
- Cloud SQL remains `UNKNOWN`. Cloud Run/SQL/IAM/WIF/registry deletion, DNS/TLS changes, and all
  legacy cleanup remain prohibited. F5b's exact retained-resource imports are recorded separately
  and do not authorize any release-time Terraform mutation.

## Phase F4 first immutable release

F3/F4 publication-fix checkpoint `38ab34dc6aaff78e0f3a9f20dbf954a071fb355a` is pushed on
`review/system_over_all` and is the only approved F4 source revision. The dedicated Docker
repository is `asia-east1-docker.pkg.dev/canvas-primacy-502703-k1/strayhub`. Its writer is
`strayhub-artifact-publisher@canvas-primacy-502703-k1.iam.gserviceaccount.com`; the canonical VM
runtime identity has repository-level reader only.

GitHub federation uses pool `github-strayhub` and provider `github`. The provider accepts only
`GAE-263/StrayHub`, `refs/heads/main`, and the `release-publication` or
`production` environment. Environment-specific principal sets separately impersonate the artifact
publisher and the reserved `strayhub-gce-deployer` identity. Neither identity has a user-managed
service-account key. The deployer currently has no project or VM role; first deployment remains an
operator action through the accepted OS Login/IAP boundary.

Default-branch workflow commit `82af90e3f45ef2841d69ddbc87f353bc0019fd2b` adds only
`.github/workflows/gce-release.yml` to `main`. The workflow requires the full trusted source input,
checks out `38ab34dc6aaff78e0f3a9f20dbf954a071fb355a`, verifies `HEAD`, and uses that revision for all
three images and the manifest. The WIF provider trusts the default-branch workflow ref
`refs/heads/main`; repository and environment restrictions remain unchanged.

The first publication attempt authenticated through WIF and pushed all three images but failed
before bundle completion because `google-github-actions/auth` created `gha-creds-*.json` in the
checkout. The trusted source now ignores only that documented temporary credential pattern; the
clean-tree release gate remains unchanged. Images from the failed run are non-canonical and must not
be used by a release.

Workflow run `33354828878` rebuilt the fixed source, exchanged GitHub OIDC through WIF, impersonated
the dedicated publisher, pushed API/Worker/Web, validated the release bundle, and uploaded artifact
`strayhub-gce-release-38ab34dc6aaff78e0f3a9f20dbf954a071fb355a`. The artifact ZIP digest is
`sha256:eb4347e308f6f52033f8374386453cc70b81526ba8a7d32833e3ef4ecb582c55`.

Release `20260831T034951Z-38ab34dc6aaf` was deployed through the canonical IAP/operator script after
an isolated production preflight. The current pointer, receipt, and running API/Worker/Web image
references all match the manifest exactly. Authenticated synthetic acceptance passed login,
tenant/RLS isolation, volunteer authorization, QR-first reporting, care-report creation, and the
cross-shelter denial. The historical `e702d7d-e3` directory is retained but is not represented as a
genuine immutable N-1, so live rollback remains deferred.

## Phase F5b second-release compatibility gate

The F5b source candidate contains retained-resource Terraform ownership, fail-closed retirement of
legacy mutation entrypoints, deployment documentation/workflow validation and contract tests. It
does not change application code, Compose/runtime configuration, database models, Alembic
migrations, authentication, tenant/RLS behavior, LINE/LIFF behavior, or release bundle format.

Both the first immutable release and the F5b candidate declare migration head
`0037_animal_external_sources`. On that evidence the second release may be published with
`backward-compatible-with-previous`; this is not a schema downgrade claim. The rollback tool must
still verify both manifests/receipts, target the recorded N-1, preserve the database and volumes,
and refuse any digest, checksum, compatibility, or backup-preflight failure.

After the second release is deployed and accepted, define N as its exact release ID and retain
`20260831T034951Z-38ab34dc6aaf` as N-1. A live N -> N-1 -> N drill remains separately gated on a
fresh completed backup and must never run before the second release is healthy.

## Phase F5b second immutable release and live drill

Source `5f0664f0a63994c7be113473e9e31906242b6b77` was published by GitHub Actions run
`33362441959` after OIDC/WIF, registry authentication, release verification and artifact upload all
passed. Artifact checksum:
`sha256:a5e5d511f99ee3925934961509017bc5388d2cc107d77ca6e273b699f6ed300e`.

Release N `20260831T060436Z-5f0664f0a639` uses exact API
`sha256:3236bc21319cdd8ae284588a9535fe23a73817dc818ccb72d439794ffdee2008`, Worker
`sha256:77e6075ae1856df0ff46772d3a7418ba634d2c18d636b608f618e243f7dd776b`, and Web
`sha256:9642600c8280028ea18ff6f40977d925382e4e6ebcff1623ebe242ef09b1624f`. Deployment preflight,
migration-head verification, runtime health and authenticated acceptance passed.

Fresh backup `20260831T062155Z-e3daily2165` passed through GCS `_COMPLETE`. The live drill then
passed N -> N-1, exact N-1 digest/runtime/authenticated acceptance, N-1 -> N roll-forward, and final
exact N digest/runtime/authenticated acceptance. Database migration and downgrade were both NONE;
named volumes, DNS/TLS and legacy infrastructure were unchanged. Production is back on N and both
immutable releases remain retained.

The reusable E5 verifier's original fixed idempotency key collided with its historical report. The
F5b drill used release-specific synthetic idempotency keys and the committed LINE draft-cancel API;
no DB row was manually deleted and no credential/token was logged. Future acceptance invocations
must continue using a unique reviewed synthetic run key.
