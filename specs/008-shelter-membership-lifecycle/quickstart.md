# Quickstart: 收容所成員封存與權限管理版型改善

## Prerequisites

- Repository root: `/Users/js/gae_cowork_project/StrayHub`
- Frontend running at `http://127.0.0.1:3000`
- API and local database running with the seed data
- Test account: `local-shelter-admin-a` / `local-only-password`

## Scenario 1: Default list and role sections

1. Open `http://127.0.0.1:3000/shelters` and sign in as the local shelter admin.
2. Confirm the page title is `權限管理`.
3. Confirm `管理人員` contains SHELTER_ADMIN and STAFF, while `志工` contains VOLUNTEER.
4. Confirm archived memberships are absent from both normal sections.
5. Confirm `建立帳號` and `查看已封存成員` are available without scrolling to the bottom.

## Scenario 2: Archive and restore

1. Choose a non-current membership and select `封存`.
2. Confirm the warning and complete the action.
3. Confirm the membership disappears from `/shelters`.
4. Open `http://127.0.0.1:3000/shelters/archived`.
5. Search by display name or username and confirm the archived membership is visible.
6. Restore it and confirm it returns to the appropriate role section on `/shelters`.
7. Verify the audit records for archive and restore contain actor, target, time, and before/after state.

## Scenario 3: Account creation modal

1. From the top of `/shelters`, select `建立帳號`.
2. Confirm the modal contains account, display name, temporary password, and role fields.
3. Close with Escape and reopen; confirm the temporary password was not retained.
4. Create a STAFF account and confirm the modal closes, the form resets, and the new account appears under `管理人員`.
5. Try a duplicate username and confirm the modal remains open with a safe error message and no password leakage.

## Scenario 4: Responsive and tenant boundaries

1. Repeat the normal and archived pages at 1440px, 768px, and 360px widths.
2. Confirm no horizontal overflow, overlapping controls, or inaccessible actions.
3. Attempt access as a non-admin role and confirm the existing denial behavior remains.
4. Confirm an archived membership from organization A cannot appear while managing organization B.

## Automated validation

```bash
./node_modules/.bin/vitest run 'app/(management)/shelters/page.test.tsx'
./node_modules/.bin/tsc --noEmit
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/contract/test_organization_management_contract.py
env UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check services/api/app/api/organization_management.py services/api/app/application/organization_management.py services/api/app/persistence/repositories/organization_repository.py
env UV_CACHE_DIR=/tmp/uv-cache uv run ruff check services/api/app/api/organization_management.py services/api/app/application/organization_management.py services/api/app/persistence/repositories/organization_repository.py
PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 npm --prefix apps/web run test:e2e -- e2e/organization-management.spec.ts e2e/p1-management.spec.ts
```

The final implementation must also add focused tests for the archived route, archive/restore authorization, last-admin protection, and the modal interaction.
