from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from services.api.app.api.errors import DomainError


class DraftState(StrEnum):
    SELECTING_ANIMAL = "selecting_animal"
    CONFIRMING_ANIMAL = "confirming_animal"
    ANSWERING_WALK_COMPLETION = "answering_walk_completion"
    ANSWERING_ACTIVITY = "answering_activity"
    ANSWERING_GAIT = "answering_gait"
    ANSWERING_DEFECATION = "answering_defecation"
    AWAITING_STOOL_MEDIA = "awaiting_stool_media"
    ANSWERING_ANIMAL_INTERACTION = "answering_animal_interaction"
    ANSWERING_SPECIAL_STATUS = "answering_special_status"
    AWAITING_NOTE = "awaiting_note"
    AWAITING_STORY = "awaiting_story"
    REVIEWING = "reviewing"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


REQUIRED_ANSWER_KEYS = (
    "walk_completion",
    "activity",
    "gait",
    "defecation",
    "animal_interaction",
    "appearance_special_status",
)
UNOBSERVED = "unobserved"
NO_STOOL_CODE = "defecation.none"
WALK_COMPLETION_CODES = {
    "walk_completion.completed",
    "walk_completion.partially_completed",
    "walk_completion.not_done",
}

_NEXT_STATES = {
    DraftState.SELECTING_ANIMAL: DraftState.CONFIRMING_ANIMAL,
    DraftState.CONFIRMING_ANIMAL: DraftState.ANSWERING_WALK_COMPLETION,
    DraftState.ANSWERING_WALK_COMPLETION: DraftState.ANSWERING_ACTIVITY,
    DraftState.ANSWERING_ACTIVITY: DraftState.ANSWERING_GAIT,
    DraftState.ANSWERING_GAIT: DraftState.ANSWERING_DEFECATION,
    DraftState.ANSWERING_DEFECATION: DraftState.AWAITING_STOOL_MEDIA,
    DraftState.AWAITING_STOOL_MEDIA: DraftState.ANSWERING_ANIMAL_INTERACTION,
    DraftState.ANSWERING_ANIMAL_INTERACTION: DraftState.ANSWERING_SPECIAL_STATUS,
    DraftState.ANSWERING_SPECIAL_STATUS: DraftState.AWAITING_NOTE,
    DraftState.AWAITING_NOTE: DraftState.AWAITING_STORY,
    DraftState.AWAITING_STORY: DraftState.REVIEWING,
    DraftState.REVIEWING: DraftState.SUBMITTING,
    DraftState.SUBMITTING: DraftState.SUBMITTED,
}
_QUESTIONS = {
    DraftState.ANSWERING_WALK_COMPLETION: "walk_completion",
    DraftState.ANSWERING_ACTIVITY: "activity",
    DraftState.ANSWERING_GAIT: "gait",
    DraftState.ANSWERING_DEFECATION: "defecation",
    DraftState.ANSWERING_ANIMAL_INTERACTION: "animal_interaction",
    DraftState.ANSWERING_SPECIAL_STATUS: "appearance_special_status",
}
_ORDER = (
    DraftState.ANSWERING_WALK_COMPLETION,
    DraftState.ANSWERING_ACTIVITY,
    DraftState.ANSWERING_GAIT,
    DraftState.ANSWERING_DEFECATION,
    DraftState.AWAITING_STOOL_MEDIA,
    DraftState.ANSWERING_ANIMAL_INTERACTION,
    DraftState.ANSWERING_SPECIAL_STATUS,
    DraftState.AWAITING_NOTE,
    DraftState.AWAITING_STORY,
    DraftState.REVIEWING,
)
_PREVIOUS = {
    DraftState.CONFIRMING_ANIMAL: DraftState.SELECTING_ANIMAL,
    DraftState.ANSWERING_WALK_COMPLETION: DraftState.CONFIRMING_ANIMAL,
    DraftState.ANSWERING_ACTIVITY: DraftState.ANSWERING_WALK_COMPLETION,
    DraftState.ANSWERING_GAIT: DraftState.ANSWERING_ACTIVITY,
    DraftState.ANSWERING_DEFECATION: DraftState.ANSWERING_GAIT,
    DraftState.AWAITING_STOOL_MEDIA: DraftState.ANSWERING_DEFECATION,
    DraftState.ANSWERING_SPECIAL_STATUS: DraftState.ANSWERING_ANIMAL_INTERACTION,
    DraftState.AWAITING_NOTE: DraftState.ANSWERING_SPECIAL_STATUS,
    DraftState.AWAITING_STORY: DraftState.AWAITING_NOTE,
    DraftState.REVIEWING: DraftState.AWAITING_STORY,
    DraftState.SUBMITTING: DraftState.REVIEWING,
}


@dataclass
class DraftAnswers:
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
        unsupported = [key for key in self.values if key not in REQUIRED_ANSWER_KEYS]
        if unsupported:
            raise DomainError(
                "invalid_answer_key", f"不支援的回報答案：{', '.join(unsupported)}", 422
            )
        missing = [key for key in REQUIRED_ANSWER_KEYS if key not in self.values]
        if missing:
            raise DomainError("incomplete_answers", f"缺少必要回報答案：{', '.join(missing)}", 422)
        value = self.values["walk_completion"]
        if value != UNOBSERVED and value not in WALK_COMPLETION_CODES:
            raise DomainError("invalid_walk_completion", "散步完成狀態代碼無效", 422)


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
            raise DomainError("incomplete_answers", "完成 6 個標準答案後才能進入確認或送出", 422)
        self.state = target
        self.last_interaction_at = datetime.now(timezone.utc)

    def next_answer_key(self) -> str:
        key = _QUESTIONS.get(self.state)
        if key is None:
            raise DomainError("invalid_state_transition", "目前步驟不接受答案", 409)
        if key in self.answers.values and key not in self.reconfirmation_keys:
            raise DomainError("invalid_state_transition", "目前步驟已完成", 409)
        return key

    def answer(self, key: str, value: Any) -> None:
        self.answers.set(key, value)
        self.last_interaction_at = datetime.now(timezone.utc)

    def answer_current(self, value: Any) -> DraftState:
        key = self.next_answer_key()
        self.answer(key, value)
        self.reconfirmation_keys.discard(key)
        self.transition(_NEXT_STATES[self.state])
        return self.state

    def answer_question(self, key: str, value: Any) -> DraftState:
        if key != self.next_answer_key():
            raise DomainError("unexpected_answer", "目前步驟不接受這個答案", 409)
        return self.answer_current(value)

    def back(self) -> DraftState:
        if self.state == DraftState.ANSWERING_ANIMAL_INTERACTION:
            previous = (
                DraftState.ANSWERING_DEFECATION
                if self.answers.values.get("defecation") in {NO_STOOL_CODE, UNOBSERVED}
                else DraftState.AWAITING_STOOL_MEDIA
            )
        else:
            previous = _PREVIOUS.get(self.state)
        if previous is None:
            raise DomainError("invalid_state_transition", "目前步驟不能返回上一步", 409)
        if previous in _ORDER:
            for state in _ORDER[_ORDER.index(previous) :]:
                key = _QUESTIONS.get(state)
                if key:
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
