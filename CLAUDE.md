# CLAUDE.md

## Project

StrayHub is a **multi-shelter animal shelter management platform**.

Main stack:

* Backend: FastAPI + Python
* Frontend: React + TypeScript
* Python environment: uv
* Local infrastructure: Docker Compose
* Deployment: Linux / GCP
* LINE integration for messaging and volunteer identity

Use the repository's existing structure and conventions as the source of truth.

## Core architecture rule

**Multi-shelter isolation is a critical requirement.**

For shelter-owned data:

* Never assume a single shelter.
* Scope queries by `shelter_id` or the project's equivalent tenant identifier.
* Verify shelter membership server-side before granting access.
* Never trust a client-supplied shelter identifier without authorization validation.
* Treat cross-shelter data exposure as a critical security bug.

Apply shelter isolation to animals, volunteers, users, staff, events, reports, and other shelter-owned resources.

## Backend

Before modifying a FastAPI feature, inspect the related:

1. Router
2. Request/response schema
3. Service/business logic
4. Repository/model/database access
5. Authentication/authorization dependencies
6. Tests
7. Frontend consumers if the API contract changes

Follow existing architecture.

Do not create a new service, repository, folder, or abstraction when an equivalent pattern already exists.

Preserve existing async/sync conventions.

## Frontend

The frontend uses React + TypeScript.

Follow existing:

* component patterns
* hooks
* routing
* state management
* API client/service layer
* TypeScript types

When backend API contracts change:

* Search for all frontend consumers.
* Update TypeScript types.
* Update API client calls.
* Verify affected frontend code still builds.

## API contracts

Changes to any of these require checking frontend/integration consumers:

* endpoint path or method
* request fields
* response fields/types
* HTTP status codes
* authentication requirements
* shelter-scoping behavior

Avoid silent breaking changes.

## Authentication

Authentication and authorization are separate.

Authorization must be enforced by the backend.

For LINE identity:

* Treat LINE user ID as an external identity only.
* Map it to an internal user/volunteer record.
* Verify shelter membership or invitation before granting shelter access.
* Keep LINE secrets and access tokens in environment variables.

## Python

Use `uv` when working with the Python environment.

Typical commands:

```bash
uv sync
uv add <package>
uv remove <package>
uv run <command>
```

Avoid system-level `pip install` unless explicitly required.

## Validation

Use targeted validation first.

Backend examples:

```bash
uv run pytest <relevant-tests>
uv run ruff check <relevant-files>
```

Frontend:

Inspect `package.json` and use the scripts actually defined by the project, such as:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

For API changes, use relevant tests or `curl` when useful.

### Formatting (required before every commit/push)

CI (`.github/workflows/ci.yml`) fails on formatting drift. Passing tests and typecheck is **not**
enough. Formatting is enforced at commit time by pre-commit hooks (`.pre-commit-config.yaml`:
`ruff format`, `ruff check`, Prettier for `apps/web`).

* One-time setup per clone: `uv run pre-commit install` (frontend hook also needs
  `npm ci --prefix apps/web`). If `git commit` says no `.pre-commit-config.yaml`, merge the latest
  `main` into your branch.
* When a hook reformats files, the commit fails on purpose: review the changes, `git add` them,
  and commit again. Do not bypass with `--no-verify`.
* Manual commands (before pushing, or if hooks are not installed):
  * Frontend: `npx prettier --write <files>` from `apps/web`, then
    `npm --prefix apps/web run format:check`.
  * Backend: `uv run ruff format <files>` and `uv run ruff check <files>`; CI also runs
    `uv run ruff format --check .`.
* Format only files you changed; do not run a whole-repo format that touches unrelated files
  (Done criteria #6).
* The full frontend CI gate is `test` + `typecheck` + `format:check` + `build`; run the first
  three locally before pushing.
* When branches are stacked (a PR based on another PR's branch), the formatting fix belongs on the
  branch that introduced the file, then merge it upward (no rebase/force-push).

## Docker

Local infrastructure may use:

```text
infra/local/
```

Use existing Compose files and service names.

Common command:

```bash
docker compose -f infra/local/docker-compose.yml ps
```

When debugging, prefer focused logs:

```bash
docker compose logs --tail=100 <service>
```

Avoid dumping unnecessary large logs into context.

## Shell scripts

Shell scripts must use Unix LF line endings.

Avoid CRLF errors such as:

```text
env: 'bash\r': No such file or directory
```

## LINE webhook

When changing LINE webhook behavior:

* Preserve `X-Line-Signature` verification.
* Keep webhook responses fast.
* Do not disable verification to bypass webhook failures.
* Consider duplicate event handling/idempotency.

## Database

Before changing schema or models:

* Inspect the existing ORM and migration tooling.
* Check relationships and tenant/shelter scoping.
* Follow the project's migration workflow.
* Consider compatibility with existing data.

For shelter-owned tables, explicitly verify tenant isolation.

## Debugging

For common API failures, check the correct layer first:

```text
404 → route / reverse proxy / path
405 → HTTP method
413 → upload/request size
422 → request validation
500 → application failure
```

Do not modify application code before identifying whether the failure is in:

```text
client
→ nginx / reverse proxy
→ FastAPI routing
→ validation
→ business logic
→ database
```

## GCE production deployment

Deployment and production-operations notes are kept in `CLAUDE.local.md` (git-ignored; this repo is public).

## Git

Before finishing substantial work:

```bash
git status
git diff
```

Do not commit, push, reset, rebase, force-push, delete branches, or discard unrelated local changes unless explicitly requested.

## Completion report

When development work is completed, report back to the user in natural Traditional Chinese as
commonly used in Taiwan (繁體中文，台灣慣用語與用字), summarizing what was implemented — not in
English.

## Done criteria

A change is complete when:

1. Requested behavior works.
2. Shelter isolation remains correct.
3. Authentication/authorization impact is checked.
4. Frontend consumers are checked for API changes.
5. Relevant validation passes.
6. No unrelated changes are included.
