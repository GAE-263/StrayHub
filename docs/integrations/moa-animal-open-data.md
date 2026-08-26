# MOA public-shelter animal synchronization

## Purpose and entry point

This is an operator-run external-data synchronizer, not curated demo seed data and
not a public HTTP API. It reuses Animal Profile, MediaProcessingService,
MinioStorageAdapter, QrTokenService and existing tenant scope helpers. It creates
neither users/memberships/grants nor DailyReportableScope entries. Existing
server-side volunteer authorization remains mandatory; QR possession is only a locator.

```bash
uv run alembic upgrade head
uv run python -m scripts.import_moa_shelter_animals \
  --shelter "新北市新店區公立動物之家" --kind dog --limit 60 --dry-run
uv run python -m scripts.import_moa_shelter_animals \
  --shelter "新北市新店區公立動物之家" --kind dog --limit 60
```

Use operator-controlled database/storage settings, never an HTTP caller's tenant
parameter. `--shelter` is required; only `dog` is supported; `--limit` is 1–60
(default 60). There is no all-shelters mode. Run dry-run before every new shelter.
The dry-run transaction is PostgreSQL READ ONLY; no image downloads, bucket
creation, DB mutations, QR creation, or storage writes occur. Planned update counts
compare source-managed profile fields, not image bytes (which are not downloaded).

## Official source and attribution

- [MOA animal-adoption dataset documentation](https://data.moa.gov.tw/open_detail.aspx?id=QcbUEzN6E6DL)
- [Official JSON API](https://data.moa.gov.tw/Service/OpenData/TransService.aspx?UnitId=QcbUEzN6E6DL)
- [Government dataset / license listing](https://data.gov.tw/dataset/85903)
- [Government Data Open License v1.0](https://data.gov.tw/license)

Attribution: 農業部動物保護司「動物認領養」開放資料, with retrieval/sync timestamps
retained locally. The government dataset lists the open-data license; preserve
source attribution and consult its terms for downstream reuse. StrayHub does not
claim ownership of the animal photographs or a broader independent image license.
`AnimalsCore.ashx` and third-party mirrors are not importer sources.

MOA documents `animal_id` as the unique record identifier. Its creation/update
dates describe data records, not proven shelter intake dates. The official feed
is current adoption data, not a complete historical animal lifecycle ledger.

## Selection and presence

Fetch the complete official response (maximum 32 MiB / 100,000 records); trim and
exact-match `shelter_name`, then require `animal_kind == 狗`. Require one official
`animal_shelter_pkid` for that exact shelter name. Sort valid normalized records by
`animal_update` DATE descending, then numeric `animal_id` descending; missing update
dates sort last. Import/update at most the requested limit.

Presence uses **all current target-shelter dog IDs**, not only the selected 60.
Previously imported IDs still present outside the selected window get a fresh
`last_seen_at` and remain `present`, but their profile is not updated until selected.
IDs genuinely absent become `unavailable`; their last actual `last_seen_at` remains.
Reappearing IDs become `present`. `last_imported_at` advances only on successful
selected-record synchronization. No Animal deletion or status transition occurs.

An empty/malformed dataset, zero dogs for the exact shelter, ambiguous shelter ID,
or invalid/duplicate target IDs fails closed before DB writes. Field normalization
failures are reported individually; **any** such failure disables absence transitions
for that run. A legitimate completely empty shelter therefore needs operator review;
the importer deliberately does not mark every local animal unavailable automatically.
Neither `unavailable` nor older top-60 exclusion means adopted, transferred or dead.

## Identity, persistence and migration

`AnimalExternalSource` → `animal_external_sources` (migration
`0037_animal_external_sources`, parent `0036_animal_profile`):

- `organization_id`, `animal_id`, `source`, `external_id`, `source_shelter_id`.
- `source_updated_at` nullable DATE; `last_imported_at`, `last_seen_at` UTC timestamps.
- `source_status`: `present` / `unavailable`.
- `source_snapshot`: 23 whitelisted, trimmed fields, each bounded to 1 KiB UTF-8;
  total JSON at most 32 KiB, also enforced by a database check.
- `photo_source_checksum` (original bytes SHA-256), `photo_object_key` (last importer-owned photo).
- Standard identity/audit timestamps, organization/source/status index.

Identity is `source = MOA_ADOPTION_OPEN_DATA` + official `animal_id` as `external_id`.
`uq_animal_external_identity` enforces that pair globally; `uq_animal_external_mapping`
allows one mapping per Animal/source. `fk_external_animal_tenant` enforces matching
organization/animal via the narrow added `animals(organization_id,id)` unique key.
RLS and FORCE RLS use existing organization/platform rules; normal tenant B cannot
read or write tenant A mappings. No new authentication/cross-tenant privilege exists.

Organization code is `MOA-SHELTER-<animal_shelter_pkid>`; UUID5 uses the namespace URL
`strayhub:MOA_ADOPTION_OPEN_DATA:shelter:<id>`. Animals likewise use UUID5 with
`strayhub:MOA_ADOPTION_OPEN_DATA:animal:<animal_id>`. Existing mappings preserve Animal
IDs. A conflicting organization code or external ID already bound elsewhere fails
safely: the importer never silently attaches to an unrelated shelter or transfers
an Animal across tenants. Resolve real shelter transfers separately.

Downgrade removes only the source mapping table and added Animal composite unique
constraint, not Animal Profile, Animals, MediaAssets, QR, or historical scope data.
**Back up mappings before downgrade:** they are synchronization history and photo
ownership state. Re-upgrade does not reconstruct them. Restore the backup before
resuming synchronization; stable Animal UUID collisions fail rather than duplicate
existing animals when mappings are missing.

## Field mapping and ownership

| MOA field | StrayHub destination | Normalization / ownership |
| --- | --- | --- |
| `animal_id` | external mapping `external_id` | Positive numeric identifier, not shelter number |
| `animal_shelter_pkid` | stable Organization code/ID and mapping | Exact shelter identity |
| `shelter_name` | Organization.name | Trim; initialize only, preserve existing manual name |
| `shelter_address` / `shelter_tel` | Organization.address / contact | Fill missing only; preserve manual values |
| `animal_subid` | Animal.shelter_number / name | Trim; neutral stable name = number, fallback `MOA-<id>` |
| `animal_Variety` | Animal.breed | Trim, empty → null |
| `animal_sex` | Animal.sex | M/公 → male; F/母 → female; otherwise unknown |
| `animal_age` | Animal.age_description | ADULT → 成犬; CHILD → 幼犬; otherwise null |
| `animal_update` | mapping.source_updated_at | Official date only, never intake date |
| `album_file` | validated media → current_photo_key | Content-addressed storage; policy below |
| bodytype, colour, foundplace, sterilization, bacterin, remark, caption, source dates/status | mapping.source_snapshot | Retain for provenance, not automatically volunteer-visible |

Animal name, shelter number, breed, sex and age description are **source-managed**
and refreshed on selected-record sync; local edits to those five fields may be
overwritten. Animal status, area, intake date, birth date/estimated flag, behavior
notes and care guidance are **not** overwritten. On creation these nullable fields
are null, birth_date_estimated is false, status is active. No invented names, birth
dates, intake dates, cages, MedicalRecords or care instructions. Remarks are not
promoted into care_guidance. New organizations are active, timezone Asia/Taipei,
service_area null; existing status/timezone/service_area remain unchanged.

## Images and the PNG/JPEG caveat

`album_file` is accepted only on approved official hosts (`www.pet.gov.tw`,
`asms.coa.gov.tw`) and upload paths, without credentials/query/fragment; redirects
are checked again. HTTP is upgraded to HTTPS. No arbitrary URL fetch capability.
Connect timeout 5s, per-read timeout 20s, total attempt deadline 30s, three attempts
with 0.25/0.5s backoff; retry transport errors and 429/500/502/503/504 only.
At most three images download concurrently. Image responses are limited to 10 MiB.

Decode actual bytes with Pillow: JPEG/PNG/WebP, at least 32×32, at most 40M pixels,
reject corrupt/truncated/decompression-bomb and blank/tiny placeholder images.
Known placeholder URLs are rejected. These checks cannot semantically detect
every arbitrary illustrated placeholder. Never trust extension or declared MIME.
Verified official records `455402`, `462538`, `465458` use `.png` URLs / PNG headers
but actual JPEG bytes; regression tests reproduce that mismatch without embedding
the original photos into the repository.

Raw SHA-256 selects a deterministic versioned object key:
`moa/animals/<external_id>/<source_sha256>/primary.<actual-extension>`.
MediaProcessingService receives the **detected** MIME, sanitizes metadata/EXIF and
computes the processed checksum. MinIO scopes it under `organizations/<org-id>/`.
The importer reads back storage bytes and verifies the processed checksum before
setting `current_photo_key`; MediaAsset records processed MIME, checksum and
`exif_removed=true`. Existing signed-URL APIs expose images through current tenant
authorization, without a new public API contract.

- First valid image: create MediaAsset and set primary photo.
- Same source bytes: refetch to verify source checksum, reuse existing MediaAsset
  and storage bytes after checksum verification; no unnecessary PUT/re-upload.
- Changed bytes: new deterministic version, new MediaAsset; replace importer-owned
  primary photo only after successful processing/storage. Keep previous version.
- Missing/invalid/failed image: retain last valid primary (or null on first import),
  report image failure; Animal may still import. Never fabricate a photo key.
- Primary photo changed manually away from the last importer key: preserve it.
- Missing/corrupt stored object: repair from validated official bytes; verify again.

Database and object storage are not a distributed transaction. A subsequent DB
rollback can leave an unreferenced deterministic object; it does not point an Animal
at failed data. Do not delete old versioned objects without a reference-aware cleanup
policy. Such cleanup is not part of Item 1.

## Transactions, QR and failures

`scripts/import_moa_shelter_animals.py` fetches/normalizes/downloads before beginning
the write transaction. `MoaImportService.run(...)` requires a caller-owned transaction.
It locks `moa-import:<organization code>` using PostgreSQL advisory transaction lock,
bootstraps only that Organization through the existing operator platform boundary,
then switches to organization scope for every Animal/mapping/media/QR query/write.
Animal rows are locked during updates. Each record has a SAVEPOINT; image DB writes
have a nested SAVEPOINT, so image failure can preserve the Animal. Outer commit
is one shelter run; a fatal transaction failure rolls all its DB changes back.

Active animals create/reuse QR through existing `QrTokenService.create_or_reuse`,
including its per-animal transaction lock. Existing inactive animals are not
reactivated and do not get a new QR. No raw token or signed URL is logged.
Animal creation/profile/photo updates use existing system AuditService records.

Summary includes fetched/eligible/requested/selected counts; created/updated/unchanged
Animals; total currently unavailable mappings; downloaded/reused/updated/failed
images; created/reused QR; normalization/image/record errors. `images_updated`
includes first ingestion; `images_downloaded` includes unchanged source downloads.
`animals_unchanged` ignores metadata heartbeat writes. Dry-run counts are plans.
Exit 0 = no reported errors; 2 = completed with per-record/image/normalization errors;
1 = fatal fetch/validation/DB/storage-bootstrap failure. Errors are sanitized codes,
not raw SQL, exception payloads, QR tokens or credentials.

## Implementation and tests

- CLI: `scripts/import_moa_shelter_animals.py`.
- Core: `application/moa_import_service.py`, `domain/moa_import.py`.
- HTTP/decode: `infrastructure/moa_open_data.py`.
- ORM: `persistence/models/animal_external_source.py`.
- Tests: `tests/unit/test_moa_import.py`, `tests/integration/test_moa_import.py`.

Integration tests use `STRAYHUB_TEST_DATABASE_URL`, real PostgreSQL with
`SET LOCAL ROLE strayhub_runtime`, rolled-back fixtures and a one-connection pool.
Migrate the dedicated test DB first. Include existing media/QR/RLS regressions.
Public request/response schemas are unchanged. Real imported shelter-number names
exposed a 360px profile/QR-card intrinsic-width overflow: one scoped
`.animal-profile-page { overflow-wrap: anywhere; }` rule fixes it, with a RED→GREEN
CSS contract test. No UI redesign or conversation changes were made.

The opt-in `tests/integration/test_moa_import_migration.py` accepts only a localhost
`strayhub_moa_*` disposable database through `STRAYHUB_MOA_MIGRATION_TEST_URL`.
It snapshots all other tables, downgrades to 0036, upgrades to 0037, proves their
contents unchanged, restores its in-memory mapping backup and checks FORCE RLS.
Never point migration round-trip tests at the live demo database.

## Reusable multi-shelter commands

```bash
uv run python -m scripts.import_moa_shelter_animals \
  --shelter "新北市五股區公立動物之家" --kind dog --limit 60 --dry-run
uv run python -m scripts.import_moa_shelter_animals \
  --shelter "新北市五股區公立動物之家" --kind dog --limit 60
```

No second importer or code change is needed. Wugu was **not imported** in Item 1;
Item 2 executed the commands above, with results and remaining blockers below.
Defer body size, coat color, found place, sterilization/vaccination modeling and
source-unavailable → Animal lifecycle decisions to explicit product work.

## Xindian demo verification — 2026-08-26

This is MOA-synchronized public data, separate from the curated FurKids demo
provenance in `docs/demo/furkids_demo_dataset.md`.

- Branch `demo/data_collection`; previous Alembic head `0036_animal_profile`.
- Official response: 8,258 records; exact Xindian dog set: 224; selected/imported: 60.
- Organization: 新北市新店區公立動物之家 / `MOA-SHELTER-51` /
  `af6b2409-bc91-5f5a-bdd3-2f3d51775a95`; 新北市新店區安泰路235號;
  02-22159462; Asia/Taipei.
- Dry-run: 60 planned creates, zero writes/downloads/errors.
- First real run: 60 Animals, 60 media ingestions, 60 QR created; no errors.
- Identical second run: 0 created/updated Animals, 60 unchanged; 60 media reused,
  0 media uploads/updates; 60 QR reused, 0 created; no errors/unavailable records.
- PostgreSQL metadata migration: dedicated DB upgrade/downgrade/upgrade successful;
  real runtime-role RLS and pool reuse covered by tests. Local demo upgraded only.
- Populated round-trip test: PASS (1 test); hashes of all non-mapping tables remain
  identical across downgrade/re-upgrade, 60 mapping rows restored from test backup,
  RLS + FORCE RLS retained. Main demo remains at `0037_animal_external_sources`.
- All 60 MinIO objects: processed SHA-256 matches MediaAsset, decoded JPEG, no EXIF;
  59 original URLs end `.png`; signed URL GET = 200. No credentials/URLs logged.
- Browser verification uses a dedicated DB copy (60 Xindian / 5 FurKids animals),
  temporary test identities there, and existing MinIO images; no demo user permission
  changes. Xindian list has 3 pages × 20 animals; all 60 thumbnails load, final
  next-page button disables. FurKids switch shows only its 5 curated animals.
  At 360×800 and 1440×900 the corrected profile, complete shelter number, real photo
  and QR preview fit without document overflow. The existing server-generated QR
  resolves to the volunteer confirmation card with correct shelter, complete number,
  sex/breed/age and loaded MinIO photo at both exact viewports. This is browser UI
  validation, not a physical-device scanner/sendMessages test.
- Full Vitest: 319/319; TypeScript check and isolated production build pass.
  Focused backend importer/media/QR/RLS suite: 52 passed (including real EXIF input
  cleanup tests for JPEG/PNG/WebP). Ruff check/format and
  `git diff --check` pass. CSS-only regression is separate from importer logic.
- Browser screenshots: `/tmp/strayhub-moa-browser-1mAHYp/` (local ephemeral evidence).
  Temporary API/web processes were stopped; temporary users/memberships in the
  disposable DB deactivated. The main demo's users/permissions were not changed.

## Wugu Item 2 verification — 2026-08-26

Initial Item 2 status was **PARTIALLY READY**: data/object/database isolation passed,
but runtime HTTP/UI exposed shared authentication scope defects. The authorized
follow-up below fixes those defects without changing the importer, QR/LINE behavior,
production frontend, schema or RLS policies. See the final verification results below.

### Exact official identity and dry-run

- Exact `shelter_name`: 新北市五股區公立動物之家 (no fuzzy match).
- `animal_shelter_pkid`: `58`; stable code `MOA-SHELTER-58`.
- Organization ID: `565254ea-5f3c-5f07-8255-354a61a0a94b` (different from Xindian).
- Address: 新北市五股區外寮路9-9號; phone: 02-82925265; timezone: Asia/Taipei.
- Official feed: 8,258 records; exact Wugu dog set: 327; selected/imported: 60.
- Dry-run: 60 planned Animal creates, 0 profile updates, 60 planned image downloads,
  60 expected QR creates / 0 reuse (all selected animals new), 0 normalization errors.
  The existing CLI's `qr_created=0` and `images_downloaded=0` in dry-run are actual
  side-effect counters, not planned counts. There were no DB or MinIO writes.

### Real import and idempotency

| Counter | First run | Identical second run |
| --- | ---: | ---: |
| Animals created | 60 | 0 |
| Animals updated | 0 | 0 |
| Animals unchanged | 0 | 60 |
| Source unavailable | 0 | 0 |
| Images downloaded | 60 | 60 |
| Images ingested/updated | 60 | 0 |
| Images reused | 0 | 60 |
| Image / record failures | 0 | 0 |
| QR created | 60 | 0 |
| QR reused | 0 | 60 |

All Animal, external mapping, MediaAsset and QR IDs were captured after the first
run and compared after the second: identical, no duplicates. No DailyReportableScope
entries were introduced. Item 1 source ownership and lifecycle rules are unchanged.
Two additional real-PostgreSQL importer tests prove identical name/number/breed/sex
in distinct shelters do not collide, and missing names use distinct official-ID
fallbacks. Existing complete-set-vs-top-window presence regression still passes.

### Separate counts and storage isolation

| Shelter | Animals | MOA mappings | MediaAssets | Active QR |
| --- | ---: | ---: | ---: | ---: |
| FurKids | 5 | 0 | 5 | 5 |
| Xindian | 60 | 60 | 60 | 60 |
| Wugu | 60 | 60 | 60 | 60 |

Before/after complete row hashes for FurKids and Xindian Animals, external mappings
(including source status and timestamps), MediaAssets and QR are identical.
Wugu synchronization did not touch their records, source state or identities.

All 125 tenant-scoped MinIO objects were read and matched their existing MediaAsset
SHA-256, decoded successfully and contained no EXIF. Wugu's 60 photos are JPEG;
57 original URLs end `.png`. This is the known Item 1 format caveat, not a new
shelter-specific case. No extra image logic was required. Object keys and stable
MediaAsset IDs remained distinct; source disappearance did not delete any Animal.
No signed URLs or storage credentials are included in this report.

### Runtime RLS verification

`tests/isolation/test_moa_three_shelter_rls.py` is a read-only opt-in test for a DB
containing the documented 5/60/60 fixture. It checks all six directed shelter pairs
for Animals, external mappings, MediaAsset and Animal QR, using unfiltered SELECTs
under `SET LOCAL ROLE strayhub_runtime`, with explicit assertions that the role is
neither superuser nor BYPASSRLS. It also checks direct foreign-tenant filters return
zero rows and reuses the same physical pool connection across organization scopes.

```bash
MOA_THREE_SHELTER_TEST=1 STRAYHUB_TEST_DATABASE_URL=<local-test-dsn> \
  uv run pytest tests/isolation/test_moa_three_shelter_rls.py -q
```

Result: **PASS**, including the actual demo database; all six directions denied.
This proves database resource isolation, not successful HTTP context switching.

### Initial HTTP / browser blocker (historical; fixed in follow-up)

A new disposable DB `strayhub_moa_item2_20260826` was migrated to existing head 0037
and populated only with copies of the three shelters' animal/media/QR data.
Synthetic admin access to all three and Xindian-only, Wugu-only, and multi-shelter
volunteer access were created only in this disposable DB. The verification API used
`strayhub_runtime` on its connections; tenant RLS was never disabled.

1. Fresh DB provisioning lacks runtime grants for tables created in migration 0002
   before 0003's ALTER DEFAULT PRIVILEGES. Login initially fails HTTP 503 with
   PostgreSQL 42501 `permission denied for table users`. The test DB alone received
   SELECT/UPDATE on `users` and SELECT/INSERT/UPDATE on `session_records` and
   `refresh_token_records`. This is a fixture prerequisite, **not** a production fix.
2. With those ACLs, login succeeds, but `PUT /v1/auth/active-shelter-context` fails
   HTTP 503 / PostgreSQL 42501: `new row violates row-level security policy for table
   "audit_records"`. `ActiveShelterContextService.switch()` verifies access and
   changes the SessionRecord, then inserts target-organization audit data without
   changing the DB scope to that target. Initial selection remains auth-user scope;
   a cross-shelter switch retains the previous organization scope. The existing
   audit RLS correctly rejects the target write.

Relevant implementation: `application/authentication/context_service.py`,
`api/authentication.py`, `api/dependencies.py`, and the policy in migration 0005.
The user subsequently authorized a shared authentication/context-switch correction;
it is not a Wugu importer/schema defect. Do not grant BYPASSRLS, disable audit RLS,
skip auditing, or use an owner-role API to report a successful runtime verification.
The demo database's permissions and users were not modified.

At that initial checkpoint, management organization switching, stale-row checks, per-shelter UI
pagination, Wugu profile/QR previews, volunteer own-QR success/foreign-QR denials,
and explicit multi-shelter volunteer switching at 360×800/1440×900 were **blocked
or unverified**. The initial browser reached only the login screen. Error responses
observed contained no animal details, but this was not a
replacement for the requested complete allow/deny matrix. Imported data and the
independent PostgreSQL checks remain valid.

### Regression and next action

- Focused backend suite: **64 passed**, including MOA normalization/import integration,
  image sanitization, three-shelter RLS, management/profile, animal selection, QR and
  existing handoff RLS tests.
- Full Vitest: **319/319 passed**; TypeScript check passed. Frontend unchanged.
- Ruff check and format check for `services/api/app scripts tests` passed (419 files
  already formatted); `git diff --check` passed.
- Alembic remains `0037_animal_external_sources`; no migration was added.
- Local evidence (ephemeral): `/tmp/strayhub-moa-item2-evidence/` holds official
  identity, before/after hashes and stable-ID snapshots. Verification scripts in
  `/tmp/moa_item2_*.py` are local test harnesses, not alternative importers.
- Temporary verification API/web processes were stopped and synthetic users and
  memberships deactivated. Existing demo services were left running.

Reproduce the focused backend run against the disposable three-shelter test DB:

```bash
MOA_THREE_SHELTER_TEST=1 STRAYHUB_TEST_DATABASE_URL=<local-test-dsn> uv run pytest \
  tests/unit/test_moa_import.py tests/integration/test_moa_import.py \
  tests/unit/test_media_sanitization.py tests/isolation/test_moa_three_shelter_rls.py \
  tests/integration/test_management_animals.py tests/integration/test_animal_profile_api.py \
  tests/unit/test_animal_selection_application.py tests/unit/test_animal_selection_repositories.py \
  tests/integration/test_scope_free_animal_selection_api.py tests/unit/test_qr_token_service.py \
  tests/unit/test_qr_management.py tests/unit/test_qr_deep_link.py \
  tests/security/test_qr_token_tampering.py tests/isolation/test_care_report_handoff_rls.py -q
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
uv run ruff check services/api/app scripts tests
uv run ruff format --check services/api/app scripts tests
git diff --check
```

The follow-up below replaces the initial blocker status. Retain the completed Wugu
import; do not re-seed or duplicate animals. Product deferrals remain body size, coat color, found place,
sterilization/vaccination modeling, source-unavailable lifecycle semantics and
broader public-shelter rollout.

## Authorized context-switch correction and Wugu verification — 2026-08-26

The shared ordering correction is documented in
`specs/001-volunteer-care-report/research.md`, Decision 10. In short: validate the
trusted user/session, verify target membership/grant in exact auth-user/org scope,
establish target tenant scope, update session, write target audit, commit once.
Audit or commit failure rolls everything back; the next request reconstructs scope
from the unchanged persisted session. No platform privilege or RLS bypass is used.

Two related runtime-only blockers were also corrected at the existing auth boundary:
current volunteer requests must read grants in exact auth scope; login/refresh and
`GET /v1/organizations` reuse effective own-organization enumeration so the selector
shows all, and only, currently authorized shelters. The selector does not silently
switch or confer foreign-resource access. API schemas are unchanged; canonical/runtime
OpenAPI descriptions and generated comments are synchronized. No LINE questionnaire,
WebhookSession, QR producer, importer or production UI code was changed.

### Runtime provisioning and environment boundary

`scripts/configure_runtime_role.py` checks role privileges, tenant-table DML and
RLS/FORCE RLS. Its explicit `--apply` grants only SELECT/INSERT/UPDATE on `users`,
`session_records`, `refresh_token_records`, created before 0003 default privileges.
The role remains `strayhub_runtime`, non-owner, non-superuser and NOBYPASSRLS.
The setup is wired into `demo.sh` and `verify_local.sh` after migration.

The fresh-DB regression fixture proves nine missing grants, applies the setup and
checks idempotency. The synthetic-only verification DB was repaired. **The existing
demo DB received only a read-only audit and still lacks those nine grants**: applying
credential/session-table ACLs there was not permitted in this run. An authorized
operator must approve/apply setup before running that database with the runtime role.
No owner-role API was used to make any verification pass. No deployment, demo service
restart, real-account changes or migration occurred; Alembic remains 0037.

### Completed runtime HTTP checks

Against the dedicated three-shelter copy using `strayhub_runtime` and synthetic
non-platform accounts:

- FurKids list: 5; Xindian: 60; Wugu: 60, no mixed organization IDs.
- Xindian/Wugu pagination independently returns 20/20/20 unique animals.
- Three sample profiles and active QR per shelter return matching server-side identity.
- All six directed pairs deny foreign animal detail, QR and MediaAsset access.
- Xindian-only and Wugu-only volunteers resolve/confirm their own animals; foreign
  QR resolution, candidate authorization and direct confirmation deny safely; foreign
  shelter-number search returns no animals. No foreign animal ID/name in errors.
- Multi-shelter candidate response includes only organization ID/name, preserves
  Xindian context and denies immediate Wugu resolution; explicit switch permits it.
- No DailyReportableScope rows required or created. Four-resource RLS and pooled
  connection checks also pass independently on the actual demo DB.

### Automated regression results

- Focused backend/auth/import/contract/RLS suite: 139 passed.
- Additional organization/volunteer/LINE/LIFF regressions: 27 passed.
- Final fresh-DB context-switch suite: 7 passed (six included in the earlier focused suite,
  plus the final persisted three-shelter HTTP switching regression).
  Includes target audit metadata, unauthorized target, audit failure after flush,
  commit-time FK failure, old-context preservation, revoked grant and one physical
  runtime connection reused across requests. Each fixture DB is removed afterward.
- Full Vitest: 319/319; typecheck and ordinary production build: PASS.
- Focused Playwright: 27/27 on an isolated dev server with `LIFF_HANDOFF_E2E_MOCK=1`.
  Existing context-label/timeline-link assertions were updated to current UI text;
  a failed-switch mock now preserves the original context. Added delayed-old-tenant
  request regression across A → B → A. Production UI unchanged.
- The initial Playwright run on the ordinary production build failed three SDK-mock
  scenarios plus the two stale text assertions. The isolated production cache also
  failed to include the mock; a fresh dev compilation correctly ran all SDK cases.
  These initial failures are not claimed as passes or fixed with production changes.
- Ruff check/format and `git diff --check`: PASS. Generated contract parity: PASS.

Playwright reproduction (separate test server only; do not use SDK mock for demo):

```bash
LIFF_HANDOFF_E2E_MOCK=1 npm --prefix apps/web run dev -- --port 3012
PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3012 \
  npm --prefix apps/web run test:e2e -- e2e/management-shell.spec.ts \
  e2e/management-core.spec.ts e2e/organization-management.spec.ts \
  e2e/animal-confirmation-qr.spec.ts
```

### Actual browser verification (ordinary build, real runtime API)

The in-app browser used the ordinary production build, not the LIFF mock server,
against the synthetic-only DB and `strayhub_runtime` API:

- Management selector: FurKids → Xindian → Wugu → FurKids, correct label and
  matching rows after each switch, no 503. Returning to FurKids showed exactly
  the original five and no imported-shelter rows.
- Both public-shelter lists: three pages × 20, independently at 1440×900 and
  360×800. All 60 photos per shelter loaded, no document horizontal overflow;
  the existing table retains its own scrollable area on narrow screens. Full
  shelter numbers remain visible in the name/profile, and pagination is usable.
- Three Wugu profiles opened with correct name/number, breed, sex, age, photo and
  one active QR preview. Phone QR label wraps long names/numbers without clipping;
  the first profile and volunteer confirmation card fit both exact viewports.
- Wugu-only synthetic volunteer opened its real QR deep link and saw the matching
  Wugu confirmation card/photo/profile without DailyReportableScope.
- Multi-shelter volunteer started in Xindian. Wugu QR showed an explicit switch
  dialog and no animal identity. Cancel kept Xindian; reopening reloaded the same
  server-side Xindian context. Confirm switched to Wugu and then exposed the correct
  animal confirmation card. No silent switch, questionnaire, LINE message or report
  submission was performed during this browser validation.

Code and synthetic-environment verification are complete. Operational caveat:
existing demo identity/session ACL application remains pending explicit operator
approval, as described above; it is not silently reported as repaired.
Final status: **PARTIALLY READY** solely for this existing-demo ACL application;
the code fix and requested synthetic runtime HTTP/UI/QR isolation checks passed.
All verification API/web/mock-server processes were stopped, browser viewport
restored, and synthetic users/memberships deactivated. Existing demo services and
real users were left unchanged. The completed Wugu import was not repeated.
