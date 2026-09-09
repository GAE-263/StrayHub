"""Manual E1/hard-timeout probe; requires local PostgreSQL, Redis and worker."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import redis.asyncio as redis
from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.celery_app import celery_app
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.models.ai_job import AIProcessingJob
from services.api.app.persistence.repositories.adoption_draft_repository import (
    adoption_draft_token_digest,
)
from services.worker.app.tasks.reconciliation import _publish
from sqlalchemy import select


async def _wait_for_status(job_id, organization_id, expected: str, timeout: float) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            status = await session.scalar(
                select(AIProcessingJob.status).where(AIProcessingJob.id == job_id)
            )
        if status == expected:
            return
        await asyncio.sleep(0.2)
    raise TimeoutError(f"job did not reach {expected}")


async def main() -> None:
    organization_id, adopter_id, animal_id, draft_id, job_id = (uuid4() for _ in range(5))
    settings = get_settings()
    database_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(
            "INSERT INTO organizations (id,name,code,status,created_at,updated_at) "
            "VALUES ($1,'Timeout Probe',$2,'active',now(),now())",
            organization_id,
            f"TIMEOUT-{organization_id.hex[:8]}",
        )
        await connection.execute(
            "INSERT INTO users (id,username,display_name,status,created_at,updated_at) "
            "VALUES ($1,$2,'Timeout Probe','active',now(),now())",
            adopter_id,
            f"timeout-{adopter_id.hex[:8]}",
        )
        await connection.execute(
            "INSERT INTO animals "
            "(id,organization_id,name,status,is_adoptable,created_at,updated_at) "
            "VALUES ($1,$2,'小安', 'active',true,now(),now())",
            animal_id,
            organization_id,
        )
        async with session_factory() as session, session.begin():
            await set_organization_scope(session, organization_id)
            now = datetime.now(timezone.utc)
            session.add_all(
                [
                    AdoptionDraft(
                        id=draft_id,
                        opaque_token_digest=adoption_draft_token_digest(str(draft_id)),
                        organization_id=organization_id,
                        adopter_user_id=adopter_id,
                        path="specific_animal",
                        target_animal_id=animal_id,
                        current_step="awaiting_ai_suitability",
                        answers={"housing_type": "house"},
                        reconfirmation_keys=[],
                        interaction_version=1,
                        status="active",
                        last_interaction_at=now,
                        expires_at=now + timedelta(hours=1),
                    ),
                    AIProcessingJob(
                        id=job_id,
                        organization_id=organization_id,
                        job_type="adoption_suitability",
                        target_type="adoption_draft",
                        target_id=draft_id,
                        domain_version=1,
                        execution_backend="celery",
                        provider="google_gemini",
                        model_name="probe",
                        model_version="probe",
                        prompt_template_id="probe",
                        prompt_version="1",
                        output_schema_version="1",
                        status="queued",
                        retry_count=0,
                    ),
                ]
            )
        payload = {
            "job_id": str(job_id),
            "resource_id": str(draft_id),
            "organization_id": str(organization_id),
            "expected_version": 1,
        }
        celery_app.send_task(
            "test.suitability_hard_timeout_probe",
            kwargs=payload,
            task_id=str(job_id),
            queue="release-probe-control",
        )
        await _wait_for_status(job_id, organization_id, "running", 10)
        await asyncio.sleep(5)
        published = await _publish(session_factory, job_id=job_id, organization_id=organization_id)
        if not published:
            raise RuntimeError("stale running job was not republished")
        broker = redis.from_url(settings.celery_broker_url)
        try:
            queued = await broker.llen(settings.celery_queue_ai)
            if queued != 1:
                raise RuntimeError(f"recovery publish was not queued: {queued=}")
            print(json.dumps({"hard_timeout": "observed", "recovery": "queued"}))
        finally:
            await broker.delete(settings.celery_queue_ai)
            await broker.aclose()
    finally:
        await connection.execute(
            "DELETE FROM ai_processing_jobs WHERE organization_id=$1", organization_id
        )
        await connection.execute(
            "DELETE FROM adoption_drafts WHERE organization_id=$1", organization_id
        )
        await connection.execute("DELETE FROM animals WHERE organization_id=$1", organization_id)
        await connection.execute("DELETE FROM users WHERE id=$1", adopter_id)
        await connection.execute("DELETE FROM organizations WHERE id=$1", organization_id)
        await connection.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
