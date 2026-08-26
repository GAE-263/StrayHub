"""心得步驟不該邀請志工略過一個送出時一定會被擋下的步驟。

原本 requires_note 只在送出時驗證，中途毫無提示，而心得那一步照常提供
「略過心得」。志工照著按，走到最後才被拒絕——實測顯示他的反應是放棄整筆回報。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from services.api.app.api.line_webhook import _chit_chat_reply, _options_requiring_note


class _Option:
    def __init__(self, code: str, display_name: str, requires_note: bool, category_id: str) -> None:
        self.code = code
        self.display_name = display_name
        self.requires_note = requires_note
        self.category_id = category_id


class _ObservationRepositoryStub:
    def __init__(self, options: list[_Option], categories: list[SimpleNamespace]) -> None:
        self._options = options
        self._categories = categories

    async def effective_options(self, *, include_disabled_history: bool = False):
        return self._options

    async def categories(self, *, include_disabled: bool = False):
        return self._categories


OPTIONS = [
    _Option("resource_guarding.other", "其他", True, "cat-guarding"),
    _Option("resource_guarding.tense", "緊繃", False, "cat-guarding"),
    _Option("emotion.other", "其他", True, "cat-emotion"),
    _Option("emotion.calm", "平靜或放鬆", False, "cat-emotion"),
    # 這個分類的代碼與選項前綴不一致，是 2026-08-21 手機實測踩到的那一個。
    _Option("appearance.other", "其他", True, "cat-appearance"),
    _Option("appearance.normal", "看起來正常", False, "cat-appearance"),
]
CATEGORIES = [
    SimpleNamespace(id="cat-guarding", code="resource_guarding", display_name="護食"),
    SimpleNamespace(id="cat-emotion", code="emotion", display_name="情緒"),
    SimpleNamespace(
        id="cat-appearance",
        code="appearance_special_status",
        display_name="外觀／特殊狀態",
    ),
]


@pytest.fixture
def patched_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.api.app.api.line_webhook as webhook

    monkeypatch.setattr(
        webhook,
        "ObservationRepository",
        lambda session, organization_id: _ObservationRepositoryStub(OPTIONS, CATEGORIES),
    )


@pytest.mark.asyncio
async def test_no_requirement_when_no_option_asks_for_text(patched_repository: None) -> None:
    answers = {"resource_guarding": "resource_guarding.tense", "emotion": "emotion.calm"}
    assert await _options_requiring_note(None, None, answers) == []


@pytest.mark.asyncio
async def test_requirement_names_the_category_and_option(patched_repository: None) -> None:
    answers = {"resource_guarding": "resource_guarding.other", "emotion": "emotion.calm"}
    # 訊息必須指名，志工才知道要回去改哪一題。
    assert await _options_requiring_note(None, None, answers) == ["護食：其他"]


@pytest.mark.asyncio
async def test_every_option_needing_text_is_listed(patched_repository: None) -> None:
    answers = {"resource_guarding": "resource_guarding.other", "emotion": "emotion.other"}
    assert await _options_requiring_note(None, None, answers) == ["護食：其他", "情緒：其他"]


@pytest.mark.asyncio
async def test_category_title_survives_a_prefix_that_differs_from_its_code(
    patched_repository: None,
) -> None:
    """分類要走 category_id 認，不能從選項代碼的前綴推。

    「外觀／特殊狀態」的代碼是 appearance_special_status，選項卻以 appearance.
    開頭。用前綴查標題會落空，志工在卡片上看到的是英文代碼 appearance。
    """
    answers = {"appearance_special_status": "appearance.other"}
    assert await _options_requiring_note(None, None, answers) == ["外觀／特殊狀態：其他"]


@pytest.mark.asyncio
async def test_unknown_code_is_ignored_rather_than_crashing(patched_repository: None) -> None:
    answers = {"feeding": "feeding.retired_code"}
    assert await _options_requiring_note(None, None, answers) == []


def test_chit_chat_points_at_the_menu_when_nothing_is_in_progress() -> None:
    reply = _chit_chat_reply(None)
    assert "開始散步回報" in reply
    # 志工隨口打字不是錯誤，回覆不該像錯誤訊息。
    assert "錯誤" not in reply and "不接受" not in reply


def test_chit_chat_explains_the_buttons_when_a_draft_is_open() -> None:
    reply = _chit_chat_reply(SimpleNamespace(current_step="answering_feeding"))
    assert "按鈕" in reply
    assert "錯誤" not in reply and "不接受" not in reply
