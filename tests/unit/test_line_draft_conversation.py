from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.line_draft_conversation import (
    LineDraftConversationService,
)
from services.api.app.domain.line_care_report_state import DraftState


class FakeSession:
    async def flush(self) -> None:
        return None


class FakeDraftRepository:
    def __init__(self, draft):
        self.organization_id = draft.organization_id
        self.session = FakeSession()
        self.draft = draft

    async def get_by_token(self, token):
        return self.draft if token == "token" else None

    async def get_active_for_volunteer(self, volunteer_user_id):
        return self.draft if self.draft.volunteer_user_id == volunteer_user_id else None


def draft(*, user_id, organization_id):
    return SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        volunteer_user_id=user_id,
        status="active",
        current_step=DraftState.CONFIRMING_ANIMAL.value,
        answers={},
        note=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        last_interaction_at=None,
        animal_id=uuid4(),
        membership_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_conversation_uses_draft_state_not_postback_step() -> None:
    user_id = uuid4()
    repository = FakeDraftRepository(draft(user_id=user_id, organization_id=uuid4()))
    service = LineDraftConversationService(repository)

    result = await service.handle(
        token="token",
        volunteer_user_id=user_id,
        action="confirm_animal",
        value=None,
        event_id="event-1",
    )

    assert result.state == DraftState.ANSWERING_COMPLETION
    assert repository.draft.current_step == DraftState.ANSWERING_COMPLETION.value


@pytest.mark.asyncio
async def test_current_draft_cancel_does_not_create_report() -> None:
    user_id = uuid4()
    repository = FakeDraftRepository(draft(user_id=user_id, organization_id=uuid4()))

    result = await LineDraftConversationService(repository).handle(
        token=None,
        volunteer_user_id=user_id,
        action="cancel_current",
        value=None,
        event_id="event-2",
    )

    assert result.state == DraftState.CANCELLED
    assert repository.draft.status == "cancelled"


@pytest.mark.asyncio
async def test_other_volunteer_cannot_use_draft() -> None:
    repository = FakeDraftRepository(draft(user_id=uuid4(), organization_id=uuid4()))

    with pytest.raises(DomainError, match="不存在或無法存取"):
        await LineDraftConversationService(repository).handle(
            token="token",
            volunteer_user_id=uuid4(),
            action="confirm_animal",
            value=None,
            event_id="event-3",
        )
