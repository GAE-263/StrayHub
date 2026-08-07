from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.observation import ObservationCategory, ObservationOption


class ObservationRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def effective_options(
        self, *, include_disabled_history: bool = False
    ) -> list[ObservationOption]:
        status_clause = True if include_disabled_history else ObservationOption.status == "active"
        result = await self.session.execute(
            select(ObservationOption)
            .where(
                or_(
                    ObservationOption.organization_id.is_(None),
                    ObservationOption.organization_id == self.organization_id,
                ),
                status_clause,
            )
            .order_by(ObservationOption.display_order, ObservationOption.code)
        )
        return list(result.scalars())

    async def categories(self) -> list[ObservationCategory]:
        result = await self.session.execute(
            select(ObservationCategory)
            .where(
                or_(
                    ObservationCategory.organization_id.is_(None),
                    ObservationCategory.organization_id == self.organization_id,
                ),
                ObservationCategory.status == "active",
            )
            .order_by(ObservationCategory.display_order)
        )
        return list(result.scalars())

    async def add_option(self, option: ObservationOption) -> ObservationOption:
        if option.organization_id != self.organization_id:
            raise ValueError("organization option scope mismatch")
        self.session.add(option)
        await self.session.flush()
        return option

    async def get_option(self, option_id: UUID) -> ObservationOption | None:
        result = await self.session.execute(
            select(ObservationOption).where(
                ObservationOption.id == option_id,
                ObservationOption.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()
