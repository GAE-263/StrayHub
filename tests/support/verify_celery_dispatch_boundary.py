"""Run only in the disposable boundary-test Worker image/network, never a live DB.

Pipe this script to the isolated Worker container's ``python -``. The publisher
is stubbed; real transactions, Worker settings, and reconciliation are exercised.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import delete, select


def main() -> None:
    database = urlsplit(os.environ.get("DATABASE_URL", ""))
    broker = urlsplit(os.environ.get("CELERY_BROKER_URL", ""))
    assert os.environ.get("BOUNDARY_TEST_PROJECT") == "strayhub-celery-boundary-local"
    assert database.hostname == "postgres" and database.path == "/strayhub_test"
    assert database.username == "boundary"
    assert broker.hostname == "redis" and broker.path == "/0"
    assert os.environ.get("APP_ENV") == "production"
    assert os.environ.get("CELERY_AI_ENABLED") == "false"

    from services.api.app.application.celery_job_dispatch import dispatch_ai_job
    from services.api.app.infrastructure.celery_app import celery_app
    from services.api.app.persistence.database.scope import set_organization_scope
    from services.api.app.persistence.models.ai_job import AIProcessingJob
    from services.api.app.persistence.models.identity import Organization
    from services.worker.app.celery_runtime import runtime
    from services.worker.app.tasks.reconciliation import reconcile_ai_dispatch

    celery_app.loader.import_default_modules()
    org_id, job_id, target_id = uuid4(), uuid4(), uuid4()

    async def seed(factory):
        async with factory() as session, session.begin():
            session.add(Organization(id=org_id, name="Boundary synthetic", code=str(org_id)))
            await session.flush()
            await set_organization_scope(session, org_id)
            session.add(
                AIProcessingJob(
                    id=job_id,
                    organization_id=org_id,
                    target_id=target_id,
                    job_type="adoption_suitability",
                    target_type="adoption_draft",
                    execution_backend="celery",
                    status="pending_enqueue",
                    domain_version=1,
                    provider="mock",
                    model_name="boundary",
                    model_version="1",
                    prompt_template_id="boundary",
                    prompt_version="1",
                    output_schema_version="1",
                )
            )

    async def status(factory):
        async with factory() as session, session.begin():
            await set_organization_scope(session, org_id)
            return await session.scalar(
                select(AIProcessingJob.status).where(
                    AIProcessingJob.id == job_id,
                    AIProcessingJob.organization_id == org_id,
                )
            )

    async def cleanup(factory):
        async with factory() as session, session.begin():
            await set_organization_scope(session, org_id)
            await session.execute(
                delete(AIProcessingJob).where(
                    AIProcessingJob.id == job_id,
                    AIProcessingJob.organization_id == org_id,
                )
            )
            await session.execute(delete(Organization).where(Organization.id == org_id))

    try:
        runtime.run(seed)
        with patch.object(celery_app, "send_task", side_effect=ConnectionError("synthetic outage")):
            assert not runtime.run(
                lambda factory: dispatch_ai_job(job_id, uuid4(), factory=factory)
            )
            assert not runtime.run(lambda factory: dispatch_ai_job(job_id, org_id, factory=factory))
            assert runtime.run(status) == "enqueue_failed"
            assert reconcile_ai_dispatch.run() == 0
            assert runtime.run(status) == "enqueue_failed"
        with patch.object(
            celery_app, "send_task", return_value=SimpleNamespace(id=str(job_id))
        ) as send:
            assert reconcile_ai_dispatch.run() == 1
            assert runtime.run(status) == "queued"
            assert reconcile_ai_dispatch.run() == 0
            assert not runtime.run(lambda factory: dispatch_ai_job(job_id, org_id, factory=factory))
            send.assert_called_once()
            assert send.call_args.kwargs["kwargs"]["organization_id"] == str(org_id)
            assert send.call_args.kwargs["task_id"] == str(job_id)
        assert "services.api.app.persistence.database.engine" not in sys.modules
        print(
            "PASS: production Worker settings; real dispatch/reconciliation; "
            "tenant guard; retry; dedup"
        )
    finally:
        runtime.run(cleanup)
        runtime.close()


if __name__ == "__main__":
    main()
