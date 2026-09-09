from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.api.app.application.async_job_types import CELERY_TASK_BY_JOB_TYPE
from services.api.app.infrastructure.celery_app import celery_app
from services.api.app.observability.logging import get_logger
from services.api.app.persistence.database.scope import set_organization_scope, set_platform_scope
from services.api.app.persistence.models.ai_job import AIProcessingJob

logger = get_logger(__name__)
RECONCILE_BATCH_SIZE = 100


def _payload(job: AIProcessingJob) -> dict[str, str | int]:
    return {
        "job_id": str(job.id),
        "resource_id": str(job.target_id),
        "organization_id": str(job.organization_id),
        "expected_version": job.domain_version,
    }


async def dispatch_ai_job(
    job_id: UUID, organization_id: UUID, *, factory: async_sessionmaker[AsyncSession]
) -> bool:
    """Best-effort post-commit publish; the persisted job remains recoverable."""
    async with factory() as session:
        async with session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.scalar(
                select(AIProcessingJob).where(
                    AIProcessingJob.id == job_id,
                    AIProcessingJob.organization_id == organization_id,
                    AIProcessingJob.execution_backend == "celery",
                )
            )
            if (
                job is None
                or job.status not in {"pending_enqueue", "enqueue_failed"}
                or job.job_type not in CELERY_TASK_BY_JOB_TYPE
            ):
                return False
            task_name = CELERY_TASK_BY_JOB_TYPE[job.job_type]
            payload = _payload(job)
    try:
        result = celery_app.send_task(task_name, kwargs=payload, task_id=str(job_id))
    except Exception:
        logger.exception(
            "celery_job_publish_failed",
            extra={"job_id": str(job_id), "organization_id": str(organization_id)},
        )
        await _mark_dispatch_status(
            job_id, organization_id, factory=factory, status="enqueue_failed"
        )
        return False
    await _mark_dispatch_status(
        job_id,
        organization_id,
        factory=factory,
        status="queued",
        celery_task_id=result.id,
    )
    return True


async def _mark_dispatch_status(
    job_id: UUID,
    organization_id: UUID,
    *,
    factory: async_sessionmaker[AsyncSession],
    status: str,
    celery_task_id: str | None = None,
) -> None:
    async with factory() as session:
        async with session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.scalar(
                select(AIProcessingJob)
                .where(
                    AIProcessingJob.id == job_id,
                    AIProcessingJob.organization_id == organization_id,
                    AIProcessingJob.execution_backend == "celery",
                )
                .with_for_update()
            )
            if job is None or job.status not in {"pending_enqueue", "enqueue_failed", "queued"}:
                return
            job.status = status
            if celery_task_id is not None:
                job.celery_task_id = celery_task_id
                job.dispatched_at = datetime.now(timezone.utc)


async def pending_celery_dispatches(
    factory: async_sessionmaker[AsyncSession],
    *,
    visibility_timeout: int,
    limit: int = RECONCILE_BATCH_SIZE,
) -> list[tuple[UUID, UUID]]:
    bounded_limit = max(1, min(limit, RECONCILE_BATCH_SIZE))
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(seconds=visibility_timeout)
    async with factory() as session:
        async with session.begin():
            await set_platform_scope(session)
            rows = await session.execute(
                select(AIProcessingJob.id, AIProcessingJob.organization_id)
                .where(
                    AIProcessingJob.execution_backend == "celery",
                    or_(
                        AIProcessingJob.status.in_(
                            ("pending_enqueue", "enqueue_failed", "retry_wait")
                        ),
                        (
                            (AIProcessingJob.status == "running")
                            & or_(
                                AIProcessingJob.claimed_at.is_(None),
                                AIProcessingJob.claimed_at < stale_before,
                            )
                        ),
                        (
                            AIProcessingJob.status.in_(("succeeded", "failed"))
                            & AIProcessingJob.job_type.in_(
                                (
                                    "adoption_suitability",
                                    "adoption_profile_extraction",
                                    "adoption_followup_recommendations",
                                    "adoption_recommendation_curation",
                                    "growth_diary_analysis",
                                )
                            )
                            & AIProcessingJob.validation_result["notification_status"]
                            .as_string()
                            .in_(("pending", "retry_wait", "failed", "sending"))
                        ),
                    ),
                    or_(
                        AIProcessingJob.available_at.is_(None),
                        AIProcessingJob.available_at <= now,
                    ),
                )
                .order_by(AIProcessingJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(bounded_limit)
            )
            return list(rows.all())
