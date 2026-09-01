from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.line_draft_service import DraftSelectionAction, LineDraftService
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

    async def clear_media(self, draft_id):
        self.cleared_draft_id = draft_id


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


@pytest.mark.asyncio
async def test_selection_creates_resumes_and_requires_explicit_switch() -> None:
    repository = Repository()
    service = LineDraftService(repository)
    user_id, membership_id, first_animal, second_animal = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    created = await service.select_confirmed_animal(
        volunteer_user_id=user_id, membership_id=membership_id, animal_id=first_animal
    )
    assert created.action == DraftSelectionAction.CREATED
    assert created.token
    resumed = await service.select_confirmed_animal(
        volunteer_user_id=user_id, membership_id=membership_id, animal_id=first_animal
    )
    assert resumed.action == DraftSelectionAction.RESUMED
    pending = await service.select_confirmed_animal(
        volunteer_user_id=user_id, membership_id=membership_id, animal_id=second_animal
    )
    assert pending.action == DraftSelectionAction.NEEDS_SWITCH_CONFIRMATION
    assert created.draft.animal_id == first_animal
    assert created.draft.candidate_animal_id is None


@pytest.mark.asyncio
async def test_explicit_switch_clears_animal_specific_context() -> None:
    repository = Repository()
    service = LineDraftService(repository)
    user_id, membership_id, first_animal, second_animal = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    created = await service.select_confirmed_animal(
        volunteer_user_id=user_id, membership_id=membership_id, animal_id=first_animal
    )
    draft = created.draft
    draft.answers = {"gait": "gait.normal"}
    draft.reconfirmation_keys = ["gait"]
    draft.note = "上一隻的健康補充"
    draft.story = "上一隻的小故事"
    switched = await service.select_confirmed_animal(
        volunteer_user_id=user_id,
        membership_id=membership_id,
        animal_id=second_animal,
        confirm_switch=True,
        expected_current_animal_id=first_animal,
    )
    assert switched.action == DraftSelectionAction.SWITCHED
    assert draft.animal_id == second_animal
    assert draft.answers == {}
    assert draft.reconfirmation_keys == []
    assert draft.note is None and draft.story is None
    assert repository.cleared_draft_id == draft.id


@pytest.mark.asyncio
async def test_replayed_switch_fails_when_expected_animal_changed() -> None:
    repository = Repository()
    service = LineDraftService(repository)
    user_id, membership_id = uuid4(), uuid4()
    first, second, stale_target = uuid4(), uuid4(), uuid4()
    await service.select_confirmed_animal(
        volunteer_user_id=user_id, membership_id=membership_id, animal_id=first
    )
    await service.select_confirmed_animal(
        volunteer_user_id=user_id,
        membership_id=membership_id,
        animal_id=second,
        confirm_switch=True,
        expected_current_animal_id=first,
    )
    with pytest.raises(DomainError, match="已變更"):
        await service.select_confirmed_animal(
            volunteer_user_id=user_id,
            membership_id=membership_id,
            animal_id=stale_target,
            confirm_switch=True,
            expected_current_animal_id=first,
        )
