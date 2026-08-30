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
