"""Background Worker entry point for local development."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from sqlalchemy import select

from services.api.app.persistence.database.scope import set_platform_scope
from services.api.app.persistence.models.identity import Organization
from services.api.app.persistence.models.volunteer_access import VolunteerDecisionBatch
from services.worker.app.handlers.volunteer_access_handler import VolunteerAccessHandler
from services.worker.app.persistence.session import create_worker_session_factory

VOLUNTEER_WORK_INTERVAL_SECONDS = 60


async def run_volunteer_iteration(factory, *, worker_id: str) -> None:
    async with factory() as discovery_session:
        await set_platform_scope(discovery_session)
        organization_ids = list(
            (
                await discovery_session.execute(
                    select(Organization.id).where(Organization.status == "active")
                )
            ).scalars()
        )
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


async def run() -> None:
    factory = create_worker_session_factory()
    worker_id = os.environ.get("STRAYHUB_WORKER_ID", f"worker-{uuid4()}")
    try:
        while True:
            try:
                await run_volunteer_iteration(factory, worker_id=worker_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # The next bounded iteration retries stale claims and pending work.
                pass
            await asyncio.sleep(VOLUNTEER_WORK_INTERVAL_SECONDS)
    finally:
        await factory.kw["bind"].dispose()


if __name__ == "__main__":
    asyncio.run(run())
