# Animal profile V1

## Purpose and data model

Animal identity and its stable QR binding stay on the existing tenant-owned
`animals` table. Migration `0036_animal_profile` follows
`0035_care_report_handoffs` and adds only these columns:

| Field | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| sex | varchar(10) | no | unknown | `male` / `female` / `unknown`; UI 公 / 母 / 未知 |
| breed | varchar(120) | yes | null | Source or shelter wording; no taxonomy |
| intake_date | date | yes | null | Entry into the current shelter |
| birth_date | date | yes | null | Exact or estimated birth date |
| birth_date_estimated | boolean | no | false | Birth date is an estimate |
| age_description | varchar(120) | yes | null | Source wording when date is unavailable |
| behavior_notes | text | yes | null | Management-facing descriptive behavior |
| care_guidance | text | yes | null | Safe operational instructions for volunteers |

Existing rows remain valid without a profile. No data is reinterpreted or
destructively rewritten, and RLS policies, tenant keys, animal IDs, shelter
numbers, QR bindings, photos and CareReport snapshots remain unchanged.
Downgrade drops only the new profile columns/constraints and therefore loses
profile data; do not run it against populated production profiles without backup.

## Birth date and age

No mutable integer age is stored. Both management and volunteer views use
`apps/web/lib/animal-profile.ts` to calculate completed years (or months for
animals under one year) from calendar dates. An injectable `today` argument keeps
tests independent of real time. Exact dates display e.g. `5歲`; estimated dates
display `約5歲`. When birth date exists it takes display precedence over
`age_description`. Otherwise display the description, or `未知` if neither exists.
The form explains this precedence; clearing a nullable field sends `null`.

An age lower bound such as `5歲以上` is not enough to derive a birth date. The
FurKids seed leaves all birth dates null and estimated flags false.

## Validation

`services/api/app/domain/animal_profile.py` owns the typed profile and PATCH input.
Text is trimmed, blank-only strings are rejected, short text is bounded at 120
characters and notes at 4000. Notes retain internal line breaks and render as
plain text, never HTML. Explicit null clears nullable fields; omitted fields
remain unchanged. Unknown request keys (including organization, animal identity,
status and photo keys) are rejected.

Dates are typed DATE values. When both dates exist, birth must be on/before
intake. An estimated flag requires a birth date. The complete merged profile is
validated under a row lock, including when only one date is patched. These two
relationships and the sex enum also have database CHECK constraints. There is
no wall-clock future-date restriction; UI renders future birth dates as unknown.

## API, authorization and audit

- `GET /v1/management/animals`: paginated `{items, page, page_size, total}`.
- `GET /v1/management/animals/{animal_id}`: `{animal: ManagementAnimal}`.
- `PATCH /v1/management/animals/{animal_id}/profile`: `AnimalProfileUpdate`
  input, `{animal: ManagementAnimal}` output.
- Existing `PATCH /v1/management/animals/{animal_id}` remains the status-only
  operation with required reason and reminder suspension. Profile updates never
  call or bypass that status logic.

All three profile operations reuse `current_request_context`,
`require_staff_or_admin`, the verified current organization, tenant-filtered
queries and existing PostgreSQL RLS. Authorized roles are STAFF, SHELTER_ADMIN,
and PLATFORM_ADMIN with a verified organization context. A foreign-tenant animal
returns the same safe 404 as an absent animal; volunteers cannot use the manager
update endpoint. No client-provided organization is accepted.

`ManagementAnimalService.update_profile()` obtains `SELECT ... FOR UPDATE`, merges
only provided profile fields, validates, writes and records `animal.profile_updated`
through `AuditService`. The audit contains meaningful JSON before/after values,
actor, organization and animal ID, in the same committed transaction. No-op
updates do not create a redundant audit. Invalid merged profiles return
`invalid_animal_profile` / 422; request schema errors use existing validation
handling. Internal callers pass the already-authorized actor and tenant.

Management responses include all profile fields, existing `photo_key`, an optional
five-minute `photo_url` signed using the existing tenant-scoped media service, and
`area_path` (parent/current area within the same organization). Photo failure does
not block reading the animal profile. Canonical OpenAPI now also correctly
describes the existing `{animal: ...}` detail envelope and actual identity/area
keys; this is a contract correction, not a runtime envelope change.

## Safe volunteer boundary

`AnimalCandidateResponse` explicitly exposes only these new profile fields on
list/search, QR resolution and confirmation: `sex`, `breed`, `birth_date`,
`birth_date_estimated`, `age_description`, `care_guidance`.

`behavior_notes` is management-only; it is not included by generic ORM dumps.
`care_guidance` is deliberately volunteer-visible and must contain safe practical
instructions, not private staff notes. Medical history, diagnoses and internal
profile notes are not exposed on confirmation cards. Intake date remains a
management field. Existing UUID transport fields are not displayed to volunteers.

Authorization, active animal/QR checks, effective membership/grant checks,
confirmation token binding and handoff creation/consumption semantics are
unchanged. The LINE Bot questionnaire and CareReportDraft/submission code are
outside this item.

## UI and accessibility

Management list adds a small photo and breed/sex summary without long notes.
`AnimalBasicProfile` adds the full profile before the existing care workspace.
Its form uses shared Field/Input/Select/Textarea/Button components, Traditional
Chinese labels and explicit visibility help. Save returns focus to the edit
button and announces success. Validation errors receive focus and use `role=alert`.
Warnings combine a heading, icon and text, never color alone. Full shelter numbers
are retained, including on narrow screens. No media gallery is added.

## Verification (2026-08-26)

The realistic local PostgreSQL database was upgraded from
`0035_care_report_handoffs` to `0036_animal_profile` with `uv run alembic upgrade head`.
`uv run alembic current` confirmed the new head. Downgrade was not run against
the populated demo database. Existing animals, QR bindings, original photo
checksums and medical/report/reminder counts were preserved.

The focused backend/security/contract suite passed (65 tests):

```bash
uv run pytest \
  tests/unit/test_animal_profile.py \
  tests/integration/test_animal_profile_api.py \
  tests/integration/test_management_animals.py \
  tests/integration/test_scope_free_animal_selection_api.py \
  tests/unit/test_animal_selection_application.py \
  tests/unit/test_animal_selection_repositories.py \
  tests/unit/test_seed_furkids_demo.py \
  tests/isolation/test_care_report_handoff_rls.py \
  tests/isolation/test_cross_tenant_resource_matrix.py \
  tests/contract/test_animal_profile_contract.py \
  tests/contract/test_animal_selection_contract.py \
  tests/contract/test_management_workbench_contract.py \
  tests/contract/test_generated_contract_types.py \
  tests/contract/test_openapi_contract.py -q
```

The profile integration test exercises actual PostgreSQL CHECK constraints,
HTTP read/update validation, no-op and nullable PATCH behavior, audit before/after,
volunteer denial, a non-bypass runtime RLS role, foreign-tenant read/write denial,
connection reuse and unchanged status/reminder suspension. It rolls back its
fixtures. Authentication and authorization dependencies are reused unchanged.

Other passing commands:

```bash
npm --prefix apps/web run test                    # 318 tests
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
npm --prefix apps/web run format:check
npm --prefix packages/contracts run check
uv run ruff check services/api/app scripts tests
uv run ruff format --check services/api/app scripts tests
git diff --check
```

Browser coverage:

```bash
PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3012 \
  npm --prefix apps/web run test:e2e -- \
  e2e/animal-profile.spec.ts e2e/animal-confirmation-qr.spec.ts \
  e2e/manager-animal-qr.spec.ts
# 23 passed; server must be built with LIFF_HANDOFF_E2E_MOCK=1.

FURKIDS_PROFILE_REAL=1 PLAYWRIGHT_SKIP_WEBSERVER=1 \
  PLAYWRIGHT_BASE_URL=http://127.0.0.1:3010 \
  npm --prefix apps/web run test:e2e -- e2e/furkids-animal-profile-real.spec.ts
# 3 passed against the seeded real API/PostgreSQL/object storage.
```

Use a **fresh, isolated `.next` build** for the existing LIFF mock tests: switching
`LIFF_HANDOFF_E2E_MOCK` with a cached/concurrently served build produced harness
failures. An isolated source copy with a fresh mock build passed all 23 tests;
the working checkout was then restored to a normal non-mock production build.
Do not change application behavior to compensate for a stale test bundle.

The opt-in real-data test requires the documented local demo admin/volunteer
accounts and a web server proxying the local API. It checks all five animals at
360×800, 768×1024 and 1440×900: list photos/names/numbers, detail profile, no-change
edit/save with focus, and actual manager-issued QR deep links in volunteer
confirmation. Trace capture is disabled so real QR tokens are not retained in
traces. It does not create handoffs, change animal data or test physical LINE
device behavior. Fixture-based browser tests additionally verify invalid dates,
accessible labels, warning text, and axe checks on forms/confirmation cards.

## Deferred

Breed/species taxonomy, microchip records, adoption/sterilization workflows,
vaccination master fields, media galleries, profile history/versioning and advanced
tags are intentionally deferred. Profile notes do not replace MedicalRecord or
CareReport.
