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

Live rollback remains **DEFERRED** until two genuine immutable, compatible releases exist. Do not
manufacture a previous release or weaken the compatibility gate for acceptance.

## Failure and security rules

- A migration failure prevents pointer activation; the script attempts to restart the unchanged
  current release without a database downgrade.
- A failure after pointer activation writes no success receipt and requires incident review. The
  deploy script does not silently claim success or invent an automatic schema rollback.
- Normal stop/restart never uses `docker compose down -v`; named volumes and backups remain intact.
- Release files and receipts contain provenance only. Secret values, environment dumps, JWT keys,
  authentication cookies, database URLs, and credentials must never be logged or archived.
- Cloud SQL remains `UNKNOWN`. Cloud Run/SQL/IAM/WIF/registry deletion, shared-resource imports,
  DNS/TLS changes, and all legacy cleanup remain prohibited.
