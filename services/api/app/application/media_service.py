from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from services.api.app.application.media_sanitization import ImageOutputPolicy, sanitize_image
from services.api.app.infrastructure.storage.ports import (
    ObjectMetadata,
    ObjectScope,
    ObjectStoragePort,
    StoredObject,
)


@dataclass(frozen=True)
class SanitizedMedia:
    data: bytes
    content_type: str
    checksum: str


class MediaProcessingService:
    """集中執行圖片安全政策，再交由 Object Storage Port 保存。"""

    def __init__(self, storage: ObjectStoragePort) -> None:
        self.storage = storage

    @staticmethod
    def sanitize(
        data: bytes,
        *,
        declared_content_type: str,
        output_policy: ImageOutputPolicy = "preserve",
    ) -> SanitizedMedia:
        cleaned, content_type, checksum = sanitize_image(
            data,
            declared_content_type=declared_content_type,
            output_policy=output_policy,
        )
        return SanitizedMedia(cleaned, content_type, checksum)

    async def store_cleaned(
        self,
        *,
        organization_id: UUID,
        object_key: str,
        data: bytes,
        declared_content_type: str,
        output_policy: ImageOutputPolicy = "preserve",
    ) -> StoredObject:
        cleaned = self.sanitize(
            data,
            declared_content_type=declared_content_type,
            output_policy=output_policy,
        )
        metadata = ObjectMetadata(
            content_type=cleaned.content_type,
            size=len(cleaned.data),
            checksum=cleaned.checksum,
            exif_removed=True,
            created_at=datetime.now(timezone.utc),
        )
        return await self.storage.put(
            scope=ObjectScope(organization_id),
            key=object_key,
            data=cleaned.data,
            metadata=metadata,
        )

    async def promote_cleaned(
        self,
        *,
        organization_id: UUID,
        temporary_key: str,
        formal_key: str,
        content_type: str,
    ) -> StoredObject:
        """將已清理的暫存物件複製至正式 key，再刪除暫存物件。"""
        scope = ObjectScope(organization_id)
        data = await self.storage.get(scope=scope, key=temporary_key)
        cleaned = self.sanitize(data, declared_content_type=content_type)
        formal = await self._put_cleaned(
            scope=scope,
            object_key=formal_key,
            cleaned=cleaned,
        )
        await self.storage.delete(scope=scope, key=temporary_key)
        return formal

    async def delete_temporary(self, *, organization_id: UUID, object_key: str) -> None:
        await self.storage.delete(scope=ObjectScope(organization_id), key=object_key)

    async def _put_cleaned(
        self,
        *,
        scope: ObjectScope,
        object_key: str,
        cleaned: SanitizedMedia,
    ) -> StoredObject:
        return await self.storage.put(
            scope=scope,
            key=object_key,
            data=cleaned.data,
            metadata=ObjectMetadata(
                content_type=cleaned.content_type,
                size=len(cleaned.data),
                checksum=cleaned.checksum,
                exif_removed=True,
                created_at=datetime.now(timezone.utc),
            ),
        )
