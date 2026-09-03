from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.line_postback_service import InMemoryBotDraft, LinePostbackService
from services.api.app.domain.line_care_report_state import (
    DraftState,
    DraftStateMachine,
)


def test_postback_flow_uses_server_state_and_reaches_summary_without_media_or_note() -> None:
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
            event_id="confirm-1",
            line_user_id=str(volunteer_id),
            draft_token="draft-token",
            action="confirm",
            organization_id=organization_id,
        )
        == "processed"
    )
    values = {
        "walk_completion": "walk_completion.completed",
        "activity": "activity.usual",
        "gait": "gait.normal",
        "defecation": "defecation.normal",
        "animal_interaction": "animal_interaction.friendly",
        "appearance_special_status": "appearance.none_found",
    }
    for index, value in enumerate(values.values(), start=1):
        if service.drafts["draft-token"].machine.state == DraftState.AWAITING_STOOL_MEDIA:
            service.handle(
                event_id="skip-stool",
                line_user_id=str(volunteer_id),
                draft_token="draft-token",
                action="skip_stool_media",
                organization_id=organization_id,
            )
        assert (
            service.handle(
                event_id=f"answer-{index}",
                line_user_id=str(volunteer_id),
                draft_token="draft-token",
                action="answer",
                value=value,
                organization_id=organization_id,
            )
            == "processed"
        )
    assert (
        service.handle(
            event_id="skip-note",
            line_user_id=str(volunteer_id),
            draft_token="draft-token",
            action="skip_note",
            organization_id=organization_id,
        )
        == "processed"
    )
    assert (
        service.handle(
            event_id="skip-story",
            line_user_id=str(volunteer_id),
            draft_token="draft-token",
            action="skip_story",
            organization_id=organization_id,
        )
        == "processed"
    )
    assert service.drafts["draft-token"].machine.state == DraftState.REVIEWING


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
