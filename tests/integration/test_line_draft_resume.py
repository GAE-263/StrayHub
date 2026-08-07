from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.line_draft_service import LineDraftService
from services.api.app.domain.line_care_report_state import DraftState


class Repository:
    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.items = []

    async def get_active_for_volunteer(self, volunteer_user_id):
        return next(
            (
                item
                for item in self.items
                if item.volunteer_user_id == volunteer_user_id and item.status == "active"
            ),
            None,
        )

    async def add(self, draft):
        if draft.id is None:
            draft.id = uuid4()
        self.items.append(draft)
        return draft

    async def get(self, draft_id):
        return next((item for item in self.items if item.id == draft_id), None)


@pytest.mark.asyncio
async def test_resume_is_single_active_draft_and_cancel_allows_a_new_one() -> None:
    repository = Repository()
    service = LineDraftService(repository, ttl_seconds=60)
    volunteer_id = uuid4()
    first, _ = await service.create(
        volunteer_user_id=volunteer_id, membership_id=uuid4(), animal_id=uuid4()
    )
    with pytest.raises(DomainError, match="已有未完成"):
        await service.create(
            volunteer_user_id=volunteer_id, membership_id=uuid4(), animal_id=uuid4()
        )
    assert (await service._active(first.id)).id == first.id
    await service.cancel(first.id)
    second, _ = await service.create(
        volunteer_user_id=volunteer_id, membership_id=uuid4(), animal_id=uuid4()
    )
    assert second.id != first.id
    assert second.current_step == DraftState.CONFIRMING_ANIMAL.value


@pytest.mark.asyncio
async def test_expired_draft_cannot_resume() -> None:
    repository = Repository()
    service = LineDraftService(repository)
    draft, _ = await service.create(
        volunteer_user_id=uuid4(), membership_id=uuid4(), animal_id=uuid4()
    )
    draft.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(DomainError, match="草稿已過期"):
        await service._active(draft.id)
    assert draft.status == "expired"
