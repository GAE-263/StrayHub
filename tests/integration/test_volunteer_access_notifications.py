from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.volunteer_notification_service import (
    VolunteerNotificationService,
)


@pytest.mark.asyncio
async def test_manual_retry_only_requeues_failed_and_is_operation_idempotent() -> None:
    organization_id = uuid4()
    failed = SimpleNamespace(
        id=uuid4(),
        status="failed",
        available_at=None,
        claim_token=uuid4(),
        claimed_at=datetime.now(timezone.utc),
        claimed_by="old-worker",
    )
    waiting = SimpleNamespace(id=uuid4(), status="retry_wait")

    class Repository:
        def __init__(self):
            self.organization_id = organization_id
            self.batches = {}
            self.items = {}

        async def notification(self, delivery_id, *, for_update=False):
            return {failed.id: failed, waiting.id: waiting}.get(delivery_id)

        async def retry_batch_by_operation(self, operation_id):
            return self.batches.get(operation_id)

        async def retry_items(self, batch_id):
            return self.items[batch_id]

        async def add(self, value):
            self.batches[value.operation_id] = value
            return value

        async def add_all(self, values):
            self.items[values[0].batch_id] = list(values)

    repository = Repository()
    service = VolunteerNotificationService(repository)
    operation_id = uuid4()
    batch, items = await service.retry_failed(
        operation_id=operation_id,
        notification_ids=[failed.id, waiting.id],
        actor_user_id=uuid4(),
    )
    assert batch.requeued_count == 1
    assert batch.conflict_count == 1
    assert [item.result for item in items] == ["requeued", "conflict"]
    assert failed.status == "retry_wait"
    replay, replay_items = await service.retry_failed(
        operation_id=operation_id,
        notification_ids=[failed.id, waiting.id],
        actor_user_id=uuid4(),
    )
    assert replay is batch
    assert replay_items == items
    with pytest.raises(DomainError, match="operation"):
        await service.retry_failed(
            operation_id=operation_id,
            notification_ids=[failed.id],
            actor_user_id=uuid4(),
        )


@pytest.mark.asyncio
async def test_manual_retry_selection_is_unique_and_bounded() -> None:
    service = VolunteerNotificationService(SimpleNamespace(organization_id=uuid4()))
    target = uuid4()
    with pytest.raises(DomainError, match="重複"):
        await service.retry_failed(
            operation_id=uuid4(),
            notification_ids=[target, target],
            actor_user_id=uuid4(),
        )
    with pytest.raises(DomainError, match="500"):
        await service.retry_failed(
            operation_id=uuid4(),
            notification_ids=[uuid4() for _ in range(501)],
            actor_user_id=uuid4(),
        )
