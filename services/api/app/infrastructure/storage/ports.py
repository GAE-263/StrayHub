from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ObjectScope:
    organization_id: UUID


@dataclass(frozen=True)
class ObjectMetadata:
    content_type: str
    size: int
    checksum: str
    exif_removed: bool
    created_at: datetime


@dataclass(frozen=True)
class StoredObject:
    key: str
    scope: ObjectScope
    metadata: ObjectMetadata


class ObjectStoragePort(Protocol):
    async def put(
        self, *, scope: ObjectScope, key: str, data: bytes, metadata: ObjectMetadata
    ) -> StoredObject: ...

    async def get(self, *, scope: ObjectScope, key: str) -> bytes: ...

    async def delete(self, *, scope: ObjectScope, key: str) -> None: ...

    async def signed_url(self, *, scope: ObjectScope, key: str, expires_seconds: int) -> str: ...
