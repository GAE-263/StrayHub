from __future__ import annotations

from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.application.ports.line_messaging import LineMessagingPort
from services.api.app.infrastructure.storage.ports import (
    ObjectStoragePort,
    StoredObject,
)
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.models.care_report_draft import DraftMediaAsset


class LineImageService:
    def __init__(self, line: LineMessagingPort, storage: ObjectStoragePort) -> None:
        self.line = line
        self.media = MediaProcessingService(storage)

    async def attach_to_draft(
        self,
        *,
        message_id: str,
        organization_id: UUID,
        object_key: str,
        draft_accepts_media: bool = True,
        draft_id: UUID | None = None,
        source_event_id: str | None = None,
        subject: str | None = None,
        session=None,
    ) -> StoredObject:
        if not draft_accepts_media:
            raise DomainError("invalid_draft_step", "目前步驟不接受照片", 409)
        if subject not in {None, "stool", "portrait"}:
            raise DomainError("invalid_media_subject", "照片用途無效", 422)
        content = await self.line.get_image_content(message_id=message_id)
        stored = await self.media.store_cleaned(
            organization_id=organization_id,
            object_key=object_key,
            data=content.content,
            declared_content_type=content.content_type,
        )
        if session is not None:
            asset = MediaAsset(
                organization_id=organization_id,
                object_key=stored.key,
                content_type=stored.metadata.content_type,
                checksum=stored.metadata.checksum,
                status="temporary",
                purpose="care_report_draft",
                subject=subject,
                exif_removed=True,
            )
            session.add(asset)
            await session.flush()
            if draft_id is not None:
                session.add(
                    DraftMediaAsset(
                        draft_id=draft_id,
                        media_asset_id=asset.id,
                        source_event_id=source_event_id,
                    )
                )
                await session.flush()
        return stored
