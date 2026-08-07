from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.care_report import MediaAsset


class MediaRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get(self, media_id: UUID) -> MediaAsset | None:
        result = await self.session.execute(
            select(MediaAsset).where(
                MediaAsset.id == media_id,
                MediaAsset.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def require_formal(self, media_id: UUID) -> MediaAsset:
        media = await self.get(media_id)
        if media is None or media.status in {"temporary", "failed", "unusable", "archived"}:
            raise DomainError("media_not_found", "照片不存在或無法存取", 404)
        if not media.exif_removed:
            raise DomainError("unsafe_media", "照片尚未完成安全清理", 409)
        return media
