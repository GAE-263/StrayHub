# Care Report Handoff

## Purpose

LIFF identifies and confirms the animal. LINE Bot performs the care-report conversation.
`CareReportHandoff` is the tenant-bound, user-bound, one-time server-side state that safely
bridges those responsibilities. The LINE message is only a trigger and never carries the
animal or authorization context.

This design does not replace `DailyReportableScope`, the animal confirmation card, the
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

The future cross-shelter LIFF flow must explicitly confirm a switch before creating the
handoff. The handoff records the final, server-verified organization; it never performs a
silent organization switch.

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
- The existing `DailyReportableScope` rule remains enforced in this item.
- An expired handoff cannot be consumed.
- A consumed handoff cannot be reused.
- Consumption locks and transitions the row atomically.
- Final draft and report-submission authorization remains the Bot/care-report flow's
  responsibility.
- Normal tenant scope cannot read or consume another organization's handoff.

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

The Bot integration must construct the service in the webhook event's organization-scoped
`AsyncSession` with `CareReportHandoffRepository`, `AuthenticationRepository`,
`AnimalRepository`, and `ReportableScopeRepository`. It must call consume and
`LineDraftService` in that same transaction. The existing webhook event boundary catches
`DomainError` before the transaction exits; this also allows an encountered expired row to
commit its terminal `expired` state while returning the safe error UX.

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
- `authorization_no_longer_valid`: user, organization, membership, grant, or current
  `DailyReportableScope` authorization is no longer effective.
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
