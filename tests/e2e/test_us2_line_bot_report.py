from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.application.line_draft_conversation import LineDraftConversationService
from services.api.app.domain.line_care_report_state import DraftState


class _FakeSession:
    async def flush(self) -> None:
        return None


class _FakeDraftRepository:
    """Minimal in-memory stand-in so this acceptance test exercises the real
    LineDraftConversationService end to end without a database."""

    def __init__(self, draft):
        self.organization_id = draft.organization_id
        self.session = _FakeSession()
        self.draft = draft

    async def get_by_token(self, token):
        return self.draft if token == "us2-draft" else None

    async def get_active_for_volunteer(self, volunteer_user_id):
        return self.draft if self.draft.volunteer_user_id == volunteer_user_id else None


@pytest.mark.asyncio
async def test_us2_standard_flow_reaches_summary_without_media_or_note() -> None:
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
        token="us2-draft",
        volunteer_user_id=volunteer_id,
        action="confirm_animal",
        value=None,
        event_id="confirm",
    )
    answers = (
        "walk_completion.completed",
        "activity.usual",
        "gait.normal",
        "defecation.normal",
    )
    result = None
    for index, value in enumerate(answers):
        result = await conversation.handle(
            token="us2-draft",
            volunteer_user_id=volunteer_id,
            action="answer",
            value=value,
            event_id=f"answer-{index}",
        )
    assert result.state == DraftState.AWAITING_STOOL_MEDIA

    await conversation.handle(
        token="us2-draft",
        volunteer_user_id=volunteer_id,
        action="skip_stool_media",
        value=None,
        event_id="skip-stool-media",
    )
    for index, value in enumerate(("animal_interaction.friendly", "appearance.none_found")):
        result = await conversation.handle(
            token="us2-draft",
            volunteer_user_id=volunteer_id,
            action="answer",
            value=value,
            event_id=f"answer-remaining-{index}",
        )
    assert result.state == DraftState.AWAITING_MEDIA

    await conversation.handle(
        token="us2-draft",
        volunteer_user_id=volunteer_id,
        action="skip_media",
        value=None,
        event_id="skip-media",
    )
    await conversation.handle(
        token="us2-draft",
        volunteer_user_id=volunteer_id,
        action="skip_note",
        value=None,
        event_id="skip-note",
    )
    await conversation.handle(
        token="us2-draft",
        volunteer_user_id=volunteer_id,
        action="skip_story",
        value=None,
        event_id="skip-story",
    )

    assert draft.current_step == DraftState.REVIEWING.value
