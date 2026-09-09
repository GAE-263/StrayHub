from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from services.api.app.api.errors import DomainError

# Public: also reused by line_webhook.py to distinguish a phone-number reply
# from a free-text AI-followup answer while AWAITING_PHONE_NUMBER.
PHONE_NUMBER_PATTERN = re.compile(r"^09\d{8}$")


class AdoptionPath(StrEnum):
    SPECIFIC_ANIMAL = "specific_animal"
    RECOMMEND_ME = "recommend_me"


class AdoptionDraftState(StrEnum):
    SELECTING_ORGANIZATION = "selecting_organization"
    CHOOSING_PATH = "choosing_path"
    SELECTING_TARGET_ANIMAL = "selecting_target_animal"
    CONFIRMING_TARGET_ANIMAL = "confirming_target_animal"
    # One free-text self-introduction (either path) replaces the first ask of
    # each preference question — see AdoptionDraftStateMachine.skip_prefilled_questions.
    # Up to AWAITING_FREETEXT_PROFILE_MAX_ROUNDS rounds of supplementing by
    # free text are allowed before whatever's still missing falls back to the
    # existing one-question-at-a-time flow.
    AWAITING_FREETEXT_PROFILE = "awaiting_freetext_profile"
    ANSWERING_PREFERENCE_HOUSING = "answering_preference_housing"
    ANSWERING_PREFERENCE_EXPERIENCE = "answering_preference_experience"
    ANSWERING_PREFERENCE_OTHER_PETS = "answering_preference_other_pets"
    ANSWERING_PREFERENCE_HOUSEHOLD = "answering_preference_household"
    ANSWERING_PREFERENCE_SCHEDULE = "answering_preference_schedule"
    ANSWERING_PREFERENCE_PARENTING_STYLE = "answering_preference_parenting_style"
    ANSWERING_PREFERENCE_PATIENCE = "answering_preference_patience"
    ANSWERING_PREFERENCE_ADOPTION_MOTIVATION = "answering_preference_adoption_motivation"
    ANSWERING_PREFERENCE_SIZE = "answering_preference_size"
    ANSWERING_PREFERENCE_ENERGY = "answering_preference_energy"
    PRESENTING_MATCHES = "presenting_matches"
    SELECTING_MATCHED_ANIMAL = "selecting_matched_animal"
    ANSWERING_HOUSING = "answering_housing"
    ANSWERING_EXPERIENCE = "answering_experience"
    ANSWERING_OTHER_PETS = "answering_other_pets"
    ANSWERING_HOUSEHOLD = "answering_household"
    ANSWERING_SCHEDULE = "answering_schedule"
    ANSWERING_PARENTING_STYLE = "answering_parenting_style"
    ANSWERING_PATIENCE = "answering_patience"
    ANSWERING_ADOPTION_MOTIVATION = "answering_adoption_motivation"
    CONFIRMING_ANSWERS = "confirming_answers"
    AWAITING_AI_SUITABILITY = "awaiting_ai_suitability"
    SELECTING_ALTERNATIVE_ANIMAL = "selecting_alternative_animal"
    CONFIRMING_ALTERNATIVE_ANIMAL = "confirming_alternative_animal"
    AWAITING_AI_RECOMMENDATIONS = "awaiting_ai_recommendations"
    AWAITING_ADOPTER_NAME = "awaiting_adopter_name"
    AWAITING_CONTACT_TIME = "awaiting_contact_time"
    AWAITING_PHONE_NUMBER = "awaiting_phone_number"
    EDITING_ADOPTER_NAME = "editing_adopter_name"
    EDITING_CONTACT_TIME = "editing_contact_time"
    EDITING_PHONE_NUMBER = "editing_phone_number"
    REVIEWING = "reviewing"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


_S = AdoptionDraftState
_P = AdoptionPath

CONTACT_EDIT_STATES = {
    _S.EDITING_ADOPTER_NAME: "adopter_name",
    _S.EDITING_CONTACT_TIME: "contact_time",
    _S.EDITING_PHONE_NUMBER: "phone_number",
}

BASE_PREFERENCE_KEYS = (
    "housing_type",
    "dog_experience",
    "other_pets",
    "household_members",
    "work_schedule",
    "parenting_style",
    "patience_level",
    "adoption_motivation",
)
MATCH_PREFERENCE_KEYS = BASE_PREFERENCE_KEYS + ("preferred_size", "preferred_energy")
# 留下聯絡方式現在拆成三步：姓名 → 方便聯繫時間 → 手機號碼，兩條路徑都要收集。
CONTACT_INFO_KEYS = ("adopter_name", "contact_time", "phone_number")
ALL_ANSWER_KEYS = MATCH_PREFERENCE_KEYS + CONTACT_INFO_KEYS

REQUIRED_KEYS_BY_PATH: dict[AdoptionPath, tuple[str, ...]] = {
    _P.SPECIFIC_ANIMAL: BASE_PREFERENCE_KEYS + CONTACT_INFO_KEYS,
    _P.RECOMMEND_ME: MATCH_PREFERENCE_KEYS + CONTACT_INFO_KEYS,
}

# How many rounds of free-text supplementing AWAITING_FREETEXT_PROFILE allows
# before whatever's still missing is handed off to the one-question-at-a-time
# fallback regardless of how much more the adopter offers to type.
AWAITING_FREETEXT_PROFILE_MAX_ROUNDS = 2

# Transitions that do not depend on which path was chosen are keyed with path=None.
# Transitions out of a path-specific state are keyed with that state's concrete path.
_NEXT_STATES: dict[tuple[AdoptionDraftState, AdoptionPath | None], AdoptionDraftState] = {
    (_S.SELECTING_ORGANIZATION, None): _S.CHOOSING_PATH,
    (_S.CHOOSING_PATH, _P.SPECIFIC_ANIMAL): _S.SELECTING_TARGET_ANIMAL,
    (_S.CHOOSING_PATH, _P.RECOMMEND_ME): _S.AWAITING_FREETEXT_PROFILE,
    (_S.SELECTING_TARGET_ANIMAL, _P.SPECIFIC_ANIMAL): _S.CONFIRMING_TARGET_ANIMAL,
    (_S.CONFIRMING_TARGET_ANIMAL, _P.SPECIFIC_ANIMAL): _S.AWAITING_FREETEXT_PROFILE,
    (_S.CONFIRMING_TARGET_ANIMAL, _P.RECOMMEND_ME): _S.AWAITING_ADOPTER_NAME,
    (_S.AWAITING_FREETEXT_PROFILE, _P.SPECIFIC_ANIMAL): _S.ANSWERING_HOUSING,
    (_S.AWAITING_FREETEXT_PROFILE, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_HOUSING,
    (_S.ANSWERING_HOUSING, _P.SPECIFIC_ANIMAL): _S.ANSWERING_EXPERIENCE,
    (_S.ANSWERING_EXPERIENCE, _P.SPECIFIC_ANIMAL): _S.ANSWERING_OTHER_PETS,
    (_S.ANSWERING_OTHER_PETS, _P.SPECIFIC_ANIMAL): _S.ANSWERING_HOUSEHOLD,
    (_S.ANSWERING_HOUSEHOLD, _P.SPECIFIC_ANIMAL): _S.ANSWERING_SCHEDULE,
    (_S.ANSWERING_SCHEDULE, _P.SPECIFIC_ANIMAL): _S.ANSWERING_PARENTING_STYLE,
    (_S.ANSWERING_PARENTING_STYLE, _P.SPECIFIC_ANIMAL): _S.ANSWERING_PATIENCE,
    (_S.ANSWERING_PATIENCE, _P.SPECIFIC_ANIMAL): _S.ANSWERING_ADOPTION_MOTIVATION,
    (_S.ANSWERING_ADOPTION_MOTIVATION, _P.SPECIFIC_ANIMAL): _S.CONFIRMING_ANSWERS,
    (_S.CONFIRMING_ANSWERS, _P.SPECIFIC_ANIMAL): _S.AWAITING_AI_SUITABILITY,
    # 這一步的實際下一站取決於 AI 分析結果（≥60% 直接留聯絡方式；<60% 追問特殊
    # 需求後改走 SELECTING_ALTERNATIVE_ANIMAL），由背景任務直接寫入
    # current_step，不經過 advance()／transition() —— 這裡宣告的是「預設」的
    # 高分路徑，純粹是為了讓圖保持完整、供 back() 反查使用。
    (_S.AWAITING_AI_SUITABILITY, _P.SPECIFIC_ANIMAL): _S.AWAITING_ADOPTER_NAME,
    (_S.SELECTING_ALTERNATIVE_ANIMAL, _P.SPECIFIC_ANIMAL): _S.CONFIRMING_ALTERNATIVE_ANIMAL,
    (_S.CONFIRMING_ALTERNATIVE_ANIMAL, _P.SPECIFIC_ANIMAL): _S.AWAITING_ADOPTER_NAME,
    (_S.ANSWERING_PREFERENCE_HOUSING, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_EXPERIENCE,
    (_S.ANSWERING_PREFERENCE_EXPERIENCE, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_OTHER_PETS,
    (_S.ANSWERING_PREFERENCE_OTHER_PETS, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_HOUSEHOLD,
    (_S.ANSWERING_PREFERENCE_HOUSEHOLD, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_SCHEDULE,
    (_S.ANSWERING_PREFERENCE_SCHEDULE, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_PARENTING_STYLE,
    (_S.ANSWERING_PREFERENCE_PARENTING_STYLE, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_PATIENCE,
    (
        _S.ANSWERING_PREFERENCE_PATIENCE,
        _P.RECOMMEND_ME,
    ): _S.ANSWERING_PREFERENCE_ADOPTION_MOTIVATION,
    (_S.ANSWERING_PREFERENCE_ADOPTION_MOTIVATION, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_SIZE,
    (_S.ANSWERING_PREFERENCE_SIZE, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_ENERGY,
    (_S.ANSWERING_PREFERENCE_ENERGY, _P.RECOMMEND_ME): _S.PRESENTING_MATCHES,
    # 規則式先篩出候選池後不直接揭曉，先進 AWAITING_AI_RECOMMENDATIONS，
    # 由 durable Celery job 重新評分排序；完成後才以 conditional write 將
    # current_step 更新為 SELECTING_MATCHED_ANIMAL。
    (_S.PRESENTING_MATCHES, _P.RECOMMEND_ME): _S.AWAITING_AI_RECOMMENDATIONS,
    (_S.AWAITING_AI_RECOMMENDATIONS, _P.RECOMMEND_ME): _S.SELECTING_MATCHED_ANIMAL,
    (_S.SELECTING_MATCHED_ANIMAL, _P.RECOMMEND_ME): _S.CONFIRMING_TARGET_ANIMAL,
    (_S.AWAITING_ADOPTER_NAME, None): _S.AWAITING_CONTACT_TIME,
    (_S.AWAITING_CONTACT_TIME, None): _S.AWAITING_PHONE_NUMBER,
    (_S.AWAITING_PHONE_NUMBER, None): _S.REVIEWING,
    (_S.REVIEWING, None): _S.SUBMITTING,
    (_S.SUBMITTING, None): _S.SUBMITTED,
}

_PREVIOUS_STATE: dict[tuple[AdoptionDraftState, AdoptionPath | None], AdoptionDraftState] = {
    (_S.CHOOSING_PATH, None): _S.SELECTING_ORGANIZATION,
    (_S.SELECTING_TARGET_ANIMAL, _P.SPECIFIC_ANIMAL): _S.CHOOSING_PATH,
    (_S.CONFIRMING_TARGET_ANIMAL, _P.SPECIFIC_ANIMAL): _S.SELECTING_TARGET_ANIMAL,
    (_S.AWAITING_FREETEXT_PROFILE, _P.SPECIFIC_ANIMAL): _S.CONFIRMING_TARGET_ANIMAL,
    (_S.AWAITING_FREETEXT_PROFILE, _P.RECOMMEND_ME): _S.CHOOSING_PATH,
    (_S.ANSWERING_HOUSING, _P.SPECIFIC_ANIMAL): _S.AWAITING_FREETEXT_PROFILE,
    (_S.ANSWERING_EXPERIENCE, _P.SPECIFIC_ANIMAL): _S.ANSWERING_HOUSING,
    (_S.ANSWERING_OTHER_PETS, _P.SPECIFIC_ANIMAL): _S.ANSWERING_EXPERIENCE,
    (_S.ANSWERING_HOUSEHOLD, _P.SPECIFIC_ANIMAL): _S.ANSWERING_OTHER_PETS,
    (_S.ANSWERING_SCHEDULE, _P.SPECIFIC_ANIMAL): _S.ANSWERING_HOUSEHOLD,
    (_S.ANSWERING_PARENTING_STYLE, _P.SPECIFIC_ANIMAL): _S.ANSWERING_SCHEDULE,
    (_S.ANSWERING_PATIENCE, _P.SPECIFIC_ANIMAL): _S.ANSWERING_PARENTING_STYLE,
    (_S.ANSWERING_ADOPTION_MOTIVATION, _P.SPECIFIC_ANIMAL): _S.ANSWERING_PATIENCE,
    (_S.AWAITING_AI_SUITABILITY, _P.SPECIFIC_ANIMAL): _S.CONFIRMING_ANSWERS,
    (_S.CONFIRMING_ANSWERS, _P.SPECIFIC_ANIMAL): _S.ANSWERING_ADOPTION_MOTIVATION,
    (_S.SELECTING_ALTERNATIVE_ANIMAL, _P.SPECIFIC_ANIMAL): _S.AWAITING_AI_SUITABILITY,
    (_S.CONFIRMING_ALTERNATIVE_ANIMAL, _P.SPECIFIC_ANIMAL): _S.SELECTING_ALTERNATIVE_ANIMAL,
    (_S.AWAITING_ADOPTER_NAME, _P.SPECIFIC_ANIMAL): _S.AWAITING_AI_SUITABILITY,
    (_S.ANSWERING_PREFERENCE_HOUSING, _P.RECOMMEND_ME): _S.AWAITING_FREETEXT_PROFILE,
    (_S.ANSWERING_PREFERENCE_EXPERIENCE, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_HOUSING,
    (_S.ANSWERING_PREFERENCE_OTHER_PETS, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_EXPERIENCE,
    (_S.ANSWERING_PREFERENCE_HOUSEHOLD, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_OTHER_PETS,
    (_S.ANSWERING_PREFERENCE_SCHEDULE, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_HOUSEHOLD,
    (_S.ANSWERING_PREFERENCE_PARENTING_STYLE, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_SCHEDULE,
    (_S.ANSWERING_PREFERENCE_PATIENCE, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_PARENTING_STYLE,
    (
        _S.ANSWERING_PREFERENCE_ADOPTION_MOTIVATION,
        _P.RECOMMEND_ME,
    ): _S.ANSWERING_PREFERENCE_PATIENCE,
    (_S.ANSWERING_PREFERENCE_SIZE, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_ADOPTION_MOTIVATION,
    (_S.ANSWERING_PREFERENCE_ENERGY, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_SIZE,
    (_S.PRESENTING_MATCHES, _P.RECOMMEND_ME): _S.ANSWERING_PREFERENCE_ENERGY,
    (_S.AWAITING_AI_RECOMMENDATIONS, _P.RECOMMEND_ME): _S.PRESENTING_MATCHES,
    (_S.SELECTING_MATCHED_ANIMAL, _P.RECOMMEND_ME): _S.AWAITING_AI_RECOMMENDATIONS,
    (_S.CONFIRMING_TARGET_ANIMAL, _P.RECOMMEND_ME): _S.SELECTING_MATCHED_ANIMAL,
    (_S.AWAITING_ADOPTER_NAME, _P.RECOMMEND_ME): _S.CONFIRMING_TARGET_ANIMAL,
    (_S.AWAITING_CONTACT_TIME, None): _S.AWAITING_ADOPTER_NAME,
    (_S.AWAITING_PHONE_NUMBER, None): _S.AWAITING_CONTACT_TIME,
    (_S.REVIEWING, None): _S.AWAITING_PHONE_NUMBER,
    (_S.SUBMITTING, None): _S.REVIEWING,
}

# Question-bearing states only; states that merely pick/confirm an animal carry no
# `answers` entry of their own (the target animal id lives on the persistence row).
_STATE_QUESTIONS: dict[AdoptionDraftState, tuple[str, ...]] = {
    _S.ANSWERING_PREFERENCE_HOUSING: ("housing_type",),
    _S.ANSWERING_PREFERENCE_EXPERIENCE: ("dog_experience",),
    _S.ANSWERING_PREFERENCE_OTHER_PETS: ("other_pets",),
    _S.ANSWERING_PREFERENCE_HOUSEHOLD: ("household_members",),
    _S.ANSWERING_PREFERENCE_SCHEDULE: ("work_schedule",),
    _S.ANSWERING_PREFERENCE_PARENTING_STYLE: ("parenting_style",),
    _S.ANSWERING_PREFERENCE_PATIENCE: ("patience_level",),
    _S.ANSWERING_PREFERENCE_ADOPTION_MOTIVATION: ("adoption_motivation",),
    _S.ANSWERING_PREFERENCE_SIZE: ("preferred_size",),
    _S.ANSWERING_PREFERENCE_ENERGY: ("preferred_energy",),
    _S.ANSWERING_HOUSING: ("housing_type",),
    _S.ANSWERING_EXPERIENCE: ("dog_experience",),
    _S.ANSWERING_OTHER_PETS: ("other_pets",),
    _S.ANSWERING_HOUSEHOLD: ("household_members",),
    _S.ANSWERING_SCHEDULE: ("work_schedule",),
    _S.ANSWERING_PARENTING_STYLE: ("parenting_style",),
    _S.ANSWERING_PATIENCE: ("patience_level",),
    _S.ANSWERING_ADOPTION_MOTIVATION: ("adoption_motivation",),
    _S.AWAITING_ADOPTER_NAME: ("adopter_name",),
    _S.AWAITING_CONTACT_TIME: ("contact_time",),
    _S.AWAITING_PHONE_NUMBER: ("phone_number",),
}

# Used by back() to know which subsequent answers to purge, per path.
_STATE_ORDER_BY_PATH: dict[AdoptionPath, tuple[AdoptionDraftState, ...]] = {
    _P.SPECIFIC_ANIMAL: (
        _S.AWAITING_FREETEXT_PROFILE,
        _S.ANSWERING_HOUSING,
        _S.ANSWERING_EXPERIENCE,
        _S.ANSWERING_OTHER_PETS,
        _S.ANSWERING_HOUSEHOLD,
        _S.ANSWERING_SCHEDULE,
        _S.ANSWERING_PARENTING_STYLE,
        _S.ANSWERING_PATIENCE,
        _S.ANSWERING_ADOPTION_MOTIVATION,
        _S.CONFIRMING_ANSWERS,
        _S.AWAITING_AI_SUITABILITY,
        _S.AWAITING_ADOPTER_NAME,
        _S.AWAITING_CONTACT_TIME,
        _S.AWAITING_PHONE_NUMBER,
    ),
    _P.RECOMMEND_ME: (
        _S.AWAITING_FREETEXT_PROFILE,
        _S.ANSWERING_PREFERENCE_HOUSING,
        _S.ANSWERING_PREFERENCE_EXPERIENCE,
        _S.ANSWERING_PREFERENCE_OTHER_PETS,
        _S.ANSWERING_PREFERENCE_HOUSEHOLD,
        _S.ANSWERING_PREFERENCE_SCHEDULE,
        _S.ANSWERING_PREFERENCE_PARENTING_STYLE,
        _S.ANSWERING_PREFERENCE_PATIENCE,
        _S.ANSWERING_PREFERENCE_ADOPTION_MOTIVATION,
        _S.ANSWERING_PREFERENCE_SIZE,
        _S.ANSWERING_PREFERENCE_ENERGY,
        _S.AWAITING_ADOPTER_NAME,
        _S.AWAITING_CONTACT_TIME,
        _S.AWAITING_PHONE_NUMBER,
    ),
}


def _resolve(
    table: dict[tuple[AdoptionDraftState, AdoptionPath | None], AdoptionDraftState],
    state: AdoptionDraftState,
    path: AdoptionPath | None,
) -> AdoptionDraftState | None:
    if path is not None and (state, path) in table:
        return table[(state, path)]
    return table.get((state, None))


def can_go_back(state: AdoptionDraftState, path: AdoptionPath | None) -> bool:
    """Whether `AdoptionDraftStateMachine(state=state, path=path).back()`
    would succeed from here — lets a caller (line_webhook.py deciding
    whether to offer a "回到上一頁" quick-reply) check this without
    triggering back()'s own DomainError as a control-flow signal. Only
    SELECTING_ORGANIZATION (the very first step) has no previous state."""
    return _resolve(_PREVIOUS_STATE, state, path) is not None


def _validate_phone_number(value: Any) -> None:
    if not isinstance(value, str) or not PHONE_NUMBER_PATTERN.match(value):
        raise DomainError("invalid_phone_number", "請輸入 10 碼台灣手機號碼，例如 0912345678", 422)


@dataclass
class AdoptionDraftAnswers:
    """部分答案；草稿可以缺少任何必要題目。"""

    values: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        if key not in ALL_ANSWER_KEYS:
            raise DomainError("invalid_answer_key", f"不支援的領養問卷答案：{key}", 422)
        if value is None or value == "":
            raise DomainError("invalid_answer_value", f"領養問卷答案不可為空：{key}", 422)
        if key == "phone_number":
            _validate_phone_number(value)
        if key in {"adopter_name", "contact_time"} and len(str(value)) > 100:
            raise DomainError("invalid_answer_value", f"欄位內容過長：{key}", 422)
        self.values[key] = value

    def missing(self, path: AdoptionPath | None) -> list[str]:
        if path is None:
            return list(ALL_ANSWER_KEYS)
        return [key for key in REQUIRED_KEYS_BY_PATH[path] if key not in self.values]

    def complete(self, path: AdoptionPath | None) -> bool:
        return not self.missing(path)


@dataclass(frozen=True)
class AdoptionInquiryAnswers:
    path: AdoptionPath
    values: dict[str, Any]

    def __post_init__(self) -> None:
        missing = [key for key in REQUIRED_KEYS_BY_PATH[self.path] if key not in self.values]
        if missing:
            raise DomainError(
                "incomplete_answers", f"缺少必要領養問卷答案：{', '.join(missing)}", 422
            )
        _validate_phone_number(self.values["phone_number"])


@dataclass
class AdoptionDraftStateMachine:
    state: AdoptionDraftState = AdoptionDraftState.SELECTING_ORGANIZATION
    path: AdoptionPath | None = None
    answers: AdoptionDraftAnswers = field(default_factory=AdoptionDraftAnswers)
    reconfirmation_keys: set[str] = field(default_factory=set)
    last_interaction_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # How many AWAITING_FREETEXT_PROFILE rounds have been consumed — see
    # AWAITING_FREETEXT_PROFILE_MAX_ROUNDS.
    freetext_profile_rounds: int = 0

    def transition(self, target: AdoptionDraftState, *, path: AdoptionPath | None = None) -> None:
        if target in {AdoptionDraftState.CANCELLED, AdoptionDraftState.EXPIRED}:
            if self.state in {
                AdoptionDraftState.SUBMITTED,
                AdoptionDraftState.CANCELLED,
                AdoptionDraftState.EXPIRED,
            }:
                raise DomainError("invalid_state_transition", "草稿目前狀態不可取消或過期", 409)
            self.state = target
            return
        if self.state in {
            AdoptionDraftState.CANCELLED,
            AdoptionDraftState.EXPIRED,
            AdoptionDraftState.SUBMITTED,
        }:
            raise DomainError("invalid_state_transition", "草稿已結束，不能再次操作", 409)
        if self.state == AdoptionDraftState.CHOOSING_PATH:
            if path is None:
                raise DomainError("path_required", "選擇領養方式時必須指定路徑", 422)
            expected = _NEXT_STATES.get((self.state, path))
        else:
            expected = _resolve(_NEXT_STATES, self.state, self.path)
        if expected != target:
            raise DomainError("invalid_state_transition", "不允許的草稿狀態轉移", 409)
        if target in {
            AdoptionDraftState.REVIEWING,
            AdoptionDraftState.SUBMITTING,
        } and not self.answers.complete(self.path):
            raise DomainError("incomplete_answers", "完成領養問卷後才能進入確認或送出", 422)
        if self.state == AdoptionDraftState.CHOOSING_PATH:
            self.path = path
        self.state = target
        self.last_interaction_at = datetime.now(timezone.utc)

    def choose_path(self, path: AdoptionPath) -> AdoptionDraftState:
        """Resolve and perform the one branching transition out of CHOOSING_PATH."""
        target = _NEXT_STATES.get((AdoptionDraftState.CHOOSING_PATH, path))
        if target is None:
            raise DomainError("invalid_state_transition", "不允許的草稿狀態轉移", 409)
        self.transition(target, path=path)
        return self.state

    def advance(self) -> AdoptionDraftState:
        """Move to the single well-defined next state; use when no extra input
        (an answer value, a chosen path) is needed to know where to go next."""
        next_state = _resolve(_NEXT_STATES, self.state, self.path)
        if next_state is None:
            raise DomainError("invalid_state_transition", "不允許的草稿狀態轉移", 409)
        self.transition(next_state)
        return self.state

    def skip_prefilled_questions(self) -> AdoptionDraftState:
        """Auto-advances through any question-bearing state (ANSWERING_*)
        whose answer(s) already exist — e.g. pre-filled by extracting a
        free-text self-introduction via AWAITING_FREETEXT_PROFILE — landing
        on the first state that still genuinely needs an answer, or on
        whatever non-question state the walk naturally reaches (CONFIRMING_
        ANSWERS, PRESENTING_MATCHES) once everything is filled. Stops at any
        state outside `_STATE_QUESTIONS` without crossing it, since those
        (PRESENTING_MATCHES in particular) carry their own side effects the
        caller is responsible for triggering, not a plain answer to skip
        past."""
        while True:
            expected = _STATE_QUESTIONS.get(self.state)
            if expected is None:
                return self.state
            if not all(item in self.answers.values for item in expected):
                return self.state
            next_state = _resolve(_NEXT_STATES, self.state, self.path)
            if next_state is None:
                return self.state
            self.transition(next_state)

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

    def prepare_answer_replay(self, key: str) -> bool:
        """Allow a saved answer to be safely confirmed again on its own step.

        Older concurrent webhook handling could persist an answer while leaving
        ``current_step`` on the same question.  Treating the matching card click
        as reconfirmation lets the normal answer transition repair that draft.
        """
        expected = _STATE_QUESTIONS.get(self.state)
        if expected is None or key not in expected:
            return False
        if key in self.answers.values:
            self.reconfirmation_keys.add(key)
        return True

    def answer_current(self, value: Any) -> AdoptionDraftState:
        return self.answer_question(self.next_answer_key(), value)

    def answer_question(self, key: str, value: Any) -> AdoptionDraftState:
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
            next_state = _resolve(_NEXT_STATES, self.state, self.path)
            if next_state is None:
                raise DomainError("invalid_state_transition", "不允許的草稿狀態轉移", 409)
            self.transition(next_state)
        return self.state

    def back(self) -> AdoptionDraftState:
        """回到前一個可操作步驟，並清除該步驟及其後的答案。"""
        previous = _resolve(_PREVIOUS_STATE, self.state, self.path)
        if previous is None:
            raise DomainError("invalid_state_transition", "目前步驟不能返回上一步", 409)
        order = _STATE_ORDER_BY_PATH.get(self.path) if self.path else None
        if order and previous in order:
            previous_index = order.index(previous)
            keys_to_clear = {
                key for state in order[previous_index:] for key in _STATE_QUESTIONS.get(state, ())
            }
            for key in keys_to_clear:
                self.answers.values.pop(key, None)
        if previous == AdoptionDraftState.CHOOSING_PATH:
            self.path = None
        self.state = previous
        self.last_interaction_at = datetime.now(timezone.utc)
        return self.state

    def repair_to_first_missing(self, required_keys: tuple[str, ...]) -> str | None:
        """Move an inconsistent legacy draft to its first missing question."""
        if self.path is None:
            return None
        missing = next((key for key in required_keys if key not in self.answers.values), None)
        if missing is None:
            return None
        order = _STATE_ORDER_BY_PATH[self.path]
        target = next(
            (state for state in order if missing in _STATE_QUESTIONS.get(state, ())),
            None,
        )
        if target is None:
            raise DomainError("invalid_state_transition", "找不到需要補填的問卷題目", 409)
        self.state = target
        self.reconfirmation_keys.discard(missing)
        self.last_interaction_at = datetime.now(timezone.utc)
        return missing

    def repair_for_resume(self) -> str | None:
        """Validate answers that must exist before the saved current step."""
        if self.path is None:
            return None
        order = _STATE_ORDER_BY_PATH[self.path]
        if self.state in order:
            required = tuple(
                key
                for state in order[: order.index(self.state)]
                for key in _STATE_QUESTIONS.get(state, ())
            )
        elif self.state in {
            _S.CONFIRMING_ANSWERS,
            _S.AWAITING_AI_SUITABILITY,
            _S.SELECTING_ALTERNATIVE_ANIMAL,
            _S.CONFIRMING_ALTERNATIVE_ANIMAL,
        }:
            required = BASE_PREFERENCE_KEYS
        elif self.state in {
            _S.PRESENTING_MATCHES,
            _S.AWAITING_AI_RECOMMENDATIONS,
            _S.SELECTING_MATCHED_ANIMAL,
        }:
            required = MATCH_PREFERENCE_KEYS
        elif self.state in {_S.REVIEWING, _S.SUBMITTING}:
            required = REQUIRED_KEYS_BY_PATH[self.path]
        else:
            return None
        return self.repair_to_first_missing(required)

    def edit_contact(self, key: str) -> None:
        if self.state != _S.REVIEWING or key not in CONTACT_EDIT_STATES.values():
            raise DomainError("invalid_contact_edit", "請從領養意願摘要選擇要修改的聯絡資料", 409)
        self.state = next(state for state, field in CONTACT_EDIT_STATES.items() if field == key)

    def save_contact(self, value: str) -> None:
        key = CONTACT_EDIT_STATES.get(self.state)
        if key is None:
            raise DomainError("invalid_contact_edit", "目前沒有正在修改的聯絡資料", 409)
        clean = value.strip()
        if not clean or len(clean) > 100:
            raise DomainError("invalid_contact_value", "請輸入 1 至 100 字的聯絡資料", 422)
        self.answers.set(key, clean)
        self.state = _S.REVIEWING
        self.last_interaction_at = datetime.now(timezone.utc)

    def cancel_contact_edit(self) -> None:
        if self.state not in CONTACT_EDIT_STATES:
            raise DomainError("invalid_contact_edit", "目前沒有正在修改的聯絡資料", 409)
        self.state = _S.REVIEWING

    def submit(self) -> AdoptionInquiryAnswers:
        if self.state != AdoptionDraftState.SUBMITTING:
            raise DomainError("invalid_state_transition", "草稿尚未進入送出狀態", 409)
        if self.path is None:
            raise DomainError("invalid_state_transition", "草稿尚未選擇領養方式", 409)
        result = AdoptionInquiryAnswers(path=self.path, values=dict(self.answers.values))
        self.state = AdoptionDraftState.SUBMITTED
        return result
