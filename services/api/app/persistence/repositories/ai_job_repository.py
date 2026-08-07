from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.ai_job import AIProcessingJob


class AIJobRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get(self, job_id: UUID) -> AIProcessingJob | None:
        result = await self.session.execute(
            select(AIProcessingJob).where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, job: AIProcessingJob) -> AIProcessingJob:
        if job.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        self.session.add(job)
        await self.session.flush()
        return job

    async def pending_reconciliation(self) -> list[AIProcessingJob]:
        result = await self.session.execute(
            select(AIProcessingJob).where(
                AIProcessingJob.organization_id == self.organization_id,
                AIProcessingJob.status.in_(
                    ["pending", "pending_enqueue", "enqueue_failed", "retry_wait"]
                ),
            )
        )
        return list(result.scalars())
