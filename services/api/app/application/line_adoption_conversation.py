from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.adoption_inquiry_submission import (
    AdoptionInquirySubmissionService,
)
from services.api.app.application.adoption_matching_service import AdoptionMatchingService
from services.api.app.application.audit_service import AuditService
from services.api.app.domain.adoption_matching import AdopterPreferences, MatchScore
from services.api.app.domain.line_adoption_state import (
    AWAITING_FREETEXT_PROFILE_MAX_ROUNDS,
    REQUIRED_KEYS_BY_PATH,
    AdoptionDraftAnswers,
    AdoptionDraftState,
    AdoptionDraftStateMachine,
    AdoptionPath,
)
from services.api.app.persistence.repositories.adoption_draft_repository import (
    AdoptionDraftRepository,
)
from services.api.app.persistence.repositories.adoption_inquiry_repository import (
    AdoptionInquiryRepository,
)
from services.api.app.persistence.repositories.animal_repository import AnimalRepository


@dataclass(frozen=True)
class AdoptionConversationResult:
    state: AdoptionDraftState
    inquiry_id: UUID | None = None
    candidate_match_ids: tuple[UUID, ...] = ()
    # True only on the one `handle()` call whose action actually transitions
    # the draft INTO AWAITING_AI_SUITABILITY — not on every subsequent
    # redisplay (e.g. re-tapping the rich menu resumes an existing draft
    # already sitting in that state). The AI suitability analysis background
    # task keys off this edge so it fires exactly once per draft.
    entered_awaiting_ai_suitability: bool = False
    # Same idea, for the recommend_me path's AI-curated recommendation list.
    entered_awaiting_ai_recommendations: bool = False


class LineAdoptionConversationService:
    """在 AdoptionDraft 上執行 Bot 對話，不信任 Postback 的 step 或權限欄位。"""

    def __init__(
        self,
        draft_repository: AdoptionDraftRepository,
        *,
        organization_validator: Callable[[UUID], Awaitable[bool]] | None = None,
        answer_validator: Callable[[str, str], None] | None = None,
        match_top_n: int = 3,
    ) -> None:
        self.draft_repository = draft_repository
        self.organization_validator = organization_validator
        self.answer_validator = answer_validator
        self.match_top_n = match_top_n

    async def handle(
        self,
        *,
        token: str | None,
        adopter_user_id: UUID,
        action: str,
        value: str | None,
        event_id: str,
    ) -> AdoptionConversationResult:
        draft = (
            await self.draft_repository.get_by_token(token)
            if token
            else await self.draft_repository.get_active_for_adopter(adopter_user_id)
        )
        if draft is None or draft.adopter_user_id != adopter_user_id or draft.status != "active":
            raise DomainError("draft_access_denied", "對話不存在或無法存取", 404)
        if draft.expires_at <= datetime.now(timezone.utc):
            draft.status = "expired"
            draft.current_step = AdoptionDraftState.EXPIRED.value
            raise DomainError("draft_expired", "對話已過期", 409)

        initial_state = AdoptionDraftState(draft.current_step)
        machine = AdoptionDraftStateMachine(
            state=initial_state,
            path=AdoptionPath(draft.path) if draft.path else None,
            answers=AdoptionDraftAnswers(dict(draft.answers)),
            reconfirmation_keys=set(draft.reconfirmation_keys or []),
            freetext_profile_rounds=draft.freetext_profile_rounds or 0,
        )
        inquiry_id: UUID | None = None
        session = self.draft_repository.session

        if action == "select_organization":
            organization_id = _require_uuid(value, "organization_id_required", "需要選擇收容所")
            if draft.organization_id is not None:
                raise DomainError("organization_already_selected", "已經選擇過收容所", 409)
            if self.organization_validator is not None and not await self.organization_validator(
                organization_id
            ):
                raise DomainError("organization_not_available", "該收容所目前無法領養媒合", 404)
            draft.organization_id = organization_id
            machine.advance()
        elif action == "choose_path":
            if value not in {path.value for path in AdoptionPath}:
                raise DomainError("invalid_path", "需要選擇有效的領養方式", 422)
            # Idempotent against a duplicate tap on the same path choice —
            # e.g. LINE redelivering the postback, or the adopter tapping
            # again before the first reply rendered. choose_path() only
            # knows how to fire from CHOOSING_PATH itself; a second call
            # after the draft has already moved on would otherwise hit
            # transition()'s generic "不允許的草稿狀態轉移" even though the
            # adopter's actual intent (go down this path) is already
            # satisfied. Choosing a genuinely different path after one is
            # already committed is still rejected, same as before.
            already_on_this_path = (
                machine.state != AdoptionDraftState.CHOOSING_PATH
                and machine.path == AdoptionPath(value)
            )
            if not already_on_this_path:
                machine.choose_path(AdoptionPath(value))
                draft.path = machine.path.value if machine.path else None
        elif action == "select_target_animal":
            animal_id = _require_uuid(value, "animal_id_required", "需要選擇動物")
            animal = await AnimalRepository(session, draft.organization_id).get(animal_id)
            if animal is None or not animal.is_adoptable or animal.status != "active":
                raise DomainError("animal_not_adoptable", "動物不存在或目前不可領養", 404)
            draft.target_animal_id = animal_id
            machine.advance()
        elif action == "confirm_target_animal":
            machine.advance()
        elif action == "finish_freetext_profile":
            # The adopter explicitly opts out of typing any more free-text
            # supplements (see AWAITING_FREETEXT_PROFILE_MAX_ROUNDS for the
            # other way this same fallback triggers) — whatever's still
            # missing gets asked one question at a time from here.
            if machine.state != AdoptionDraftState.AWAITING_FREETEXT_PROFILE:
                raise DomainError("invalid_state_transition", "目前步驟不接受這個操作", 409)
            await self._leave_freetext_profile(session, draft, machine)
        elif action == "confirm_answers":
            machine.advance()
        elif action == "select_matched_animal":
            animal_id = _require_uuid(value, "animal_id_required", "需要選擇動物")
            if str(animal_id) not in (draft.candidate_match_ids or []):
                raise DomainError("animal_not_offered", "請從系統推薦的動物中選擇", 409)
            draft.target_animal_id = animal_id
            machine.advance()
        elif action == "select_alternative_animal":
            # 心有所屬・AI 適配度 <60% 後的替代名單 —「維持這隻」也是候選之一
            # （見 _run_adoption_ai_followup_recommendations），一樣要先選再
            # 確認，才會進入留下聯絡方式。
            animal_id = _require_uuid(value, "animal_id_required", "需要選擇動物")
            if str(animal_id) not in (draft.candidate_match_ids or []):
                raise DomainError("animal_not_offered", "請從系統推薦的動物中選擇", 409)
            draft.target_animal_id = animal_id
            machine.advance()
        elif action == "confirm_alternative_animal":
            machine.advance()
        elif action == "answer":
            if value is None:
                raise DomainError("answer_required", "需要回答問卷問題", 422)
            # Idempotent against a duplicate tap that arrives after the
            # question it was meant for has already been answered — e.g.
            # two near-simultaneous taps on the same quick-reply button, now
            # safely serialized (not corrupting each other) by
            # AdoptionDraftRepository's FOR UPDATE lock rather than racing,
            # but the second one would otherwise still hit next_answer_key()'s
            # "目前步驟已完成"/"目前步驟不接受答案" even though the adopter's
            # answer already landed. skip_prefilled_questions() is a no-op
            # everywhere a question is genuinely still pending, so this costs
            # nothing in the normal case — see choose_path's matching guard
            # above for the same idea applied to that action.
            state_before_skip = machine.state
            machine.skip_prefilled_questions()
            advanced_past_a_stale_question = machine.state != state_before_skip
            try:
                next_key = machine.next_answer_key()
            except DomainError as error:
                if error.code != "invalid_state_transition":
                    raise
                new_state = machine.state
            else:
                try:
                    if self.answer_validator is not None:
                        self.answer_validator(next_key, value)
                    new_state = machine.answer_current(value)
                except DomainError as error:
                    # Same idempotency idea, one step further: the question
                    # this tap was actually meant for turned out to already
                    # be answered elsewhere (free-text extraction, or a
                    # duplicate tap that won the race) — skip_prefilled_
                    # questions() above moved on to a *different*, genuinely
                    # still-pending question, so the tapped value naturally
                    # doesn't match its options. Nothing to apply; let the
                    # caller re-render wherever the draft actually is now.
                    if error.code != "invalid_answer_value" or not advanced_past_a_stale_question:
                        raise
                    new_state = machine.state
            if new_state == AdoptionDraftState.PRESENTING_MATCHES:
                # top_n is wider than the 3-5 finally shown — this is just the
                # rule-based candidate pool that AI reranks in the background
                # (see _run_adoption_ai_recommendation_curation) before the
                # adopter ever sees it.
                matches = await self._compute_matches(session, draft.organization_id, machine)
                draft.candidate_match_ids = [str(match.animal_id) for match in matches]
                draft.match_results = [_match_result(match) for match in matches]
                # PRESENTING_MATCHES is a system-computed interstitial, not a
                # step that waits for input; move straight into
                # AWAITING_AI_RECOMMENDATIONS to await the background AI task.
                machine.advance()
            elif (
                new_state == AdoptionDraftState.CONFIRMING_ANSWERS
                and machine.path == AdoptionPath.SPECIFIC_ANIMAL
                and draft.target_animal_id is not None
            ):
                # The specific_animal path never ranks a candidate pool, but it
                # asks the same preference questions after confirming the
                # target — score that one animal now that the answers exist.
                match = await AdoptionMatchingService(session, draft.organization_id).score_target(
                    draft.target_animal_id, self._preferences_from_answers(machine.answers.values)
                )
                draft.match_results = [_match_result(match)] if match is not None else []
        elif action == "phone_number":
            if value is None:
                raise DomainError("phone_number_required", "需要提供手機號碼", 422)
            machine.answer_question("phone_number", value)
        elif action == "back":
            machine.back()
            if machine.path is None:
                draft.path = None
                draft.target_animal_id = None
                draft.candidate_match_ids = []
                draft.match_results = []
            if machine.state == AdoptionDraftState.SELECTING_ORGANIZATION:
                # organization_id lives on the draft row, not inside the
                # state machine, so it isn't cleared by machine.back() on its
                # own — without this, re-picking a shelter after backing all
                # the way out hits "already selected" (see 心有所屬 testing
                # notes: 返回地區選單 → pick a shelter → organization_already_selected).
                draft.organization_id = None
        elif action in {"submit", "submit_current"}:
            machine.transition(AdoptionDraftState.SUBMITTING)
            answers = machine.submit()
            if draft.target_animal_id is None:
                raise DomainError("target_animal_required", "尚未選擇要領養的動物", 409)
            animal = await AnimalRepository(session, draft.organization_id).get(
                draft.target_animal_id
            )
            if animal is None:
                raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
            # 推薦名單 only — see AdoptionInquiry.ai_recommendation_overridden.
            # candidate_match_ids is whatever the AI last curated; if the
            # final target isn't in it, the adopter went looking beyond the
            # recommendations (see "browse_all_animals").
            overridden = (
                str(draft.target_animal_id) not in (draft.candidate_match_ids or [])
                if machine.path == AdoptionPath.RECOMMEND_ME
                else None
            )
            inquiry = await AdoptionInquirySubmissionService(
                AdoptionInquiryRepository(session, draft.organization_id),
                audit=AuditService(session),
            ).submit(
                draft=draft,
                animal=animal,
                answers=answers,
                match_scores_snapshot=(draft.match_results or None),
                ai_recommendation_overridden=overridden,
            )
            inquiry_id = inquiry.id
        elif action in {"cancel", "cancel_current"}:
            machine.transition(AdoptionDraftState.CANCELLED)
        else:
            raise DomainError("invalid_postback_action", "目前步驟不允許此操作", 409)

        draft.answers = dict(machine.answers.values)
        draft.reconfirmation_keys = sorted(machine.reconfirmation_keys)
        draft.freetext_profile_rounds = machine.freetext_profile_rounds
        draft.current_step = machine.state.value
        if machine.state == AdoptionDraftState.SUBMITTED:
            draft.status = "submitted"
        elif machine.state == AdoptionDraftState.CANCELLED:
            draft.status = "cancelled"
        elif machine.state == AdoptionDraftState.EXPIRED:
            draft.status = "expired"
        draft.last_interaction_at = datetime.now(timezone.utc)
        await session.flush()
        return AdoptionConversationResult(
            state=machine.state,
            inquiry_id=inquiry_id,
            candidate_match_ids=tuple(UUID(item) for item in draft.candidate_match_ids or []),
            entered_awaiting_ai_suitability=(
                initial_state != AdoptionDraftState.AWAITING_AI_SUITABILITY
                and machine.state == AdoptionDraftState.AWAITING_AI_SUITABILITY
            ),
            entered_awaiting_ai_recommendations=(
                initial_state != AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS
                and machine.state == AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS
            ),
        )

    async def apply_freetext_answers(
        self, *, adopter_user_id: UUID, extracted: dict[str, str]
    ) -> AdoptionConversationResult:
        """Merges one round of AI-extracted answers (from a free-text self-
        introduction — see line_webhook.py's _run_adoption_profile_extraction)
        into the draft. Runs outside `handle()`'s action dispatch, the same
        way an AI background task writes `current_step` directly elsewhere in
        this feature, since nothing about it comes from a postback/text
        action a human tapped or typed literally matching one of the cases
        below. Unrecognised keys/values are dropped rather than trusted —
        the caller already validates against the known option codes before
        calling this, but this stays defensive as the last line of defence
        before something bad lands in `draft.answers`.

        Stays in AWAITING_FREETEXT_PROFILE for another round if answers are
        still incomplete and AWAITING_FREETEXT_PROFILE_MAX_ROUNDS hasn't been
        used up yet; otherwise falls through to the one-question-at-a-time
        flow for whatever's left, same as the explicit
        "finish_freetext_profile" action.
        """
        draft = await self.draft_repository.get_active_for_adopter(adopter_user_id)
        if draft is None or draft.status != "active":
            raise DomainError("draft_access_denied", "對話不存在或無法存取", 404)
        initial_state = AdoptionDraftState(draft.current_step)
        if initial_state != AdoptionDraftState.AWAITING_FREETEXT_PROFILE:
            raise DomainError("invalid_state_transition", "目前步驟不接受這個操作", 409)
        machine = AdoptionDraftStateMachine(
            state=initial_state,
            path=AdoptionPath(draft.path) if draft.path else None,
            answers=AdoptionDraftAnswers(dict(draft.answers)),
            reconfirmation_keys=set(draft.reconfirmation_keys or []),
            freetext_profile_rounds=draft.freetext_profile_rounds or 0,
        )
        session = self.draft_repository.session
        valid_keys = set(REQUIRED_KEYS_BY_PATH[machine.path]) if machine.path else set()
        for key, value in extracted.items():
            if key in valid_keys and value:
                try:
                    machine.answers.set(key, value)
                except DomainError:
                    continue
        machine.freetext_profile_rounds += 1
        out_of_rounds = machine.freetext_profile_rounds >= AWAITING_FREETEXT_PROFILE_MAX_ROUNDS
        if machine.answers.complete(machine.path) or out_of_rounds:
            await self._leave_freetext_profile(session, draft, machine)
        draft.answers = dict(machine.answers.values)
        draft.reconfirmation_keys = sorted(machine.reconfirmation_keys)
        draft.freetext_profile_rounds = machine.freetext_profile_rounds
        draft.current_step = machine.state.value
        draft.last_interaction_at = datetime.now(timezone.utc)
        await session.flush()
        return AdoptionConversationResult(
            state=machine.state,
            entered_awaiting_ai_recommendations=(
                machine.state == AdoptionDraftState.AWAITING_AI_RECOMMENDATIONS
            ),
        )

    async def _leave_freetext_profile(
        self, session, draft, machine: AdoptionDraftStateMachine
    ) -> None:
        """Shared by the explicit "finish_freetext_profile" action and
        apply_freetext_answers running out of rounds: advance past
        AWAITING_FREETEXT_PROFILE into the first still-unanswered question
        (skipping whatever free text already covered), replicating whichever
        side effect the normal one-by-one flow would have triggered on
        landing there (recommend_me's rule-based candidate pool, or
        specific_animal's rule-based score for the one already-chosen
        animal) — skip_prefilled_questions() deliberately stops short of
        those states rather than crossing them silently."""
        machine.advance()
        machine.skip_prefilled_questions()
        if machine.state == AdoptionDraftState.PRESENTING_MATCHES:
            matches = await self._compute_matches(session, draft.organization_id, machine)
            draft.candidate_match_ids = [str(match.animal_id) for match in matches]
            draft.match_results = [_match_result(match) for match in matches]
            machine.advance()
        elif (
            machine.state == AdoptionDraftState.CONFIRMING_ANSWERS
            and machine.path == AdoptionPath.SPECIFIC_ANIMAL
            and draft.target_animal_id is not None
        ):
            match = await AdoptionMatchingService(session, draft.organization_id).score_target(
                draft.target_animal_id, self._preferences_from_answers(machine.answers.values)
            )
            draft.match_results = [_match_result(match)] if match is not None else []

    async def _compute_matches(
        self, session, organization_id: UUID, machine: AdoptionDraftStateMachine
    ) -> list[MatchScore]:
        preferences = self._preferences_from_answers(machine.answers.values)
        return await AdoptionMatchingService(session, organization_id).recommend(
            preferences, top_n=self.match_top_n
        )

    @staticmethod
    def _preferences_from_answers(values: dict) -> AdopterPreferences:
        return AdopterPreferences(
            housing_type=values["housing_type"],
            dog_experience=values["dog_experience"],
            other_pets=values["other_pets"],
            household_members=values["household_members"],
            work_schedule=values["work_schedule"],
            preferred_size=values.get("preferred_size"),
            preferred_energy=values.get("preferred_energy"),
        )


def _match_result(match: MatchScore) -> dict:
    return {"animal_id": str(match.animal_id), "score": match.score, "reasons": list(match.reasons)}


def _require_uuid(value: str | None, code: str, message: str) -> UUID:
    if not value:
        raise DomainError(code, message, 422)
    try:
        return UUID(value)
    except ValueError as exc:
        raise DomainError(code, message, 422) from exc
