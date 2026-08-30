# CI Refactor Review

## CI Refactor Plan

The repository Plan skill was invoked before workflow edits. Its spec-kit setup resolved
`specs/010-shelter-admin-governance-confirmation`, which is unrelated to this CI-only request, so
that feature's existing plan and design artifacts were intentionally left unchanged. This phased
review is the task-specific implementation plan requested for the CI refactor.

## Current State

- Primary CI (`.github/workflows/ci.yml`) runs one `python` job on pull requests and pushes to
  `main`, backed by PostgreSQL 16. It installs uv dependencies, applies Alembic migrations, runs
  Ruff lint and formatting checks, and runs the complete pytest suite.
- The GCP demo build gate (`.github/workflows/demo-build.yml`) runs one `demo-build` job for
  deployment-related path changes. It repeats the backend setup, migration, Ruff, and pytest
  checks; runs frontend and generated-contract checks; validates Terraform; scans GCP demo files
  for secrets; builds the API, worker, and web images; and uploads build metadata.
- Backend duplication is `uv sync --dev`, `uv run alembic upgrade head`, `uv run ruff check .`,
  `uv run ruff format --check .`, and the full `uv run pytest` suite (the demo build adds quiet and
  warning-suppression flags).
- Frontend checks exist only in the demo build through `npm --prefix apps/web run quality`. That
  script runs Vitest, TypeScript, mobile/jsdom tests, accessibility/jsdom tests, and Prettier. It
  does not run the required production `next build` command.
- Contracts exist only in the demo build through `npm ci --prefix packages/contracts` and
  `npm --prefix packages/contracts run check`, which verifies generated OpenAPI TypeScript output.
- Deployment-specific checks are Terraform format/init/validate, a scoped secret scan, three
  Docker image builds, Docker metadata generation, and build-metadata artifact upload.
- Expected time hotspots are the complete PostgreSQL-backed pytest suite, repeated frontend
  Vitest/jsdom runs inside `quality`, three uncached Docker builds, Terraform initialization, and
  repeated dependency installation across the two workflows.
- Repository-local files cannot reveal GitHub branch-protection rules. Existing required checks
  may depend on the current `python` and/or `demo-build` check names. Job identifiers and existing
  deployment check naming should therefore remain conservative unless repository settings are
  inspected separately.

## Target State

- Primary CI is the source of truth for backend quality, frontend quality, contracts, and any
  deterministic critical integration/security checks.
- GCP Demo Build Gate is the source of truth for deployability: Terraform remains during the GCP
  transition, alongside the secret scan, Docker builds, metadata, and deployment artifact.
- Only stable critical Playwright flows should become a pull-request gate; full, visual, and broad
  accessibility suites remain deferred.

## Phase 0 — Inventory

- [x] Map current workflow responsibilities
- [x] Identify duplicated commands
- [x] Identify branch-protection/check-name risk
- [x] Identify estimated CI time hotspots

Status: Complete; inventory recorded without workflow edits.
Files changed: `review.md`
Commands run: Plan skill setup; workflow/package/project/README/GCP/test inventory; recent CI log review.
PASS/FAIL: PASS
Open issues: GitHub branch-protection rules are not inspectable from repository files.
Next phase safe: YES

## Phase 1 — Primary CI parity

- [x] Preserve backend job
- [x] Add frontend quality job
- [x] Add contracts job
- [x] Enable uv/npm cache
- [x] Verify locally

Status: Complete after repairing the two stale backend test expectations.
Files changed: `.github/workflows/ci.yml`, `tests/contract/test_local_product_quality_contract.py`,
`tests/test_feature_quality.py`, `review.md`
Commands run: `uv sync --dev`; `uv run alembic upgrade head`; `uv run ruff check .`;
`uv run ruff format --check .`; `uv run pytest` with CI-equivalent local database variables;
`npm ci --prefix apps/web`; frontend `test`, `typecheck`, `format:check`, and `build` scripts;
`npm ci --prefix packages/contracts`; contracts `check` script; targeted regression tests for the
two baseline failures.
PASS/FAIL: PASS — frontend (79 files/357 tests), typecheck, format, production build, contracts,
Alembic, Ruff lint/format, and workflow YAML validation passed. Full pytest completed with 953
passed, 2 explicitly documented opt-in skips, and 0 failures.
Open issues: PostgreSQL/RLS tests require the database environment variables already present in CI.
The existing `python` job/check identifier remains unchanged because branch-protection settings are
unknown. `npm ci` reports seven dependency audit findings (four moderate, two high, one critical);
remediation was not attempted because dependency changes are outside scope.
Next phase safe: YES; Phase 2 was subsequently authorized and completed below.

## Phase 2 — Demo build deduplication

- [x] Map duplicated quality checks
- [x] Remove duplicated backend quality
- [x] Remove duplicated frontend quality
- [x] Remove duplicated contracts check
- [x] Retain deployment-specific checks
- [x] Retain Terraform validation
- [x] Verify workflow syntax
- [x] Verify deployment Docker builds remain represented
- [x] Confirm no loss of required code-quality coverage

Status: PASS — workflow refactor, static/Terraform checks, and all three production image builds
passed locally.
Files changed: `.github/workflows/demo-build.yml`, `review.md`
Commands run: Compared both workflows line-by-line; inspected all three Dockerfiles; parsed both
workflow YAML files; ran Terraform fmt/init/validate; ran the retained secret scan; ran the focused
GCP workflow contract and a coverage-ownership assertion; attempted the API Docker build; checked
the local Docker base-image cache; pulled the three required base images; built and inspected the
API, Worker, and Web production images; ran `git diff --check`.
PASS/FAIL: PASS — workflow, coverage, Terraform, secret-scan, and all three runtime Docker builds
passed.
Open issues: The unused `id-token: write` permission is recorded as a follow-up rather than changed
in Phase 2. Trigger paths remain relevant to the retained Docker build contexts.
Next phase safe: YES

### Phase 2 Result

Status: PASS

Files changed:

- `.github/workflows/demo-build.yml`
- `review.md`

Removed duplicate quality checks:

- Backend dev dependency install, Alembic migration, Ruff lint/format, and full pytest
- Host-level frontend dependency install and frontend quality script
- Host-level contracts dependency install and generated-contract check
- PostgreSQL service and backend database environment used only by the removed quality checks
- uv and Node setup used only by the removed host-level quality checks

Retained deployment checks:

- Terraform format, backend-free initialization, and validation
- Existing `infra/gcp-demo` secret scan without scope or pattern changes
- Production API, Worker, and Web Docker image builds
- Docker metadata generation and build metadata artifact upload

Coverage ownership:

- Backend Ruff, pytest, and Alembic migration → `.github/workflows/ci.yml`
- Frontend test, typecheck, format, and production build → `.github/workflows/ci.yml`
- Contracts → `.github/workflows/ci.yml`
- Terraform → `.github/workflows/demo-build.yml`
- Docker builds → `.github/workflows/demo-build.yml`
- Secret scan and deployment metadata → `.github/workflows/demo-build.yml`

Verification:

- YAML: PASS
- Terraform: PASS
- Secret scan: PASS
- Docker builds: PASS — API, Worker, and Web production images built and their tags were inspected
- Focused GCP workflow contract: PASS
- Coverage ownership assertion: PASS
- `git diff --check`: PASS

Open issues:

- Consider removing unused `id-token: write` in a separate permission-hardening task.

Next phase safe: YES — Phase 2 is fully verified; Phase 3 must begin with test-layout analysis.

## Phase 3 — Integration/security split

- [x] Evaluate backend-fast vs PostgreSQL/RLS split
- [x] Implement only if current tests cleanly support it — deferred because classification is mixed
- [x] Never reduce RLS or shelter-isolation coverage

Status: DEFERRED after classification analysis; no workflow split implemented.
Files changed: `review.md` only for Phase 3 analysis.
Commands run: Collected tests by directory; counted files with direct PostgreSQL references;
inspected marker usage and the nested quality matrix; collected the two exhaustive candidate
partitions; executed the database-free candidate (`tests/unit`, `tests/contract`, and
`tests/performance`). The complementary PostgreSQL candidate execution was intentionally stopped
when the task was narrowed to classification analysis only.
PASS/FAIL: PASS for analysis — 955 tests are accounted for, and the 591-test database-free
candidate passed. Implementation is intentionally deferred.
Open issues: Existing semantic markers are registered but scarcely applied. Security, E2E,
integration, and isolation directories mix database-bound and lightweight tests, while
`tests/test_feature_quality.py` starts a nested pytest run across several classifications. A split
today would require a brittle per-file list or would place most lightweight security checks in the
PostgreSQL job.
Next phase safe: NO

### Phase 3 Test Classification Analysis

| Classification      | Files | Tests | Files with direct PostgreSQL references |
| ------------------- | ----: | ----: | --------------------------------------: |
| Unit                |    71 |   449 |                                       0 |
| Contract            |    33 |   137 |                                       0 |
| Performance         |     3 |     5 |                                       0 |
| Security            |    29 |    89 |                                       2 |
| Integration         |    72 |   209 |                                      19 |
| Isolation           |    16 |    31 |                                      11 |
| E2E                 |    13 |    33 |                                       4 |
| Root quality matrix |     1 |     2 |         Nested cross-classification run |

Candidate partitions:

- Database-free candidate: Unit + Contract + Performance = 591 tests; verified PASS without a
  PostgreSQL test URL.
- PostgreSQL candidate: Security + Integration + Isolation + E2E + root quality matrix = 364 tests;
  collection verified, execution not part of this classification-only task.
- Total coverage: 591 + 364 = 955 tests, matching the current complete suite.

Classification risks:

- Directory-level splitting is exhaustive but semantically imprecise: 27 of 29 security files do
  not directly reference PostgreSQL, yet the two database-bound security files prevent assigning
  the whole directory to a database-free job.
- Integration, isolation, and E2E directories also mix direct database tests with tests that use
  mocked or application-level boundaries.
- Registered pytest markers cannot currently drive a reliable split because most tests do not use
  the semantic `unit`, `contract`, `integration`, `isolation`, `security`, or `e2e` markers.
- The root quality matrix launches a nested pytest process across unit, contract, security,
  integration, and isolation paths, which creates hidden ownership and possible duplication.

Decision: Do not change `.github/workflows/ci.yml` in Phase 3 yet. First establish a maintained,
reviewable classification mechanism (prefer consistent semantic markers and remove the nested
cross-classification ownership ambiguity), then prove both partitions locally without reducing any
RLS, tenant-isolation, volunteer-approval, or authorization coverage.

## Phase 4 — Critical E2E

- [x] Select and document stable critical Playwright flows
- [x] Add a dedicated `test:e2e:critical` script
- [x] Add a separate `Critical E2E` primary CI job
- [x] Verify the critical suite repeatedly against an isolated local Web server
- [x] Keep visual, broad accessibility, responsive/keyboard matrix, and full E2E out of the PR gate

Status: PASS — the isolated 20-test Chromium suite passed twice and is now a separate primary CI
job.
Files changed: `.github/workflows/ci.yml`, `apps/web/package.json`, `review.md`.
Commands run:

- Started an isolated Next.js development server on `127.0.0.1:3002` with the API target pinned to
  `127.0.0.1:8001`.
- Ran the broader candidate suite once: 27 passed and 7 deterministic assertion failures exposed
  stale LIFF/volunteer-application expectations.
- Ran the following command twice after narrowing the gate; 20 tests passed both times (8.0s and
  9.2s):

  ```bash
  PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3002 \
    npm --prefix apps/web run test:e2e:critical
  ```

PASS/FAIL: PASS. The gate covers login/home behavior, active-shelter selection, cross-shelter
context switching and stale-response isolation, the volunteer QR/care-report core, and the care
agenda. Each spec uses Playwright route mocks and requires only the Web server plus Chromium.
Open issues: `volunteer-application-status.spec.ts`, the currently failing cases in
`volunteer-access-approval.spec.ts`, and the invalid-organization case in
`liff-route-isolation.spec.ts` are deferred because their expectations do not match the current
UI. They were not weakened, skipped, or used to justify application/LIFF behavior changes. The
full, visual, broad accessibility, responsive, and keyboard suites remain outside this PR gate.
Next phase safe: YES — planned CI phases are complete; deferred suites require separate ownership
and baseline repair.

## Deferred

- [ ] Full/nightly E2E
- [ ] Visual regression nightly
- [ ] Reconcile volunteer application/approval and LIFF route E2E expectations with current UI
- [ ] Remove Terraform validation after GCP single-VM nginx deployment is implemented
- [ ] Replace Terraform validation with `docker compose config`, nginx configuration validation,
      production image builds, secret scanning, and deployment-script validation after that deployment
      architecture exists

## CI Refactor Final Status

- Phase 0 — PASS
- Phase 1 — PASS
- Phase 2 — PASS
- Phase 3 — DEFERRED
- Phase 4 — PASS

### Workflow Ownership

- Backend Quality → `.github/workflows/ci.yml` (`python`)
- Frontend Quality → `.github/workflows/ci.yml` (`Frontend Quality`)
- Contracts → `.github/workflows/ci.yml` (`Contracts`)
- Critical E2E → `.github/workflows/ci.yml` (`Critical E2E`)
- Terraform → `.github/workflows/demo-build.yml`
- Secret Scan → `.github/workflows/demo-build.yml`
- Docker Builds → `.github/workflows/demo-build.yml`
- Build Metadata → `.github/workflows/demo-build.yml`

All four primary CI jobs are independent and have no `needs:` chain. The primary `python` job keeps
`setup-terraform` because the unchanged full pytest suite directly executes the Terraform CLI in
`tests/contract/test_gcp_iac_contract.py`; the standalone deployment gate remains owned by
`demo-build.yml`.

### Required PR Checks

- `python`
- `Frontend Quality`
- `Contracts`
- `Critical E2E`

Future only: `PostgreSQL Security / RLS`, after stable test markers and classification exist.

### Deferred

- PostgreSQL/RLS job split until stable markers/classification exist. Current exhaustive candidates
  remain 591 database-free tests and 364 PostgreSQL-candidate tests (955 total); splitting now would
  rely on brittle file lists because database-bound tests are mixed across security, integration,
  isolation, and E2E directories.
- 7 stale LIFF/volunteer E2E assertions.
- Full/nightly E2E.
- Visual regression/nightly.
- Terraform removal or replacement only after the GCP single-VM nginx deployment becomes canonical.

No RLS, tenant-isolation, authorization, or other backend test coverage was reduced.

### Deployment Gate

- Terraform format, backend-free initialization, and validation.
- Secret scan.
- API image build.
- Worker image build.
- Web image build.
- Build metadata artifact.

API and Worker retain the previously verified Phase 2 build evidence because their inputs did not
change. The Web production image was rebuilt successfully after `apps/web/package.json` gained the
critical E2E script. Terraform and secret-scan evidence remain valid because no relevant infra or
deployment workflow files changed after Phase 2.

### Final Verification

- `uv run ruff check .` — PASS.
- `uv run ruff format --check .` — PASS (631 files).
- `npm --prefix apps/web run test` — PASS (79 files, 357 tests).
- `npm --prefix apps/web run typecheck` — PASS.
- `npm --prefix apps/web run format:check` — PASS.
- `npm --prefix apps/web run build` — PASS.
- `npm --prefix packages/contracts run check` — PASS.
- Critical E2E — PASS (20 tests across 4 specs) against the isolated `127.0.0.1:3002` Web server.
  The unqualified local command first encountered an unrelated existing development server on port
  3001 (`EADDRINUSE`); no user process was stopped, and the clean isolated rerun passed.
- Web production Docker image rebuild — PASS (`strayhub-demo-web:ci-finalize`).
- Workflow YAML parse — PASS.
- `git diff --check` — PASS.
- `actionlint` — not run because it is not installed; tooling was not reinstalled.

Durable verification evidence: [`docs/verification/ci-refactor-verification.md`](docs/verification/ci-refactor-verification.md).

## Production Config Fail-Fast

Status: READY. Scope cleanup: PASS. Non-local API startup now aggregates missing, placeholder, loopback, and known
local-default configuration errors without including secret values. Worker and migration startup use
the same policy with a database-only process profile because those processes do not consume the API's
LINE, JWT, PII, MinIO, or AI configuration.

Scope: Runtime configuration hardening only; no authentication redesign, RLS/tenant change, database
schema change, deployment, or secret generation.

Scope cleanup: PASS. The previously introduced LINE feature-toggle expansion was removed and deferred.
Authentication, webhook, volunteer identity, and LINE verifier runtime behavior remain at baseline.

Files changed: `services/api/app/config/settings.py`, worker session bootstrap, Alembic bootstrap, GCP
demo migration env wiring, `.env.example`, `README.md`, `review.md`, and focused config tests.

Validation policy: `local` keeps repository development defaults; explicit `test`/`testing` permits
deterministic fixtures; every other environment validates before traffic, jobs, or migrations. API
requires safe DB, active MinIO, auth/JWT, confirmation signing, non-local PII, existing LINE runtime
credentials, and any selected external AI provider. Worker/migration require their safe DB only.
Errors are deterministic and field-name-only.

Local behavior: unchanged. `./scripts/demo.sh check` passes with local PostgreSQL, MinIO, generated
demo JWT material, local PII material, and fake/local LINE behavior.

Non-local behavior: missing active JWT keys, unsafe key references/issuer, local/empty PII config,
loopback/development DB or MinIO config, fake LINE/LIFF config, local confirmation secret, or incomplete
external AI config exits immediately. Mock AI remains credential-free.

Tests: focused config/auth/LINE/security/IaC tests pass (49 tests); full backend passes on a fresh,
migrated disposable PostgreSQL database (970 passed, 2 expected skips); repository-wide Ruff lint and
format checks, Terraform format check, and `git diff --check` pass. Manual API probes confirm local and
safe synthetic production imports exit zero, while unsafe production import exits non-zero. Unsafe
production Worker and Alembic probes also exit non-zero before opening a database connection.

Deployment compatibility: current GCP demo config is NOT ready for the API policy. Before deploying:

1. configure the runtime storage actually used by the API by setting `MINIO_ENDPOINT`,
   `MINIO_ACCESS_KEY`, and `MINIO_SECRET_KEY` to non-local values, or separately implement/select the
   already-present GCS adapter in a future storage task;
2. set safe `LINE_CHANNEL_ID` and `LIFF_ID` values required by the existing runtime;
3. replace `AUTH_JWT_ISSUER`, `AUTH_JWT_ACTIVE_PRIVATE_KEY_REFERENCE`, and
   `AUTH_JWT_ACTIVE_PUBLIC_KEY_REFERENCE` local defaults;
4. verify the injected `DATABASE_URL` is non-loopback and does not use repository development
   credentials.

The worker and migration job are compatible with the new process-specific policy once their injected
`DATABASE_URL` passes the same DB checks. Terraform now explicitly marks the migration job as
`APP_ENV=gcp-demo` so it cannot silently use local behavior.

Open issues: GCP config advertises GCS but API runtime consumers remain directly wired to MinIO; backend
selection is intentionally outside this configuration-hardening task. A separate deferred task must
design any future LINE integration feature toggle, including webhook response semantics, verifier and
LIFF behavior, volunteer fallback behavior, and management UI implications. No migration is required.

Deployment compatibility: NOT READY. Migration: NONE.

## Deployment Source-of-Truth Cleanup

Canonical target: GCE single VM with nginx and Docker Compose running Next.js, FastAPI, Worker,
PostgreSQL, and MinIO; Secret Manager and Cloud KMS remain managed dependencies, while GCS is backup
only.

Current status: inventory and migration plan complete; canonical GCE/Compose, production nginx,
backup/restore, preflight, and systemd artifacts do not exist yet.

Legacy architecture: `infra/gcp-demo` and its Terraform, Cloud Run, Cloud SQL, runtime GCS, scripts,
CI workflow, contract tests, and documentation remain referenced and must stay transitional.

Migration strategy: Phase A inventory, Phase B canonical artifacts, Phase C production-like local
verification, Phase D managed-service wiring, Phase E real GCE acceptance, then Phase F legacy removal.

Immediate next phase: design and separately review Phase B production Compose/nginx/preflight/runtime
config/persistence/backup/restore artifacts.

Deletion allowed now: NO.

## Phase B1 Production Compose and Runtime Contract

Status: READY. Canonical Compose is `infra/gce/docker-compose.production.yml`; the runtime config
contract is `docs/deployment/production-config-contract.md`; operator preflight is
`infra/gce/scripts/preflight.sh`; and synthetic non-local inputs are
`infra/gce/.env.production.example`.

Runtime boundary: PostgreSQL 16, MinIO, FastAPI, Worker, and Next.js share the canonical private
Compose network. PostgreSQL and MinIO use named volumes. A short-lived MinIO bucket bootstrap and a
tools-profile one-shot Alembic service are not part of the long-running runtime. API and Web host
bindings are loopback-only verification aids pending Phase B2 nginx.

Database boundary: migration and runtime credentials are separate. The runtime login is not a
superuser, cannot bypass RLS, and inherits the existing `strayhub_runtime` role; Alembic uses the
schema-owning migration login and reached `0037_animal_external_sources`. Schema migration added:
NONE.

Verification: PASS with isolated project `strayhub-b1-verify`. Compose config, preflight,
PostgreSQL/MinIO health, one-shot migration, API fail-fast/startup/health, long-running Worker, Web
startup, internal Web-to-API reach, MinIO write/read, and PostgreSQL/MinIO persistence across normal
`down`/`up` all passed. The isolated stack and its verification volumes were removed afterward.
Focused deployment/config tests passed (25); repository Ruff lint, Ruff format check, and
`git diff --check` passed.

Cloud dependency: the B1 Compose runtime requires no Cloud Run, Cloud SQL, runtime GCS, Cloud Run
migration job, or legacy deploy script. Existing production-style Dockerfiles are reused as
transitional image assets only; legacy files remain intact.

Deferred: nginx, TLS, real GCE, systemd, live Secret Manager wiring, functional KMS/PII validation,
real LINE/LIFF calls, GCS backup, backup/restore scripts, replacement CI, Terraform state migration,
and legacy removal. Legacy deletion allowed now: NO.

## GCE Verification JWT Key Isolation (Historical, Superseded)

Historical decision: ACCEPT COMMITTED VERIFICATION KEY after isolation hardening. The
runtime-generated policy in the next section supersedes this decision; no verification PEM is now
accepted as a repository artifact.

Provenance: the RSA pair was generated once with OpenSSL specifically for the isolated Phase B1
`strayhub-b1-verify` smoke on 2026-08-29. Both files remain untracked in the current working tree and
have zero Git-history commits. They were not copied from a deterministic fixture or production
source, registered with an external issuer, uploaded to Secret Manager, or used outside the isolated
local B1 stack.

Metadata: RSA 2048; private and public PEMs parse; the public key derived from the private key matches
the checked-in public file. No key contents were copied into review evidence.

Isolation: canonical Compose now requires operator-selected key-file paths and no longer hard-codes
the fixture names. Only the synthetic env marked `B1_VERIFICATION_ONLY=true` selects them. Compose
mounts the private key read-only into API only with requested mode `0400`; no Worker, Web, migration,
PostgreSQL, or MinIO mount exists. Real GCE keys remain a Secret Manager responsibility.

Image/scanner safety: `.dockerignore` excludes the verification PEM directory from every build
context; source Dockerfiles use narrow `COPY` statements; direct inspection found neither PEM in the
API, Worker, nor Web images. The repository-wide local secret scan has one documented exact-file
exception, while Terraform and legacy deploy scripts have no fixture reference or upload path.

Evidence: verification README warning, preflight marker/path confinement, reference allowlist,
Terraform/deploy isolation, Docker build-context policy, key metadata/pair match, production Secret
Manager contract, and narrow scanner exception are enforced by focused contract tests. Local file
modes are private `0600` and public `0644`, but documentation explicitly does not treat Git modes as
a production security boundary. Commit: not created.

## Runtime-Generated JWT Verification Policy

This decision supersedes the preceding acceptance of a committed verification fixture. Phase B1 JWT
material is now generated after checkout under the Git-ignored
`infra/gce/verification/generated/` directory; neither PEM is a repository artifact.

Preflight invokes `generate-verification-jwt-keys.sh`, which generates an RSA 2048 PKCS#8/private and
derived-public pair when missing or invalid, reuses a valid matching pair, repairs modes to `0600` and
`0644`, and supports explicit local rotation through `--force`. It prints metadata only.

The synthetic env selects only the ignored generated paths. Compose remains path-parameterized and
mounts the files read-only into API only. Terraform, legacy deploy scripts, and Secret Manager upload
paths do not reference the generated directory. The obsolete committed-PEM secret-scan exception was
removed, while `.dockerignore` excludes the generated directory from every image context.

Production policy is unchanged: real JWT private/public keys come from Secret Manager or another
approved production source and are staged outside the repository. Generated verification keys are
not valid production, staging, shared-demo, or externally reachable credentials. Migration: NONE.

Validation: generator generation/reuse/invalid-repair/force-rotation and RSA pair metadata PASS;
preflight and Compose config PASS; isolated migration/API/Worker/Web/API-health/Web-to-API PASS;
container mounts read-only into API only with effective `0600`/`0644`; focused contracts 33 PASS;
repository secret scan without a PEM exception PASS; Ruff, format, and `git diff --check` PASS. The
isolated Compose stack and volumes were removed after verification.

## Phase B2 Production nginx Single-Origin Routing

Status: READY. Canonical nginx config is `infra/gce/nginx/strayhub.conf`; routing policy is
`docs/deployment/production-nginx-routing.md`. The pinned `nginx:1.27.5-alpine` service is the only
host-published service, with synthetic HTTP ingress on configurable port `8088`. API, Web,
PostgreSQL, MinIO, and Worker remain private on the Compose network.

Routing: `/healthz` and `/v1/*` preserve their complete paths to `api:8080`; `/` and every other
path go to `web:8080`. `/v1/line/webhook` is structurally compatible with the FastAPI router, and
`/volunteer-application` remains a Next.js route. No LINE payload, external LINE call, LIFF logic,
authentication behavior, application code, database schema, or tenant/RLS behavior changed.

Proxy policy: upstreams use Compose DNS names only. nginx forwards `Host`, `X-Real-IP`,
`X-Forwarded-For`, and `X-Forwarded-Proto`; has no HMR/dev route, MinIO route, PostgreSQL route, or
loopback upstream; and mounts its config read-only. The temporary `1m` body limit matches the
existing Next.js proxy limit. No explicit proxy timeout override was added.

Verification: Compose render PASS; preflight PASS; `nginx -t` PASS in preflight and the running
container; migration PASS; isolated PostgreSQL/MinIO/API/Web health and Worker runtime PASS. Through
nginx only: `/` 200, `/healthz` 200, `/v1/public/volunteer-organizations` 200,
`/volunteer-application` 200, `/v1/line/webhook` GET 405, and an unknown Web path 404. The LINE 405
proves structural routing without sending a payload; access evidence retained the complete `/v1`
paths. Focused B1/B2/JWT contracts: 23 PASS. The isolated containers, network, and volumes were
removed.

Deferred: TLS, DNS, firewall policy, real GCE provisioning, systemd, live Secret Manager wiring,
functional KMS verification, GCS backup, backup/restore, legacy CI replacement, Terraform state
migration, and legacy removal. Migration: NONE.

## Phase B3 PostgreSQL and MinIO Backup / Restore

Status: READY. Canonical operator contract is `docs/deployment/backup-restore.md`; generated artifacts
use the narrow Git-ignored `infra/gce/backup/generated/` root or an explicit protected external root.
The one-shot scripts add no Compose service, port, nginx route, application behavior, schema
migration, tenant/RLS change, LINE/LIFF change, live GCS call, or legacy deletion.

Backup model: one UTC backup ID groups a PostgreSQL custom-format logical dump and SHA-256 metadata,
a MinIO key/size/SHA-256 inventory and object tree, and a non-secret `manifest.json`. PostgreSQL and
MinIO are captured sequentially; the manifest explicitly records that the pair is not transactionally
atomic. Owner-only artifact modes and strict path validation passed.

PostgreSQL drill: PASS in `strayhub-b3-verify`. Migration ran; one synthetic probe row was dumped and
restored into `strayhub_b3_restore_drill`; Alembic head matched
`0037_animal_external_sources`; 37 RLS-enabled tables, 40 policies, restricted runtime-role flags,
and the runtime SELECT grant remained valid. Missing-confirmation and normal-database targets were
rejected.

MinIO drill: PASS. Two synthetic objects with nested keys were backed up, restored only into
`strayhub-b3-restore-drill`, copied back, and matched object count 2 plus canonical inventory SHA-256.
Anonymous access remained disabled. Missing-confirmation targets were rejected.

Manifest/retention: manifest integrity PASS. Proposed proof-of-concept retention is seven daily and
four weekly generations; monthly retention and all automated pruning remain deferred. Local B3
staging is not durable/off-VM backup. Production readiness requires private GCS upload, IAM,
retention, and restore-from-GCS verification in Phase D. Migration: NONE. Commit: included in the
coherent Phase B3 deployment commit.

## Phase B4 TLS / DNS / Firewall Edge

Status: READY. Canonical policy is `docs/deployment/tls-dns-firewall.md`. nginx is the
only service with published HTTP/HTTPS ports. Plain HTTP serves only the isolated HTTP-01 webroot and
otherwise returns 308; HTTPS preserves the B2 Web, API, health, webhook, and LIFF route ownership.

TLS model: host-level Certbot/Let's Encrypt with certificate name `strayhub`, read-only Certbot state
and ACME webroot mounts, and a future successful-renewal nginx reload hook. Local verification uses
an ignored runtime-generated self-signed certificate; no TLS key is committed or accepted for
production. DNS uses one canonical hostname on a reserved static IP. Application firewall exposure
is TCP 80/443 only; internal services remain private and SSH is restricted.

No real DNS, firewall, certificate, GCE, systemd, Secret Manager, KMS, GCS, Terraform, CI, legacy,
application, database, tenant/RLS, or LINE/LIFF state change is included. Migration: NONE. Commit:
included in the coherent Phase B4 deployment commit.

Verification: Compose render, preflight, and nginx syntax PASS. The isolated `strayhub-b4-final`
stack returned HTTP 308, served the ACME probe exactly, returned HTTPS 200 for Web, health, public
versioned API, and Volunteer LIFF, and returned the expected webhook GET 405. Only nginx published
ports (verification 8088/8443); all internal services remained private. Focused B1/B2/B4/JWT
contracts: 30 PASS. The isolated stack and volumes were removed after the drill.

## Phase D1 Secret Manager Runtime Staging

Status: READY. Canonical policy is `docs/deployment/secret-manager.md`. One read-only
fetch maps explicit, parameterized Secret Manager IDs into private immutable generations. Scalar
secrets use `runtime.env`; the active JWT pair remains file-based. An atomic `current` symlink keeps
the generation coherent, with directory mode 0700 and secret file mode 0600.

Production uses the non-secret `.env.production.template` plus external staged material under
`/var/lib/strayhub/secrets`; it rejects B1 verification markers and generated repository paths. The
B1 verifier remains unchanged. API, Worker, Migration, PostgreSQL, MinIO, LINE, confirmation, JWT,
and optional external-AI ownership are explicit; no application behavior or schema changes exist.

No live Secret Manager/IAM mutation, KMS call, GCS transfer, GCE provisioning, systemd, TLS/DNS/
firewall mutation, legacy deletion, Terraform state change, or CI replacement is included.
Migration: NONE. Commit: included in the coherent Phase D1 deployment commit.

Verification: synthetic fetch/staging, required-secret failure preservation, atomic rotation,
0700/0600 permissions, JWT pair validation, two-env Compose render, and production preflight PASS.
API, Worker, and Migration production fail-fast checks passed. An isolated production-mode API
started and returned healthy without exposing a host port. The B1 verification preflight remained
green. Focused D1/B1-B4/JWT/backup contracts: 45 PASS. Repository secret scan, Ruff, format, and
`git diff --check` passed. Temporary synthetic data and Docker resources were removed.

## Phase D2 Cloud KMS Functional Wiring

Status: READY. Canonical policy is `docs/deployment/cloud-kms.md`. The existing `PiiCipher` port,
Google Cloud KMS adapter, volunteer PII service, encrypted metadata, tenant/field authenticated data,
and API dependency wiring are retained. No parallel encryption framework or schema change exists.

Every non-local API must select `gcp-kms` with a full environment-specific CryptoKey resource name.
Settings, the adapter, and production preflight reject invalid names. Compose supplies only the
provider and resource name to API; it contains no credentials or key material. The future GCE VM
service account uses ADC and key-scoped `roles/cloudkms.cryptoKeyEncrypterDecrypter`; D2 changes no
live IAM and does not use a downloaded service-account JSON key.

Local injected-client verification covers exact resource/AAD invocation, non-empty ciphertext,
round-trip equality, returned CryptoKeyVersion metadata, old-version decrypt, permission denial,
malformed ciphertext, client failure, audit-before-decrypt, and no local fallback. Only synthetic PII
is used and error output contains neither plaintext nor ciphertext. Live KMS is deferred because no
approved test project/key/ADC is configured.

No GCS transfer, GCE provisioning, systemd, DNS/firewall/TLS mutation, legacy deletion, Terraform
state change, CI replacement, product behavior, DB schema, tenant/RLS, or LINE/LIFF change is
included. Focused D2 KMS/PII/config contracts: 85 PASS. Broader unit/security backend tests: 559
PASS. Production and B1-B4 preflights, Compose config, repository secret scan, Ruff, format, and
`git diff --check`: PASS. Migration: NONE. Commit: included in the coherent Phase D2 deployment
commit.

## Phase D3 GCS Backup Wiring and Restore Verification

Status: PARTIALLY READY. Canonical policy is `docs/deployment/gcs-backup.md`. Host-side
`gcloud storage` scripts wrap the existing B3 artifact contract; MinIO remains runtime media and no
application/Compose service receives GCS backup configuration. Upload verifies before/after transfer
and writes `_COMPLETE` last. Download requires the marker, refuses overwrite, and revalidates all
PostgreSQL and MinIO hashes before exposing fresh restore staging.

Canonical auth is the future GCE VM service account through ADC. Bucket IAM is limited to
`roles/storage.objectCreator` plus `roles/storage.objectViewer` on the specific private backup
bucket; lifecycle owns deletion. The proposed 7-day unlocked retention plus 35-day age lifecycle is
a rolling window, not exact seven-daily/four-weekly selection. Public access, JSON keys, HMAC,
Object Admin, manual production pruning, and live IAM mutation are excluded.

No approved test bucket exists. A filesystem-backed fake `gcloud` exercised the production scripts,
including marker ordering and incomplete/corrupt rejection. The isolated `strayhub-d3-verify` drill
created a real PostgreSQL dump and MinIO artifact, uploaded them, removed local staging, downloaded
fresh, and restored the synthetic row, Alembic head, RLS/runtime-role checks, MinIO key, bytes, and
inventory checksum. This is local end-to-end evidence, not live GCS acceptance.

No real GCE, systemd, DNS/firewall/TLS mutation, runtime GCS migration, legacy deletion, Terraform
state change, CI replacement, product behavior, DB schema, tenant/RLS, or LINE/LIFF change is
included. Focused GCE/D3 contracts: 57 PASS. Repository secret scan, Ruff, format, and
`git diff --check`: PASS. Migration: NONE. Commit: included in the coherent Phase D3 deployment
commit.

## Phase E1 GCE Provisioning — Live Apply

Status: READY after controlled idempotency replacement. Confirmed account `b97502027@gmail.com`, project
`canvas-primacy-502703-k1`, region `asia-east1`, and zone `asia-east1-b`; both location resources are
UP. Read-only inventory found two unrelated us-central1 VMs/static IPs on the default VPC, no
asia-east1 target collision, no Cloud Run service or bucket, and disabled Secret Manager/KMS/Cloud
SQL Admin APIs. No API was enabled.

The new isolated `infra/gce/terraform/` plan owns only a custom VPC/subnet, public 80/443 firewall,
IAP-only SSH firewall, reserved regional IPv4, dedicated keyless VM service account, and one
`e2-medium` Ubuntu 24.04 LTS VM with a 30 GiB `pd-balanced` auto-delete boot disk and 2 GiB persistent
swap. Host bootstrap installs Docker/Compose and creates protected paths but deploys no app or
secret. Local bootstrap state is ignored; a dedicated remote backend remains required before apply.

Terraform provider `hashicorp/google` is locked to v6.50.0. The reviewed `7 to add, 0 to change, 0
to destroy` plan applied successfully. The live VM is `RUNNING` at reserved IP `34.81.77.204` with
the expected isolated network, firewall, disk, keyless service account, and no legacy impact.

IAP, Ubuntu 24.04, Docker 29.7.2, Compose v5.5.0, hello-world, host paths, 2 GiB swap, outbound
connectivity, ADC identity, and intended sockets passed. The original reset exposed a bootstrap
repeat failure: GPG attempted an interactive overwrite of the Docker keyring. The source fix adds
`--batch --yes`; startup-script ForceNew semantics produced a separately reviewed replacement plan.

Before replacement, the VM had no app, database, MinIO, secret, backup, Docker volume, or production
data. The exact saved `1 add, 0 change, 1 destroy` plan replaced only the VM, changing instance ID
`5710279376629586026` to `5310649467353876523`. Reserved IP `34.81.77.204`, VPC, subnet, firewalls,
and service account persisted. First startup, an explicit second bootstrap execution, and one
post-replacement reboot all exited zero; fstab and Docker repository entries remained singular,
Docker/Compose, swap, protected paths, and ADC remained healthy. Final Terraform plan: no changes.

No Cloud Run, Cloud SQL, GCS, KMS, Secret Manager, legacy IAM/state, DNS/TLS/LINE, app/schema/tenant
behavior, or migration was touched. E2/E3/E4: NOT STARTED. Focused provisioning contracts: 10 PASS.
Secret scan, Ruff, format, Terraform fmt/validate, shell syntax, and `git diff --check`: PASS. Commit:
not created.

## Phase E2 Live Secret Manager / KMS / GCS Acceptance

Status: READY. Confirmed VM metadata ADC identity
`strayhub-gce-sa@canvas-primacy-502703-k1.iam.gserviceaccount.com` with no JSON credential. Newly
enabled APIs were Secret Manager and Cloud KMS; Storage was already enabled.

Eleven required `strayhub-prod-*` secrets received synthetic acceptance versions and exact
secret-level `roles/secretmanager.secretAccessor`. Live canonical fetch staged one 0700/0600 atomic
generation without logging values; a failed nonexistent-prefix fetch preserved `current`. The live
Ubuntu run found a GNU/BSD `stat` ordering bug in production preflight, which is now covered by a
contract test. Production fail-fast preflight then passed without starting the app stack.

Dedicated KMS resource
`projects/canvas-primacy-502703-k1/locations/asia-east1/keyRings/strayhub-pii/cryptoKeys/pii-encryption`
has only key-scoped Encrypter/Decrypter for the VM SA. The existing adapter passed live ADC encrypt,
decrypt, exact synthetic round trip, key-version scope, malformed-ciphertext fail-closed, and no
local fallback without logging plaintext or ciphertext.

Private bucket `strayhub-backups-canvas-primacy-502703-k1` is asia-east1, uniform-access and
PAP-enforced, with unlocked 7-day retention and 35-day age deletion. VM IAM is only bucket-scoped
Object Creator/Viewer. A six-object synthetic B3 set uploaded and revalidated before `_COMPLETE` was
written last; a fresh seven-object download restored the synthetic PostgreSQL row, Alembic head,
RLS/runtime role, two MinIO objects, bytes, and inventory checksum. The isolated stack, volumes,
source, images, and local artifacts were removed; the governed GCS acceptance set remains.

Secret/KMS/GCS resources were created with controlled `gcloud` pending canonical managed-service
Terraform/remote-state ownership review. No app deployment, systemd, DNS/TLS/LINE change, production
DB/MinIO data, legacy resource, Terraform state migration, CI replacement, or schema migration was
performed. Commit and push: NONE.

## Phase E3 systemd / Operational Supervision

Status: READY. Repo-owned systemd units define one ordered boot transaction: live Secret
Manager staging, production preflight, the existing Compose Alembic migration, canonical runtime
startup, and bounded localhost health verification. A separate oneshot uses the existing B3/D3
backup chain, with `flock` overlap rejection and a persistent daily 03:00 UTC timer.

The main stop path is bounded `docker compose stop`, never volume deletion. PostgreSQL and MinIO
named volumes remain persistent, long-running Compose services retain `unless-stopped`, and
migration/minio-bootstrap retain no-loop policies. Unit files contain no secret values or credential
JSON. The synthetic DB URL blocker was resolved with one enabled version added to each existing
database URL secret: `strayhub_app` is the restricted runtime role and `strayhub_migration` is the
migration role. No secret resource/version was deleted, no other secret changed, and the runtime
role remains non-superuser without database/role creation or `BYPASSRLS`.

Fresh secret staging, preflight, migration, and all local routes passed at Alembic head
`0037_animal_external_sources`. A systemd restart preserved the two named volumes and did not rerun
migration; an API host-PID crash recovered automatically with restart count 1. One controlled reboot
recovered Docker, secret fetch, migration, the complete runtime, the same static IP, ADC identity,
volumes, and head. Manual backup `20260830T033225Z-e3daily6182` passed local integrity, VM-ADC GCS
upload/download verification, and `_COMPLETE`; held-lock overlap rejection passed. The daily timer
is enabled/active with `Persistent=true`. Empty MinIO backup verification now reconstructs the
directory GCS cannot store before applying the unchanged strict inventory checks. Resource headroom
was healthy (2.9 GiB memory available; root disk 32% used), and no secret value was logged.

No DNS, Let's Encrypt issuance, LINE/LIFF endpoint update, public cutover, legacy cleanup, Terraform
state migration, deployment CI, product behavior, schema, or tenant/RLS change was made. IAM, KMS,
and GCS policy were unchanged. Migration: NONE. Commit and push: NONE. Phase E4: NOT STARTED.
