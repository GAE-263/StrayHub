from __future__ import annotations

from pathlib import Path

import pytest
from services.api.app.api import line_webhook
from services.api.app.application.line_menu_actions import (
    ADOPTION_ENTRY_ACTIONS,
    BACK_TO_DEFAULT_MENU_ACTION,
    MENU_PLACEHOLDER_ACTIONS,
)
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter

# 這些 action 由 webhook 自行處理，不在 MENU_PLACEHOLDER_ACTIONS 裡。
WEBHOOK_HANDLED_ACTIONS = {
    "start_binding",
    "start_volunteer_application",
    "adoption_placeholder",
    BACK_TO_DEFAULT_MENU_ACTION,
    *ADOPTION_ENTRY_ACTIONS,
}


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
@pytest.mark.parametrize("action", sorted(ADOPTION_ENTRY_ACTIONS))
async def test_adopter_menu_items_open_the_fake_adoption_entry_page(
    action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        line_webhook,
        "get_settings",
        lambda: SimpleNamespace(web_public_base_url="https://example.ngrok-free.dev"),
    )
    line = MockLineAdapter()

    handled = await line_webhook._handle_menu_action(line, _postback_event(f"action={action}"))

    assert handled is True
    action_payload = line.replies[0][1][0]["quickReply"]["items"][0]["action"]
    assert action_payload["uri"] == "https://example.ngrok-free.dev/adoption-entry/index.html"


@pytest.mark.asyncio
async def test_back_to_default_menu_switches_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_switch(line_user_id: str | None) -> bool:
        assert line_user_id == "Uvolunteer0123456789"
        return True

    monkeypatch.setattr(line_webhook, "_switch_menu_to_default", fake_switch)
    line = MockLineAdapter()
    event = _postback_event("action=back_to_default_menu")
    event["source"] = {"userId": "Uvolunteer0123456789"}

    handled = await line_webhook._handle_menu_action(line, event)

    assert handled is True
    assert "已切回主選單" in line.replies[0][1][0]["text"]


@pytest.mark.asyncio
async def test_back_to_default_menu_reports_unavailable_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_switch(line_user_id: str | None) -> bool:
        return False

    monkeypatch.setattr(line_webhook, "_switch_menu_to_default", fake_switch)
    line = MockLineAdapter()
    event = _postback_event("action=back_to_default_menu")
    event["source"] = {"userId": "Uvolunteer0123456789"}

    handled = await line_webhook._handle_menu_action(line, event)

    assert handled is True
    assert "尚未啟用" in line.replies[0][1][0]["text"]


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


@pytest.mark.parametrize(
    "path", sorted(Path("infra/local").glob("line-rich-menu-*.yaml")), ids=lambda p: p.stem
)
def test_every_configured_menu_action_has_a_handler(path: Path) -> None:
    """選單項目沒接處理者的話，postback 會掉進照護回報流程回「缺少回報草稿識別」。

    寫死清單會在改選單時失效，所以直接讀 yaml 比對。
    """
    import yaml

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    for item in document["actions"]:
        action = item["data"].split("action=", 1)[1].split("&")[0]
        assert action in MENU_PLACEHOLDER_ACTIONS or action in WEBHOOK_HANDLED_ACTIONS, (
            f"{path.name} 的 {action} 沒有任何處理者"
        )


def test_default_menu_offers_volunteer_and_adoption_entries() -> None:
    """一進來就分成志工／領養兩條路；綁定不是獨立按鈕（報名時會隱含建立）。"""
    import yaml

    document = yaml.safe_load(
        Path("infra/local/line-rich-menu-default.yaml").read_text(encoding="utf-8")
    )
    actions = [item["data"].split("action=", 1)[1] for item in document["actions"]]

    assert actions == ["start_volunteer_application", "adoption_placeholder"]
