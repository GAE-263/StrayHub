from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.application.audit_service import AuditService
from services.api.app.application.ports.pii import PiiRevealAuditEvent
from services.api.app.persistence.database.scope import set_organization_scope


class CommittedPiiRevealAuditor:
    def __init__(
        self,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    ) -> None:
        self.session_factory = session_factory

    async def persist_committed_reveal(self, event: PiiRevealAuditEvent) -> None:
        async with self.session_factory() as session:
            await set_organization_scope(session, event.organization_id)
            await AuditService(session).record(
                organization_id=event.organization_id,
                actor_user_id=event.actor_user_id,
                action="pii.revealed",
                resource_type="volunteer_application_profile",
                resource_id=event.application_id,
                source_channel="crm",
                after={
                    "provided_fields": event.provided_fields,
                    "actor_role": event.actor_role,
                    "data_category": event.provided_fields,
                    "purpose_code": event.purpose_code,
                    "request_id": event.request_id,
                    "policy_version": event.policy_version,
                    "encryption_key_version": event.encryption_key_version,
                    "retention_expires_at": event.retention_expires_at,
                },
                reason=None,
            )
            await session.commit()
