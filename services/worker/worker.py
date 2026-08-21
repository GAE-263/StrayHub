"""Background Worker entry point for local development."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from sqlalchemy import select

from services.api.app.persistence.database.scope import set_platform_scope
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.models.volunteer_access import VolunteerDecisionBatch
from services.worker.app.handlers.ai_job_runner import AIJobRunner, build_ai_client
from services.worker.app.handlers.volunteer_access_handler import VolunteerAccessHandler
from services.worker.app.persistence.session import create_worker_session_factory

VOLUNTEER_WORK_INTERVAL_SECONDS = 60
# AI Job 的節奏比志工權限作業快，志工送出回報後不應等上一分鐘才開始分析。
AI_WORK_INTERVAL_SECONDS = 15


async def active_organization_ids(factory) -> list:
    async with factory() as discovery_session:
        await set_platform_scope(discovery_session)
        return list(
            (
                await discovery_session.execute(
                    select(Organization.id).where(Organization.status == "active")
                )
            ).scalars()
        )


async def run_volunteer_iteration(factory, *, worker_id: str) -> None:
    organization_ids = await active_organization_ids(factory)
    for organization_id in organization_ids:
        async with factory() as session:
            handler = VolunteerAccessHandler(session, worker_id=worker_id)
            await handler.expire_access(organization_id)
        async with factory() as session:
            await set_platform_scope(session)
            batch_ids = list(
                (
                    await session.execute(
                        select(VolunteerDecisionBatch.id).where(
                            VolunteerDecisionBatch.organization_id == organization_id,
                            VolunteerDecisionBatch.status.in_(("queued", "processing")),
                        )
                    )
                ).scalars()
            )
        for batch_id in batch_ids:
            async with factory() as session:
                await VolunteerAccessHandler(session, worker_id=worker_id).process_batch_chunk(
                    organization_id, batch_id
                )
        async with factory() as session:
            await VolunteerAccessHandler(session, worker_id=worker_id).deliver_notifications(
                organization_id
            )


async def run_ai_iteration(factory, *, worker_id: str, client, storage=None) -> None:
    organization_ids = await active_organization_ids(factory)
    for organization_id in organization_ids:
        runner = AIJobRunner(factory, worker_id=worker_id, client=client, storage=storage)
        await runner.run_pending(organization_id)


async def _run_forever(work, *, interval_seconds: float) -> None:
    while True:
        try:
            await work()
        except asyncio.CancelledError:
            raise
        except Exception:
            # The next bounded iteration retries stale claims and pending work.
            pass
        await asyncio.sleep(interval_seconds)


async def run() -> None:
    factory = create_worker_session_factory()
    worker_id = os.environ.get("STRAYHUB_WORKER_ID", f"worker-{uuid4()}")
    ai_client = build_ai_client()
    try:
        # 兩條迴圈各自獨立：志工權限作業卡住時，AI 分析仍要繼續消化佇列。
        await asyncio.gather(
            _run_forever(
                lambda: run_volunteer_iteration(factory, worker_id=worker_id),
                interval_seconds=VOLUNTEER_WORK_INTERVAL_SECONDS,
            ),
            _run_forever(
                lambda: run_ai_iteration(factory, worker_id=worker_id, client=ai_client),
                interval_seconds=AI_WORK_INTERVAL_SECONDS,
            ),
        )
    finally:
        await factory.kw["bind"].dispose()


if __name__ == "__main__":
    asyncio.run(run())
