from __future__ import annotations

from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.infrastructure.storage.ports import ObjectScope, ObjectStoragePort


class MediaAccessService:
    def __init__(self, storage: ObjectStoragePort, organization_id: UUID) -> None:
        self.storage = storage
        self.organization_id = organization_id

    async def signed_url(
        self, *, media_organization_id: UUID, object_key: str, expires_seconds: int = 300
    ) -> str:
        if media_organization_id != self.organization_id:
            raise DomainError("media_access_denied", "照片不存在或無法存取", 404)
        return await self.storage.signed_url(
            scope=ObjectScope(self.organization_id), key=object_key, expires_seconds=expires_seconds
        )
