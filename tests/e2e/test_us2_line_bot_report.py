from uuid import uuid4

import pytest
from services.api.app.application.line_postback_service import InMemoryBotDraft, LinePostbackService
from services.api.app.domain.line_care_report_state import (
    DraftState,
    DraftStateMachine,
)


@pytest.mark.asyncio
async def test_us2_standard_flow_reaches_summary_without_media_or_note() -> None:
    service = LinePostbackService()
    volunteer_id = uuid4()
    organization_id = uuid4()
    service.register_draft(
        "us2-draft",
        InMemoryBotDraft(
            organization_id,
            volunteer_id,
            DraftStateMachine(DraftState.CONFIRMING_ANIMAL),
        ),
    )
    service.handle(
        event_id="confirm",
        line_user_id=str(volunteer_id),
        draft_token="us2-draft",
        action="confirm",
        organization_id=organization_id,
    )
    values = {
        "walk_completion": "walk_completion.completed",
        "activity": "activity.usual",
        "gait": "gait.normal",
        "defecation": "defecation.none",
        "animal_interaction": "animal_interaction.friendly",
        "appearance_special_status": "appearance.none_found",
    }
    for index, value in enumerate(values.values()):
        service.handle(
            event_id=f"answer-{index}",
            line_user_id=str(volunteer_id),
            draft_token="us2-draft",
            action="answer",
            value=value,
            organization_id=organization_id,
        )
    service.handle(
        event_id="skip-note",
        line_user_id=str(volunteer_id),
        draft_token="us2-draft",
        action="skip_note",
        organization_id=organization_id,
    )
    service.handle(
        event_id="skip-story",
        line_user_id=str(volunteer_id),
        draft_token="us2-draft",
        action="skip_story",
        organization_id=organization_id,
    )
    assert service.drafts["us2-draft"].machine.state == DraftState.REVIEWING
