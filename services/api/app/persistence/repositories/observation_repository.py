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

    async def categories(self, *, include_disabled: bool = False) -> list[ObservationCategory]:
        status_clause = True if include_disabled else ObservationCategory.status == "active"
        result = await self.session.execute(
            select(ObservationCategory)
            .where(
                or_(
                    ObservationCategory.organization_id.is_(None),
                    ObservationCategory.organization_id == self.organization_id,
                ),
                status_clause,
            )
            .order_by(ObservationCategory.display_order)
        )
        return list(result.scalars())

    async def get_category(self, category_id: UUID) -> ObservationCategory | None:
        result = await self.session.execute(
            select(ObservationCategory).where(
                ObservationCategory.id == category_id,
                or_(
                    ObservationCategory.organization_id.is_(None),
                    ObservationCategory.organization_id == self.organization_id,
                ),
            )
        )
        return result.scalar_one_or_none()

    async def option_code_exists(self, code: str) -> bool:
        """Stable Codes are unique across the effective tenant vocabulary."""
        result = await self.session.execute(
            select(ObservationOption.id)
            .where(
                ObservationOption.code == code,
                or_(
                    ObservationOption.organization_id.is_(None),
                    ObservationOption.organization_id == self.organization_id,
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

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
