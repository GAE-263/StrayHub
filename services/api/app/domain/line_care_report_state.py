from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from services.api.app.api.errors import DomainError


class DraftState(StrEnum):
    SELECTING_ANIMAL = "selecting_animal"
    CONFIRMING_ANIMAL = "confirming_animal"
    ANSWERING_COMPLETION = "answering_completion"
    ANSWERING_FEEDING = "answering_feeding"
    ANSWERING_WATER = "answering_water"
    ANSWERING_ACTIVITY = "answering_activity"
    ANSWERING_ELIMINATION = "answering_elimination"
    ANSWERING_BEHAVIOR = "answering_behavior"
    ANSWERING_SPECIAL_STATUS = "answering_special_status"
    AWAITING_MEDIA = "awaiting_media"
    AWAITING_NOTE = "awaiting_note"
    REVIEWING = "reviewing"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


REQUIRED_ANSWER_KEYS = (
    "care_completion",
    "walk_completion",
    "feeding",
    "water",
    "activity",
    "urination",
    "defecation",
    "resource_guarding",
    "human_interaction",
    "animal_interaction",
    "emotion",
    "walk_reaction",
    "appearance_special_status",
)

CARE_COMPLETION_CODES = {
    "care_completion.completed",
    "care_completion.partially_completed",
    "care_completion.not_provided",
    "care_completion.not_observed",
    "care_completion.uncertain",
}
WALK_COMPLETION_CODES = {
    "walk_completion.completed",
    "walk_completion.partially_completed",
    "walk_completion.not_done",
    "walk_completion.not_observed",
    "walk_completion.uncertain",
}

_NEXT_STATES: dict[DraftState, DraftState] = {
    DraftState.SELECTING_ANIMAL: DraftState.CONFIRMING_ANIMAL,
    DraftState.CONFIRMING_ANIMAL: DraftState.ANSWERING_COMPLETION,
    DraftState.ANSWERING_COMPLETION: DraftState.ANSWERING_FEEDING,
    DraftState.ANSWERING_FEEDING: DraftState.ANSWERING_WATER,
    DraftState.ANSWERING_WATER: DraftState.ANSWERING_ACTIVITY,
    DraftState.ANSWERING_ACTIVITY: DraftState.ANSWERING_ELIMINATION,
    DraftState.ANSWERING_ELIMINATION: DraftState.ANSWERING_BEHAVIOR,
    DraftState.ANSWERING_BEHAVIOR: DraftState.ANSWERING_SPECIAL_STATUS,
    DraftState.ANSWERING_SPECIAL_STATUS: DraftState.AWAITING_MEDIA,
    DraftState.AWAITING_MEDIA: DraftState.AWAITING_NOTE,
    DraftState.AWAITING_NOTE: DraftState.REVIEWING,
    DraftState.REVIEWING: DraftState.SUBMITTING,
    DraftState.SUBMITTING: DraftState.SUBMITTED,
}

_STATE_QUESTIONS: dict[DraftState, tuple[str, ...]] = {
    DraftState.ANSWERING_COMPLETION: ("care_completion", "walk_completion"),
    DraftState.ANSWERING_FEEDING: ("feeding",),
    DraftState.ANSWERING_WATER: ("water",),
    DraftState.ANSWERING_ACTIVITY: ("activity",),
    DraftState.ANSWERING_ELIMINATION: ("urination", "defecation"),
    DraftState.ANSWERING_BEHAVIOR: (
        "resource_guarding",
        "human_interaction",
        "animal_interaction",
        "emotion",
        "walk_reaction",
    ),
    DraftState.ANSWERING_SPECIAL_STATUS: ("appearance_special_status",),
}

_STATE_ORDER = (
    DraftState.ANSWERING_COMPLETION,
    DraftState.ANSWERING_FEEDING,
    DraftState.ANSWERING_WATER,
    DraftState.ANSWERING_ACTIVITY,
    DraftState.ANSWERING_ELIMINATION,
    DraftState.ANSWERING_BEHAVIOR,
    DraftState.ANSWERING_SPECIAL_STATUS,
    DraftState.AWAITING_MEDIA,
    DraftState.AWAITING_NOTE,
    DraftState.REVIEWING,
)
_PREVIOUS_STATE: dict[DraftState, DraftState] = {
    DraftState.CONFIRMING_ANIMAL: DraftState.SELECTING_ANIMAL,
    DraftState.ANSWERING_COMPLETION: DraftState.CONFIRMING_ANIMAL,
    DraftState.ANSWERING_FEEDING: DraftState.ANSWERING_COMPLETION,
    DraftState.ANSWERING_WATER: DraftState.ANSWERING_FEEDING,
    DraftState.ANSWERING_ACTIVITY: DraftState.ANSWERING_WATER,
    DraftState.ANSWERING_ELIMINATION: DraftState.ANSWERING_ACTIVITY,
    DraftState.ANSWERING_BEHAVIOR: DraftState.ANSWERING_ELIMINATION,
    DraftState.ANSWERING_SPECIAL_STATUS: DraftState.ANSWERING_BEHAVIOR,
    DraftState.AWAITING_MEDIA: DraftState.ANSWERING_SPECIAL_STATUS,
    DraftState.AWAITING_NOTE: DraftState.AWAITING_MEDIA,
    DraftState.REVIEWING: DraftState.AWAITING_NOTE,
    DraftState.SUBMITTING: DraftState.REVIEWING,
}


@dataclass
class DraftAnswers:
    """部分答案；草稿可以缺少任何必要題目。"""

    values: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        if key not in REQUIRED_ANSWER_KEYS:
            raise DomainError("invalid_answer_key", f"不支援的回報答案：{key}", 422)
        if value is None or value == "":
            raise DomainError("invalid_answer_value", f"回報答案不可為空：{key}", 422)
        self.values[key] = value

    def missing(self) -> list[str]:
        return [key for key in REQUIRED_ANSWER_KEYS if key not in self.values]

    def complete(self) -> bool:
        return not self.missing()


@dataclass(frozen=True)
class CareReportAnswers:
    values: dict[str, Any]

    def __post_init__(self) -> None:
        missing = [key for key in REQUIRED_ANSWER_KEYS if key not in self.values]
        if missing:
            raise DomainError("incomplete_answers", f"缺少必要回報答案：{', '.join(missing)}", 422)
        _validate_completion_codes(self.values)


def _validate_completion_codes(values: dict[str, Any]) -> None:
    if values["care_completion"] not in CARE_COMPLETION_CODES:
        raise DomainError("invalid_care_completion", "照護完成狀態代碼無效", 422)
    if values["walk_completion"] not in WALK_COMPLETION_CODES:
        raise DomainError("invalid_walk_completion", "散步完成狀態代碼無效", 422)
    if isinstance(values["walk_reaction"], str) and values["walk_reaction"].startswith(
        "walk_completion."
    ):
        raise DomainError("mixed_walk_code", "散步完成與散步反應代碼不可混用", 422)


@dataclass
class DraftStateMachine:
    state: DraftState = DraftState.SELECTING_ANIMAL
    answers: DraftAnswers = field(default_factory=DraftAnswers)
    reconfirmation_keys: set[str] = field(default_factory=set)
    last_interaction_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def transition(self, target: DraftState) -> None:
        if target in {DraftState.CANCELLED, DraftState.EXPIRED}:
            if self.state in {DraftState.SUBMITTED, DraftState.CANCELLED, DraftState.EXPIRED}:
                raise DomainError("invalid_state_transition", "草稿目前狀態不可取消或過期", 409)
            self.state = target
            return
        if self.state in {DraftState.CANCELLED, DraftState.EXPIRED, DraftState.SUBMITTED}:
            raise DomainError("invalid_state_transition", "草稿已結束，不能再次操作", 409)
        if _NEXT_STATES.get(self.state) != target:
            raise DomainError("invalid_state_transition", "不允許的草稿狀態轉移", 409)
        if target in {DraftState.REVIEWING, DraftState.SUBMITTING} and not self.answers.complete():
            raise DomainError("incomplete_answers", "完成 13 個標準答案後才能進入確認或送出", 422)
        self.state = target
        self.last_interaction_at = datetime.now(timezone.utc)

    def answer(self, key: str, value: Any) -> None:
        self.answers.set(key, value)
        self.last_interaction_at = datetime.now(timezone.utc)

    def next_answer_key(self) -> str:
        expected = _STATE_QUESTIONS.get(self.state)
        if expected is None:
            raise DomainError("invalid_state_transition", "目前步驟不接受答案", 409)
        key = next(
            (
                item
                for item in expected
                if item in self.reconfirmation_keys or item not in self.answers.values
            ),
            None,
        )
        if key is None:
            raise DomainError("invalid_state_transition", "目前步驟已完成", 409)
        return key

    def answer_current(self, value: Any) -> DraftState:
        return self.answer_question(self.next_answer_key(), value)

    def answer_question(self, key: str, value: Any) -> DraftState:
        """Accept only the question belonging to the server-side current step."""
        expected = _STATE_QUESTIONS.get(self.state)
        if expected is None or key != self.next_answer_key():
            raise DomainError("unexpected_answer", "目前步驟不接受這個答案", 409)
        self.answer(key, value)
        self.reconfirmation_keys.discard(key)
        if all(
            item in self.answers.values and item not in self.reconfirmation_keys
            for item in expected
        ):
            self.transition(_NEXT_STATES[self.state])
        return self.state

    def back(self) -> DraftState:
        """回到前一個可操作步驟，並清除該步驟及其後的答案。"""
        if self.state not in _PREVIOUS_STATE:
            raise DomainError("invalid_state_transition", "目前步驟不能返回上一步", 409)
        previous = _PREVIOUS_STATE[self.state]
        if previous in _STATE_ORDER:
            previous_index = _STATE_ORDER.index(previous)
            keys_to_clear = {
                key
                for state in _STATE_ORDER[previous_index:]
                for key in _STATE_QUESTIONS.get(state, ())
            }
            for key in keys_to_clear:
                self.answers.values.pop(key, None)
        self.state = previous
        self.last_interaction_at = datetime.now(timezone.utc)
        return self.state

    def submit(self) -> CareReportAnswers:
        if self.state != DraftState.SUBMITTING:
            raise DomainError("invalid_state_transition", "草稿尚未進入送出狀態", 409)
        result = CareReportAnswers(dict(self.answers.values))
        self.state = DraftState.SUBMITTED
        return result
