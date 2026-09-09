from __future__ import annotations

from uuid import UUID

from celery import Task

from services.api.app.config.settings import get_worker_settings
from services.api.app.infrastructure.celery_app import celery_app
from services.worker.app.celery_runtime import runtime
from services.worker.app.handlers.ai_job_runner import AIJobRunner, build_ai_client


@celery_app.task(bind=True, name="care_report.process_ai")
def process_ai(
    self: Task,
    *,
    job_id: str,
    resource_id: str,
    organization_id: str,
    expected_version: int,
) -> str:
    del resource_id, expected_version
    if not get_worker_settings().celery_ai_enabled:
        return "disabled"
    job_uuid = UUID(job_id)
    organization_uuid = UUID(organization_id)
    claim_token = str(self.request.id or job_uuid)
    client = build_ai_client()
    processed = runtime.run(
        lambda factory: AIJobRunner(
            factory,
            worker_id=str(self.request.hostname or "celery-worker"),
            client=client,
        ).run_celery_job(organization_uuid, job_uuid, claim_token=claim_token)
    )
    return "processed" if processed else "ignored"
