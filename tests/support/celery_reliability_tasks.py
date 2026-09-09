"""Fault-injection tasks loaded only by the manual Celery reliability probe."""

from __future__ import annotations

import time
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded
from celery import Task
from services.api.app.application.adoption_suitability_job_service import (
    claim_suitability_job,
)
from services.api.app.infrastructure.celery_app import celery_app
from services.worker.app.celery_runtime import runtime


@celery_app.task(bind=True, name="test.suitability_hard_timeout_probe")
def suitability_hard_timeout_probe(
    self: Task,
    *,
    job_id: str,
    resource_id: str,
    organization_id: str,
    expected_version: int,
) -> str:
    snapshot = runtime.run(
        lambda factory: claim_suitability_job(
            factory,
            job_id=UUID(job_id),
            draft_id=UUID(resource_id),
            organization_id=UUID(organization_id),
            expected_version=expected_version,
            claim_token=str(self.request.id),
            worker_name=str(self.request.hostname or "timeout-probe"),
        )
    )
    if snapshot is None:
        return "duplicate"
    try:
        time.sleep(30)
    except SoftTimeLimitExceeded:
        # Deliberately ignore the soft signal so Celery must terminate this
        # child at the hard limit. This module is never loaded in production.
        time.sleep(30)
    return "unexpected_completion"
