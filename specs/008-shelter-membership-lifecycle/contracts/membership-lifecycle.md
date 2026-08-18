# Membership Lifecycle Contract

## Authorization

All operations require the existing Membership management boundary:

- `PLATFORM_ADMIN` may operate on allowed platform organizations.
- `SHELTER_ADMIN` may operate only on the current organization.
- Other roles receive the existing authorization denial shape and do not learn another organization's membership identifiers.

## API: Default Membership List

`GET /v1/organizations/{organizationId}/memberships`

- Default response excludes `status = archived`.
- Response retains `id`, `organization_id`, `user_id`, `role`, `status`, `valid_from`, `expires_at`, `medical_care_access`, `username`, `display_name`, and derived `volunteer_authorization_status`.
- Results are grouped by the client into volunteers (`VOLUNTEER`) first and staff (`SHELTER_ADMIN`, `STAFF`) second; staff are ordered by administrator before staff, then each section is ordered by active, disabled, expired, revoked.

## API: Archived Membership List

`GET /v1/organizations/{organizationId}/memberships/archived`

Response:

```json
{
  "items": [
    {
      "id": "membership-id",
      "organization_id": "organization-id",
      "user_id": "user-id",
      "role": "STAFF",
      "status": "archived",
      "archived_at": "2026-08-18T10:00:00+08:00",
      "archived_by": "本機收容所管理員 A",
      "username": "local-staff-a",
      "display_name": "本機工作人員 A",
      "medical_care_access": false
    }
  ]
}
```

The endpoint MUST apply the same organization scope, identity projection, error behavior, and authorization audit boundary as the default list.

## API: Archive Membership

`POST /v1/organizations/{organizationId}/memberships/{membershipId}/archive`

- Archives the membership and records `membership.archived`.
- Rejects archiving the current operator.
- Rejects archiving the last available `SHELTER_ADMIN`.
- Returns the archived membership projection.

## API: Restore Membership

`POST /v1/organizations/{organizationId}/memberships/{membershipId}/restore`

- Restores the pre-archive status when valid.
- For an expired volunteer period, returns `expired` and does not grant active volunteer access.
- Records `membership.restored`.
- Returns the restored membership projection.

## API: Re-enable Membership

`PATCH /v1/organizations/{organizationId}/memberships/{membershipId}` with `{ "status": "active" }`

- Re-enables a disabled SHELTER_ADMIN or STAFF Membership and records the existing membership update Audit event.
- For a VOLUNTEER Membership, rejects re-enabling when the latest volunteer authorization is `expired` or `revoked`; a new valid volunteer authorization must be established through the existing volunteer access flow.
- Returns `volunteer_authorization_status` so the client can distinguish account status from authorization status.

## UI Routes

- `/shelters`: active, invited, disabled, expired, and revoked memberships according to existing display rules; archived memberships excluded. The volunteer section is first, followed by the staff section.
- `/shelters/archived`: archived memberships only, grouped with the same section order and offering search and restore.

## UI Interaction Contract

- The primary page header exposes `建立帳號` and `查看已封存成員`.
- The account form opens in a modal with `帳號`, `顯示名稱`, `暫時密碼`, and `角色`.
- Modal close, Escape, validation failure, loading, success, and authorization failure must be observable and accessible.
- Disabled, expired, and revoked cards use a muted gray visual treatment; revoked volunteer authorization is labeled `授權已撤銷` and is distinct from Membership archive or disable status.
