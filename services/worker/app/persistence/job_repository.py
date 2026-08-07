from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.ai_job import AIProcessingJob

CLAIMABLE_STATUSES = ("pending", "pending_enqueue", "enqueue_failed", "retry_wait")


class WorkerJobRepository:
    """以 Organization Scope 操作 AI Job，並以 row lock 保護 claim。"""

    def __init__(self, session: AsyncSession, organization_id: UUID, *, worker_id: str) -> None:
        self.session = session
        self.organization_id = organization_id
        self.worker_id = worker_id

    async def claim_next(self) -> tuple[AIProcessingJob, str] | None:
        await set_organization_scope(self.session, self.organization_id)
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(AIProcessingJob)
            .where(
                AIProcessingJob.organization_id == self.organization_id,
                AIProcessingJob.status.in_(CLAIMABLE_STATUSES),
                or_(
                    AIProcessingJob.available_at.is_(None),
                    AIProcessingJob.available_at <= now,
                ),
            )
            .order_by(AIProcessingJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        token = secrets.token_urlsafe(32)
        job.status = "running"
        job.claim_token = token
        job.claimed_at = now
        job.claimed_by = self.worker_id
        job.started_at = job.started_at or now
        await self.session.flush()
        return job, token

    async def reclaim_stale(self, *, timeout_seconds: int) -> int:
        await set_organization_scope(self.session, self.organization_id)
        threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        result = await self.session.execute(
            select(AIProcessingJob).where(
                AIProcessingJob.organization_id == self.organization_id,
                AIProcessingJob.status == "running",
                AIProcessingJob.claimed_at < threshold,
            )
        )
        jobs = list(result.scalars())
        now = datetime.now(timezone.utc)
        for job in jobs:
            job.status = "retry_wait"
            job.retry_count += 1
            job.available_at = now
            job.claim_token = None
            job.claimed_at = None
            job.claimed_by = None
        await self.session.flush()
        return len(jobs)

    async def finish(
        self,
        job_id: UUID,
        *,
        claim_token: str,
        status: str,
        failure_reason: str | None = None,
    ) -> AIProcessingJob:
        if status not in {"succeeded", "failed", "retry_wait"}:
            raise DomainError("invalid_job_status", "AI Job 結束狀態無效", 422)
        await set_organization_scope(self.session, self.organization_id)
        result = await self.session.execute(
            select(AIProcessingJob).where(
                AIProcessingJob.id == job_id,
                AIProcessingJob.organization_id == self.organization_id,
            )
        )
        job = result.scalar_one_or_none()
        if job is None or job.claim_token != claim_token or job.claimed_by != self.worker_id:
            raise DomainError("job_claim_mismatch", "AI Job 不屬於目前 Worker Claim", 409)
        now = datetime.now(timezone.utc)
        job.status = status
        job.failure_reason = failure_reason
        job.completed_at = now if status in {"succeeded", "failed"} else None
        job.available_at = now if status == "retry_wait" else None
        job.claim_token = None
        job.claimed_at = None
        job.claimed_by = None
        await self.session.flush()
        return job
