from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs

import pytest
from services.api.app.api import line_webhook
from services.api.app.application.line_growth_diary_flex import (
    GrowthDiaryHistoryEntry,
    build_growth_diary_ai_reply_card,
    build_growth_diary_history_carousel,
    growth_diary_quick_reply_items,
)
from services.api.app.application.line_menu_actions import (
    BACK_TO_DEFAULT_MENU_ACTION,
    add_back_to_default_menu,
    is_menu_action,
)
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter


def _back_actions(message: dict) -> list[dict]:
    return [
        item["action"]
        for item in message.get("quickReply", {}).get("items", [])
        if item.get("action", {}).get("data") == f"action={BACK_TO_DEFAULT_MENU_ACTION}"
    ]


def test_terminal_navigation_uses_existing_parser_contract_once() -> None:
    message = add_back_to_default_menu({"type": "text", "text": "完成"})
    message = add_back_to_default_menu(message)

    actions = _back_actions(message)
    assert len(actions) == 1
    assert actions[0]["label"] == "返回主選單"
    assert parse_qs(actions[0]["data"])["action"] == [BACK_TO_DEFAULT_MENU_ACTION]
    assert is_menu_action(BACK_TO_DEFAULT_MENU_ACTION)


def test_growth_diary_intermediate_navigation_does_not_offer_default_menu() -> None:
    message = {"type": "text", "text": "請傳照片或文字"}
    message["quickReply"] = {"items": growth_diary_quick_reply_items()}

    assert _back_actions(message) == []


def test_growth_diary_terminal_builders_offer_default_menu_once() -> None:
    ai_reply = build_growth_diary_ai_reply_card(mood="neutral", reply_text="收到")
    history = build_growth_diary_history_carousel(
        [
            GrowthDiaryHistoryEntry(
                date_label="09/11",
                animal_name="合成毛孩",
                kind="text",
                note="合成日記",
                mood=None,
                reply=None,
            )
        ]
    )

    assert len(_back_actions(ai_reply)) == 1
    assert len(_back_actions(history)) == 1


@pytest.mark.asyncio
async def test_growth_diary_no_inquiry_terminal_offers_default_menu(monkeypatch) -> None:
    monkeypatch.setattr(line_webhook, "list_inquiries_for_adopter", lambda *_args: _empty())
    line = MockLineAdapter()

    await line_webhook._reply_growth_diary_entry_choice(
        object(),
        line,
        {"replyToken": "reply-1"},
        adopter_user_id=object(),
    )

    assert len(_back_actions(line.replies[0][1][0])) == 1


@pytest.mark.asyncio
async def test_adoption_intermediate_state_does_not_offer_default_menu() -> None:
    line = MockLineAdapter()
    draft = SimpleNamespace(
        current_step="selecting_organization",
        interaction_version=1,
    )

    await line_webhook._adoption_reply_for_state(
        object(),
        line,
        {"replyToken": "reply-1"},
        draft=draft,
        public_base_url=None,
    )

    assert _back_actions(line.replies[0][1][0]) == []


async def _empty() -> list:
    return []


@pytest.mark.parametrize("count", [13, 14])
def test_return_action_rejects_overflow_without_dropping_business_actions(count):
    import copy

    message = {
        "quickReply": {
            "items": [
                {"type": "action", "action": {"type": "postback", "data": f"action=choice_{i}"}}
                for i in range(count)
            ]
        }
    }
    before = copy.deepcopy(message)
    with pytest.raises(ValueError, match="quick_reply_capacity"):
        add_back_to_default_menu(message)
    assert message == before


def test_return_action_fits_twelve_actions_and_remains_idempotent():
    message = {
        "quickReply": {
            "items": [
                {"type": "action", "action": {"type": "postback", "data": f"action=choice_{i}"}}
                for i in range(12)
            ]
        }
    }
    add_back_to_default_menu(message)
    add_back_to_default_menu(message)
    assert len(message["quickReply"]["items"]) == 13
    assert len(_back_actions(message)) == 1


@pytest.mark.asyncio
async def test_menu_failure_logs_type_without_sensitive_exception(monkeypatch, caplog):
    from unittest.mock import AsyncMock

    router = SimpleNamespace(
        link_for_user=AsyncMock(side_effect=RuntimeError("synthetic-private-payload"))
    )
    monkeypatch.setattr(line_webhook, "_rich_menu_router", lambda: router)
    assert await line_webhook._switch_rich_menu("synthetic-user", "VOLUNTEER") is False
    assert "error_class=RuntimeError" in caplog.text
    assert "synthetic-private-payload" not in caplog.text
    assert "synthetic-user" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
