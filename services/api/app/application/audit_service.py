from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.database.base import model_dump_for_audit
from services.api.app.persistence.models.audit import AuditRecord


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        organization_id: UUID | None,
        actor_user_id: UUID | None,
        actor_reference: str | None = None,
        action: str,
        resource_type: str,
        resource_id: UUID | None = None,
        operation_id: UUID | None = None,
        source_channel: str,
        before: Any = None,
        after: Any = None,
        reason: str | None = None,
        result: str = "success",
    ) -> AuditRecord:
        if not action or not resource_type or not source_channel:
            raise ValueError("audit action, resource_type and source_channel are required")
        if organization_id is None and resource_type not in {"organization", "platform"}:
            raise ValueError("tenant business audit records require an organization scope")
        if actor_user_id is None and not (actor_reference or "").strip():
            raise ValueError("system audit records require actor_reference")
        if actor_user_id is not None and actor_reference is not None:
            raise ValueError("audit record must use exactly one actor identity")
        record = AuditRecord(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            actor_type="system" if actor_user_id is None else "user",
            actor_reference=(actor_reference or "").strip() or None,
            operation_id=operation_id or uuid4(),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            source_channel=source_channel,
            before_data=model_dump_for_audit(before) if before is not None else None,
            after_data=model_dump_for_audit(after) if after is not None else None,
            reason=reason,
            result=result,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def record_scope_switch(
        self, *, actor_user_id: UUID, organization_id: UUID, reason: str | None = None
    ) -> AuditRecord:
        return await self.record(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="scope_switch",
            resource_type="shelter_context",
            source_channel="api",
            reason=reason,
        )

    async def record_denial(
        self,
        *,
        organization_id: UUID | None,
        actor_user_id: UUID | None,
        resource_type: str,
        resource_id: UUID | None = None,
        source_channel: str = "api",
        reason: str | None = None,
        before: Any = None,
        after: Any = None,
    ) -> AuditRecord:
        return await self.record(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="access_denied",
            resource_type=resource_type,
            resource_id=resource_id,
            source_channel=source_channel,
            before=before,
            after=after,
            reason=reason,
            result="denied",
        )

    async def record_correction(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        before: Any,
        after: Any,
        source_channel: str = "api",
        reason: str | None = None,
    ) -> AuditRecord:
        return await self.record(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="correction",
            resource_type=resource_type,
            resource_id=resource_id,
            source_channel=source_channel,
            before=before,
            after=after,
            reason=reason,
        )

    async def record_archive(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        resource_type: str,
        resource_id: UUID,
        source_channel: str = "api",
        reason: str | None = None,
    ) -> AuditRecord:
        return await self.record(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="archive",
            resource_type=resource_type,
            resource_id=resource_id,
            source_channel=source_channel,
            reason=reason,
        )
