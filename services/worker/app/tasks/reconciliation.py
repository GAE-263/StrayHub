from __future__ import annotations

from sqlalchemy import select

from services.api.app.application.async_job_types import CELERY_TASK_BY_JOB_TYPE
from services.api.app.application.celery_job_dispatch import pending_celery_dispatches
from services.api.app.infrastructure.celery_app import celery_app
from services.api.app.observability.logging import get_logger
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.worker.app.celery_runtime import runtime

logger = get_logger(__name__)


@celery_app.task(name="system.reconcile_ai_dispatch")
def reconcile_ai_dispatch() -> int:
    pending = runtime.run(lambda factory: pending_celery_dispatches(factory))
    dispatched = 0
    for job_id, organization_id in pending:
        try:
            if runtime.run(
                lambda factory, job_id=job_id, organization_id=organization_id: _publish(
                    factory, job_id=job_id, organization_id=organization_id
                )
            ):
                dispatched += 1
        except Exception:
            logger.exception(
                "celery_reconciliation_publish_failed",
                extra={"job_id": str(job_id), "organization_id": str(organization_id)},
            )
    return dispatched


async def _publish(factory, *, job_id, organization_id) -> bool:
    async with factory() as session:
        async with session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.scalar(
                select(AIProcessingJob)
                .where(
                    AIProcessingJob.id == job_id,
                    AIProcessingJob.organization_id == organization_id,
                )
                .with_for_update()
            )
            if (
                job is None
                or job.execution_backend != "celery"
                or job.status not in {"pending_enqueue", "enqueue_failed", "running"}
                or job.job_type not in CELERY_TASK_BY_JOB_TYPE
            ):
                return False
            task_name = CELERY_TASK_BY_JOB_TYPE[job.job_type]
            payload = {
                "job_id": str(job.id),
                "resource_id": str(job.target_id),
                "organization_id": str(job.organization_id),
                "expected_version": job.domain_version,
            }
            result = celery_app.send_task(task_name, kwargs=payload, task_id=str(job.id))
            job.status = "queued"
            job.celery_task_id = result.id
            from datetime import datetime, timezone

            job.dispatched_at = datetime.now(timezone.utc)
            return True
