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
Next phase safe: YES technically; Phase 2 remains explicitly prohibited by the baseline-repair request.

## Phase 2 — Demo build deduplication

- [ ] Remove duplicated backend quality
- [ ] Remove duplicated frontend quality
- [ ] Remove duplicated contracts check
- [ ] Keep deployment-specific checks
- [ ] Keep Terraform for now

Status: Not started; explicitly prohibited by the CI baseline-repair request.
Files changed: None yet.
Commands run: None yet.
PASS/FAIL: Pending.
Open issues: None evaluated in this baseline-only repair.
Next phase safe: NO

## Phase 3 — Integration/security split

- [ ] Evaluate backend-fast vs PostgreSQL/RLS split
- [ ] Implement only if current tests cleanly support it
- [ ] Never reduce RLS or shelter-isolation coverage

Status: Not assessed in this baseline-only repair; no CI split implemented.
Files changed: None yet.
Commands run: None yet.
PASS/FAIL: Pending.
Open issues: PostgreSQL/RLS environment and fixture coupling still requires a separate analysis.
Next phase safe: NO

## Phase 4 — Critical E2E

- [ ] Select stable critical Playwright flows
- [ ] Add required PR E2E only if deterministic
- [ ] Keep visual, broad accessibility, and full E2E out of the PR gate

Status: Not assessed in this baseline-only repair; no PR E2E gate implemented.
Files changed: None yet.
Commands run: None yet.
PASS/FAIL: Pending.
Open issues: CI service and fixture requirements must be proven sufficient before adding a gate.
Next phase safe: NO

## Deferred

- [ ] Full/nightly E2E
- [ ] Visual regression nightly
- [ ] Remove Terraform validation after GCP single-VM nginx deployment is implemented
- [ ] Replace Terraform validation with `docker compose config`, nginx configuration validation,
  production image builds, secret scanning, and deployment-script validation after that deployment
  architecture exists
