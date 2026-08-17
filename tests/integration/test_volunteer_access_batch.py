from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_batch_service import VolunteerBatchService


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
        filters={"status": "pending"},
        request_payload={"selection": "all_filtered"},
    )
    applications.append(SimpleNamespace(id=uuid4(), version=1, status="pending"))

    assert batch.requested_count == 1200
    assert len(items) == 1200
    assert all(len(chunk) <= 500 for chunk in service.chunks(items))
    assert sum(len(chunk) for chunk in service.chunks(items)) == 1200


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
