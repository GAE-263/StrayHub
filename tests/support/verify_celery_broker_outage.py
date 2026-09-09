"""Manual dispatcher probe; run while the configured Redis broker is down."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from services.api.app.application.celery_job_dispatch import dispatch_ai_job
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.ai_job import AIProcessingJob
from sqlalchemy import select
from tests.integration.test_celery_adoption_suitability import (
    _base_rows,
    _cleanup,
    _create_waiting_job,
)


async def main() -> None:
    organization_id = uuid4()
    adopter_id, animal_id, draft_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()
    await engine.dispose(close=False)
    await _base_rows(organization_id, adopter_id, animal_id)
    try:
        await _create_waiting_job(organization_id, adopter_id, animal_id, draft_id, job_id)
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            job = await session.scalar(select(AIProcessingJob).where(AIProcessingJob.id == job_id))
            assert job is not None
            job.status = "pending_enqueue"
        dispatched = await dispatch_ai_job(job_id, organization_id)
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            status = await session.scalar(
                select(AIProcessingJob.status).where(AIProcessingJob.id == job_id)
            )
        if dispatched or status != "enqueue_failed":
            raise RuntimeError(f"unsafe broker failure result: {dispatched=}, {status=}")
        print('{"broker_outage":"observed","job_status":"enqueue_failed"}')
    finally:
        await _cleanup(organization_id, adopter_id)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
