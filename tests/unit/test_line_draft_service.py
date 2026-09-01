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
    draft.answers = {"activity": "activity.usual", "gait": "gait.normal"}

    candidate_id = uuid4()
    await service.begin_reselection(draft.id, candidate_animal_id=candidate_id)
    await service.confirm_reselection(draft.id)

    assert draft.animal_id == candidate_id
    assert draft.candidate_animal_id is None
    assert draft.reconfirmation_keys == ["activity", "gait"]
    assert draft.answers == {"activity": "activity.usual", "gait": "gait.normal"}
