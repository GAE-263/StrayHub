from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.application.line_postback_service import InMemoryBotDraft, LinePostbackService
from services.api.app.domain.line_care_report_state import DraftState, DraftStateMachine


def test_postback_cannot_use_another_organization_draft() -> None:
    service = LinePostbackService()
    volunteer_id = uuid4()
    service.register_draft(
        "opaque-draft",
        InMemoryBotDraft(uuid4(), volunteer_id, DraftStateMachine(DraftState.CONFIRMING_ANIMAL)),
    )

    with pytest.raises(DomainError, match="不存在或無法存取"):
        service.handle(
            event_id="event-1",
            line_user_id=str(volunteer_id),
            draft_token="opaque-draft",
            action="confirm",
            organization_id=uuid4(),
        )
