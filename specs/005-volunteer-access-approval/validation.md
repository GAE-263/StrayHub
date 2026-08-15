# Validation：志工報名與限時授權

**Date**: 2026-08-15
**Branch**: `feat/volunteer_entry`
**Scope**: `005-volunteer-access-approval`

## Automated gate result

| Command / gate | Result |
| --- | --- |
| `VERIFY_LOCAL_SKIP_DOCKER=1 ./scripts/verify_local.sh` | PASS（exit 0）：empty database upgrade/reversible migration、fictional seed、local flow/isolation/failure/adapter contracts、full tests、lint/type、Web quality/build、generated contracts、secret scan、Worker/API/Web Docker builds |
| `uv run pytest`（由完整 gate 執行） | PASS：352 tests |
| `uv run ruff check .` / `uv run ruff format --check .` | PASS |
| Python type gate | PASS：12 source files，0 issues |
| `npm --prefix packages/contracts run check` | PASS；005 additive contract 已合併 canonical contract，generated types 無 drift |
| `npm --prefix apps/web run quality` | PASS：40 files / 70 tests；typecheck、mobile、a11y unit、Prettier 全通過 |
| `npm --prefix apps/web run build` | PASS：20 routes；含 onboarding、policy、applications、grants、notifications routes |
| Storage adapter contracts | PASS：2 tests |
| Focused volunteer browser flow | PASS：5/5（onboarding idempotency、1,200 snapshot、finite grant handoff、revoke、STAFF mount-before-fetch guard） |
| New responsive browser scenarios | PASS：5 routes × 4 required viewports；100 visible applicants / 1,200 matching snapshot、policy、grant、notification queue 無 document-level overflow |
| New keyboard scenario | PASS：filter/select-all、individual period override、confirmation dialog focus/Escape/return focus、live result、notification selection/retry |
| New volunteer axe scenario | PASS：onboarding、applications、grants、notifications、policy，critical/serious = 0 |
| Final feature-only Playwright rerun | PASS：12/12 in 33.3s（5 core flows、5 responsive route matrices、1 keyboard flow、1 axe matrix） |

## Quickstart acceptance coverage

| Area | Evidence / result |
| --- | --- |
| Migration and policy staging | Migrations `0024`, `0025`, `0026` reached one head; empty bootstrap/reversible test passed; valid legacy VOLUNTEER gets finite transition while inactive/non-volunteer rows remain inactive; organization + initial 168-hour policy atomicity covered by integration tests. |
| Entry issue/rotation and unknown status | Opaque digest/purpose/active reference resolver, tamper/cross-purpose rejection and rotation behavior covered; status-only unknown identity creates no User/Binding/Membership/Session. |
| Applications and policy | Submit is atomic and idempotent; disabled entry preserves own status; organization policy is versioned, finite and only affects later decisions. |
| Batch 100 / 1,200 | Explicit and all-filtered target snapshot, 500-item claims, partial success/conflict/failure, stale recovery and idempotent retry passed; ORG-B controls unchanged. |
| Grant lifecycle and 004 handoff | Upcoming/active/expired/revoked effective access, finite period display, active-only `/animal-confirmation` handoff, period update, immediate expiry confirmation and revoke passed. |
| Expiry / disabled user or organization | Request-time deny is immediate; background expiration and organization-scoped persistent Session/Webhook context cleanup are idempotent and bounded to the 60-second worker loop. |
| Notification failure | All required events persist independently of domain commit; transient backoff, terminal failure, organization-scoped failure list and idempotent manual bulk retry passed. |
| Platform support / tenant isolation | Explicit target organization + support reason enforced; success/denied/not-found/validation/exception audits persist; no mixed lists or cross-tenant mutation. |
| Data retention | Expiry/revoke does not delete Draft/Report/Media/history; a later grant creates a new traceable cycle. |

## Browser and visual notes

- The focused feature browser scenarios all passed after the accessible batch confirmation dialog change.
- A combined 71-test dev-server run produced 54 passes, 6 deliberately skipped new visual cases and 11 failures. Two non-feature failures were accompanied by Next dev-server `Unexpected end of JSON input`; the new volunteer keyboard test and all new responsive routes passed in that run.
- Existing visual baselines also show pre-existing/global pixel drift on the legacy routes. No snapshot was updated because T108 requires reviewer confirmation first.
- New onboarding, batch confirmation/progress/partial result, policy, grant and notification visual cases are present behind `VOLUNTEER_ACCESS_VISUAL_REVIEW=approved`; after review, run `VOLUNTEER_ACCESS_VISUAL_REVIEW=approved npm --prefix apps/web run test:visual:update` and inspect every changed image before acceptance.

## Manual evidence still required

- **SC-001 / T110 pending**：沒有以虛構自動化結果取代至少 20 位首次志工（至少 10 iOS、10 Android）的 2 分鐘／首次成功率研究。
- **SC-002 / T110 pending**：沒有以 API latency 取代至少 3 位管理員各完成 100 筆批次的 5 分鐘人工計時。
- Participant raw records, interventions, errors and recomputable pass rates do not exist yet; therefore these success criteria are not claimed as passed.

## Known non-blocking warnings

- Python 3.14 test execution reports upstream `pytest-asyncio` event-loop-policy deprecation warnings.
- Next.js dev mode reports future `allowedDevOrigins` and occasional Fast Refresh warnings; production builds pass.
