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
        expected_question: str | None = None,
        expected_version: int | None = None,
    ) -> AdoptionConversationResult:
        draft = (
            await self.draft_repository.lock_by_token(token)
            if token
            else await self.draft_repository.lock_active_for_adopter(adopter_user_id)
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
        )
        inquiry_id: UUID | None = None
        session = self.draft_repository.session

        if expected_version is not None and expected_version != draft.interaction_version:
            raise DomainError("stale_adoption_action", "這個選項已經處理過，已顯示目前題目。", 409)
        if action == "answer" and expected_question is not None:
            if expected_question != machine.next_answer_key():
                raise DomainError(
                    "stale_adoption_action", "這個選項已經處理過，已顯示目前題目。", 409
                )

        if action == "edit_contact":
            machine.edit_contact(value or "")
        elif action == "save_contact":
            machine.save_contact(value or "")
        elif action == "cancel_contact_edit":
            machine.cancel_contact_edit()
        elif action == "select_organization":
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
            animal = await AnimalRepository(session, draft.organization_id).get(
                draft.target_animal_id
            )
            if animal is None or not animal.is_adoptable or animal.status != "active":
                raise DomainError(
                    "animal_not_adoptable", "這隻動物目前無法領養，請按重新選擇。", 409
                )
            machine.advance()
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
            if self.answer_validator is not None:
                self.answer_validator(machine.next_answer_key(), value)
            new_state = machine.answer_current(value)
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
            inquiry = await AdoptionInquirySubmissionService(
                AdoptionInquiryRepository(session, draft.organization_id),
                audit=AuditService(session),
            ).submit(
                draft=draft,
                animal=animal,
                answers=answers,
                match_scores_snapshot=(draft.match_results or None),
            )
            inquiry_id = inquiry.id
        elif action in {"cancel", "cancel_current"}:
            machine.transition(AdoptionDraftState.CANCELLED)
        else:
            raise DomainError("invalid_postback_action", "目前步驟不允許此操作", 409)

        draft.answers = dict(machine.answers.values)
        draft.reconfirmation_keys = sorted(machine.reconfirmation_keys)
        draft.current_step = machine.state.value
        if machine.state == AdoptionDraftState.SUBMITTED:
            draft.status = "submitted"
        elif machine.state == AdoptionDraftState.CANCELLED:
            draft.status = "cancelled"
        elif machine.state == AdoptionDraftState.EXPIRED:
            draft.status = "expired"
        draft.last_interaction_at = datetime.now(timezone.utc)
        draft.interaction_version += 1
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
