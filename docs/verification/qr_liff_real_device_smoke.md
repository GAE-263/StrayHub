# QR / LIFF real-device smoke validation

## Status

- Date: 2026-08-25 (Asia/Taipei)
- Branch: `rework/care_report`
- Tested commit: `a56b27e`
- Overall status: **PARTIALLY VERIFIED — same-shelter LIFF producer path passed on a real LINE client; remaining negative, cross-shelter, external-camera, and physical-print cases are unrun**
- Production-code defects found: none

This record separates automated producer-side verification from observations that require a
real LINE client and phone. No token, entry reference, LINE user identifier, channel secret,
or volunteer PII is recorded here.

## Environment preflight

| Check | Result | Notes |
| --- | --- | --- |
| Required Item 1–3 commits | PASS | All required commits through `a56b27e` are present. |
| Working tree before verification | PASS | Clean; branch was three commits ahead of its remote. |
| Local FastAPI | PASS | Existing service returned a healthy response on the repository's local API port. |
| Local PostgreSQL | PASS | Real RLS/security tests connected and passed. |
| Repository HTTPS setup | READY | `scripts/demo-line.sh`, ngrok, and a fixed HTTPS URL configuration are available. |
| LIFF runtime configuration | READY | A non-placeholder LIFF ID and matching LINE Login channel ID are configured locally. Values are intentionally omitted. |
| Test entry reference | READY | A non-placeholder reference is configured locally and ignored by Git. |
| Messaging channel credentials | READY | A synthetic empty webhook signed with the configured secret passed the production signature boundary. Values are intentionally omitted. |
| LINE Developers Console | PARTIAL | Official Messaging API reads confirm the correct active webhook and a successful LINE webhook test. LIFF mode, scopes, endpoint, and `scanCodeV2` still require authenticated visual confirmation. |
| Public tunnel | PASS | The authorized fixed ngrok tunnel fronts Next.js; public Web and signed webhook checks both returned HTTP 200. |
| Safe test animal | PASS | Active synthetic `照護動物 001` (`CARE-001`) in `虛構收容所 A` was selected through the public manager UI. |
| Safe test volunteer | PASS | The real webhook resolved the trusted LINE identity and organization context before reaching the legacy draft flow. No identity value is recorded. |

The repository currently has two documented tunnel approaches. `scripts/demo-line.sh` is the
current executable workflow: one fixed HTTPS Web tunnel fronts Next.js, while its server-side
`/v1` proxy reaches local FastAPI without publishing the API directly. The older controlled
evidence guide describes two public tunnels. For this smoke, the executable script is the
narrower exposure boundary and should be used unless a reproduced routing defect requires the
older setup.

## LINE Developers checks

The following remain **BLOCKED** pending authenticated console access:

- LIFF endpoint equals the fixed HTTPS Web origin plus the configured volunteer entry path;
- LIFF app size/mode;
- `openid` and `chat_message.write` scopes;
- Scan QR enabled and `scanCodeV2` available;
- LINE Login callback/redirect settings;
- LIFF and Bot channel/provider relationship.

No console settings were changed during preflight.

After explicit user approval, stale listeners on ports 3002/8001 and the prior ngrok process
were stopped. `scripts/demo-line.sh` then started the canonical local stack on Web port 3001
and API port 8001, plus the worker and fixed HTTPS tunnel. A synthetic empty-event webhook
was HMAC-signed with the configured Messaging channel secret and returned HTTP 200 through
the public `/v1/line/webhook` path. This proves current tunnel routing, raw-body forwarding,
and signature configuration without claiming that a real LINE webhook has arrived.

The configured Messaging API access token was also verified against LINE and matched the
configured channel. LINE's webhook settings API reported that the expected endpoint is active,
and LINE's official webhook test endpoint returned success. No channel identifier or credential
was written to this record.

## Automated regression

| Command | Result |
| --- | --- |
| `npm --prefix apps/web run test` | PASS — 72 files, 310 tests |
| `npm --prefix apps/web run typecheck` | PASS |
| `npm --prefix apps/web run build` | PASS |
| `npm --prefix apps/web run format:check` | PASS |
| `LIFF_HANDOFF_E2E_MOCK=1 npm --prefix apps/web run test:e2e -- e2e/animal-confirmation-qr.spec.ts e2e/manager-animal-qr.spec.ts` | PASS — 17 tests |
| Focused QR/handoff backend tests | PASS — 15 tests |
| Real PostgreSQL QR tampering and handoff RLS/isolation tests | PASS — 6 tests |
| `uv run ruff check services/api/app tests` | PASS |
| `uv run ruff format --check services/api/app tests` | PASS |

The Playwright run verifies the same-shelter producer, explicit authorized cross-shelter
switch, unauthorized no-identity response, exact-number fallback, supported/unavailable/
failed LINE trigger paths, duplicate protection, close failure fallback, manager QR preview,
responsive layouts, accessibility, and A4 print media. These are mocked platform checks and
are not evidence of real LINE behavior.

An initial Playwright attempt reused a generated non-mock Next.js bundle and therefore took
the expected manual fallback instead of invoking the LIFF mock. Removing only the generated
`.next` cache and compiling with `LIFF_HANDOFF_E2E_MOCK=1` produced the passing 17-test run.
No source change was required.

## Real-device matrix

| Device | OS | LINE/runtime | Entry method | Result |
| --- | --- | --- | --- | --- |
| Not yet provided | UNRUN | UNRUN | LINE built-in scanner | BLOCKED |
| Not yet provided | UNRUN | External browser / OS camera | Phone camera | BLOCKED |

## Smoke results

| Scenario | Result |
| --- | --- |
| Manager generate/reuse and preview on deployed smoke environment | PASS |
| Screen-displayed QR scan | PASS — real LINE client opened the LIFF animal flow |
| Printed physical label | UNRUN |
| Printed QR scan | UNRUN |
| Same-shelter animal card and confirmation | PASS — user-observed |
| Pending `CareReportHandoff` creation from real LIFF | PASS — persisted `pending`, `source=liff_scan`, fixed 15-minute TTL |
| Exact `開始照護回報` message from `sendMessages` | PASS — user-observed |
| Duplicate automatic trigger count | PASS — exactly one, user-observed |
| Synthetic public webhook receipt and signature | PASS |
| Real LINE webhook receipt and trusted identity | PASS — signed message events were persisted after trusted identity/context resolution |
| Successful `closeWindow` return to LINE | PASS — user-observed |
| External-camera manual fallback | UNRUN |
| Authorized cross-shelter cancel/confirm | UNRUN |
| Unauthorized cross-shelter identity non-disclosure | UNRUN |
| Revoked/invalid QR | UNRUN |
| Inactive animal | UNRUN |
| Bot handoff consumption | DEFERRED TO BOT TEAM — webhook currently enters the legacy draft conversation directly |
| 15-minute consumer TTL | DEFERRED TO BOT TEAM |

## Real-device execution checklist

After explicit tunnel approval and LINE Developers sign-in:

1. Start the isolated repository smoke environment without printing configured identifiers.
2. Confirm the fixed HTTPS LIFF endpoint, scopes, QR scanning capability, channel relationship,
   and callback settings in LINE Developers Console.
3. Select synthetic active organizations, animals, memberships, and matching grants; confirm
   no `DailyReportableScope` is required.
4. Generate/reuse the Animal QR as a shelter administrator and verify the label identity.
5. Test screen and, if practical, physical printed QR scans on a real phone.
6. Run same-shelter, authorized cross-shelter cancel/confirm, unauthorized cross-shelter,
   revoked QR, and inactive-animal scenarios.
7. From LINE chat, verify exactly one `開始照護回報` message and successful return to chat.
8. From an external camera/browser, verify pending handoff creation and manual fallback.
9. Confirm webhook signature and trusted LINE identity only after real Messaging channel
   credentials are configured outside the repository.
10. Restore any synthetic test data changed for revoked/inactive scenarios and stop the tunnel.

## Known limitations

- Bot-side handoff consumption, `CareReportDraft`, questionnaire, and submission are outside
  this smoke and remain owned by the report-flow team.
- The real `開始照護回報` webhook reached the backend and passed signature and trusted LINE
  identity/context resolution. It then failed with the persisted error code
  `draft_access_denied`, producing `草稿不存在或無法存取`. The corresponding `liff_scan`
  handoff remained `pending` and unconsumed. This is the documented Bot integration gap:
  `line_webhook.py` does not yet call
  `CareReportHandoffService.consume_pending_handoff(...)` before entering the legacy draft
  conversation. It is not a QR/LIFF producer defect and was not changed in Item 4.
- Real `sendMessages`, `closeWindow`, `scanCodeV2`, physical QR scanning, and console settings
  cannot be inferred from browser mocks.
- A safe manager QR preview was captured without raw URL/token text. Phone/LINE evidence has
  not been captured because the real-device flow has not started.
- The free ngrok browser-warning interstitial appeared on the first ordinary browser visit.
  It did not prevent LIFF completion, but the real LINE run confirmed that it appears before
  StrayHub and therefore remains a smoke-environment usability limitation.

## Current real-device status

```text
REAL DEVICE PRINTED QR SCAN: BLOCKED
REAL DEVICE LIFF SENDMESSAGES: PASS
REAL DEVICE LIFF CLOSEWINDOW: PASS
```
