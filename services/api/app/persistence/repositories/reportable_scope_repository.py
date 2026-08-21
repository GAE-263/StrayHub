from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.reportable_scope import DailyReportableScope


class ReportableScopeRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    def _scoped(self, entity, *, volunteer_user_id: UUID, current: datetime):
        """Every scope query shares this join; a second copy of it would drift.

        An animal can match through both its own row and its area, so the
        select is DISTINCT — without it the same animal appears twice.
        """
        return (
            select(entity)
            .select_from(DailyReportableScope)
            .join(
                Animal,
                and_(
                    Animal.organization_id == DailyReportableScope.organization_id,
                    or_(
                        DailyReportableScope.animal_id == Animal.id,
                        DailyReportableScope.area_id == Animal.area_id,
                    ),
                ),
            )
            .where(
                DailyReportableScope.organization_id == self.organization_id,
                DailyReportableScope.status == "active",
                DailyReportableScope.starts_at <= current,
                DailyReportableScope.ends_at >= current,
                Animal.status == "active",
                or_(
                    DailyReportableScope.volunteer_user_id.is_(None),
                    DailyReportableScope.volunteer_user_id == volunteer_user_id,
                ),
                or_(
                    DailyReportableScope.animal_id == Animal.id,
                    DailyReportableScope.area_id == Animal.area_id,
                ),
            )
            .distinct()
        )

    async def active_animal_ids(
        self, *, volunteer_user_id: UUID, now: datetime | None = None
    ) -> set[UUID]:
        result = await self.session.execute(
            self._scoped(
                Animal.id,
                volunteer_user_id=volunteer_user_id,
                current=now or datetime.now(timezone.utc),
            )
        )
        return {animal_id for animal_id in result.scalars() if animal_id is not None}

    async def active_animals(
        self, *, volunteer_user_id: UUID, now: datetime | None = None
    ) -> list[Animal]:
        """The animals themselves, so callers stop re-reading the whole shelter.

        Ordered by shelter number then name so the sequence a volunteer sees is
        stable between taps; ``id`` breaks remaining ties.
        """
        result = await self.session.execute(
            self._scoped(
                Animal,
                volunteer_user_id=volunteer_user_id,
                current=now or datetime.now(timezone.utc),
            ).order_by(Animal.shelter_number, Animal.name, Animal.id)
        )
        return list(result.scalars())

    async def is_animal_reportable(
        self, *, animal_id: UUID, volunteer_user_id: UUID, now: datetime | None = None
    ) -> bool:
        return animal_id in await self.active_animal_ids(
            volunteer_user_id=volunteer_user_id,
            now=now,
        )
