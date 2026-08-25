from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.line_draft_service import LineDraftService
from services.api.app.persistence.models.care_report_draft import CareReportDraft


class FakeDraftRepository:
    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.drafts: list[CareReportDraft] = []

    async def get_active_for_volunteer(self, volunteer_user_id):
        return next(
            (
                draft
                for draft in self.drafts
                if draft.volunteer_user_id == volunteer_user_id and draft.status == "active"
            ),
            None,
        )

    async def add(self, draft):
        self.drafts.append(draft)
        return draft

    async def get(self, draft_id):
        return next((draft for draft in self.drafts if draft.id == draft_id), None)


@pytest.mark.asyncio
async def test_one_active_draft_per_volunteer_and_opaque_token() -> None:
    repository = FakeDraftRepository()
    service = LineDraftService(repository, ttl_seconds=60)
    volunteer_id = uuid4()

    draft, token = await service.create(
        volunteer_user_id=volunteer_id, membership_id=uuid4(), animal_id=uuid4()
    )
    assert token
    assert draft.opaque_token_digest != token

    with pytest.raises(DomainError, match="未完成回報"):
        await service.create(
            volunteer_user_id=volunteer_id, membership_id=uuid4(), animal_id=uuid4()
        )


@pytest.mark.asyncio
async def test_reselect_animal_preserves_answers_but_requires_reconfirmation() -> None:
    repository = FakeDraftRepository()
    service = LineDraftService(repository, ttl_seconds=60)
    original_animal_id = uuid4()
    draft, _ = await service.create(
        volunteer_user_id=uuid4(), membership_id=uuid4(), animal_id=original_animal_id
    )
    draft.answers = {"gait": "gait.normal", "appearance_special_status": "appearance.none_found"}

    candidate_id = uuid4()
    await service.begin_reselection(draft.id, candidate_animal_id=candidate_id)
    await service.confirm_reselection(draft.id)

    assert draft.animal_id == candidate_id
    assert draft.candidate_animal_id is None
    assert draft.reconfirmation_keys == ["gait", "appearance_special_status"]
    assert draft.answers == {
        "gait": "gait.normal",
        "appearance_special_status": "appearance.none_found",
    }


@pytest.mark.asyncio
async def test_reselect_animal_drops_the_previous_animals_free_text() -> None:
    """答案可以重新確認，心得不行——那是寫給某一隻的，不能跟著換過去。"""
    repository = FakeDraftRepository()
    service = LineDraftService(repository, ttl_seconds=60)
    draft, _ = await service.create(
        volunteer_user_id=uuid4(), membership_id=uuid4(), animal_id=uuid4()
    )
    draft.note = "小黑後腳有點拖"
    draft.story = "今天終於願意讓我摸頭"

    await service.begin_reselection(draft.id, candidate_animal_id=uuid4())
    await service.confirm_reselection(draft.id)

    assert draft.note is None
    assert draft.story is None
