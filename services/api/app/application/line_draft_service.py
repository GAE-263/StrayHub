from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.domain.line_care_report_state import DraftState
from services.api.app.persistence.models.care_report_draft import CareReportDraft
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)


class DraftSelectionAction(StrEnum):
    CREATED = "created"
    RESUMED = "resumed"
    NEEDS_SWITCH_CONFIRMATION = "needs_switch_confirmation"
    SWITCHED = "switched"


@dataclass(frozen=True)
class DraftSelectionDecision:
    action: DraftSelectionAction
    draft: CareReportDraft
    token: str | None = None
    target_animal_id: UUID | None = None


class LineDraftService:
    def __init__(self, repository: CareReportDraftRepository, *, ttl_seconds: int = 86400) -> None:
        self.repository = repository
        self.ttl_seconds = ttl_seconds

    async def create(
        self,
        *,
        volunteer_user_id: UUID,
        membership_id: UUID,
        animal_id: UUID,
        source_event_id: str | None = None,
    ) -> tuple[CareReportDraft, str]:
        existing = await self.repository.get_active_for_volunteer(volunteer_user_id)
        if existing is not None:
            raise DomainError("active_draft_exists", "已有未完成回報，請先繼續或放棄", 409)
        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        draft = CareReportDraft(
            opaque_token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
            organization_id=self.repository.organization_id,
            volunteer_user_id=volunteer_user_id,
            membership_id=membership_id,
            animal_id=animal_id,
            candidate_animal_id=None,
            current_step=DraftState.CONFIRMING_ANIMAL.value,
            answers={},
            answer_source_event_id=source_event_id,
            modification_summary={},
            reconfirmation_keys=[],
            status="active",
            last_interaction_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        return await self.repository.add(draft), raw_token

    async def begin_reselection(
        self,
        draft_id: UUID,
        *,
        candidate_animal_id: UUID,
        source_event_id: str | None = None,
    ) -> CareReportDraft:
        draft = await self._active(draft_id)
        if candidate_animal_id == draft.animal_id:
            raise DomainError("same_animal", "請選擇不同的動物", 422)
        draft.candidate_animal_id = candidate_animal_id
        draft.answer_source_event_id = source_event_id
        draft.modification_summary = {
            "reselection": True,
            "previous_animal_id": str(draft.animal_id),
            "candidate_animal_id": str(candidate_animal_id),
            "answers_reconfirm": list(draft.reconfirmation_keys or []),
            "media_reused": False,
        }
        draft.current_step = DraftState.CONFIRMING_ANIMAL.value
        draft.last_interaction_at = datetime.now(timezone.utc)
        return draft

    async def select_confirmed_animal(
        self,
        *,
        volunteer_user_id: UUID,
        membership_id: UUID,
        animal_id: UUID,
        confirm_switch: bool = False,
        expected_current_animal_id: UUID | None = None,
        source_event_id: str | None = None,
    ) -> DraftSelectionDecision:
        active = await self.repository.get_active_for_volunteer(volunteer_user_id)
        if active is None:
            draft, token = await self.create(
                volunteer_user_id=volunteer_user_id,
                membership_id=membership_id,
                animal_id=animal_id,
                source_event_id=source_event_id,
            )
            return DraftSelectionDecision(DraftSelectionAction.CREATED, draft, token)
        active = await self._active(active.id)
        if active.animal_id == animal_id:
            active.membership_id = membership_id
            return DraftSelectionDecision(DraftSelectionAction.RESUMED, active)
        if not confirm_switch:
            return DraftSelectionDecision(
                DraftSelectionAction.NEEDS_SWITCH_CONFIRMATION,
                active,
                target_animal_id=animal_id,
            )
        if expected_current_animal_id is None or active.animal_id != expected_current_animal_id:
            raise DomainError("draft_switch_conflict", "回報草稿已變更，請重新確認", 409)
        active.candidate_animal_id = animal_id
        active.membership_id = membership_id
        active.answer_source_event_id = source_event_id
        await self.confirm_reselection(active.id)
        return DraftSelectionDecision(DraftSelectionAction.SWITCHED, active)

    async def select_handoff_animal(
        self,
        *,
        volunteer_user_id: UUID,
        membership_id: UUID,
        animal_id: UUID,
        source_event_id: str | None = None,
    ) -> DraftSelectionDecision:
        """Apply a trusted LIFF handoff without putting its animal in a postback."""
        active = await self.repository.get_active_for_volunteer(volunteer_user_id)
        if active is not None and active.expires_at <= datetime.now(timezone.utc):
            active.status = "expired"
            active.current_step = DraftState.EXPIRED.value
            active = None
        if active is None:
            draft, token = await self.create(
                volunteer_user_id=volunteer_user_id,
                membership_id=membership_id,
                animal_id=animal_id,
                source_event_id=source_event_id,
            )
            return DraftSelectionDecision(DraftSelectionAction.CREATED, draft, token)

        active = await self._active(active.id)
        if active.animal_id == animal_id:
            self._restore_handoff_switch(active)
            active.membership_id = membership_id
            active.answer_source_event_id = source_event_id
            active.last_interaction_at = datetime.now(timezone.utc)
            return DraftSelectionDecision(DraftSelectionAction.RESUMED, active)

        summary = dict(active.modification_summary or {})
        if summary.get("handoff_selection"):
            previous_step = summary.get("handoff_previous_step")
            previous_source_event_id = summary.get("handoff_previous_source_event_id")
            previous_summary = dict(summary.get("handoff_previous_modification_summary") or {})
        else:
            previous_step = active.current_step
            previous_source_event_id = active.answer_source_event_id
            previous_summary = summary
        active.candidate_animal_id = animal_id
        active.membership_id = membership_id
        active.answer_source_event_id = source_event_id
        active.modification_summary = {
            "handoff_selection": True,
            "previous_animal_id": str(active.animal_id),
            "candidate_animal_id": str(animal_id),
            "handoff_previous_step": previous_step,
            "handoff_previous_source_event_id": previous_source_event_id,
            "handoff_previous_modification_summary": previous_summary,
            "answers_reused": True,
            "media_reused": True,
        }
        active.current_step = DraftState.CONFIRMING_ANIMAL.value
        active.last_interaction_at = datetime.now(timezone.utc)
        return DraftSelectionDecision(
            DraftSelectionAction.NEEDS_SWITCH_CONFIRMATION,
            active,
            target_animal_id=animal_id,
        )

    async def confirm_handoff_switch(self, *, volunteer_user_id: UUID) -> CareReportDraft:
        active = await self.repository.get_active_for_volunteer(volunteer_user_id)
        if active is None:
            raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
        active = await self._active(active.id)
        if not (active.modification_summary or {}).get("handoff_selection"):
            raise DomainError("handoff_switch_not_pending", "目前沒有待確認的動物切換", 409)
        return await self.confirm_reselection(active.id)

    async def cancel_handoff_switch(self, *, volunteer_user_id: UUID) -> CareReportDraft:
        active = await self.repository.get_active_for_volunteer(volunteer_user_id)
        if active is None:
            raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
        active = await self._active(active.id)
        if not (active.modification_summary or {}).get("handoff_selection"):
            raise DomainError("handoff_switch_not_pending", "目前沒有待確認的動物切換", 409)
        self._restore_handoff_switch(active)
        active.last_interaction_at = datetime.now(timezone.utc)
        return active

    async def confirm_reselection(self, draft_id: UUID) -> CareReportDraft:
        draft = await self._active(draft_id)
        if draft.candidate_animal_id is None:
            raise DomainError("candidate_animal_required", "尚未選擇要更換的動物", 409)
        draft.animal_id = draft.candidate_animal_id
        draft.candidate_animal_id = None
        clear_media = getattr(self.repository, "clear_media", None)
        if clear_media is not None:
            await clear_media(draft.id)
        draft.answers = {}
        draft.reconfirmation_keys = []
        draft.modification_summary = {
            "reselection": True,
            "answers_reused": False,
            "media_reused": False,
        }
        draft.note = None
        draft.story = None
        draft.current_step = DraftState.ANSWERING_WALK_COMPLETION.value
        draft.last_interaction_at = datetime.now(timezone.utc)
        return draft

    @staticmethod
    def _restore_handoff_switch(draft: CareReportDraft) -> None:
        summary = dict(draft.modification_summary or {})
        if not summary.get("handoff_selection"):
            return
        previous_step = summary.get("handoff_previous_step")
        try:
            restored_step = DraftState(previous_step).value
        except (TypeError, ValueError):
            raise DomainError("draft_switch_conflict", "回報草稿已變更，請重新確認", 409) from None
        draft.candidate_animal_id = None
        draft.answer_source_event_id = summary.get("handoff_previous_source_event_id")
        draft.modification_summary = dict(
            summary.get("handoff_previous_modification_summary") or {}
        )
        draft.current_step = restored_step

    async def resume(self, draft_id: UUID, *, volunteer_user_id: UUID) -> CareReportDraft:
        draft = await self._active(draft_id)
        if draft.volunteer_user_id != volunteer_user_id:
            raise DomainError("draft_access_denied", "草稿不存在或無法存取", 404)
        return draft

    async def cancel(self, draft_id: UUID) -> CareReportDraft:
        draft = await self._active(draft_id)
        draft.status = "cancelled"
        draft.current_step = DraftState.CANCELLED.value
        return draft

    async def expire(self, draft_id: UUID) -> CareReportDraft:
        draft = await self._active(draft_id)
        draft.status = "expired"
        draft.current_step = DraftState.EXPIRED.value
        return draft

    async def _active(self, draft_id: UUID) -> CareReportDraft:
        draft = await self.repository.get(draft_id)
        if draft is None or draft.status != "active":
            raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
        if draft.expires_at <= datetime.now(timezone.utc):
            draft.status = "expired"
            draft.current_step = DraftState.EXPIRED.value
            raise DomainError("draft_expired", "草稿已過期", 409)
        return draft
