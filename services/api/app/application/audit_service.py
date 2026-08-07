from __future__ import annotations

from typing import Any
from uuid import UUID

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
        action: str,
        resource_type: str,
        resource_id: UUID | None = None,
        source_channel: str,
        before: Any = None,
        after: Any = None,
        reason: str | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            source_channel=source_channel,
            before_data=model_dump_for_audit(before) if before is not None else None,
            after_data=model_dump_for_audit(after) if after is not None else None,
            reason=reason,
        )
        self.session.add(record)
        await self.session.flush()
        return record
