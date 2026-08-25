# Care Report Handoff

## Purpose

LIFF identifies and confirms the animal. LINE Bot performs the care-report conversation.
`CareReportHandoff` is the tenant-bound, user-bound, one-time server-side state that safely
bridges those responsibilities. The LINE message is only a trigger and never carries the
animal or authorization context.

This design does not delete `DailyReportableScope`, the animal confirmation card, the
existing five-minute confirmation token, `CareReportDraft`, or final report authorization.

## User flow

```text
Volunteer
→ scan Animal QR
→ LIFF resolves animal + shelter
→ verify active volunteer authorization
→ show animal confirmation card
→ confirm
→ create/replace pending handoff
→ send "開始照護回報" when possible
→ return to LINE
→ LINE webhook resolves trusted user identity
→ atomically consume pending handoff
→ Bot creates/continues Care Report Draft
```

If `liff.sendMessages()` is unavailable:

```text
sendMessages unavailable
→ handoff remains pending
→ user returns to LINE
→ clicks care-report action again
→ Bot consumes pending handoff
```

The implemented cross-shelter LIFF flow explicitly confirms a switch before resolving animal
identity or creating the handoff. The handoff records the final, server-verified organization;
it never performs a silent organization switch.

## Ownership boundary

The QR/LIFF team owns QR or exact shelter-number resolution, animal validation, current
volunteer authorization, the confirmation card, verification of the confirmation token,
and creating/replacing the pending handoff.

The LINE Bot team owns trusted webhook identity resolution, atomically consuming the
pending handoff, creating or continuing `CareReportDraft`, the questionnaire, answer
persistence, and final submission authorization.

Neither side reads the other side's frontend or conversation state. `CareReportHandoff` is
the only integration state between them.

## State machine

```text
pending → consumed
pending → expired
pending → superseded
```

`expired`, `consumed`, and `superseded` are terminal. Expiration is persisted when a consume
attempt encounters a pending row whose `expires_at` has passed. Reads do not extend TTL.

## TTL

Pending handoffs expire 15 minutes after creation. The TTL is fixed at creation and is not
extended by reads, retries, duplicate webhook deliveries, or failed trigger delivery.

## One-active-handoff rule

There is at most one `pending` handoff per user across all organizations. Creation obtains a
transaction-scoped per-user PostgreSQL advisory lock, supersedes every existing pending row
owned by that authenticated user, and creates the new pending row. A partial unique index on
`user_id WHERE status = 'pending'` is the database backstop.

The cross-organization supersede step uses StrayHub's authenticated-user RLS scope. It can
see only handoffs whose `user_id` is the already authenticated user; ordinary organization
scope remains unable to read another organization's handoffs.

## Implemented persistence

- ORM model: `CareReportHandoff` in
  `services/api/app/persistence/models/care_report_handoff.py`
- Table: `care_report_handoffs`
- Migration: `services/api/migrations/versions/0035_care_report_handoffs.py`
- Repository: `CareReportHandoffRepository` in
  `services/api/app/persistence/repositories/care_report_handoff_repository.py`
- Persisted states: `pending`, `consumed`, `expired`, `superseded`
- Persisted context: organization, user, membership, animal, source, fixed expiry, consumed
  timestamp, superseded timestamp, and normal audit timestamps

The table has forced PostgreSQL RLS, a global partial unique index for one pending row per
user, an organization/user/status lookup index, and a pending-expiry index. The RLS policy
permits ordinary organization scope, the existing authenticated-user scope used only for the
user's cross-organization replacement, or the existing platform scope. No new platform
privilege was introduced.

## Security invariants

- QR possession is not authorization.
- The LINE trigger text is not authorization.
- Bot trusts verified webhook LINE identity, not message or postback payload.
- `開始照護回報` contains no animal, organization, membership, confirmation-token,
  handoff-token, or PII value.
- A handoff is bound to one organization, user, membership, and animal.
- Membership and its matching grant must be effective when creating and consuming.
- The organization, user, and animal must be active when consuming.
- Ordinary QR-first reporting does not interpret `DailyReportableScope` as an allow-list or
  restriction model.
- An expired handoff cannot be consumed.
- A consumed handoff cannot be reused.
- Consumption locks and transitions the row atomically.
- Final draft and report-submission authorization remains the Bot/care-report flow's
  responsibility.
- Normal tenant scope cannot read or consume another organization's handoff.

## Ordinary reporting authorization

`VolunteerReportingAuthorizationService` in
`services/api/app/application/volunteer_reporting_authorization.py` is the shared
application-layer boundary for animal list/search, QR resolution, animal confirmation, and
handoff create/consume.

Ordinary QR-first reporting requires all of the following:

- active internal user;
- active verified organization;
- current effective `VOLUNTEER` membership for that user and organization;
- current active grant matching that exact membership, user, and organization;
- active animal belonging to the verified organization when an animal is selected;
- active, non-revoked QR bound to that organization and animal on the QR path; and
- the existing five-minute, context-bound confirmation token for handoff creation.

`DailyReportableScope` is not required for ordinary QR-first animal list/search, QR
resolution, confirmation, handoff creation, or handoff consumption. Its table, historical
rows, repository, RLS, and management APIs remain intact for legacy/history purposes. The
presence or absence of a row must not be interpreted as a new restriction model.

QR resolution remains limited to the verified current organization. Cross-shelter deep links
use the narrow authorized preflight described below; they do not perform a global animal
lookup or automatic switch.

The existing HTTP draft creation, final submission, and legacy LINE selection/conversation
paths still contain their prior scope checks. Those report-flow-team paths are explicitly
deferred; the future handoff consumer can create a draft through `LineDraftService` without
that HTTP draft gate, but its final submission authorization must be cut over by the owning
team before the end-to-end Bot flow ships.

## Implemented LIFF / QR producer

The volunteer route is `/animal-confirmation`. It is scanner-first and uses the installed
`@line/liff` singleton through `apps/web/lib/liff-scanner.ts`; it does not initialize LIFF a
second time. `liff.isApiAvailable("scanCodeV2")` controls capability and
`liff.scanCodeV2()` supplies the scanned value. If scanning is unavailable, the page remains
usable through the exact shelter-number fallback. Physical QR codes use this canonical deep
link:

```text
/animal-confirmation?organization_id=<candidate organization UUID>&qr_token=<opaque token>
```

`organization_id` is an untrusted routing hint and `qr_token` is only an opaque locator. The
client parses neither animal identity nor authorization from the URL. It removes the query
string after reading it and never stores QR, confirmation, or handoff tokens in browser
storage.

For a same-shelter QR, the page calls `POST /v1/qr-tokens/resolve` in the current tenant and
shows the returned safe animal candidate. For a different candidate organization, it first
calls:

```http
POST /v1/qr-tokens/candidate-organization

{
  "qr_token": "<opaque locator>",
  "candidate_organization_id": "<untrusted candidate UUID>"
}
```

The endpoint is implemented in `services/api/app/api/animal_selection.py`. It uses the
existing authenticated-user/exact-organization RLS boundary to verify effective volunteer
access plus a valid QR and active animal in that organization. Its response contains only
`organization_id` and `organization_name`; animal identity is not returned. The application
restores the request's original tenant scope before returning. The page then presents an
accessible explicit switch dialog. Only after confirmation does it call the existing
`PUT /v1/auth/active-shelter-context`, followed by the normal tenant-scoped QR resolver.
Cancellation makes no context change and returns focus to the scanner action.

The fallback for a complete shelter number calls the existing tenant-scoped
`GET /v1/animals/search` and accepts only one exact `shelter_number` match. Partial search is
available only behind the secondary `搜尋動物` action and remains current-tenant only. All
resolution paths feed the same confirmation card, which displays the photo when available,
name, full shelter number, cage/area, and verified shelter name.

On `確認並開始回報`, the page calls
`POST /v1/animals/{animalId}/confirm`, holds its five-minute confirmation token only in the
current async call, and immediately calls `POST /v1/care-report-handoffs`. Source mapping is:

- LIFF `scanCodeV2`: `liff_scan`
- physical QR/deep link: `qr_deeplink`
- exact-number or secondary search: `shelter_number`

Success means only that the 15-minute pending handoff is ready. After that HTTP request
succeeds, `apps/web/lib/liff-line-handoff.ts` attempts exactly one automatic producer trigger
for that handoff. It sends only this payload:

```json
[{ "type": "text", "text": "開始照護回報" }]
```

The eligibility rule follows the installed `@line/liff` 2.30 runtime: LIFF must have an
initialized ID (`liff.id !== null`), be running in the LINE client (`liff.isInClient()`),
expose `sendMessages`, and report `chat_message.write` permission as `granted` or `prompt`.
The SDK's permission wrapper may complete the prompt. An `unavailable` permission result, an
external browser, an uninitialized runtime, a missing function, or any capability/send error
uses the manual fallback. The producer does not use `isApiAvailable()` for `sendMessages`
because the installed SDK's availability API does not list that function.

After a successful send, the page displays `正在返回 LINE 繼續照護回報…` and calls
`liff.closeWindow()` only in an initialized in-client runtime. If closing is unavailable or
throws, the pending handoff is kept and the manual fallback remains usable. The fallback
tells the volunteer to return to LINE, select `照護回報` or type `開始照護回報`, and notes
that confirmation remains for about 15 minutes. Physical QR deep links outside LINE are an
expected fallback case. No automatic retry occurs after a failure, and component operation
epochs prevent a late result from resurrecting stale or unmounted UI.

LIFF does not consume the handoff, extend its TTL, create a `CareReportDraft`, submit a
report, or claim that a report was submitted. Messaging API push is not required. The exact
trigger currently has no dedicated Bot consumer in `services/api/app/api/line_webhook.py`;
Bot integration remains responsible for resolving the trusted webhook identity and calling
the service below. LINE Developers console enablement and real-client behavior still require
physical-device validation.

## Management Animal QR lifecycle

The management animal detail route `/animals/{animalId}` contains the V1 `照護 QR Code`
card implemented by `apps/web/features/animal-management/AnimalCareQrCard.tsx`. It loads only
QR rows for that tenant-scoped animal through:

```http
GET /v1/management/qr-codes?animal_id=<current organization animal UUID>
```

If no active QR exists, an administrator must explicitly select `產生 QR Code`, which calls
`POST /v1/management/qr-codes`. Creation remains restricted to `SHELTER_ADMIN` or a
tenant-scoped `PLATFORM_ADMIN`; the existing read boundary remains available to management
staff. The animal must be active and belong to the current verified organization. Creation
uses a transaction-scoped organization-and-animal advisory lock and reuses the current active
row instead of generating on page load or creating another active row.

New-format QR records continue to store only a SHA-256 token digest. The printable opaque
locator is deterministically reconstructed from the random QR record ID plus a
domain-separated HMAC using the existing server confirmation-secret key. The opaque token
does not encode animal, organization, volunteer, confirmation, or handoff data. Existing
legacy random-token rows remain active but cannot be reconstructed from their digest; the UI
does not silently invalidate them. It explains that reprinting requires the guarded
`重新產生` action and replacement of the old physical label.

Regeneration requires explicit confirmation that the old label will stop working. The server
locks the animal, revokes the selected active record, and creates a new active record with a
new opaque locator, preserving the revoked row as history. A concurrent or repeated
regeneration cannot create another replacement from the already revoked record. Inactive or
transferred animals cannot receive a new or replacement QR. A transferred animal's old QR
also fails the existing organization/animal consistency checks during volunteer resolution.

The API returns the canonical relative deep-link form:

```text
/animal-confirmation?organization_id=<untrusted candidate organization UUID>&qr_token=<opaque locator>
```

The manager page resolves that path against the public application origin before rendering
the QR. The organization ID remains only a routing hint. The printed code is a locator and
does not authorize reporting; Item 2B still requires authenticated effective volunteer
membership, matching grant, verified organization, valid active QR, and active animal.

The preview uses `qrcode.react` 4.2.0 to render a real SVG with a four-module quiet zone and
medium error correction. Normal UI never renders the raw token or deep link as text. The
print-only A4 portrait layout hides navigation and actions, renders a 90 mm label with an
approximately 50 mm QR, and includes only StrayHub, `照護回報 QR Code`, animal name, shelter
number, shelter name, and the current area when available. Automated Chromium PDF inspection
verified a single unclipped A4 page. Physical printed-label scanning remains unverified on a
real device.

The resulting field flow is:

```text
manager generates or reuses active Animal QR
→ preview printable label
→ print and attach label
→ volunteer scans
→ Item 2B resolves and confirms the authorized animal
→ Item 2C creates the pending handoff and triggers LINE when possible
→ Bot consumer uses trusted webhook identity and server-side handoff state
```

`DailyReportableScope` is not consulted or configured by this manager QR lifecycle.

## Integration contract for Bot agent

1. Receive a trusted LINE webhook.
2. Resolve `LineUserBinding`, internal user, and the verified `WebhookSession` organization.
3. Ask `CareReportHandoffService.consume_pending_handoff()` to atomically consume the
   current valid pending handoff.
4. Do not accept `animal_id` from LINE message or postback data.
5. If no handoff exists, return the normal "scan/confirm an animal first" UX.
6. If a handoff is returned, use its trusted server-side animal, organization, and membership
   context.
7. Create `CareReportDraft` with the existing internal `LineDraftService`; the consumed
   handoff replaces any need to expose or replay the LIFF confirmation token in LINE.
8. Create the draft and consume the handoff in the same database transaction. A draft failure
   must roll back consumption.
9. Never consume the same handoff twice.

## API / service signatures

### LIFF HTTP operation

Router file: `services/api/app/api/care_report_handoffs.py`

```http
POST /v1/care-report-handoffs
Authorization: Bearer <access token>
X-Session-Id: <server session when required by existing auth flow>
Content-Type: application/json

{
  "animal_id": "<uuid>",
  "confirmation_token": "<five-minute confirmation token>",
  "source": "liff_scan | qr_deeplink | shelter_number"
}
```

The endpoint derives user, organization, membership, and session from `RequestContext`.
Response fields are limited to `id`, `status`, and `expires_at`; there is no handoff token.
The canonical OpenAPI operation ID is `createOrReplaceCareReportHandoff`. There is no public
consume endpoint.

### Application service

File: `services/api/app/application/care_report_handoff_service.py`

Class: `CareReportHandoffService`

```python
await service.create_or_replace_handoff(
    user_id=...,
    organization_id=...,
    membership_id=...,
    session_id=...,
    animal_id=...,
    confirmation_token=...,
    source=...,
)

await service.consume_pending_handoff(
    user_id=...,
    organization_id=...,
)
```

The create call is for the authenticated LIFF endpoint. The consume call is internal and
accepts only the trusted user and organization resolved from the LINE webhook boundary. Both
methods return the persisted `CareReportHandoff`. The consumed result contains trusted
`organization_id`, `user_id`, `membership_id`, and `animal_id` context. Both methods flush but
do not commit so their callers control the surrounding transaction.

The Bot integration must construct `VolunteerReportingAuthorizationService` from
`AuthenticationRepository` and the organization-scoped `AnimalRepository`, then inject it
with `CareReportHandoffRepository` into `CareReportHandoffService`. It must call consume and
`LineDraftService` in the same webhook event transaction. The existing webhook event boundary
catches `DomainError` before the transaction exits; this also allows an encountered expired
row to commit its terminal `expired` state while returning the safe error UX.

## Confirmation token decision

The handoff stores independently verified server-side confirmation context. Creation verifies
the existing signed five-minute token against the authenticated user, organization,
membership, session, and animal, then discards it. Neither the raw token nor a digest is stored.

The token is not suitable as the handoff itself because its five-minute TTL is shorter than
the approved 15-minute handoff TTL and webhook processing does not use the LIFF
`SessionRecord.id`. The internal Bot path already creates drafts through `LineDraftService`;
successful one-time handoff consumption is its trusted animal-confirmation proof. HTTP draft
creation continues to require the existing confirmation token.

## Error semantics

- `no_pending_handoff`: no current pending handoff exists for the trusted user and tenant.
- `handoff_expired`: the current pending handoff exceeded its fixed TTL and was marked expired.
- `handoff_already_consumed`: the latest handoff is already consumed.
- `authorization_no_longer_valid`: user, organization, membership, or matching grant is no
  longer effective.
- `animal_no_longer_available`: the trusted handoff animal is missing, inactive, or no longer
  belongs to the handoff organization.
- `animal_confirmation_required`: the create request did not contain a valid confirmation
  token bound to the authenticated context.
- `invalid_handoff_source`: the create source is not one of `liff_scan`, `qr_deeplink`, or
  `shelter_number`.

Errors do not expose animal details.

## Examples

### Happy path

LIFF confirms animal A and creates a pending handoff. Sending `開始照護回報` causes the
trusted webhook flow to lock and consume it. The Bot creates the draft from the returned
server-side context in the same transaction.

### sendMessages unavailable

LIFF creates the handoff but cannot invoke `sendMessages()`. Nothing is rolled back. The user
returns to LINE and clicks the Rich Menu care-report action; the Bot consumes the still-pending
handoff.

### second animal supersedes first

The user confirms animal A and then animal B. Creation for B marks A `superseded` and creates B
as the only pending handoff. Only B can be consumed.

### duplicate webhook delivery

The first transaction locks and consumes the pending handoff. A concurrent or later delivery
cannot find a pending row and receives `handoff_already_consumed`. It must not create another
draft.

### expired handoff

A consume attempt after 15 minutes marks the row `expired` and returns `handoff_expired`.
Reads and retries never revive it.

### grant revoked between LIFF confirmation and Bot consumption

Consumption revalidates the exact membership and matching grant. It returns
`authorization_no_longer_valid`, leaves no consumed handoff context for draft creation, and
does not disclose animal details.

## What the Bot team must NOT do

- Do not parse animal identity from `開始照護回報`.
- Do not accept client-provided `animal_id` as handoff truth.
- Do not perform global cross-tenant handoff lookup.
- Do not revive expired or consumed handoffs.
- Do not bypass current membership/grant checks.
- Do not query or update the handoff table directly; use `CareReportHandoffService`.
