"""LIFF 掃完 QR 會自動送一句「開始照護回報」到聊天室。

它長得跟志工隨手打的字一模一樣，所以純文字的路由順序是有安全性的：入口指令
必須先被認出來。在此之前，草稿只要停在備註或故事那一題，這句自動訊息就會被
當成答案寫進去——而且是寫進「上一隻狗」的回報裡，因為志工正是走到下一隻狗
的籠子前面才掃的碼。
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from services.api.app.api.line_webhook import (
    _LIFF_CARE_REPORT_TRIGGER,
    _route_text_message,
)
from services.api.app.application.line_draft_service import DraftState

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WEB_HANDOFF = _REPO_ROOT / "apps/web/lib/liff-line-handoff.ts"


def _draft(step: DraftState) -> SimpleNamespace:
    return SimpleNamespace(current_step=step.value)


def test_the_bot_and_the_web_agree_on_the_exact_trigger_text() -> None:
    """兩邊是靠字面完全相同才對得上，任一邊改字就整條流程斷掉。"""
    source = _WEB_HANDOFF.read_text(encoding="utf-8")
    match = re.search(r'CARE_REPORT_TRIGGER_TEXT\s*=\s*"([^"]+)"', source)
    assert match is not None, f"{_WEB_HANDOFF} 沒有 CARE_REPORT_TRIGGER_TEXT"
    assert match.group(1) == _LIFF_CARE_REPORT_TRIGGER


def test_trigger_text_is_an_entry_command_not_a_note_answer() -> None:
    assert _route_text_message(_draft(DraftState.AWAITING_NOTE), _LIFF_CARE_REPORT_TRIGGER) == (
        "start_report"
    )


def test_trigger_text_is_an_entry_command_not_a_story_answer() -> None:
    assert _route_text_message(_draft(DraftState.AWAITING_STORY), _LIFF_CARE_REPORT_TRIGGER) == (
        "start_report"
    )


def test_trigger_text_still_starts_a_report_when_nothing_is_in_progress() -> None:
    assert _route_text_message(None, _LIFF_CARE_REPORT_TRIGGER) == "start_report"


def test_trigger_text_tolerates_the_whitespace_line_may_add() -> None:
    assert _route_text_message(None, f"  {_LIFF_CARE_REPORT_TRIGGER}\n") == "start_report"


def test_a_real_note_is_still_captured_as_an_answer() -> None:
    assert _route_text_message(_draft(DraftState.AWAITING_NOTE), "今天左後腳有點跛") == "answer"


def test_a_real_story_is_still_captured_as_an_answer() -> None:
    assert _route_text_message(_draft(DraftState.AWAITING_STORY), "看到推車就衝過去") == "answer"


def test_text_that_merely_contains_the_trigger_is_still_a_note() -> None:
    """志工真的在備註裡提到這四個字時，不該被吃掉整筆回報的進度。"""
    answer = f"剛剛按了{_LIFF_CARE_REPORT_TRIGGER}但沒反應"
    assert _route_text_message(_draft(DraftState.AWAITING_NOTE), answer) == "answer"


def test_free_text_without_a_committed_animal_searches_for_the_dog() -> None:
    assert _route_text_message(None, "小財") == "search"
    assert _route_text_message(_draft(DraftState.SELECTING_ANIMAL), "小財") == "search"


def test_chatter_midway_through_the_questionnaire_is_not_an_answer() -> None:
    assert _route_text_message(_draft(DraftState.ANSWERING_ACTIVITY), "哈囉") == "chit_chat"


def test_blank_text_never_becomes_a_search() -> None:
    assert _route_text_message(None, "   ") == "chit_chat"
