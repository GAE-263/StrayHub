from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.domain.line_care_report_state import REQUIRED_ANSWER_KEYS, DraftState
from services.api.app.persistence.models.care_report_draft import CareReportDraft
from services.api.app.persistence.repositories.care_report_draft_repository import (
    CareReportDraftRepository,
)


class LineDraftService:
    def __init__(self, repository: CareReportDraftRepository, *, ttl_seconds: int = 86400) -> None:
        self.repository = repository
        self.ttl_seconds = ttl_seconds

    async def create(
        self, *, volunteer_user_id: UUID, membership_id: UUID, animal_id: UUID
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
            reconfirmation_keys=[],
            status="active",
            last_interaction_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        return await self.repository.add(draft), raw_token

    async def begin_reselection(
        self, draft_id: UUID, *, candidate_animal_id: UUID
    ) -> CareReportDraft:
        draft = await self._active(draft_id)
        if candidate_animal_id == draft.animal_id:
            raise DomainError("same_animal", "請選擇不同的動物", 422)
        draft.candidate_animal_id = candidate_animal_id
        draft.current_step = DraftState.CONFIRMING_ANIMAL.value
        draft.last_interaction_at = datetime.now(timezone.utc)
        return draft

    async def confirm_reselection(self, draft_id: UUID) -> CareReportDraft:
        draft = await self._active(draft_id)
        if draft.candidate_animal_id is None:
            raise DomainError("candidate_animal_required", "尚未選擇要更換的動物", 409)
        draft.animal_id = draft.candidate_animal_id
        draft.candidate_animal_id = None
        draft.reconfirmation_keys = [
            key for key in REQUIRED_ANSWER_KEYS if key in (draft.answers or {})
        ]
        draft.current_step = DraftState.ANSWERING_COMPLETION.value
        draft.last_interaction_at = datetime.now(timezone.utc)
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
