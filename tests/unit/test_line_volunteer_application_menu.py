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
