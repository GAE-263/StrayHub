# Tasks: 收容所成員封存與權限管理版型改善

**Input**: Design documents from `/specs/008-shelter-membership-lifecycle/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/membership-lifecycle.md, quickstart.md

**Tests**: Included because the feature specification defines independent acceptance tests, authorization boundaries, responsive behavior, and regression-sensitive lifecycle rules.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare the existing contracts, route, and test surfaces for the new membership lifecycle without changing behavior yet.

- [X] T001 [P] Add the archived-membership route and API scenarios to the feature test matrix in `specs/008-shelter-membership-lifecycle/quickstart.md`
- [X] T002 [P] Record the new membership lifecycle response fields and route names in `specs/008-shelter-membership-lifecycle/contracts/membership-lifecycle.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the persisted state, migration, repository queries, and shared contracts required by every user story.

- [X] T003 [P] Add `archived`, `archived_from_status`, `archived_at`, and `archived_by_user_id` handling to `services/api/app/persistence/models/identity.py`
- [X] T004 Create the forward migration and downgrade path for Membership archive fields in `services/api/migrations/versions/0028_membership_archiving.py`
- [X] T005 [P] Add organization-scoped default and archived Membership repository queries, including User identity projection, in `services/api/app/persistence/repositories/organization_repository.py`
- [X] T006 [P] Extend the canonical Membership schemas with archive fields and archive lifecycle operations in `specs/001-volunteer-care-report/contracts/openapi.yaml` and `packages/contracts/src/openapi.ts`
- [X] T007 [P] Add contract fixtures and response assertions for archived Membership projections in `tests/contract/test_organization_management_contract.py`

**Checkpoint**: Persistence, contracts, and tenant-scoped query primitives are ready before story implementation begins.

---

## Phase 3: User Story 1 - 封存與查詢收容所成員 (Priority: P1) 🎯 MVP

**Goal**: Let a shelter administrator archive a Membership, remove it from the default list, find it on `/shelters/archived`, and restore it safely without deleting historical data.

**Independent Test**: With `local-shelter-admin-a`, archive a non-current Membership, verify it disappears from `/shelters`, find it on `/shelters/archived`, restore it, and verify its prior role/status and audit records.

### Tests for User Story 1

- [X] T008 [P] [US1] Add service tests for archive, restore, disabled-membership re-enable rules, prior-status preservation, expired/revoked-volunteer protection, self-archive rejection, and last-admin protection in `tests/unit/test_organization_management_service.py`
- [X] T009 [P] [US1] Validate default exclusion, archived listing, archive/restore audit events, and organization isolation through `tests/contract/test_organization_management_contract.py`, `apps/web/e2e/organization-management.spec.ts`, and `specs/008-shelter-membership-lifecycle/quickstart.md`
- [X] T010 [P] [US1] Add frontend route tests for archived-member search, restore action, empty state, and safe identity fallback in `apps/web/app/(management)/shelters/archived/page.test.tsx`

### Implementation for User Story 1

- [X] T011 [US1] Implement archive, restore, and disabled-membership re-enable domain rules, previous-status capture, volunteer authorization checks, and administrator safety guards in `services/api/app/application/organization_management.py`
- [X] T012 [US1] Implement organization-scoped archived listing, archive, and restore endpoints with audit events in `services/api/app/api/organization_management.py`
- [X] T013 [US1] Update Membership response serialization and generated contracts for archive metadata in `services/api/app/api/organization_management.py`, `specs/001-volunteer-care-report/contracts/openapi.yaml`, and `packages/contracts/src/openapi.ts`
- [X] T014 [US1] Add the `/shelters/archived` management route with search, role grouping, identity projection, restore feedback, and authorization error handling in `apps/web/app/(management)/shelters/archived/page.tsx`
- [X] T015 [US1] Add the normal-page archived-membership link and archive confirmation flow while keeping archived entries out of `/shelters` in `apps/web/app/(management)/shelters/page.tsx`
- [X] T016 [US1] Add end-to-end archive, archived-route lookup, restore, and last-admin protection coverage in `apps/web/e2e/organization-management.spec.ts`

**Checkpoint**: User Story 1 is independently usable and historical records remain intact.

---

## Phase 4: User Story 2 - 分區檢視工作人員與志工 (Priority: P1)

**Goal**: Present VOLUNTEER above SHELTER_ADMIN and STAFF under 工作人員, with fixed role/status ordering, muted inactive cards, counts, empty states, and role-appropriate controls on both routes.

**Independent Test**: Load normal and archived routes with mixed roles and verify every Membership appears in exactly one role section with correct controls.

### Tests for User Story 2

- [X] T017 [P] [US2] Add unit coverage for role grouping, section counts, empty states, STAFF-only medical permission controls, re-enable action, status ordering, revoked authorization labels, and muted card classes in `apps/web/app/(management)/shelters/page.test.tsx`
- [X] T018 [P] [US2] Add end-to-end assertions for management-staff and volunteer sections in `apps/web/e2e/organization-management.spec.ts` and `apps/web/e2e/p1-management.spec.ts`

### Implementation for User Story 2

- [X] T019 [P] [US2] Add reusable role labels, identity fallback, status ordering, volunteer authorization labels, and section presentation helpers in `apps/web/app/(management)/shelters/page.tsx` and `apps/web/app/(management)/shelters/archived/page.tsx`
- [X] T020 [US2] Refactor the normal Membership list into upper 志工 and lower 工作人員 sections, preserving role updates, medical permission updates, disable/re-enable behavior, and existing volunteer authorization semantics in `apps/web/app/(management)/shelters/page.tsx`
- [X] T021 [US2] Implement equivalent section order, status presentation, muted revoked cards, and empty states on the archived route in `apps/web/app/(management)/shelters/archived/page.tsx`
- [X] T022 [US2] Keep the management navigation label as 權限管理 and expose the archived route entry point from `apps/web/app/(management)/shelters/page.tsx` and `apps/web/components/management/AppSidebar.tsx`

**Checkpoint**: User Story 2 is independently readable and does not change authorization behavior.

---

## Phase 5: User Story 3 - 使用清楚且響應式的管理版型 (Priority: P2)

**Goal**: Apply a calmer administration layout inspired by established dashboard and user-list patterns while keeping the project's existing visual system and controls.

**Independent Test**: Verify `/shelters` and `/shelters/archived` at 1440px, 768px, and 360px with no horizontal overflow, overlap, or inaccessible action.

### Tests for User Story 3

- [X] T023 [P] [US3] Validate responsive and accessible behavior for both membership routes at 1440px, 768px, and 360px in `specs/008-shelter-membership-lifecycle/quickstart.md`
- [X] T024 [P] [US3] Capture stable desktop and mobile membership section/card states during browser review in `specs/008-shelter-membership-lifecycle/quickstart.md`

### Implementation for User Story 3

- [X] T025 [US3] Rework membership page layout tokens, section spacing, active/inactive card treatments, action rows, mobile stacking, and archived-page styling in `apps/web/app/globals.css`
- [X] T026 [US3] Update the normal and archived page structure to expose primary actions, section counts, search, empty states, and secondary actions with the new layout in `apps/web/app/(management)/shelters/page.tsx` and `apps/web/app/(management)/shelters/archived/page.tsx`
- [X] T027 [US3] Validate keyboard focus, semantic labels, modal focus return, and error-safe layout behavior through `apps/web/components/ui/dialog.tsx`, `apps/web/app/(management)/shelters/page.test.tsx`, and browser review

**Checkpoint**: User Story 3 is independently verifiable across the supported viewport widths.

---

## Phase 6: User Story 4 - 以 Modal 建立帳號 (Priority: P2)

**Goal**: Move account creation into a first-class modal opened from the page header, with safe validation and reset behavior.

**Independent Test**: Open the modal from the page header, create a STAFF account, verify it appears in 工作人員, and verify Escape/cancel/error behavior.

### Tests for User Story 4

- [X] T028 [P] [US4] Add unit coverage for modal open/close, Escape, focus return, password reset, validation error retention, and successful reload in `apps/web/app/(management)/shelters/page.test.tsx`
- [X] T029 [P] [US4] Add end-to-end coverage for account creation from the page header at desktop and mobile widths in `apps/web/e2e/organization-management.spec.ts`

### Implementation for User Story 4

- [X] T030 [US4] Integrate the existing accessible Dialog as the account creation modal with non-sensitive reset and submit states in `apps/web/app/(management)/shelters/page.tsx` and `apps/web/components/ui/dialog.tsx`
- [X] T031 [US4] Add the header action, modal state, form submission, error handling, and list refresh integration in `apps/web/app/(management)/shelters/page.tsx`
- [X] T032 [US4] Add modal content spacing and mobile sizing rules for account creation in `apps/web/app/globals.css`

**Checkpoint**: User Story 4 is independently usable without scrolling to the bottom of the page.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validate the complete feature against the specification, contracts, authorization rules, and quickstart scenarios.

- [X] T033 [P] Update feature-specific API and UI documentation links in `specs/008-shelter-membership-lifecycle/quickstart.md` and `specs/008-shelter-membership-lifecycle/contracts/membership-lifecycle.md`
- [X] T034 [P] Run focused Python formatting and static checks for changed backend files in `services/api/app/api/organization_management.py`, `services/api/app/application/organization_management.py`, `services/api/app/persistence/models/identity.py`, `services/api/app/persistence/repositories/organization_repository.py`, and `services/api/migrations/versions/0028_membership_archiving.py`
- [X] T035 [P] Run focused frontend typecheck, unit tests, responsive checks, accessibility checks, and formatting for changed frontend files in `apps/web/app/(management)/shelters/page.tsx`, `apps/web/app/(management)/shelters/archived/page.tsx`, `apps/web/components/management/`, and `apps/web/app/globals.css`
- [X] T036 Execute the manual archive, archived-route, restore, modal, responsive, identity, and timezone-removal scenarios in `specs/008-shelter-membership-lifecycle/quickstart.md` with the local management fixture
- [X] T037 Verify `git diff --check`, migration head `0028_membership_archiving`, tenant-scoped API behavior, and the relevant regression suite before marking `specs/008-shelter-membership-lifecycle/tasks.md` complete

- [X] T038 [P] [US1] Add contract coverage for `volunteer_authorization_status`, disabled-membership re-enable behavior, and revoked/expired volunteer rejection in `tests/contract/test_organization_management_contract.py` and `services/api/app/api/organization_management.py`
- [X] T039 [US1] Add organization-scoped latest volunteer grant status projection and re-enable guard support in `services/api/app/persistence/repositories/organization_repository.py`, `services/api/app/application/organization_management.py`, and `services/api/app/api/organization_management.py`
- [X] T040 [US2] Update normal and archived membership response types, labels, action controls, and sorting so revoked authorization is distinct from account status in `apps/web/app/(management)/shelters/page.tsx` and `apps/web/app/(management)/shelters/archived/page.tsx`
- [X] T041 [US2] Remove timezone presentation from the permission management page while retaining backend organization timezone data and unrelated settings behavior in `apps/web/app/(management)/shelters/page.tsx` and `apps/web/app/globals.css`
- [X] T042 [US2] Add focused tests for re-enable controls, section order, status order, revoked authorization presentation, and timezone removal in `apps/web/app/(management)/shelters/page.test.tsx`, `apps/web/app/(management)/shelters/archived/page.test.tsx`, and `apps/web/e2e/organization-management.spec.ts`
- [X] T043 [US3] Update the responsive and visual treatment assertions for muted disabled, expired, and revoked cards at 1440px, 768px, and 360px in `specs/008-shelter-membership-lifecycle/quickstart.md` and `apps/web/e2e/organization-management.spec.ts`
- [X] T044 [P] Update feature data model and API lifecycle documentation for separate volunteer authorization status and Membership re-enable semantics in `specs/008-shelter-membership-lifecycle/data-model.md`, `specs/008-shelter-membership-lifecycle/contracts/membership-lifecycle.md`, and `specs/008-shelter-membership-lifecycle/research.md`
- [X] T045 Verify all requirements, checklists, task completion markers, and constitution gates after implementation using the Spec-Kit analysis workflow in `specs/008-shelter-membership-lifecycle/spec.md`, `specs/008-shelter-membership-lifecycle/checklists/requirements.md`, and `specs/008-shelter-membership-lifecycle/tasks.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies; confirms the feature-specific validation surface.
- **Phase 2 (Foundational)**: Depends on Phase 1; blocks all story work because lifecycle fields and scoped queries are shared.
- **Phase 3 (US1)**: Depends on Phase 2; MVP for archive, separate route, restore, and data safety.
- **Phase 4 (US2)**: Depends on Phase 2 and integrates with the Membership projection from US1.
- **Phase 5 (US3)**: Depends on the section structure from US2 and the archived route from US1.
- **Phase 6 (US4)**: Depends on the page header structure from US3 but can be implemented after US2 if needed.
- **Phase 7 (Polish)**: Depends on all selected stories.

### User Story Dependencies

- **US1 (P1)**: Foundational only; no dependency on other user stories.
- **US2 (P1)**: Foundational plus the Membership identity projection; can start after Phase 2, with final integration after US1.
- **US3 (P2)**: Depends on the normal and archived sections existing in US1/US2.
- **US4 (P2)**: Depends on the normal page header and section structure; no new backend data model beyond the existing account endpoint.

### Parallel Opportunities

- T003, T005, T006, and T007 can proceed in parallel after the feature artifacts are present.
- T008, T009, and T010 can proceed in parallel before US1 implementation.
- T017 and T018 can proceed in parallel before US2 implementation; T019 can proceed independently of backend work.
- T023 and T024 can proceed in parallel after the layout selectors are agreed.
- T028 and T029 can proceed in parallel before US4 implementation.
- T033, T034, and T035 can proceed in parallel after implementation, followed by T036 and T037.

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 and Phase 2.
2. Complete US1 archive, archived-route query, restore, audit, and safety guards.
3. Validate with the archive/restore quickstart scenarios.
4. Stop for review before broad layout changes if the lifecycle semantics need adjustment.

### Incremental Delivery

1. Add US2 role sections while preserving the existing permission controls.
2. Add US3 responsive administration layout and visual validation.
3. Add US4 account creation modal and header workflow.
4. Run the cross-cutting validation and regression suite.

## Notes

- `[P]` marks tasks that touch different files and have no incomplete dependency.
- Every task includes an exact repository path and a story label where required.
- No task permanently deletes a User or historical record.
