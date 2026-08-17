from __future__ import annotations

from typing import Any

import boto3

from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.storage.ports import ObjectMetadata, ObjectScope, StoredObject


class MinioStorageAdapter:
    def __init__(self, *, client: Any | None = None, bucket: str | None = None) -> None:
        settings = get_settings()
        self.bucket = bucket or settings.minio_bucket
        self.client = client or boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name="us-east-1",
        )

    @staticmethod
    def _scoped_key(scope: ObjectScope, key: str) -> str:
        return f"organizations/{scope.organization_id}/{key.lstrip('/')}"

    async def put(
        self, *, scope: ObjectScope, key: str, data: bytes, metadata: ObjectMetadata
    ) -> StoredObject:
        if not metadata.exif_removed:
            raise ValueError("object must be sanitized before storage")
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._scoped_key(scope, key),
            Body=data,
            ContentType=metadata.content_type,
            Metadata={"checksum": metadata.checksum, "exif_removed": "true"},
        )
        return StoredObject(key=key, scope=scope, metadata=metadata)

    async def get(self, *, scope: ObjectScope, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self._scoped_key(scope, key))
        return response["Body"].read()

    async def delete(self, *, scope: ObjectScope, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._scoped_key(scope, key))

    async def signed_url(self, *, scope: ObjectScope, key: str, expires_seconds: int) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._scoped_key(scope, key)},
            ExpiresIn=max(1, expires_seconds),
        )
