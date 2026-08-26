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

## Multi-shelter next use (not executed in Item 1)

```bash
uv run python -m scripts.import_moa_shelter_animals \
  --shelter "新北市五股區公立動物之家" --kind dog --limit 60 --dry-run
uv run python -m scripts.import_moa_shelter_animals \
  --shelter "新北市五股區公立動物之家" --kind dog --limit 60
```

No second importer or code change is needed. Item 2 must run these deliberately
and validate both public-shelter scopes. Wugu was **not imported** in Item 1.
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
