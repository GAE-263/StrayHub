"""心得步驟不該邀請志工略過一個送出時一定會被擋下的步驟。

原本 requires_note 只在送出時驗證，中途毫無提示，而心得那一步照常提供
「略過心得」。志工照著按，走到最後才被拒絕——實測顯示他的反應是放棄整筆回報。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.api.app.api.line_webhook import _chit_chat_reply, _options_requiring_note


class _Option:
    def __init__(self, code: str, display_name: str, requires_note: bool) -> None:
        self.code = code
        self.display_name = display_name
        self.requires_note = requires_note


class _ObservationRepositoryStub:
    def __init__(self, options: list[_Option], categories: list[SimpleNamespace]) -> None:
        self._options = options
        self._categories = categories

    async def effective_options(self, *, include_disabled_history: bool = False):
        return self._options

    async def categories(self, *, include_disabled: bool = False):
        return self._categories


OPTIONS = [
    _Option("resource_guarding.other", "其他", True),
    _Option("resource_guarding.tense", "緊繃", False),
    _Option("emotion.other", "其他", True),
    _Option("emotion.calm", "平靜或放鬆", False),
]
CATEGORIES = [
    SimpleNamespace(code="resource_guarding", display_name="護食"),
    SimpleNamespace(code="emotion", display_name="情緒"),
]


@pytest.fixture
def patched_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.api.app.api.line_webhook as webhook

    monkeypatch.setattr(
        webhook,
        "ObservationRepository",
        lambda session, organization_id: _ObservationRepositoryStub(OPTIONS, CATEGORIES),
    )

    async def fake_titles(session, organization_id):
        return {category.code: category.display_name for category in CATEGORIES}

    monkeypatch.setattr(webhook, "_category_titles", fake_titles)


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
async def test_unknown_code_is_ignored_rather_than_crashing(patched_repository: None) -> None:
    answers = {"feeding": "feeding.retired_code"}
    assert await _options_requiring_note(None, None, answers) == []


def test_chit_chat_points_at_the_menu_when_nothing_is_in_progress() -> None:
    reply = _chit_chat_reply(None)
    assert "開始照護回報" in reply
    # 志工隨口打字不是錯誤，回覆不該像錯誤訊息。
    assert "錯誤" not in reply and "不接受" not in reply


def test_chit_chat_explains_the_buttons_when_a_draft_is_open() -> None:
    reply = _chit_chat_reply(SimpleNamespace(current_step="answering_feeding"))
    assert "按鈕" in reply
    assert "錯誤" not in reply and "不接受" not in reply
