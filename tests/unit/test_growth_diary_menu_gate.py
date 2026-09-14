from __future__ import annotations

from datetime import datetime, timezone

import pytest
from services.api.app.api import line_webhook
from services.api.app.config.line_menu_smoke import verified_menu_request
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
from tests.unit.test_line_menu_smoke_scope import BOT, UID, scoped_settings


def _entry_event(
    *, uid: str = UID, source_type: str = "user", action: str = "start_growth_diary"
) -> dict:
    return {
        "type": "postback",
        "replyToken": "synthetic",
        "source": {"type": source_type, "userId": uid},
        "postback": {"data": f"action={action}&flow=growth_diary"},
    }


async def _handle(
    monkeypatch: pytest.MonkeyPatch,
    *,
    settings,
    uid: str = UID,
    destination: str = BOT,
    source_type: str = "user",
) -> tuple[bool, MockLineAdapter]:
    event = _entry_event(uid=uid, source_type=source_type)
    line = MockLineAdapter()
    monkeypatch.setattr(line_webhook, "get_settings", lambda: settings)
    async with verified_menu_request({"destination": destination, "events": [event]}, settings):
        handled = await line_webhook._handle_menu_action(line, event)
    return handled, line


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings_overrides", "uid", "destination", "source_type"),
    [
        ({"line_role_menu_test_enabled": False}, UID, BOT, "user"),
        ({}, "U" + "3" * 32, BOT, "user"),
        ({"line_role_menu_test_expires_at": "2020-01-01T00:00:00+00:00"}, UID, BOT, "user"),
        ({"line_role_menu_test_channel_id": "999"}, UID, BOT, "user"),
        ({}, UID, "U" + "4" * 32, "user"),
        ({}, UID, BOT, "group"),
        ({}, UID, BOT, "room"),
    ],
)
async def test_growth_diary_entry_fails_closed_outside_enabled_scope(
    monkeypatch: pytest.MonkeyPatch,
    settings_overrides: dict,
    uid: str,
    destination: str,
    source_type: str,
) -> None:
    handled, line = await _handle(
        monkeypatch,
        settings=scoped_settings(**settings_overrides),
        uid=uid,
        destination=destination,
        source_type=source_type,
    )

    assert handled is True
    assert line.replies[0][1][0]["text"] == "此 LINE 功能目前尚未開放。"
    assert line.pushes == []
    assert line.unlinked_users == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "settings",
    [
        scoped_settings(),
        scoped_settings(
            line_role_menu_features_enabled=True,
            line_role_menu_test_enabled=False,
            line_role_menu_test_expires_at=datetime.now(timezone.utc).isoformat(),
        ),
    ],
)
async def test_growth_diary_entry_continues_to_existing_router_when_enabled(
    monkeypatch: pytest.MonkeyPatch, settings
) -> None:
    handled, line = await _handle(monkeypatch, settings=settings)

    assert handled is False
    assert line.replies == []
    assert line.pushes == []
    assert line.unlinked_users == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [
        _entry_event(action="start_growth_diary_entry"),
        _entry_event(action="select_growth_diary_animal"),
        _entry_event(action="view_growth_diary_history"),
        {
            "type": "message",
            "source": {"type": "user", "userId": UID},
            "message": {"type": "text", "text": "取消"},
        },
        {
            "type": "message",
            "source": {"type": "user", "userId": UID},
            "message": {"type": "image", "id": "synthetic"},
        },
    ],
)
async def test_growth_diary_follow_up_events_are_not_entry_gated(
    monkeypatch: pytest.MonkeyPatch, event: dict
) -> None:
    monkeypatch.setattr(
        line_webhook,
        "get_settings",
        lambda: scoped_settings(line_role_menu_test_enabled=False),
    )
    line = MockLineAdapter()

    assert await line_webhook._handle_menu_action(line, event) is False
    assert line.replies == []
    assert line.pushes == []
    assert line.unlinked_users == []
