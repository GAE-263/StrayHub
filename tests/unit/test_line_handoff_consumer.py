from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from services.api.app.api import line_webhook
from services.api.app.api.errors import DomainError
from services.api.app.application.line_draft_service import (
    DraftSelectionAction,
    DraftSelectionDecision,
)
from services.api.app.domain.line_care_report_state import DraftState


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [DraftState.CONFIRMING_ANIMAL, DraftState.SELECTING_ANIMAL])
async def test_resume_before_questions_sends_actionable_card_with_notice(monkeypatch, state):
    user_id, organization_id, membership_id, animal_id = (uuid4() for _ in range(4))
    draft = SimpleNamespace(
        current_step=state.value,
        animal_id=animal_id,
        volunteer_user_id=user_id,
        membership_id=membership_id,
        modification_summary={},
        id=uuid4(),
        status="active",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        answers={"walk_completion": "walk_completion.completed"},
        reconfirmation_keys=[],
    )
    repository = SimpleNamespace(
        get_active_for_volunteer=AsyncMock(return_value=draft), get=AsyncMock(return_value=draft)
    )
    monkeypatch.setattr(line_webhook, "CareReportDraftRepository", lambda *_: repository)
    candidate = SimpleNamespace(animal=SimpleNamespace(id=animal_id))
    selection = SimpleNamespace(confirm=AsyncMock(return_value=candidate))
    monkeypatch.setattr(line_webhook, "_selection_service", lambda *_: selection)
    from services.api.app.application.effective_observation_service import EffectiveOption

    monkeypatch.setattr(
        line_webhook,
        "_answer_options",
        AsyncMock(return_value=[EffectiveOption("activity.normal", "精神正常")]),
    )
    monkeypatch.setattr(
        line_webhook, "_category_titles", AsyncMock(return_value={"activity": "精神體力"})
    )
    reply = AsyncMock()
    monkeypatch.setattr(line_webhook, "_reply", reply)
    event = {"postback": {"data": "action=resume_draft"}}

    await line_webhook._handle_postback(
        object(),
        object(),
        event,
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        public_base_url="https://example.test",
    )

    reply.assert_awaited_once()
    messages = reply.call_args.args[2]
    assert len(messages) == 2
    assert messages[0]["type"] == "text"
    assert messages[1]["type"] == "flex"
    assert draft.current_step == DraftState.ANSWERING_ACTIVITY.value
    assert draft.answers == {"walk_completion": "walk_completion.completed"}
    assert "精神體力" in json.dumps(messages, ensure_ascii=False)
    assert "要幫哪隻" not in json.dumps(messages, ensure_ascii=False)
    selection.confirm.assert_awaited_once_with(
        animal_id=animal_id,
        user_id=user_id,
        organization_id=organization_id,
        membership_id=membership_id,
        role="VOLUNTEER",
    )


class _Savepoint:
    def __init__(self, session) -> None:
        self.session = session

    async def __aenter__(self):
        self.session.savepoint_entered = True
        return self

    async def __aexit__(self, exc_type, _exc, _traceback):
        self.session.savepoint_rolled_back = exc_type is not None
        return False


class _Session:
    savepoint_entered = False
    savepoint_rolled_back = False

    def begin_nested(self):
        return _Savepoint(self)


class _Animals:
    def __init__(self, animals: dict) -> None:
        self.animals = animals

    async def get(self, animal_id):
        return self.animals.get(animal_id)


def _install_common(monkeypatch, *, handoff_result=None, handoff_error=None, decision=None):
    user_id, organization_id, membership_id = uuid4(), uuid4(), uuid4()
    animal_id = handoff_result.animal_id if handoff_result is not None else uuid4()
    calls: dict[str, object] = {}

    async def resolve(_session, line_user_id):
        calls["line_user_id"] = line_user_id
        return user_id, organization_id, membership_id, "VOLUNTEER"

    class HandoffService:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def consume_pending_handoff(self, **kwargs):
            calls["consume"] = kwargs
            if handoff_error is not None:
                raise handoff_error
            return handoff_result

    class DraftService:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def select_handoff_animal(self, **kwargs):
            calls["select"] = kwargs
            if isinstance(decision, Exception):
                raise decision
            return decision

    class Conversation:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def handle(self, **kwargs):
            calls["conversation"] = kwargs

    animals = _Animals({animal_id: SimpleNamespace(id=animal_id, name="阿福")})
    monkeypatch.setattr(line_webhook, "_resolve_context", resolve)
    monkeypatch.setattr(line_webhook, "AnimalRepository", lambda *_args: animals)
    monkeypatch.setattr(line_webhook, "AuthenticationRepository", lambda *_args: object())
    monkeypatch.setattr(
        line_webhook, "VolunteerReportingAuthorizationService", lambda *_args: object()
    )
    monkeypatch.setattr(line_webhook, "CareReportHandoffRepository", lambda *_args: object())
    monkeypatch.setattr(line_webhook, "CareReportHandoffService", HandoffService)
    monkeypatch.setattr(line_webhook, "CareReportDraftRepository", lambda *_args: object())
    monkeypatch.setattr(line_webhook, "LineDraftService", DraftService)
    monkeypatch.setattr(line_webhook, "LineDraftConversationService", Conversation)
    monkeypatch.setattr(
        line_webhook, "get_settings", lambda: SimpleNamespace(draft_ttl_seconds=900)
    )
    return calls, (user_id, organization_id, membership_id)


@pytest.mark.asyncio
async def test_command_consumes_handoff_and_creates_draft_in_one_savepoint(monkeypatch) -> None:
    handoff = SimpleNamespace(animal_id=uuid4(), membership_id=uuid4())
    draft = SimpleNamespace(current_step=DraftState.ANSWERING_WALK_COMPLETION.value)
    decision = DraftSelectionDecision(
        DraftSelectionAction.CREATED, draft, token="server-draft-token"
    )
    calls, (user_id, organization_id, _) = _install_common(
        monkeypatch, handoff_result=handoff, decision=decision
    )
    replies = []

    async def reply_next(*_args, **kwargs):
        replies.append(kwargs)

    monkeypatch.setattr(line_webhook, "_reply_next_step", reply_next)
    session = _Session()
    event = {"webhookEventId": "line-command-1", "replyToken": "reply-1"}

    await line_webhook._handle_walk_report_command(session, object(), event, "line-user")

    assert session.savepoint_entered is True
    assert session.savepoint_rolled_back is False
    assert calls["consume"] == {
        "user_id": user_id,
        "organization_id": organization_id,
    }
    assert calls["select"] == {
        "volunteer_user_id": user_id,
        "membership_id": handoff.membership_id,
        "animal_id": handoff.animal_id,
        "source_event_id": "line-command-1",
    }
    assert calls["conversation"]["action"] == "confirm_animal"
    assert calls["conversation"]["token"] == "server-draft-token"
    assert replies[0]["draft"] is draft
    assert replies[0]["raw_token"] == "server-draft-token"


@pytest.mark.asyncio
async def test_draft_failure_rolls_back_handoff_savepoint(monkeypatch) -> None:
    handoff = SimpleNamespace(animal_id=uuid4(), membership_id=uuid4())
    error = DomainError("draft_create_failed", "草稿建立失敗", 500)
    _install_common(monkeypatch, handoff_result=handoff, decision=error)
    session = _Session()

    with pytest.raises(DomainError) as caught:
        await line_webhook._handle_walk_report_command(
            session,
            object(),
            {"webhookEventId": "line-command-failure"},
            "line-user",
        )

    assert caught.value.code == "draft_create_failed"
    assert session.savepoint_rolled_back is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "expects_expiry_message"),
    [
        ("no_pending_handoff", False),
        ("handoff_already_consumed", False),
        ("handoff_expired", True),
    ],
)
async def test_missing_or_expired_handoff_uses_safe_locator_fallback(
    monkeypatch, error_code, expects_expiry_message
) -> None:
    error = DomainError(error_code, "handoff unavailable", 409)
    _install_common(monkeypatch, handoff_error=error)
    replies = []

    async def entry(*_args, **_kwargs):
        return {"type": "flex", "altText": "找動物"}

    async def reply(_line, _event, messages):
        replies.append(messages)

    monkeypatch.setattr(line_webhook, "_walk_entry_bubble", entry)
    monkeypatch.setattr(line_webhook, "_reply", reply)
    session = _Session()

    await line_webhook._handle_walk_report_command(
        session, object(), {"webhookEventId": "fallback"}, "line-user"
    )

    assert session.savepoint_rolled_back is False
    assert replies[0][-1]["altText"] == "找動物"
    assert (len(replies[0]) == 2) is expects_expiry_message


@pytest.mark.asyncio
async def test_handoff_switch_buttons_contain_no_client_animal_identifier(monkeypatch) -> None:
    organization_id = uuid4()
    previous_id, candidate_id = uuid4(), uuid4()
    monkeypatch.setattr(
        line_webhook,
        "AnimalRepository",
        lambda *_args: _Animals(
            {
                previous_id: SimpleNamespace(id=previous_id, name="小白"),
                candidate_id: SimpleNamespace(id=candidate_id, name="阿福"),
            }
        ),
    )
    draft = SimpleNamespace(animal_id=previous_id, candidate_animal_id=candidate_id)

    bubble = await line_webhook._handoff_switch_bubble(object(), organization_id, draft)
    serialized = str(bubble)

    assert "action=cancel_handoff_switch" in serialized
    assert "action=confirm_handoff_switch" in serialized
    assert str(previous_id) not in serialized
    assert str(candidate_id) not in serialized
