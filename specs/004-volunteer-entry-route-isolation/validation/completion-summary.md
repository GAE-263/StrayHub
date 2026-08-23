# 004 Volunteer Entry Completion Summary

**Evidence timestamp (UTC):** 2026-08-23T14:42:00Z<br>
**Branch:** `dev/volunteer_entry`<br>
**Scope:** local technical gates, controlled LINE/LIFF readiness, and remaining external acceptance

## Status

The local implementation and technical quality gates are verified. Real-device LINE/LIFF Case A–D and 005 T110 usability timing remain explicitly `BLOCKED/UNRUN`; no local fixture or Playwright result is used as a substitute for external evidence.

## Fresh Task 8 verification

| Check | Result |
| --- | --- |
| Focused LIFF bootstrap Vitest | `npm test -- --run 'app/(volunteer)/volunteer-entry/page.test.tsx'`: 43 passed |
| Frontend typecheck | `npm run typecheck`: passed |
| Frontend production build | `npm run build`: passed; Next.js 15.5.23 |
| Task 8 commit boundary | Commit `a127a75`; none of its allowlisted paths are currently dirty |
| Current later-task changes | Limited to volunteer access backend／contract／test paths plus untracked local plans、AGENTS.md and design SVGs; not included in Task 8 evidence |

## Fresh Task 9–12 route/session verification

`npm test -- --run 'lib/auth.test.ts' 'lib/liff-session.test.ts' 'lib/liff-recovery-coordinator.test.ts' 'lib/route-access.test.ts' 'components/auth/ProtectedRouteState.test.tsx' 'components/auth/AuthenticatedRouteBoundary.test.tsx' 'app/(volunteer)/layout.test.tsx' 'app/(volunteer)/animal-confirmation/page.test.tsx' 'app/(volunteer)/care-report/page.test.tsx'` passed: 9 files／73 tests.

2026-08-23T15:04:38Z UTC fresh route-composition slice also passed: management root route-group test、server-confirmed shelter-label tests、volunteer animal／care handoff tests 5 files／20 tests；frontend typecheck與production build通過。Production `/v1/auth/me` now exposes `valid_from`、`expires_at` and matching active `access_grant` evidence; management root is composed under `(management)/layout.tsx`, and header shelter labels use server-returned organization names rather than client storage codes. Task 9–12 local technical route/session slice is complete; real LINE／LIFF Case A–D and T110 remain external `BLOCKED/UNRUN`.

## Evidence matrix

| Task | Status | Evidence |
| --- | --- | --- |
| T052 visual／Axe／responsive baseline | [x] | `LIFF_ID=fake-liff-id npm --prefix apps/web run test:a11y:browser`: 16 passed; `LIFF_ID=fake-liff-id npm --prefix apps/web run test:visual`: 83 passed; P0 responsive／keyboard coverage included in the 96-test P0 run. |
| T053 server authorization／isolation／atomicity | [x] | `STRAYHUB_TEST_DATABASE_URL=postgresql://... uv run pytest`: 553 passed; contract, security, isolation, transaction rollback, stale-state and raw-secret boundary tests included. |
| T054 quickstart／controlled evidence documentation | [x] | Updated `README.md`, `specs/004-volunteer-entry-route-isolation/quickstart.md`, `contracts/README.md`, and `validation/controlled-line-evidence.md` in prior documentation slice; command `--help` checks and documentation path review passed. |
| T055 execute every quickstart validation command and save summary | [ ] | Not fully complete: the fresh Task 8 frontend checks passed, but the local Web service was not listening during Task 18 preflight, runtime LIFF/tunnel variables were unset, and no external LINE/LIFF credentials or device evidence exists. |
| T056 full constitution gates | [x] | `PATH="$HOME/.local/bin:$PATH" bash scripts/verify_local.sh` passed; standalone full `uv run pytest` with the local PostgreSQL URL passed 553 tests; frontend quality/build, generated contracts, adapters, secret scan, Docker builds, P0, browser Axe and visual gates passed. |

## Verified local flow and security boundaries

- Local fixtures cover NEW, PENDING, ACTIVE, SUSPENDED／invalid access, login redirect, cross-organization denial, route isolation, recovery, stale protected-state cleanup, keyboard access, responsive layout and visual states.
- ACTIVE local exchange reaches the volunteer handoff; non-ACTIVE states do not create protected session state.
- Protected requests use server-confirmed session and shelter context; client-provided organization values are not authorization selectors.
- StrictMode restore replay in the care report is deduplicated by organization context without allowing stale requests to overwrite newer context state.
- Raw LINE ID tokens, raw entry references, LINE user IDs, secrets, PII and protected animal/report data are not recorded in this summary.

## Controlled LINE／LIFF Case A–D

| Case | Result | Reason |
| --- | --- | --- |
| A: unknown identity → NEW → PENDING | BLOCKED/UNRUN | No real LIFF ID, LINE Login channel, controlled identity or phone run. |
| B: approval → exact Membership/Grant | BLOCKED/UNRUN | Requires the external Case A application and controlled management account. |
| C: same identity → ACTIVE → animal confirmation | BLOCKED/UNRUN | Requires real LIFF exchange and device evidence. |
| D: ORG-A／ORG-B isolation and stale data | BLOCKED/UNRUN | Requires two controlled entries/identities and device reload/back/session checks. |

### Task 18 preflight

- `cloudflared` and `ngrok` are installed.
- API `127.0.0.1:8001/healthz` returned successfully.
- Web `127.0.0.1:3001/volunteer-entry` was unavailable because the Web process was not listening.
- `LIFF_ID`, `API_BASE_URL`, `LINE_LOGIN_CHANNEL_ID`, `PUBLIC_WEB_ORIGIN`, `PUBLIC_API_ORIGIN`, and `LIFF_BASE_URL` were unset.

This is readiness evidence only, not Case A–D acceptance evidence.

## Remaining work

1. Start the Web service with real server-runtime `LIFF_ID` and API tunnel origin.
2. Establish separate HTTPS Web and API tunnels.
3. Configure the matching LINE Login channel／LIFF Endpoint with `openid` scope.
4. Execute and record masked Case A–D evidence on controlled iOS／Android devices.
5. Complete 005 T110 with at least 10 first-time iOS volunteers, 10 first-time Android volunteers, and 3 administrators performing 100-item batches each; retain raw participant data outside Git and publish only anonymized, recomputable summaries.
6. Perform the final independent diff review and create a narrow commit only after the remaining acceptance boundaries are resolved or explicitly accepted as blocked.
