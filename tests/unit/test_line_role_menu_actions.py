from __future__ import annotations

import pytest
from services.api.app.api import line_webhook
from services.api.app.application.line_menu_actions import MENU_PLACEHOLDER_ACTIONS
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter


def _postback_event(data: str) -> dict:
    return {"type": "postback", "replyToken": "reply-1", "postback": {"data": data}}


@pytest.mark.asyncio
@pytest.mark.parametrize("action", sorted(MENU_PLACEHOLDER_ACTIONS))
async def test_every_menu_action_gets_its_placeholder_reply(action: str) -> None:
    """選單項目全部要有回應；漏接的會掉進照護回報流程回「缺少回報草稿識別」。"""
    line = MockLineAdapter()

    handled = await line_webhook._handle_menu_action(line, _postback_event(f"action={action}"))

    assert handled is True
    assert line.replies[0][1][0]["text"] == MENU_PLACEHOLDER_ACTIONS[action]


@pytest.mark.asyncio
async def test_start_binding_is_answered_without_membership() -> None:
    line = MockLineAdapter()

    handled = await line_webhook._handle_menu_action(line, _postback_event("action=start_binding"))

    assert handled is True
    assert "綁定" in line.replies[0][1][0]["text"]


@pytest.mark.asyncio
async def test_care_report_postbacks_are_left_to_the_draft_handler() -> None:
    """草稿流程的 action 不可被選單處理器吃掉。"""
    line = MockLineAdapter()

    for data in ("action=answer&draft_token=t", "action=select_animal", "action=submit"):
        assert await line_webhook._handle_menu_action(line, _postback_event(data)) is False
    assert line.replies == []


@pytest.mark.asyncio
async def test_non_postback_events_are_ignored() -> None:
    line = MockLineAdapter()
    event = {"type": "message", "replyToken": "r", "message": {"type": "text", "text": "hi"}}

    assert await line_webhook._handle_menu_action(line, event) is False
    assert line.replies == []


def test_default_menu_actions_are_all_wired() -> None:
    """default 選單是所有加好友的人第一個看到的，兩顆按鈕都必須有處理。"""
    import yaml

    document = yaml.safe_load(open("infra/local/line-rich-menu-default.yaml", encoding="utf-8"))
    actions = [item["data"].split("action=", 1)[1] for item in document["actions"]]

    assert actions == ["shelter_info", "start_binding"]
    for action in actions:
        assert action in MENU_PLACEHOLDER_ACTIONS or action == "start_binding"
