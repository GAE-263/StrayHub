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
    AWAITING_MEDIA = "awaiting_media"
    AWAITING_NOTE = "awaiting_note"
    AWAITING_STORY = "awaiting_story"
    REVIEWING = "reviewing"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# A walk report asks what a volunteer can actually observe during one walk —
# no shelter-side care (feeding/water/care_completion), no subjective emotion
# reading. See docs/散步回報-題目與收集理由.md for why each of these six exists
# and why the earlier 13-key set was cut down to this.
REQUIRED_ANSWER_KEYS = (
    "walk_completion",
    "activity",
    "gait",
    "defecation",
    "animal_interaction",
    "appearance_special_status",
)

# Not a CRM option — a Bot-level marker meaning "the volunteer looked and there
# was nothing to report," distinct from a real answer. Kept out of the CRM
# vocabulary so it can never be confused with an actual observation code, and
# out of _STATE_QUESTIONS's option lists so it never shows up as a fourth
# choice; callers offer it as a separate action instead.
UNOBSERVED = "unobserved"

# The one code in the reduced defecation vocabulary that means "nothing to
# photograph" — walking past this value is how the stool-photo step decides
# whether to ask at all. Defined here, not guessed from a display label, so a
# copy change can never silently change who gets asked for a photo.
NO_STOOL_CODE = "defecation.none"

WALK_COMPLETION_CODES = {
    "walk_completion.completed",
    "walk_completion.partially_completed",
    "walk_completion.not_done",
}

_NEXT_STATES: dict[DraftState, DraftState] = {
    DraftState.SELECTING_ANIMAL: DraftState.CONFIRMING_ANIMAL,
    DraftState.CONFIRMING_ANIMAL: DraftState.ANSWERING_WALK_COMPLETION,
    DraftState.ANSWERING_WALK_COMPLETION: DraftState.ANSWERING_ACTIVITY,
    DraftState.ANSWERING_ACTIVITY: DraftState.ANSWERING_GAIT,
    DraftState.ANSWERING_GAIT: DraftState.ANSWERING_DEFECATION,
    # Every defecation answer leads here first; a caller that just recorded
    # NO_STOOL_CODE transitions once more immediately to skip past it — see
    # LineDraftConversationService.handle().
    DraftState.ANSWERING_DEFECATION: DraftState.AWAITING_STOOL_MEDIA,
    DraftState.AWAITING_STOOL_MEDIA: DraftState.ANSWERING_ANIMAL_INTERACTION,
    DraftState.ANSWERING_ANIMAL_INTERACTION: DraftState.ANSWERING_SPECIAL_STATUS,
    DraftState.ANSWERING_SPECIAL_STATUS: DraftState.AWAITING_MEDIA,
    DraftState.AWAITING_MEDIA: DraftState.AWAITING_NOTE,
    DraftState.AWAITING_NOTE: DraftState.AWAITING_STORY,
    DraftState.AWAITING_STORY: DraftState.REVIEWING,
    DraftState.REVIEWING: DraftState.SUBMITTING,
    DraftState.SUBMITTING: DraftState.SUBMITTED,
}

_STATE_QUESTIONS: dict[DraftState, tuple[str, ...]] = {
    DraftState.ANSWERING_WALK_COMPLETION: ("walk_completion",),
    DraftState.ANSWERING_ACTIVITY: ("activity",),
    DraftState.ANSWERING_GAIT: ("gait",),
    DraftState.ANSWERING_DEFECATION: ("defecation",),
    DraftState.ANSWERING_ANIMAL_INTERACTION: ("animal_interaction",),
    DraftState.ANSWERING_SPECIAL_STATUS: ("appearance_special_status",),
}

_STATE_ORDER = (
    DraftState.ANSWERING_WALK_COMPLETION,
    DraftState.ANSWERING_ACTIVITY,
    DraftState.ANSWERING_GAIT,
    DraftState.ANSWERING_DEFECATION,
    DraftState.AWAITING_STOOL_MEDIA,
    DraftState.ANSWERING_ANIMAL_INTERACTION,
    DraftState.ANSWERING_SPECIAL_STATUS,
    DraftState.AWAITING_MEDIA,
    DraftState.AWAITING_NOTE,
    DraftState.AWAITING_STORY,
    DraftState.REVIEWING,
)
_PREVIOUS_STATE: dict[DraftState, DraftState] = {
    DraftState.CONFIRMING_ANIMAL: DraftState.SELECTING_ANIMAL,
    DraftState.ANSWERING_WALK_COMPLETION: DraftState.CONFIRMING_ANIMAL,
    DraftState.ANSWERING_ACTIVITY: DraftState.ANSWERING_WALK_COMPLETION,
    DraftState.ANSWERING_GAIT: DraftState.ANSWERING_ACTIVITY,
    DraftState.ANSWERING_DEFECATION: DraftState.ANSWERING_GAIT,
    DraftState.AWAITING_STOOL_MEDIA: DraftState.ANSWERING_DEFECATION,
    # Backing up out of animal_interaction always lands on the stool-photo
    # prompt, even for a volunteer whose "沒排便" answer skipped it going
    # forward — they can just hit skip again. Simpler than threading the
    # skip condition through a static previous-state map for one edge case.
    DraftState.ANSWERING_ANIMAL_INTERACTION: DraftState.AWAITING_STOOL_MEDIA,
    DraftState.ANSWERING_SPECIAL_STATUS: DraftState.ANSWERING_ANIMAL_INTERACTION,
    DraftState.AWAITING_MEDIA: DraftState.ANSWERING_SPECIAL_STATUS,
    DraftState.AWAITING_NOTE: DraftState.AWAITING_MEDIA,
    DraftState.AWAITING_STORY: DraftState.AWAITING_NOTE,
    DraftState.REVIEWING: DraftState.AWAITING_STORY,
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
    walk_completion = values["walk_completion"]
    if walk_completion != UNOBSERVED and walk_completion not in WALK_COMPLETION_CODES:
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
