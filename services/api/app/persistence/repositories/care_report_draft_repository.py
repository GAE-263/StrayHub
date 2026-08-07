from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.models.care_report_draft import CareReportDraft, DraftMediaAsset


def draft_token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


class CareReportDraftRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get(self, draft_id: UUID) -> CareReportDraft | None:
        result = await self.session.execute(
            select(CareReportDraft).where(
                CareReportDraft.id == draft_id,
                CareReportDraft.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> CareReportDraft | None:
        result = await self.session.execute(
            select(CareReportDraft).where(
                CareReportDraft.opaque_token_digest == draft_token_digest(token),
                CareReportDraft.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_active_for_volunteer(self, volunteer_user_id: UUID) -> CareReportDraft | None:
        result = await self.session.execute(
            select(CareReportDraft).where(
                CareReportDraft.organization_id == self.organization_id,
                CareReportDraft.volunteer_user_id == volunteer_user_id,
                CareReportDraft.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def add(self, draft: CareReportDraft) -> CareReportDraft:
        if draft.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        self.session.add(draft)
        await self.session.flush()
        return draft

    async def media_ids(self, draft_id: UUID) -> list[UUID]:
        result = await self.session.execute(
            select(DraftMediaAsset.media_asset_id)
            .join(MediaAsset, MediaAsset.id == DraftMediaAsset.media_asset_id)
            .where(
                DraftMediaAsset.draft_id == draft_id,
                MediaAsset.organization_id == self.organization_id,
                DraftMediaAsset.media_asset_id.is_not(None),
            )
        )
        return list(result.scalars())
