import json
import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_batch_service import VolunteerBatchService
from services.api.app.persistence.repositories.volunteer_access_repository import (
    VolunteerAccessRepository,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.integration.test_volunteer_access_approval import (
    _cleanup_approval_fixture,
    _seed_pending_application,
)


@pytest.mark.asyncio
async def test_all_filtered_snapshot_is_immutable_and_chunked_for_resume() -> None:
    applications = [SimpleNamespace(id=uuid4(), version=1, status="pending") for _ in range(1200)]

    class Repository:
        organization_id = uuid4()

        async def pending_snapshot(self, **filters):
            return list(applications)

        async def add_all(self, values):
            self.values = list(values)

        async def add(self, value):
            self.batch = value
            return value

    service = VolunteerBatchService(Repository())
    batch, items = await service.create_snapshot(
        actor_user_id=uuid4(),
        operation_id=uuid4(),
        decision="approve",
        selection_mode="all_filtered",
        explicit_items=None,
        filters={"status": "pending", "service_date": date(2026, 8, 25)},
        request_payload={"selection": "all_filtered"},
    )
    applications.append(SimpleNamespace(id=uuid4(), version=1, status="pending"))

    assert batch.requested_count == 1200
    assert len(items) == 1200
    assert all(len(chunk) <= 500 for chunk in service.chunks(items))
    assert sum(len(chunk) for chunk in service.chunks(items)) == 1200


@pytest.mark.asyncio
async def test_all_filtered_snapshot_requires_a_date_scope_at_service_boundary() -> None:
    class Repository:
        organization_id = uuid4()

        async def pending_snapshot(self, **filters):
            raise AssertionError("unscoped snapshot must not reach the repository")

    with pytest.raises(DomainError) as error:
        await VolunteerBatchService(Repository()).create_snapshot(
            actor_user_id=uuid4(),
            operation_id=uuid4(),
            decision="approve",
            selection_mode="all_filtered",
            explicit_items=None,
            filters={"status": "pending"},
            request_payload={"selection": "all_filtered"},
        )
    assert error.value.code == "invalid_batch_date_scope"


@pytest.mark.asyncio
async def test_same_operation_payload_replays_but_different_payload_conflicts() -> None:
    existing = SimpleNamespace(request_fingerprint="same")

    class Repository:
        organization_id = uuid4()

        async def batch_by_operation(self, operation_id):
            return existing

    service = VolunteerBatchService(Repository())
    assert service.validate_operation_replay(existing, "same") is existing
    with pytest.raises(DomainError, match="operation"):
        service.validate_operation_replay(existing, "different")


@pytest.mark.asyncio
async def test_processing_keeps_95_successes_and_reports_5_stale_conflicts() -> None:
    items = [
        SimpleNamespace(
            id=uuid4(),
            application_id=uuid4(),
            expected_version=1,
            override_valid_from=None,
            override_expires_at=None,
            result="pending",
            error_code=None,
            processed_at=None,
        )
        for _ in range(100)
    ]
    stale = {item.application_id for item in items[-5:]}

    class Repository:
        organization_id = uuid4()

        async def pending_batch_items(self, batch_id, *, limit):
            return items

        async def reconcile_batch_counts(self, batch_id):
            return {
                "requested": len(items),
                "succeeded": sum(item.result == "succeeded" for item in items),
                "conflict": sum(item.result == "conflict" for item in items),
                "failed": sum(item.result == "failed" for item in items),
            }

    class AccessService:
        async def decide_application(self, **kwargs):
            if kwargs["application_id"] in stale:
                raise DomainError("application_version_conflict", "stale", 409)
            return SimpleNamespace(version=2), None, None

    batch = SimpleNamespace(
        id=uuid4(),
        decision="approve",
        actor_user_id=uuid4(),
        reason=None,
        default_valid_from=None,
        default_expires_at=None,
        policy_version_used=1,
        default_duration_hours_used=168,
        status="queued",
        requested_count=100,
        processed_count=0,
        succeeded_count=0,
        conflict_count=0,
        failed_count=0,
        completed_at=None,
    )
    await VolunteerBatchService(Repository()).process_pending_items(batch, AccessService())

    assert batch.succeeded_count == 95
    assert batch.conflict_count == 5
    assert batch.status == "completed_with_errors"


@pytest.mark.asyncio
async def test_explicit_selection_carries_service_date_into_decision() -> None:
    application_id = uuid4()
    selected_date = date(2026, 8, 25)
    received_service_dates = []

    class Repository:
        organization_id = uuid4()

        async def batch_by_operation(self, operation_id):
            return None

        async def validate_explicit_service_date_targets(self, application_ids, *, service_date):
            self.validated = (list(application_ids), service_date)

        async def add(self, value):
            return value

        async def add_all(self, values):
            self.values = list(values)

        async def reconcile_batch_counts(self, batch_id):
            return {
                "requested": 1,
                "succeeded": 1,
                "conflict": 0,
                "failed": 0,
            }

    class AccessService:
        async def decide_application(self, **kwargs):
            received_service_dates.append(kwargs["service_date"])
            return SimpleNamespace(version=2), None, None

    repository = Repository()
    service = VolunteerBatchService(repository)
    batch, items = await service.create_snapshot(
        actor_user_id=uuid4(),
        operation_id=uuid4(),
        decision="approve",
        selection_mode="explicit_items",
        explicit_items=[(application_id, 1)],
        filters={"service_date": selected_date},
        request_payload={"selection": "explicit_items", "service_date": selected_date.isoformat()},
    )

    await service.process_pending_items(batch, AccessService(), claimed_items=items)

    assert repository.validated == ([application_id], selected_date)
    serialized_snapshot = json.loads(json.dumps(batch.filter_snapshot))
    assert serialized_snapshot["service_date"] == selected_date.isoformat()
    assert received_service_dates == [selected_date]
    assert batch.status == "completed"


@pytest.mark.asyncio
async def test_unassigned_all_filtered_snapshot_preserves_unassigned_filter() -> None:
    application = SimpleNamespace(id=uuid4(), version=1, status="pending")

    class Repository:
        organization_id = uuid4()

        async def pending_snapshot(self, **filters):
            self.filters = filters
            return [application]

        async def add(self, value):
            return value

        async def add_all(self, values):
            self.values = list(values)

    repository = Repository()
    await VolunteerBatchService(repository).create_snapshot(
        actor_user_id=uuid4(),
        operation_id=uuid4(),
        decision="reject",
        reason="資料不足",
        selection_mode="all_filtered",
        explicit_items=None,
        filters={"status": "pending", "unassigned": True},
        request_payload={"selection": "all_filtered", "unassigned": True},
    )

    assert repository.filters["unassigned"] is True


@pytest.mark.asyncio
async def test_reprocessing_batch_does_not_approve_succeeded_item_twice() -> None:
    class AccessService:
        def __init__(self):
            self.calls = 0

        async def decide_application(self, **kwargs):
            self.calls += 1
            return (
                SimpleNamespace(version=2),
                SimpleNamespace(id=uuid4()),
                SimpleNamespace(id=uuid4()),
            )

    connection = await asyncpg.connect(os.environ["STRAYHUB_TEST_DATABASE_URL"])
    engine = create_async_engine(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    organization_id = uuid4()
    user_id = uuid4()
    actor_user_id = uuid4()
    application_id = uuid4()
    batch_id = uuid4()
    item_id = uuid4()
    now = datetime.now(timezone.utc)
    access_service = AccessService()
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
            """INSERT INTO volunteer_decision_batches
               (id, organization_id, operation_id, actor_user_id, decision, selection_mode,
                snapshot_at, request_fingerprint, status, requested_count, processed_count,
                succeeded_count, conflict_count, failed_count, completed_at, created_at, updated_at)
               VALUES ($1, $2, $3, $4, 'approve', 'explicit_items', $5, $6, 'completed',
                       1, 1, 1, 0, 0, $5, $5, $5)""",
            batch_id,
            organization_id,
            uuid4(),
            actor_user_id,
            now,
            "a" * 64,
        )
        await connection.execute(
            """INSERT INTO volunteer_decision_batch_items
               (id, organization_id, batch_id, application_id, expected_version, result,
                resulting_application_version, processed_at, created_at, updated_at)
               VALUES ($1, $2, $3, $4, 1, 'succeeded', 2, $5, $5, $5)""",
            item_id,
            organization_id,
            batch_id,
            application_id,
            now,
        )

        async with sessions() as session:
            repository = VolunteerAccessRepository(session, organization_id)
            batch = await repository.batch(batch_id)
            assert batch is not None
            await VolunteerBatchService(repository).process_pending_items(batch, access_service)
            await session.commit()

        assert access_service.calls == 0
        persisted = await connection.fetchrow(
            """SELECT batch.status, batch.succeeded_count, item.result
               FROM volunteer_decision_batches AS batch
               JOIN volunteer_decision_batch_items AS item ON item.batch_id = batch.id
               WHERE batch.id = $1""",
            batch_id,
        )
        assert persisted is not None
        assert persisted["status"] == "completed"
        assert persisted["succeeded_count"] == 1
        assert persisted["result"] == "succeeded"
    finally:
        await _cleanup_approval_fixture(
            connection,
            organization_ids=[organization_id],
            user_ids=[user_id, actor_user_id],
        )
        await engine.dispose()
        await connection.close()
