from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.reportable_scope import DailyReportableScope


class ReportableScopeRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def active_animal_ids(
        self, *, volunteer_user_id: UUID, now: datetime | None = None
    ) -> set[UUID]:
        current = now or datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Animal.id)
            .join(Animal, Animal.organization_id == DailyReportableScope.organization_id)
            .where(
                DailyReportableScope.organization_id == self.organization_id,
                DailyReportableScope.status == "active",
                DailyReportableScope.starts_at <= current,
                DailyReportableScope.ends_at >= current,
                or_(
                    DailyReportableScope.volunteer_user_id.is_(None),
                    DailyReportableScope.volunteer_user_id == volunteer_user_id,
                ),
                or_(
                    DailyReportableScope.animal_id == Animal.id,
                    DailyReportableScope.area_id == Animal.area_id,
                ),
            )
        )
        return {animal_id for animal_id in result.scalars() if animal_id is not None}

    async def is_animal_reportable(
        self, *, animal_id: UUID, volunteer_user_id: UUID, now: datetime | None = None
    ) -> bool:
        return animal_id in await self.active_animal_ids(
            volunteer_user_id=volunteer_user_id,
            now=now,
        )
