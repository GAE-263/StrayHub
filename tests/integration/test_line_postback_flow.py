from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.line_draft_conversation import LineDraftConversationService
from services.api.app.application.line_postback_service import InMemoryBotDraft, LinePostbackService
from services.api.app.domain.line_care_report_state import DraftState, DraftStateMachine


class _FakeSession:
    async def flush(self) -> None:
        return None


class _FakeDraftRepository:
    def __init__(self, draft):
        self.organization_id = draft.organization_id
        self.session = _FakeSession()
        self.draft = draft

    async def get_by_token(self, token):
        return self.draft if token == "draft-token" else None

    async def get_active_for_volunteer(self, volunteer_user_id):
        return self.draft if self.draft.volunteer_user_id == volunteer_user_id else None


@pytest.mark.asyncio
async def test_postback_flow_uses_server_state_and_reaches_summary_without_media_or_note() -> None:
    """The real conversation service used by the webhook, not the unused
    LinePostbackService (see test_postback_redelivery below), must be able to
    drive a full six-question flow through to REVIEWING."""
    volunteer_id = uuid4()
    organization_id = uuid4()
    draft = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        volunteer_user_id=volunteer_id,
        status="active",
        current_step=DraftState.CONFIRMING_ANIMAL.value,
        answers={},
        note=None,
        story=None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        last_interaction_at=None,
        animal_id=uuid4(),
        membership_id=uuid4(),
    )
    conversation = LineDraftConversationService(_FakeDraftRepository(draft))

    await conversation.handle(
        token="draft-token",
        volunteer_user_id=volunteer_id,
        action="confirm_animal",
        value=None,
        event_id="confirm-1",
    )
    answers = (
        "walk_completion.completed",
        "activity.usual",
        "gait.normal",
        "defecation.normal",
    )
    result = None
    for index, value in enumerate(answers, start=1):
        result = await conversation.handle(
            token="draft-token",
            volunteer_user_id=volunteer_id,
            action="answer",
            value=value,
            event_id=f"answer-{index}",
        )
    assert result.state == DraftState.AWAITING_STOOL_MEDIA

    await conversation.handle(
        token="draft-token",
        volunteer_user_id=volunteer_id,
        action="skip_stool_media",
        value=None,
        event_id="skip-stool-media",
    )
    for index, value in enumerate(("animal_interaction.friendly", "appearance.none_found")):
        result = await conversation.handle(
            token="draft-token",
            volunteer_user_id=volunteer_id,
            action="answer",
            value=value,
            event_id=f"answer-remaining-{index}",
        )
    assert result.state == DraftState.AWAITING_MEDIA

    await conversation.handle(
        token="draft-token",
        volunteer_user_id=volunteer_id,
        action="skip_media",
        value=None,
        event_id="skip-media",
    )
    await conversation.handle(
        token="draft-token",
        volunteer_user_id=volunteer_id,
        action="skip_note",
        value=None,
        event_id="skip-note",
    )
    await conversation.handle(
        token="draft-token",
        volunteer_user_id=volunteer_id,
        action="skip_story",
        value=None,
        event_id="skip-story",
    )

    assert draft.current_step == DraftState.REVIEWING.value


def test_postback_redelivery_is_idempotent_and_cross_organization_is_denied() -> None:
    service = LinePostbackService()
    volunteer_id = uuid4()
    organization_id = uuid4()
    service.register_draft(
        "draft-token",
        InMemoryBotDraft(
            organization_id, volunteer_id, DraftStateMachine(DraftState.CONFIRMING_ANIMAL)
        ),
    )
    assert (
        service.handle(
            event_id="same-event",
            line_user_id=str(volunteer_id),
            draft_token="draft-token",
            action="confirm",
            organization_id=organization_id,
        )
        == "processed"
    )
    assert (
        service.handle(
            event_id="same-event",
            line_user_id=str(volunteer_id),
            draft_token="draft-token",
            action="confirm",
            organization_id=organization_id,
        )
        == "duplicate_ignored"
    )
    with pytest.raises(DomainError, match="草稿不存在"):
        service.current_state("draft-token", organization_id=uuid4())
