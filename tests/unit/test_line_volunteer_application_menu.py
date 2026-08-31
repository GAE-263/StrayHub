from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from services.api.app.api import line_webhook
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
async def test_switch_menu_to_adopter_is_noop_without_rich_menu_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        line_webhook,
        "get_settings",
        lambda: SimpleNamespace(
            line_rich_menu_default_id="",
            line_rich_menu_volunteer_id="",
            line_rich_menu_adopter_id="",
            line_rich_menu_staff_id="",
        ),
    )

    switched = await line_webhook._switch_menu_to_adopter("Uadopter0123456789")

    assert switched is False


@pytest.mark.asyncio
async def test_switch_menu_to_adopter_is_noop_without_line_user_id() -> None:
    assert await line_webhook._switch_menu_to_adopter(None) is False


def _adoption_placeholder_event() -> dict:
    return {
        "type": "postback",
        "replyToken": "reply-3",
        "source": {"userId": "Uadopter0123456789"},
        "postback": {"data": "action=adoption_placeholder"},
    }


@pytest.mark.asyncio
async def test_adoption_placeholder_switches_rich_menu_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """四個 richMenuId 都有設定時，點「領養流程」直接切選單，不開 LIFF 頁面。"""

    async def fake_switch(line_user_id: str | None) -> bool:
        assert line_user_id == "Uadopter0123456789"
        return True

    monkeypatch.setattr(line_webhook, "_switch_menu_to_adopter", fake_switch)
    line = MockLineAdapter()

    handled = await line_webhook._handle_public_volunteer_application_entry(
        object(), line, _adoption_placeholder_event()
    )

    assert handled is True
    assert "已切換到領養選單" in line.replies[0][1][0]["text"]


@pytest.mark.asyncio
async def test_adoption_placeholder_falls_back_to_text_without_web_public_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_switch(line_user_id: str | None) -> bool:
        return False

    monkeypatch.setattr(line_webhook, "_switch_menu_to_adopter", fake_switch)
    monkeypatch.setattr(
        line_webhook, "get_settings", lambda: SimpleNamespace(web_public_base_url="")
    )

    line = MockLineAdapter()

    handled = await line_webhook._handle_public_volunteer_application_entry(
        object(), line, _adoption_placeholder_event()
    )

    assert handled is True
    assert "準備中" in line.replies[0][1][0]["text"]


@pytest.mark.asyncio
async def test_adoption_placeholder_links_fake_adoption_entry_page_when_menu_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """選單沒設定（no-op）時退回開假頁面，跟切換選單失敗時的行為一致。"""

    async def fake_switch(line_user_id: str | None) -> bool:
        return False

    monkeypatch.setattr(line_webhook, "_switch_menu_to_adopter", fake_switch)
    monkeypatch.setattr(
        line_webhook,
        "get_settings",
        lambda: SimpleNamespace(web_public_base_url="https://example.ngrok-free.dev"),
    )

    line = MockLineAdapter()

    handled = await line_webhook._handle_public_volunteer_application_entry(
        object(), line, _adoption_placeholder_event()
    )

    assert handled is True
    action = line.replies[0][1][0]["quickReply"]["items"][0]["action"]
    assert action["uri"] == "https://example.ngrok-free.dev/adoption-entry/index.html"
