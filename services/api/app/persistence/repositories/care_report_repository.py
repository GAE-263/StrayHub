from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.care_report import (
    CareReport,
    CareReportCorrection,
    CareReportMedia,
    MediaAsset,
    ReportIdempotencyKey,
)


class CareReportRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get_idempotent(self, *, volunteer_user_id: UUID, key: str) -> CareReport | None:
        result = await self.session.execute(
            select(CareReport)
            .join(ReportIdempotencyKey, ReportIdempotencyKey.report_id == CareReport.id)
            .where(
                ReportIdempotencyKey.organization_id == self.organization_id,
                ReportIdempotencyKey.volunteer_user_id == volunteer_user_id,
                ReportIdempotencyKey.key == key,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_draft(self, draft_id: UUID) -> CareReport | None:
        result = await self.session.execute(
            select(CareReport).where(
                CareReport.id.is_not(None),
                CareReport.draft_id == draft_id,
                CareReport.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, report: CareReport) -> CareReport:
        if report.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        self.session.add(report)
        await self.session.flush()
        return report

    async def add_idempotency(self, *, volunteer_user_id: UUID, key: str, report_id: UUID) -> None:
        self.session.add(
            ReportIdempotencyKey(
                organization_id=self.organization_id,
                volunteer_user_id=volunteer_user_id,
                key=key,
                report_id=report_id,
            )
        )
        await self.session.flush()

    async def attach_media(self, *, report_id: UUID, media_asset_ids: list[UUID]) -> None:
        if not media_asset_ids:
            return
        result = await self.session.execute(
            select(MediaAsset.id).where(
                MediaAsset.organization_id == self.organization_id,
                MediaAsset.id.in_(media_asset_ids),
                MediaAsset.status.in_(["temporary", "processed", "attached"]),
                MediaAsset.exif_removed.is_(True),
            )
        )
        valid_ids = set(result.scalars())
        if valid_ids != set(media_asset_ids):
            raise DomainError("media_not_found", "照片不存在或無法存取", 404)
        for media_asset_id in media_asset_ids:
            self.session.add(CareReportMedia(report_id=report_id, media_asset_id=media_asset_id))
        await self.session.flush()
        await self.session.execute(
            sa_update(MediaAsset)
            .where(
                MediaAsset.organization_id == self.organization_id,
                MediaAsset.id.in_(media_asset_ids),
            )
            .values(status="attached")
        )

    async def get(self, report_id: UUID) -> CareReport | None:
        result = await self.session.execute(
            select(CareReport).where(
                CareReport.id == report_id,
                CareReport.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_correction(self, correction: CareReportCorrection) -> CareReportCorrection:
        if correction.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        self.session.add(correction)
        await self.session.flush()
        return correction
