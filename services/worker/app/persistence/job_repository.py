from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.application.async_job_types import LEGACY_POLLING_JOB_TYPES
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.models.care_report import CareReport

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
                AIProcessingJob.execution_backend == "legacy_polling",
                AIProcessingJob.job_type.in_(LEGACY_POLLING_JOB_TYPES),
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

    async def reclaim_stale(self, *, timeout_seconds: int, max_retries: int = 3) -> int:
        await set_organization_scope(self.session, self.organization_id)
        threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        result = await self.session.execute(
            select(AIProcessingJob).where(
                AIProcessingJob.organization_id == self.organization_id,
                AIProcessingJob.execution_backend == "legacy_polling",
                AIProcessingJob.job_type.in_(LEGACY_POLLING_JOB_TYPES),
                AIProcessingJob.status == "running",
                AIProcessingJob.claimed_at < threshold,
            )
        )
        jobs = list(result.scalars())
        now = datetime.now(timezone.utc)
        for job in jobs:
            job.retry_count += 1
            terminal = job.retry_count >= max_retries
            job.status = "failed" if terminal else "retry_wait"
            job.failure_reason = "stale_claim_exhausted" if terminal else "stale_claim"
            job.completed_at = now if terminal else None
            job.available_at = None if terminal else now
            job.claim_token = None
            job.claimed_at = None
            job.claimed_by = None
            if getattr(job, "job_type", None) == "care_report_summary":
                report = await self.session.scalar(
                    select(CareReport).where(
                        CareReport.id == job.target_id,
                        CareReport.organization_id == self.organization_id,
                    )
                )
                if report is not None:
                    report.summary_status = "failed" if terminal else "pending"
        await self.session.flush()
        return len(jobs)

    async def finish(
        self,
        job_id: UUID,
        *,
        claim_token: str,
        status: str,
        failure_reason: str | None = None,
        available_at: datetime | None = None,
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
        job.available_at = (available_at or now) if status == "retry_wait" else None
        job.claim_token = None
        job.claimed_at = None
        job.claimed_by = None
        await self.session.flush()
        return job
