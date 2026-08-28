from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.line_adoption_draft_service import LineAdoptionDraftService
from services.api.app.domain.line_adoption_state import AdoptionDraftState
from services.api.app.persistence.models.adoption_draft import AdoptionDraft


class FakeAdoptionDraftRepository:
    def __init__(self) -> None:
        self.organization_id = None
        self.drafts: list[AdoptionDraft] = []

    async def get_active_for_adopter(self, adopter_user_id):
        return next(
            (
                draft
                for draft in self.drafts
                if draft.adopter_user_id == adopter_user_id and draft.status == "active"
            ),
            None,
        )

    async def add(self, draft):
        self.drafts.append(draft)
        return draft

    async def get(self, draft_id):
        return next((draft for draft in self.drafts if draft.id == draft_id), None)


@pytest.mark.asyncio
async def test_one_active_draft_per_adopter_and_no_organization_yet() -> None:
    repository = FakeAdoptionDraftRepository()
    service = LineAdoptionDraftService(repository, ttl_seconds=60)
    adopter_id = uuid4()

    draft, token = await service.create(adopter_user_id=adopter_id)

    assert token
    assert draft.organization_id is None
    assert draft.current_step == AdoptionDraftState.SELECTING_ORGANIZATION.value

    with pytest.raises(DomainError, match="未完成的領養對話"):
        await service.create(adopter_user_id=adopter_id)


@pytest.mark.asyncio
async def test_set_organization_moves_to_choosing_path_and_is_one_shot() -> None:
    repository = FakeAdoptionDraftRepository()
    service = LineAdoptionDraftService(repository, ttl_seconds=60)
    draft, _ = await service.create(adopter_user_id=uuid4())
    organization_id = uuid4()

    await service.set_organization(draft.id, organization_id=organization_id)

    assert draft.organization_id == organization_id
    assert draft.current_step == AdoptionDraftState.CHOOSING_PATH.value

    with pytest.raises(DomainError, match="已經選擇過收容所"):
        await service.set_organization(draft.id, organization_id=uuid4())


@pytest.mark.asyncio
async def test_cancel_marks_draft_cancelled() -> None:
    repository = FakeAdoptionDraftRepository()
    service = LineAdoptionDraftService(repository, ttl_seconds=60)
    draft, _ = await service.create(adopter_user_id=uuid4())

    await service.cancel(draft.id)

    assert draft.status == "cancelled"
    assert draft.current_step == AdoptionDraftState.CANCELLED.value
