from __future__ import annotations

from datetime import timedelta
from typing import Any

from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.storage.ports import ObjectMetadata, ObjectScope, StoredObject


class GcsStorageAdapter:
    """Cloud Storage adapter with an injected official-client boundary."""

    def __init__(self, *, client: Any, bucket: str | None = None) -> None:
        settings = get_settings()
        self.client = client
        self.bucket_name = bucket or settings.gcs_bucket

    def _blob(self, scope: ObjectScope, key: str) -> Any:
        bucket = self.client.bucket(self.bucket_name)
        return bucket.blob(f"organizations/{scope.organization_id}/{key.lstrip('/')}")

    async def put(
        self, *, scope: ObjectScope, key: str, data: bytes, metadata: ObjectMetadata
    ) -> StoredObject:
        if not metadata.exif_removed:
            raise ValueError("object must be sanitized before storage")
        blob = self._blob(scope, key)
        blob.metadata = {"checksum": metadata.checksum, "exif_removed": "true"}
        blob.upload_from_string(data, content_type=metadata.content_type)
        return StoredObject(key=key, scope=scope, metadata=metadata)

    async def get(self, *, scope: ObjectScope, key: str) -> bytes:
        return self._blob(scope, key).download_as_bytes()

    async def delete(self, *, scope: ObjectScope, key: str) -> None:
        self._blob(scope, key).delete()

    async def signed_url(self, *, scope: ObjectScope, key: str, expires_seconds: int) -> str:
        return self._blob(scope, key).generate_signed_url(
            version="v4", expiration=timedelta(seconds=max(1, expires_seconds)), method="GET"
        )
