from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from services.api.app.api import line_webhook
from services.api.app.application.volunteer_access_service import VolunteerAccessService
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter


def test_bot_application_entry_opens_one_shared_liff_without_shelter_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        line_webhook, "get_settings", lambda: SimpleNamespace(liff_id="shared-liff-id")
    )

    message = line_webhook._volunteer_application_entry_message()
    action = message["quickReply"]["items"][0]["action"]

    assert action["label"] == "開啟志工報名"
    assert action["type"] == "uri"
    assert urlparse(action["uri"]).path == "/shared-liff-id"
    assert urlparse(action["uri"]).query == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [
        {
            "type": "message",
            "replyToken": "reply-1",
            "message": {"type": "text", "text": "我要報名志工"},
        },
        {
            "type": "postback",
            "replyToken": "reply-2",
            "postback": {"data": "action=start_volunteer_application"},
        },
    ],
)
async def test_public_application_command_does_not_require_existing_membership(
    monkeypatch: pytest.MonkeyPatch, event: dict
) -> None:
    monkeypatch.setattr(
        line_webhook, "get_settings", lambda: SimpleNamespace(liff_id="shared-liff-id")
    )
    line = MockLineAdapter()

    handled = await line_webhook._handle_public_volunteer_application_entry(object(), line, event)

    assert handled is True
    assert len(line.replies) == 1
    assert len(line.replies[0][1][0]["quickReply"]["items"]) == 1


@pytest.mark.asyncio
async def test_start_volunteer_application_resumes_volunteer_menu_when_already_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """核准過的志工再點「志工服務」：不用重跑 LIFF，直接切回志工選單。"""

    async def fake_switch(session: object, line_user_id: str | None) -> bool:
        assert line_user_id == "Uvolunteer0123456789"
        return True

    monkeypatch.setattr(line_webhook, "_switch_menu_to_volunteer_if_active", fake_switch)
    line = MockLineAdapter()
    event = {
        "type": "postback",
        "replyToken": "reply-2",
        "source": {"userId": "Uvolunteer0123456789"},
        "postback": {"data": "action=start_volunteer_application"},
    }

    handled = await line_webhook._handle_public_volunteer_application_entry(object(), line, event)

    assert handled is True
    assert "已切回志工選單" in line.replies[0][1][0]["text"]


@pytest.mark.asyncio
async def test_start_volunteer_application_falls_back_to_liff_entry_when_not_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_switch(session: object, line_user_id: str | None) -> bool:
        return False

    monkeypatch.setattr(line_webhook, "_switch_menu_to_volunteer_if_active", fake_switch)
    monkeypatch.setattr(
        line_webhook, "get_settings", lambda: SimpleNamespace(liff_id="shared-liff-id")
    )
    line = MockLineAdapter()
    event = {
        "type": "postback",
        "replyToken": "reply-2",
        "source": {"userId": "Uvolunteer0123456789"},
        "postback": {"data": "action=start_volunteer_application"},
    }

    handled = await line_webhook._handle_public_volunteer_application_entry(object(), line, event)

    assert handled is True
    assert line.replies[0][1][0]["quickReply"]["items"][0]["action"]["label"] == "開啟志工報名"


@pytest.mark.asyncio
async def test_formal_adoption_entry_is_not_consumed_by_volunteer_router() -> None:
    line = MockLineAdapter()
    event = {
        "type": "postback",
        "replyToken": "reply-3",
        "source": {"userId": "Uadopter0123456789"},
        "postback": {"data": "action=start_adoption_matching&flow=adoption"},
    }

    handled = await line_webhook._handle_public_volunteer_application_entry(object(), line, event)

    assert handled is False
    assert line.replies == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_approval_menu_switch_is_best_effort(fail: bool) -> None:
    user_id = uuid4()

    class Identities:
        async def get_line_binding_for_user(self, requested_user_id):
            assert requested_user_id == user_id
            return SimpleNamespace(line_user_id="U-approved")

    class Router:
        def __init__(self) -> None:
            self.calls = []

        async def link_for_user(self, *, line_user_id: str, role: str | None):
            self.calls.append((line_user_id, role))
            if fail:
                raise RuntimeError("LINE unavailable")

    router = Router()
    service = VolunteerAccessService(
        repository=object(),
        identities=Identities(),
        verifier=object(),
        rich_menu_router=router,
    )

    await service._switch_rich_menu(user_id, "VOLUNTEER")

    assert router.calls == [("U-approved", "VOLUNTEER")]
