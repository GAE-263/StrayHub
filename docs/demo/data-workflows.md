# Normal demo and explicit test fixtures

## Seed responsibility inventory

Inspected `seed_local.py`, its callers, test contracts, medical/timeline extensions,
and the current 0037 schema before changing bootstrap behavior.

| Category             | Existing responsibility                                                                                                           | Classification                                                                         |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| A. Login users       | local-staff-a/b, local-volunteer-a/b, local-shelter-admin-a                                                                       | MOVE TO TEST FIXTURES; demo uses dedicated demo-* identities                           |
| B. Organizations     | ORG-A, ORG-B, ORG-DISABLED                                                                                                        | MOVE TO TEST FIXTURES                                                                  |
| C. Synthetic animals | 小黑, duplicate shelter number, MVP cage; medical extension adds synthetic animals                                                | MOVE TO TEST FIXTURES                                                                  |
| D. Volunteer states  | approved, pending, rejected, future, expired, revoked, disabled; 100 manual + 1,200 all-filtered applicants; failed notifications | MOVE TO TEST FIXTURES                                                                  |
| E. LINE/session data | Ulocal-* bindings, pre-created sessions, stale webhook sessions, entry references                                                 | MOVE TO TEST FIXTURES; no real LINE identity is seeded by normal demo                  |
| F. Vocabulary        | platform categories/options with organization_id=NULL                                                                             | SHARED BOOTSTRAP; preserved by cleanup                                                 |
| G. QR/scope data     | local-mvp-qr-* and DailyReportableScope                                                                                           | MOVE TO TEST FIXTURES; real demo Animal QR comes from FurKids/importer, no daily scope |
| H. Platform fixtures | local-platform-admin + disabled admin                                                                                             | MOVE TO TEST FIXTURES; one dedicated demo-platform-admin replaces them in demo         |
| I. E2E/isolation     | shared codes/IDs, batches, permission matrices, fixed timeline                                                                    | MOVE TO TEST FIXTURES; legacy implementation/alias remains available                   |

FurKids' five source-derived animals, approved photos, curated synthetic care history
and existing demo-furkids-admin / demo-furkids-volunteer remain KEEP IN DEMO.
The MOA importer owns only shelter/animal/source/photo/QR data, never identities.

## Dependency map

- `verify_local.sh`, `verify_local_mvp.sh`, empty-database bootstrap regression,
  medical and timeline seed extensions explicitly use test fixtures.
- Backend `tests/fixtures`, auth/LINE/volunteer/security/isolation tests and
  Playwright mock fixtures retain their ORG-A/ORG-B contracts unchanged.
- `seed_local` stays a compatibility implementation for historical quickstarts,
  source-inspecting governance tests and the separate GCP test gate. It is not
  renamed or copied; `seed_test_fixtures` calls that same function.
- Normal `demo.sh` must not run the test suite: tests may intentionally create
  fictional fixtures. Run regression against a separate disposable database.

## Account decision

Normal demo has five synthetic accounts. Interactive `demo.sh` generates a new
high-entropy shared demo password for each bootstrap and withholds it by default. Use
`--reveal-demo-password` plus the interactive `REVEAL` confirmation only when a human
must see it once. A
non-interactive run must provide `STRAYHUB_DEMO_PASSWORD` through its controlled
environment; the bootstrap rotates hashes and expires existing demo sessions.

`scripts.issue_volunteer_entry_reference` now emits only `reference_id` and issuance
metadata by default. To reveal a newly issued raw reference once, run it in an
interactive terminal with `--reveal-reference` and type `REVEAL`; redirected/non-TTY
output fails closed. `scripts/demo-line.sh` likewise masks the entry-bearing LIFF
Endpoint unless `--reveal-entry-reference` is explicitly confirmed in a terminal.
Do not persist either reveal in shell transcripts, CI output, artifacts, issues, or
screenshots. Existing automation that parsed `raw_reference` from default JSON must
migrate to an approved interactive handoff; there is intentionally no non-interactive
raw-output compatibility mode.

- `demo-furkids-admin`: reuse existing account; explicit SHELTER_ADMIN membership
  in all three demo shelters for management switching. Not a platform administrator.
- `demo-platform-admin`: platform governance only; no shelter memberships.
- `demo-furkids-volunteer`, `demo-xindian-volunteer`, `demo-wugu-volunteer`:
  one effective membership and matching grant in their own shelter only.

No real PII, no extra shelter organizations, no cross-shelter volunteer grants.

## Normal Demo

```bash
./scripts/demo.sh          # bootstrap, verify, start API / Web / Worker
./scripts/demo.sh check    # same data bootstrap and verification, no servers
./scripts/demo.sh refresh  # force official MOA sync, verify, then start services
uv run python -m scripts.verify_demo_data --photos
```

Requires local Docker PostgreSQL/MinIO, uv, npm, openssl and installed dependencies.
Only APP_ENV=local/test, loopback PostgreSQL with the exact database name `strayhub`,
and loopback MinIO are accepted. No cloud credentials/deployment are involved.
`DEMO_SKIP_DOCKER=1` reuses already running local infrastructure. Override
Connection host/port/credentials, MINIO_BUCKET, API_PORT and WEB_PORT may be overridden
for a fresh-machine simulation, but the database name must remain exactly `strayhub`.

Order: local safety check → Docker → existing Alembic head → runtime-role setup →
FurKids → verified-local MOA reuse or repair (Xindian dog/60, Wugu dog/60) → demo
accounts and shared vocabulary → exact organization/photo/QR verification → services.
Runtime setup grants only the existing SIU identity-table contract; no RLS changes.

The first run downloads approved FurKids photos and official MOA images automatically.
FurKids reuses valid existing bytes. On later normal runs, each MOA shelter first uses
the existing strongest photo verifier: active organization, tenant-bound animals,
external source mappings, active QR, processed MediaAsset metadata, MinIO object bytes
and checksum must all pass. A valid dataset is reused without MOA metadata or official
name-detail requests. An incomplete DB or missing/corrupt MinIO object takes the live
import/repair path and must pass the same verifier afterward.

Normal startup freshness therefore means a valid local three-shelter snapshot, not the
latest MOA public feed. `./scripts/demo.sh refresh` explicitly requests freshness: it
always runs metadata and official name enrichment, while the importer still skips
remote image downloads for unchanged valid local photos. A failed explicit refresh is
never presented as success and exits nonzero, while stating whether verified local data
remains available. Importer semantics remain unchanged: prior imports are not pruned to
force 60; actual counts differing from the requested 60 are reported as warnings.

The Compose `minio-data` volume persists across normal restarts and `docker compose down`,
so verified media can be reused even when MOA is unavailable. `docker compose down -v`
destroys that cache; the next bootstrap detects the missing objects and downloads or
repairs them instead of silently trusting database rows.

## Test Fixtures (separate database)

```bash
# Canonical backend test entry: prepares strayhub_test and forwards pytest arguments.
uv run python -m scripts.test_local
uv run python -m scripts.test_local tests/unit/test_demo_bootstrap.py -q

# Explicit fixture loading for manual test-only workflows:
export DATABASE_URL=postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub_test
export STRAYHUB_TEST_DATABASE_URL=postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test
uv run alembic upgrade head
uv run python -m scripts.configure_runtime_role --apply
uv run python -m scripts.seed_test_fixtures
uv run python -m scripts.seed_t255_timeline     # optional fixture extension
uv run python -m scripts.seed_medical_care --help
./scripts/verify_local.sh
```

ORG-A/ORG-B/ORG-DISABLED, local-* identities, LINE, daily-scope, authorization-state
and batch fixtures remain available. `scripts.seed_local` remains a compatibility
alias/implementation for historical test guides, not normal demo onboarding.
`seed_local`, `seed_test_fixtures`, `seed_t255_timeline`, and `seed_medical_care`
all reject the demo database, non-PostgreSQL URLs, and non-loopback hosts before
fixture mutation. Normal demo commands continue to use only `strayhub`.
Integration tests that must prove empty-database or cleanup behavior use a narrow,
explicit internal opt-in for randomly suffixed `strayhub_mvp_*` or
`strayhub_cleanup_test_*` disposable databases; that opt-in is not a developer CLI
fallback, is accepted only while the named isolation tests are running, and never
permits `strayhub` or an arbitrary database name.
The shared vocabulary still has exactly the original category/option codes/labels.

## Existing local demo cleanup

Back up PostgreSQL first. Stop app writers while applying cleanup.

```bash
uv run python -m scripts.cleanup_legacy_demo_fixtures       # read-only preview
uv run python -m scripts.cleanup_legacy_demo_fixtures --yes # explicit transaction
uv run python -m scripts.verify_demo_data --photos
```

Only exact ORG-A, ORG-B, ORG-DISABLED codes and the enumerated known fixture
usernames are candidates. No wildcard user deletion, negative organization
allow-list deletion, TRUNCATE, CASCADE DDL, FK disabling, RLS edits or migration.
The legacy `reset_local --yes` now uses this same guarded implementation.

Cleanup reflects the live PostgreSQL foreign keys, computes dependent primary
keys (including composite keys, media join tables, PII/application service dates,
handoffs, medical reminders and histories), then deletes child-first in one
transaction. Cross-tenant references abort before deletion. Self-references are
deleted in a single table statement; unsupported FK cycles fail closed. Known
fixture users referenced by retained memberships/history are preserved. Global
vocabulary and platform configuration are preserved. --yes locks writers with a
5-second lock timeout; operator DB credentials are required. No new privileges
are granted to the application runtime role. Preview prints counts, not PII/tokens.

MinIO objects are deliberately not deleted: this task removes fixture DB rows,
not shared/versioned storage. Retained photos and their checksums are untouched.
Recovery after commit requires the backup; running test seed again only recreates
synthetic fixtures, not deleted historical sessions/reports.

Unknown organizations, including abandoned dynamically named test organizations,
are **not** automatically removed. The exact demo verifier rejects them and asks
for operator review. Never broaden cleanup to `code NOT IN (...)`.

## Verification log — 2026-08-27

- Branch demo/data_collection; head/current 0037_animal_external_sources, unchanged.
- Fresh DB `strayhub_demo_fresh_55ad9306`, initially empty private MinIO bucket
  `strayhub-demo-fresh-55ad9306`: normal `demo.sh` completed all bootstrap steps
  and started API (8012), Web (3015), Worker. Exactly three organizations,
  5/60/60 animals, 125 valid local photo checksums and active QR; five demo users.
  Official live feed had 8,263 records; Xindian 224 / Wugu 327 eligible dogs,
  60 each selected; no image/record failures. An initial fresh run exposed a new
  fixture flush-before-validity bug, fixed before this second from-zero run.
- The same real HTTP management switching/pagination and all three single-shelter
  volunteer QR resolve/confirm paths pass, including foreign-tenant denials,
  without daily scope. Repeated separately with actual strayhub_runtime connections.
- Existing DB cleanup tested on backup-restored local copy
  `strayhub_demo_cleanup_retry_55ad9306`: ORG-A 102 animals → absent; ORG-B 22 →
  absent; ORG-DISABLED → absent. 1,314 unreferenced known fixture users removed;
  three referenced fixture users preserved. All retained tenant-table row hashes
  and global vocabulary/configuration hashes unchanged; second cleanup deletes zero.
- Three unrelated abandoned organizations remain, intentionally:
  approval-23a537ba8960, approval-417f02c5e60a, approval-8390e136e83f (zero animals).
  Their naming matches old approval integration fixtures, but this cleanup does
  not widen its approved exact-code list. The original `strayhub` DB has not been
  cleaned or re-seeded by this task. Operator review is needed before converting
  that existing DB to an exact-three-organization demo.
- Runtime-only existing platform-login limitation: `demo-platform-admin` receives
  HTTP 200 but an empty organizations list under strayhub_runtime. The membership-
  based three-shelter manager and all three volunteers work. No authentication
  implementation was changed or RLS bypass introduced to hide this distinction.
  Platform login needs a separate scoped correction before claiming that path ready.
- Full backend (before the final additional account-idempotency test): 863 passed,
  2 existing failures, 2 opt-in skips. Failures: stale LINE tunnel contract expects
  TUNNEL_PROVIDER although HEAD demo-line.sh is ngrok-only; the no-unexplained-skip
  gate rejects the two pre-existing explicitly opt-in MOA tests. Their runtime
  equivalents are independently verified here; failures are not claimed as passes.
- Full Vitest 319/319; dedicated cleanup/context-switch tests 9/9, plus subsequent
  account-idempotency/single-tenant regression 3/3 in the cleanup suite.
- Final focused backend run: 58 passed (demo bootstrap/cleanup, context switch,
  empty-database fixture bootstrap, MOA unit/integration). Real PostgreSQL
  three-shelter runtime-role RLS suite: 1 passed, including connection reuse.
- Real browser at 360×800 and 1440×900: exact-three organization selector,
  FurKids 5, Xindian/Wugu three pages of 20 each, all primary photos loaded,
  all three animal details and QR previews, all three volunteer confirmation
  cards. No fictional rows or horizontal overflow. No LINE message was sent.
- Playwright core/management/QR/LIFF/volunteer selection: 59 passed, 6 failed.
  Isolated QR/approval retry with a configured fake LIFF_ID: 12 passed, the same
  6 failed. Three LINE trigger SDK-mock scenarios recorded zero sends; two
  volunteer-entry flows did not reach their expected page; the bulk-selection
  assertion omits the current submitted-date filters. These untouched feature
  paths are not claimed verified by this run; no unrelated flow/test rewrite
  was included to hide the failures. Login-prefill regression passed.
- Ruff check and format check (app/scripts/tests), frontend typecheck, generated
  contract parity, shell syntax and git diff whitespace checks passed.
- Status: PARTIALLY READY. Fresh demo and guarded cleanup are verified; original
  DB conversion needs review of unknown organizations, runtime platform login
  needs its own scoped correction, and broad regression is not fully green.
- Local evidence and backup: `/tmp/strayhub-three-shelter-65d6f47a/` (backup mode 600;
  QR/browser context mode 600, do not publish). No real LINE sends or cloud changes.
