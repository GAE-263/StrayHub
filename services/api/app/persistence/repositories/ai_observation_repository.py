from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.ai_observation import AIObservation


class AIObservationRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get(self, observation_id: UUID) -> AIObservation | None:
        result = await self.session.execute(
            select(AIObservation)
            .where(
                AIObservation.id == observation_id,
                AIObservation.organization_id == self.organization_id,
            )
            .options(joinedload(AIObservation.job))
        )
        return result.scalar_one_or_none()

    async def add(self, observation: AIObservation) -> AIObservation:
        if observation.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        self.session.add(observation)
        await self.session.flush()
        return observation

    async def list_for_job(self, job_id: UUID) -> list[AIObservation]:
        result = await self.session.execute(
            select(AIObservation)
            .where(
                AIObservation.organization_id == self.organization_id,
                AIObservation.job_id == job_id,
            )
            .order_by(AIObservation.created_at)
        )
        return list(result.scalars())

    async def list_for_source(self, source_id: UUID) -> list[AIObservation]:
        result = await self.session.execute(
            select(AIObservation)
            .where(
                AIObservation.organization_id == self.organization_id,
                AIObservation.source_id == source_id,
            )
            .order_by(AIObservation.created_at)
        )
        return list(result.scalars())

    async def list_for_report(self, report_id: UUID) -> list[AIObservation]:
        result = await self.session.execute(
            select(AIObservation)
            .join(AIProcessingJob, AIProcessingJob.id == AIObservation.job_id)
            .where(
                AIObservation.organization_id == self.organization_id,
                AIProcessingJob.organization_id == self.organization_id,
                AIProcessingJob.target_type == "care_report",
                AIProcessingJob.target_id == report_id,
            )
            .options(joinedload(AIObservation.job))
            .order_by(AIObservation.created_at)
        )
        return list(result.scalars())
