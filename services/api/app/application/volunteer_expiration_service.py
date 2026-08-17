"""Idempotent convergence for expired or otherwise invalid volunteer grants."""

from __future__ import annotations

from datetime import datetime, timezone

from services.api.app.application.audit_service import AuditService
from services.api.app.application.volunteer_notification_service import (
    VolunteerNotificationService,
)
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)


class VolunteerExpirationService:
    def __init__(
        self,
        repository: VolunteerAccessRepository,
        identities: AuthenticationRepository,
        *,
        audit: AuditService | None = None,
        notifications: VolunteerNotificationService | None = None,
    ) -> None:
        self.repository = repository
        self.identities = identities
        self.audit = audit
        self.notifications = notifications

    async def sweep(self, *, now: datetime | None = None, limit: int = 500) -> int:
        clock = now or datetime.now(timezone.utc)
        grants = await self.repository.due_or_invalid_grants(now=clock, limit=limit)
        changed = 0
        for grant in grants:
            if grant.status != "active":
                continue
            membership = await self.identities.get_membership(
                grant.user_id, self.repository.organization_id
            )
            grant.status = "expired"
            grant.version += 1
            if membership is not None and membership.id == grant.membership_id:
                membership.status = "disabled"
                membership.access_version += 1
            await self.identities.clear_volunteer_contexts(
                grant.user_id, self.repository.organization_id
            )
            if self.audit is not None:
                await self.audit.record(
                    organization_id=self.repository.organization_id,
                    actor_user_id=None,
                    actor_reference="VOLUNTEER_ACCESS_WORKER",
                    action="volunteer_access_grant.expired",
                    resource_type="volunteer_access_grant",
                    resource_id=grant.id,
                    source_channel="worker",
                    after={"status": "expired", "version": grant.version},
                    reason="effective access no longer valid",
                )
            if self.notifications is not None:
                binding = await self.identities.get_line_binding_for_user(grant.user_id)
                await self.notifications.enqueue(
                    user_id=grant.user_id,
                    line_binding_id=None if binding is None else binding.id,
                    event_type="expired",
                    resource_type="volunteer_access_grant",
                    resource_id=grant.id,
                    resource_version=grant.version,
                    payload={
                        "grant_status": "expired",
                        "valid_from": grant.valid_from,
                        "expires_at": grant.expires_at,
                        "next_action": "reapply",
                    },
                )
            changed += 1
        return changed


__all__ = ["VolunteerExpirationService"]
