# Session and LINE menu stabilization contract

Mode: STABILIZATION. Production deployment and final RC promotion are excluded.

## Existing session contract

`session_records` is the server-side authentication session and revocation anchor
referenced by access-token `sid` and refresh-token rows. It is not a device registry.
The original session service (`67d46f3`) and LIFF onboarding (`0dc5fe6`) establish
session issuance; current LIFF exchange creates a fresh session on each successful
ACTIVE exchange. There is no device identifier, same-device reuse, active-session
cap, or implicit revocation of other LIFF sessions. Multiple devices therefore
also have independent sessions. Seven active sessions is EXPECTED under this
existing contract, not evidence of duplicate identity or authorization.

Refresh rotates the refresh token within the same family and session. It issues a
new access token without extending `session_records.expires_at`; a later refresh
token expiry cannot override that absolute session deadline. Reusing a rotated
refresh token revokes its family. Logout revokes the selected session and its
refresh tokens, not every device. Expired/revoked sessions fail authentication.
Protected requests revalidate current membership/grant and database scope; session
creation does not create a binding, membership, grant, or volunteer application.

A session cap is a future product decision. Do not revoke A's sessions merely to
make the count look smaller. Re-entry session deltas must be interpreted against
this contract, while domain-row deltas must remain zero.

## Menu mapping

| Persona/state | Existing resource |
| --- | --- |
| Unaffiliated/default | strayhub-default |
| Active volunteer, including care-report entry | strayhub-volunteer |
| Adopter role (when actually assigned) | strayhub-adopter |
| Authorized staff with organization context | strayhub-staff |
| Adoption hub navigation | strayhub-adoption-hub |

Menu visibility never grants authorization. Volunteer entry best-effort links
the volunteer menu only after server context resolution. Acceptance uses existing
channel resources; do not run the destructive menu recreation sync script.

The volunteer checkpoint requires enabled role menus, default/volunteer IDs,
and volunteer smoke evidence. Staff LIFF is not required: the staff handler still
checks staff membership and returns an unavailable message for missing staff LIFF.
Production retains its existing complete staff release requirements.

Before runtime update, run `infra/gce/scripts/verify-acceptance-line-menus.py` in
the prepared acceptance environment. It checks IDs against the LINE API with the
acceptance token, validates resource names/chat-bar labels and necessary actions,
and fails for a wrong existing ID as well as a missing ID. Optional configured
menus are also checked. This is the resource preflight; static Compose validation
alone is insufficient. Tokens are never printed. Resource verification is not
human menu smoke evidence: do not fabricate a human PASS or a smoke receipt.

After Gate 1, record the SHA and image digests as STABILIZATION BUILD, preserve
Postgres/Redis/MinIO volumes, and update acceptance app containers only. Record
resource preflight, A's visible menu, refresh/re-entry, tenant checks, and domain
row deltas separately. Stop before QR regardless of the result.
