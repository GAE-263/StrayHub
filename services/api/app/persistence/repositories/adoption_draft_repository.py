from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.adoption_draft import AdoptionDraft


def adoption_draft_token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


class AdoptionDraftRepository:
    """Unlike every other tenant-scoped repository, `organization_id` may be
    `None` here: an adopter's first turn (SELECTING_ORGANIZATION) happens
    before any shelter is chosen. Only `get_active_for_adopter` is safe to
    call while unscoped — every other method still filters by
    `organization_id`, matching the normal tenant-scoped repository shape.
    """

    def __init__(self, session: AsyncSession, organization_id: UUID | None) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get(self, draft_id: UUID) -> AdoptionDraft | None:
        result = await self.session.execute(
            select(AdoptionDraft).where(
                AdoptionDraft.id == draft_id,
                AdoptionDraft.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> AdoptionDraft | None:
        result = await self.session.execute(
            select(AdoptionDraft).where(
                AdoptionDraft.opaque_token_digest == adoption_draft_token_digest(token),
                AdoptionDraft.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_for_adopter(self, adopter_user_id: UUID) -> AdoptionDraft | None:
        """Not scoped by organization_id — safe to call before a shelter is chosen."""
        result = await self.session.execute(
            select(AdoptionDraft).where(
                AdoptionDraft.adopter_user_id == adopter_user_id,
                AdoptionDraft.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def add(self, draft: AdoptionDraft) -> AdoptionDraft:
        if draft.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        self.session.add(draft)
        await self.session.flush()
        return draft

    async def update(self, draft: AdoptionDraft) -> AdoptionDraft:
        if draft.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        await self.session.flush()
        return draft
