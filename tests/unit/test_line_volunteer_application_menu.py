from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from services.api.app.api import line_webhook
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter

DEMO_ORGANIZATIONS = [
    (uuid4(), "FURKIDS-ASIA", "毛小孩幸福聯盟協會", None, False),
    (uuid4(), "MOA-SHELTER-51", "新北市新店區公立動物之家", None, False),
    (uuid4(), "MOA-SHELTER-58", "新北市五股區公立動物之家", None, False),
]


def test_bot_shelter_options_map_to_one_liff_route_with_organization_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        line_webhook, "get_settings", lambda: SimpleNamespace(liff_id="shared-liff-id")
    )

    message = line_webhook._volunteer_application_selection_message(
        list(reversed(DEMO_ORGANIZATIONS))
    )
    actions = [item["action"] for item in message["quickReply"]["items"]]

    assert [action["label"] for action in actions] == [row[2] for row in DEMO_ORGANIZATIONS]
    assert all(action["type"] == "uri" for action in actions)
    parsed = [urlparse(action["uri"]) for action in actions]
    assert {item.path for item in parsed} == {"/shared-liff-id"}
    assert [parse_qs(item.query)["organization_id"] for item in parsed] == [
        [str(row[0])] for row in DEMO_ORGANIZATIONS
    ]


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
    class _Directory:
        def __init__(self, _session) -> None:
            pass

        async def list_public_volunteer_organizations(self):
            return DEMO_ORGANIZATIONS

    monkeypatch.setattr(line_webhook, "OrganizationRepository", _Directory)
    monkeypatch.setattr(
        line_webhook, "get_settings", lambda: SimpleNamespace(liff_id="shared-liff-id")
    )
    line = MockLineAdapter()

    handled = await line_webhook._handle_public_volunteer_application_entry(object(), line, event)

    assert handled is True
    assert len(line.replies) == 1
    assert len(line.replies[0][1][0]["quickReply"]["items"]) == 3
