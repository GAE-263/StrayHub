from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.domain.line_adoption_state import AdoptionDraftState
from services.api.app.persistence.models.adoption_draft import AdoptionDraft
from services.api.app.persistence.repositories.adoption_draft_repository import (
    AdoptionDraftRepository,
    adoption_draft_token_digest,
)


class LineAdoptionDraftService:
    def __init__(self, repository: AdoptionDraftRepository, *, ttl_seconds: int = 86400) -> None:
        self.repository = repository
        self.ttl_seconds = ttl_seconds

    async def create(self, *, adopter_user_id: UUID) -> tuple[AdoptionDraft, str]:
        existing = await self.repository.get_active_for_adopter(adopter_user_id)
        if existing is not None:
            raise DomainError("active_draft_exists", "已有未完成的領養對話，請先繼續或取消", 409)
        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        draft = AdoptionDraft(
            opaque_token_digest=adoption_draft_token_digest(raw_token),
            organization_id=None,
            adopter_user_id=adopter_user_id,
            path=None,
            target_animal_id=None,
            candidate_match_ids=[],
            current_step=AdoptionDraftState.SELECTING_ORGANIZATION.value,
            answers={},
            reconfirmation_keys=[],
            status="active",
            last_interaction_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        return await self.repository.add(draft), raw_token

    async def set_organization(self, draft_id: UUID, *, organization_id: UUID) -> AdoptionDraft:
        draft = await self._active(draft_id)
        if draft.organization_id is not None:
            raise DomainError("organization_already_selected", "已經選擇過收容所", 409)
        draft.organization_id = organization_id
        draft.current_step = AdoptionDraftState.CHOOSING_PATH.value
        draft.last_interaction_at = datetime.now(timezone.utc)
        return draft

    async def cancel(self, draft_id: UUID) -> AdoptionDraft:
        draft = await self._active(draft_id)
        draft.status = "cancelled"
        draft.current_step = AdoptionDraftState.CANCELLED.value
        return draft

    async def expire(self, draft_id: UUID) -> AdoptionDraft:
        draft = await self._active(draft_id)
        draft.status = "expired"
        draft.current_step = AdoptionDraftState.EXPIRED.value
        return draft

    async def _active(self, draft_id: UUID) -> AdoptionDraft:
        draft = await self.repository.get(draft_id)
        if draft is None or draft.status != "active":
            raise DomainError("draft_not_found", "草稿不存在或無法存取", 404)
        if draft.expires_at <= datetime.now(timezone.utc):
            draft.status = "expired"
            draft.current_step = AdoptionDraftState.EXPIRED.value
            raise DomainError("draft_expired", "草稿已過期", 409)
        return draft
