from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.infrastructure.storage.ports import (
    ObjectMetadata,
    ObjectScope,
    StoredObject,
)


class InMemoryStorageFake:
    def __init__(self) -> None:
        self._objects: dict[tuple[UUID, str], tuple[bytes, ObjectMetadata]] = {}

    async def put(
        self, *, scope: ObjectScope, key: str, data: bytes, metadata: ObjectMetadata
    ) -> StoredObject:
        if not metadata.exif_removed:
            raise DomainError("unsafe_media", "只有清理過 EXIF 的圖片可以保存", 422)
        self._objects[(scope.organization_id, key)] = (data, metadata)
        return StoredObject(key=key, scope=scope, metadata=metadata)

    async def get(self, *, scope: ObjectScope, key: str) -> bytes:
        stored = self._objects.get((scope.organization_id, key))
        if stored is None:
            raise DomainError("object_not_found", "物件不存在或無法存取", 404)
        return stored[0]

    async def delete(self, *, scope: ObjectScope, key: str) -> None:
        self._objects.pop((scope.organization_id, key), None)

    async def signed_url(self, *, scope: ObjectScope, key: str, expires_seconds: int) -> str:
        if (scope.organization_id, key) not in self._objects:
            raise DomainError("object_not_found", "物件不存在或無法存取", 404)
        return (
            f"https://storage.fake/{scope.organization_id}/{quote(key, safe='')}"
            f"?expires={max(1, expires_seconds)}"
        )

    def metadata(self, *, scope: ObjectScope, key: str) -> ObjectMetadata:
        try:
            return self._objects[(scope.organization_id, key)][1]
        except KeyError as exc:
            raise DomainError("object_not_found", "物件不存在或無法存取", 404) from exc

    @staticmethod
    def metadata_for(data: bytes, *, content_type: str, checksum: str) -> ObjectMetadata:
        return ObjectMetadata(
            content_type=content_type,
            size=len(data),
            checksum=checksum,
            exif_removed=True,
            created_at=datetime.now(timezone.utc),
        )
