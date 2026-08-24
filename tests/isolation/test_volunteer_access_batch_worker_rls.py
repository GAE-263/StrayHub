import os
from datetime import date, datetime, timezone
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.persistence.database.scope import set_organization_scope
from services.worker.app.handlers.volunteer_access_handler import VolunteerAccessHandler
from services.worker.app.persistence.volunteer_access_repository import (
    WorkerVolunteerAccessRepository,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.integration.test_volunteer_access_approval import (
    _cleanup_approval_fixture,
    _seed_pending_application,
)


@pytest.mark.asyncio
async def test_worker_can_load_and_process_queued_tenant_scoped_batch() -> None:
    connection = await asyncpg.connect(os.environ["STRAYHUB_TEST_DATABASE_URL"])
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id = uuid4()
    other_organization_id = uuid4()
    user_id = uuid4()
    actor_user_id = uuid4()
    application_id = uuid4()
    batch_id = uuid4()
    item_id = uuid4()
    now = datetime.now(timezone.utc)
    try:
        await _seed_pending_application(
            connection,
            organization_id=organization_id,
            user_id=user_id,
            actor_user_id=actor_user_id,
            application_id=application_id,
            now=now,
        )
        await connection.execute(
            """INSERT INTO volunteer_application_service_dates
               (id, organization_id, application_id, service_date, status,
                version, created_at, updated_at)
               VALUES ($1, $2, $3, $4, 'pending', 1, $5, $5)""",
            uuid4(),
            organization_id,
            application_id,
            date(2026, 8, 25),
            now,
        )
        await connection.execute(
            """INSERT INTO volunteer_decision_batches
               (id, organization_id, operation_id, actor_user_id, decision, reason,
                selection_mode, filter_snapshot, snapshot_at, request_fingerprint,
                status, requested_count, created_at, updated_at)
               VALUES ($1, $2, $3, $4, 'reject', 'worker regression', 'explicit_items', $5, $6, $7,
                       'queued', 1, $6, $6)""",
            batch_id,
            organization_id,
            uuid4(),
            actor_user_id,
            '{"service_date":"2026-08-25"}',
            now,
            "worker-rls-regression",
        )
        await connection.execute(
            """INSERT INTO volunteer_decision_batch_items
               (id, organization_id, batch_id, application_id, expected_version,
                result, created_at, updated_at)
               VALUES ($1, $2, $3, $4, 1, 'pending', $5, $5)""",
            item_id,
            organization_id,
            batch_id,
            application_id,
            now,
        )

        async with sessions() as session:
            await set_organization_scope(session, organization_id)
            repository = WorkerVolunteerAccessRepository(
                session, organization_id, worker_id="worker-rls-test"
            )
            assert (await repository.batch(batch_id)) is not None

            other_repository = WorkerVolunteerAccessRepository(
                session, other_organization_id, worker_id="worker-rls-test"
            )
            assert (await other_repository.batch(batch_id)) is None

        async with sessions() as session:
            result = await VolunteerAccessHandler(
                session, worker_id="worker-rls-test"
            ).process_batch_chunk(organization_id, batch_id)
            assert result is not None
            assert result.status in {"completed", "completed_with_errors"}

        persisted = await connection.fetchrow(
            """SELECT batch.status, item.result, item.error_code, application.status,
                      application.version, service_date.status, service_date.version
               FROM volunteer_decision_batches AS batch
               JOIN volunteer_decision_batch_items AS item ON item.batch_id = batch.id
               JOIN volunteer_applications AS application
                 ON application.id = item.application_id
               JOIN volunteer_application_service_dates AS service_date
                 ON service_date.application_id = application.id
                AND service_date.service_date = '2026-08-25'
               WHERE batch.id = $1""",
            batch_id,
        )
        assert persisted is not None
        assert tuple(persisted) == (
            "completed",
            "succeeded",
            None,
            "rejected",
            2,
            "rejected",
            2,
        ), tuple(persisted)
    finally:
        await connection.execute(
            """DELETE FROM volunteer_application_service_dates
               WHERE organization_id = ANY($1::uuid[])""",
            [organization_id, other_organization_id],
        )
        await connection.execute(
            """DELETE FROM audit_records
               WHERE organization_id = ANY($1::uuid[])""",
            [organization_id, other_organization_id],
        )
        await connection.execute(
            """DELETE FROM volunteer_notification_deliveries
               WHERE organization_id = ANY($1::uuid[])""",
            [organization_id, other_organization_id],
        )
        await _cleanup_approval_fixture(
            connection,
            organization_ids=[organization_id, other_organization_id],
            user_ids=[user_id, actor_user_id],
        )
        await engine.dispose()
        await connection.close()
