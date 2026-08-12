from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.persistence.models.observation_usage import ObservationOptionUsage


class ObservationOptionUsageRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def count_for_option(self, option_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(ObservationOptionUsage.id)).where(
                ObservationOptionUsage.organization_id == self.organization_id,
                ObservationOptionUsage.observation_option_id == option_id,
            )
        )
        return int(result.scalar_one() or 0)

    async def has_usage(self, option_id: UUID) -> bool:
        result = await self.session.execute(
            select(ObservationOptionUsage.id)
            .where(
                ObservationOptionUsage.organization_id == self.organization_id,
                ObservationOptionUsage.observation_option_id == option_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def add(self, usage: ObservationOptionUsage) -> ObservationOptionUsage:
        if usage.organization_id != self.organization_id:
            raise ValueError("observation usage scope mismatch")
        self.session.add(usage)
        await self.session.flush()
        return usage

    async def for_report(self, report_id: UUID) -> list[ObservationOptionUsage]:
        result = await self.session.execute(
            select(ObservationOptionUsage).where(
                ObservationOptionUsage.organization_id == self.organization_id,
                ObservationOptionUsage.care_report_id == report_id,
            )
        )
        return list(result.scalars())

    async def clear_for_report(self, report_id: UUID) -> None:
        await self.session.execute(
            delete(ObservationOptionUsage).where(
                ObservationOptionUsage.organization_id == self.organization_id,
                ObservationOptionUsage.care_report_id == report_id,
            )
        )
