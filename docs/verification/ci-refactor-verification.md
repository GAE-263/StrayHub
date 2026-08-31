# CI Refactor Verification Record

> Historical evidence only. This record describes the retired, never-instantiated GCP Demo build
> gate at the time it was verified. Phase F6 removed that source and workflow. The commands and
> paths below must not be rerun; current release validation is owned by
> `.github/workflows/gce-release.yml` and the GCE deployment contract tests.

## Verification Identity

- Date: 2026-08-28 20:45:09–20:53:08 CST (Asia/Taipei)
- Branch: `review/system_over_all`
- HEAD: `ae0798bd4eb1d97cb0914842ee3b4e2a67fc9fb7`
- Commit: `ae0798b ci: separate demo build from quality checks`
- Working tree: DIRTY
- Verified state: HEAD plus the listed working-tree changes. The executable changes verified were
  `.github/workflows/ci.yml` and `apps/web/package.json`; `review.md` was already modified as the
  phase record. This verification document and the final link in `review.md` were added after the
  executable checks and do not alter runtime behavior.
- Changed files in the final recorded state:
  - `.github/workflows/ci.yml`
  - `apps/web/package.json`
  - `review.md`
  - `docs/verification/ci-refactor-verification.md`
- Remote GitHub Actions verification = NOT APPLICABLE. The verified state includes uncommitted
  changes, and no workflow was triggered.

## Executive Result

Overall: PASS

The local primary CI checks and deployment gate passed for the dirty state identified above. The
verification does not claim that a clean commit or a remote GitHub Actions run was tested.

## CI Ownership

| Concern           | Owner                                       | Result |
| ----------------- | ------------------------------------------- | ------ |
| Backend quality   | `.github/workflows/ci.yml` / `python`       | PASS   |
| Frontend quality  | `.github/workflows/ci.yml` / `frontend`     | PASS   |
| Contracts         | `.github/workflows/ci.yml` / `contracts`    | PASS   |
| Critical E2E      | `.github/workflows/ci.yml` / `critical-e2e` | PASS   |
| Terraform         | `.github/workflows/demo-build.yml`          | PASS   |
| Secret scan       | `.github/workflows/demo-build.yml`          | PASS   |
| API image         | `.github/workflows/demo-build.yml`          | PASS   |
| Worker image      | `.github/workflows/demo-build.yml`          | PASS   |
| Web image         | `.github/workflows/demo-build.yml`          | PASS   |
| Metadata artifact | `.github/workflows/demo-build.yml`          | PASS   |

The metadata result verifies the workflow's metadata generation and `actions/upload-artifact`
wiring. Artifact upload itself is GitHub Actions-only and was not represented as a local upload.

## Backend Verification

Commands:

```bash
uv run ruff check .
uv run ruff format --check .
STRAYHUB_TEST_DATABASE_URL=postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub \
DATABASE_URL=postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub \
  uv run pytest
```

Result: PASS

- Ruff lint: PASS.
- Ruff format: PASS; 631 files already formatted.
- Pytest: 955 collected; 953 passed, 2 explicitly environment-dependent skipped, 0 failed, 1
  warning; runtime 56.09s.
- The first unqualified pytest attempt lacked the CI-provided `STRAYHUB_TEST_DATABASE_URL`. A
  second sandboxed attempt had localhost socket access denied. The recorded result is the complete
  CI-equivalent run against the healthy local PostgreSQL 16 service outside that sandbox boundary.

## Frontend Verification

Commands:

```bash
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run format:check
npm --prefix apps/web run build
```

Result: PASS

- Vitest: 79 files and 357 tests passed; runtime 4.97s.
- TypeScript: PASS.
- Prettier: PASS.
- Next.js production build: PASS; 23 routes generated or prepared.

## Contract Verification

Command:

```bash
npm --prefix packages/contracts run check
```

Result: PASS. The generated OpenAPI TypeScript contract matched the checked-in output.

## Critical E2E Verification

Command represented by the CI script:

```bash
npm --prefix apps/web run test:e2e:critical
```

Local isolated reproduction used because an unrelated existing development server owned port 3001:

```bash
API_BASE_URL=http://127.0.0.1:8001 npm --prefix apps/web run dev -- \
  --hostname 127.0.0.1 --port 3002
PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3002 \
  npm --prefix apps/web run test:e2e:critical
```

Result: PASS

- Specs: 4.
- Tests: 20 passed, 0 failed.
- Runtime: 14.7s.
- Coverage: login, management home, active multi-shelter selection and switch isolation, volunteer
  QR/care report, and care calendar.
- The 7 stale LIFF/volunteer assertions were not substituted into this critical suite and remain
  deferred.

## Deployment Gate Verification

### Terraform

Commands:

```bash
terraform fmt -check -recursive infra/gcp-demo/terraform
terraform -chdir=infra/gcp-demo/terraform init -backend=false -input=false
terraform -chdir=infra/gcp-demo/terraform validate
```

Result: PASS. Format, backend-free initialization, and validation succeeded. Initial sandboxed
init/validate attempts were blocked by DNS/provider-plugin restrictions; the same commands passed
outside the sandbox.

### Secret Scan

The exact command from `.github/workflows/demo-build.yml` was executed:

```bash
! rg -n --hidden \
  --glob '!.git/**' \
  --glob '!node_modules/**' \
  --glob '!**/.venv/**' \
  --glob '!**/.terraform/**' \
  --glob '!**/*.lock' \
  '(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC )?PRIVATE KEY-----|LINE_CHANNEL_ACCESS_[T]OKEN=)' \
  infra/gcp-demo
```

Result: PASS; no matching secret material was found in the scoped deployment files.

### Docker Images

Commands:

```bash
docker build -f infra/gcp-demo/Dockerfile.api -t strayhub-demo-api:verification .
docker build -f infra/gcp-demo/Dockerfile.worker -t strayhub-demo-worker:verification .
docker build -f infra/gcp-demo/Dockerfile.web -t strayhub-demo-web:verification .
docker image inspect \
  strayhub-demo-api:verification \
  strayhub-demo-worker:verification \
  strayhub-demo-web:verification
```

Result: PASS

| Image                               | Image ID                                                                  |
| ----------------------------------- | ------------------------------------------------------------------------- |
| `strayhub-demo-api:verification`    | `sha256:e28bea64a27d1acf8fc5bdb52a1f960222b9d52047fb127e4483dae4d7808f61` |
| `strayhub-demo-worker:verification` | `sha256:461c6663ad1cd40e55d75926f122a5781b940e37f1ae273559f0bfed3f7ba07f` |
| `strayhub-demo-web:verification`    | `sha256:63b7f43757d31c115988178ebdac601f7b99fc0be2251cfd4a6a32eb8e3b2932` |

### Metadata Artifact

Result: PASS for workflow structure. The demo gate retains `docker/metadata-action@v5`, writes
commit, image tags, and `terraform_apply=false` to `demo-build-metadata.txt`, then uploads the file
through `actions/upload-artifact@v4`. No local or remote artifact upload was claimed.

## Workflow Structure

- YAML: PASS; both workflow files parsed successfully.
- Parallelism: PASS; `python`, `frontend`, `contracts`, and `critical-e2e` have no `needs:` chain.
- Cache: PASS; uv cache is enabled, Web jobs use `apps/web/package-lock.json`, and Contracts uses
  `packages/contracts/package-lock.json`.
- Duplicate coverage: PASS. `demo-build.yml` does not run pytest, Ruff, Alembic, frontend quality,
  Contracts, PostgreSQL, setup-node/npm install, or setup-uv/uv sync. The primary `python` job keeps
  Terraform available only because the unchanged full pytest suite executes the infrastructure
  contract; the standalone deployment gate remains owned by `demo-build.yml`.
- actionlint: UNRUN — actionlint not installed.

## Deferred Items

- DEFERRED — Phase 3 PostgreSQL/RLS job split.
  - Database-free candidate: 591 tests.
  - PostgreSQL candidate: 364 tests.
  - Total: 955 tests.
  - Current markers are insufficient, and DB-dependent tests are mixed across security,
    integration, isolation, and E2E directories. No RLS or tenant-isolation coverage was reduced.
- DEFERRED — 7 stale LIFF/volunteer E2E assertions.
- DEFERRED — Full/nightly E2E.
- DEFERRED — Visual regression/nightly.
- DEFERRED — Terraform replacement until the GCP single-VM nginx deployment becomes canonical.

## Known Non-Blocking Issues

- The local PostgreSQL verification needs the same database environment variables supplied by CI.
- A user-owned development server was already listening on port 3001, so the valid critical E2E
  run used isolated port 3002 without stopping that process.
- Pytest reports one Starlette/httpx deprecation warning.
- Vitest reports Vite's CJS Node API deprecation warning.
- Docker's Web dependency installation reports 7 npm audit findings (4 moderate, 2 high, 1
  critical); dependency remediation is outside this CI verification task.
- Remote GitHub Actions status is unavailable for an uncommitted working-tree state.

## Evidence Summary

| Check                      | Result | Evidence                                                      |
| -------------------------- | ------ | ------------------------------------------------------------- |
| Repository identity        | PASS   | Branch, full HEAD SHA, commit message, and dirty files listed |
| Backend lint/format        | PASS   | Ruff lint; 631 formatted files                                |
| Backend tests              | PASS   | 953 passed, 2 skipped, 0 failed in 56.09s                     |
| Frontend tests             | PASS   | 79 files, 357 tests in 4.97s                                  |
| Frontend type/format/build | PASS   | TypeScript, Prettier, and Next.js production build            |
| Contracts                  | PASS   | Generated OpenAPI TypeScript matched                          |
| Critical E2E               | PASS   | 4 specs, 20 tests, 0 failed in 14.7s                          |
| Workflow YAML/structure    | PASS   | Parsed; jobs parallel; caches and ownership verified          |
| actionlint                 | UNRUN  | Tool is not installed                                         |
| Terraform                  | PASS   | fmt, init without backend, validate                           |
| Secret scan                | PASS   | Exact workflow scan returned no matches                       |
| API image                  | PASS   | Verification image built and inspected                        |
| Worker image               | PASS   | Verification image built and inspected                        |
| Web image                  | PASS   | Verification image built and inspected                        |
| Metadata artifact wiring   | PASS   | Metadata generation and upload steps retained                 |
| Remote GitHub Actions      | N/A    | Uncommitted verified state; no workflow triggered             |

## Reproduction

From the repository root with uv, Node.js, Terraform, Docker, Chromium, and a healthy local
PostgreSQL service available:

```bash
uv run ruff check .
uv run ruff format --check .
STRAYHUB_TEST_DATABASE_URL=postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub \
DATABASE_URL=postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub \
  uv run pytest

npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run format:check
npm --prefix apps/web run build
npm --prefix packages/contracts run check
npm --prefix apps/web run test:e2e:critical

terraform fmt -check -recursive infra/gcp-demo/terraform
terraform -chdir=infra/gcp-demo/terraform init -backend=false -input=false
terraform -chdir=infra/gcp-demo/terraform validate

! rg -n --hidden \
  --glob '!.git/**' \
  --glob '!node_modules/**' \
  --glob '!**/.venv/**' \
  --glob '!**/.terraform/**' \
  --glob '!**/*.lock' \
  '(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC )?PRIVATE KEY-----|LINE_CHANNEL_ACCESS_[T]OKEN=)' \
  infra/gcp-demo

docker build -f infra/gcp-demo/Dockerfile.api -t strayhub-demo-api:verification .
docker build -f infra/gcp-demo/Dockerfile.worker -t strayhub-demo-worker:verification .
docker build -f infra/gcp-demo/Dockerfile.web -t strayhub-demo-web:verification .
docker image inspect \
  strayhub-demo-api:verification \
  strayhub-demo-worker:verification \
  strayhub-demo-web:verification
git diff --check
```

## Final Assessment

CI REFACTOR VERIFIED
