from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.database.scope import (
    set_authentication_user_scope,
    set_organization_scope,
)
from services.api.app.persistence.models.care_report_handoff import CareReportHandoff


class CareReportHandoffRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        if not isinstance(organization_id, UUID):
            raise DomainError("organization_scope_required", "缺少收容所資料範圍", 403)
        self.session = session
        self.organization_id = organization_id

    async def replace_pending(
        self, handoff: CareReportHandoff, *, now: datetime
    ) -> CareReportHandoff:
        if handoff.organization_id != self.organization_id:
            raise DomainError("organization_scope_mismatch", "收容所資料範圍不符", 404)

        # A handoff is globally unique per authenticated user, not per shelter.
        # The authenticated-user RLS scope exposes only that user's handoffs and
        # is restored to the verified organization before returning.
        await set_authentication_user_scope(self.session, handoff.user_id)
        try:
            await self.session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": f"care-report-handoff:{handoff.user_id}"},
            )
            result = await self.session.execute(
                select(CareReportHandoff)
                .where(
                    CareReportHandoff.user_id == handoff.user_id,
                    CareReportHandoff.status == "pending",
                )
                .with_for_update()
            )
            pending = list(result.scalars())
            for existing in pending:
                existing.status = "superseded"
                existing.superseded_at = now
            if pending:
                await self.session.flush()
            self.session.add(handoff)
            await self.session.flush()
            return handoff
        finally:
            await set_organization_scope(self.session, self.organization_id)

    async def lock_pending_for_user(self, user_id: UUID) -> CareReportHandoff | None:
        result = await self.session.execute(
            select(CareReportHandoff)
            .where(
                CareReportHandoff.organization_id == self.organization_id,
                CareReportHandoff.user_id == user_id,
                CareReportHandoff.status == "pending",
            )
            .order_by(CareReportHandoff.created_at.desc(), CareReportHandoff.id.desc())
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def latest_for_user(self, user_id: UUID) -> CareReportHandoff | None:
        result = await self.session.execute(
            select(CareReportHandoff)
            .where(
                CareReportHandoff.organization_id == self.organization_id,
                CareReportHandoff.user_id == user_id,
            )
            .order_by(CareReportHandoff.created_at.desc(), CareReportHandoff.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def flush(self) -> None:
        await self.session.flush()
