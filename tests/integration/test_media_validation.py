from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from services.api.app.api.errors import DomainError
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.infrastructure.storage.ports import ObjectScope


def _jpeg() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (3, 3), "purple").save(stream, format="JPEG")
    return stream.getvalue()


@pytest.mark.asyncio
async def test_media_policy_rejects_mismatched_mime_and_keeps_only_clean_object() -> None:
    storage = InMemoryStorageFake()
    service = MediaProcessingService(storage)
    organization_id = uuid4()
    with pytest.raises(DomainError, match="實際格式"):
        await service.store_cleaned(
            organization_id=organization_id,
            object_key="drafts/bad.png",
            data=_jpeg(),
            declared_content_type="image/png",
        )
    stored = await service.store_cleaned(
        organization_id=organization_id,
        object_key="drafts/good.jpg",
        data=_jpeg(),
        declared_content_type="image/jpeg",
    )
    assert storage.metadata(scope=stored.scope, key=stored.key).exif_removed is True
    assert b"Exif" not in await storage.get(scope=stored.scope, key=stored.key)


@pytest.mark.asyncio
async def test_temporary_media_is_deleted_after_promotion() -> None:
    storage = InMemoryStorageFake()
    service = MediaProcessingService(storage)
    organization_id = uuid4()
    await service.store_cleaned(
        organization_id=organization_id,
        object_key="temporary/photo.jpg",
        data=_jpeg(),
        declared_content_type="image/jpeg",
    )
    await service.promote_cleaned(
        organization_id=organization_id,
        temporary_key="temporary/photo.jpg",
        formal_key="reports/report.jpg",
        content_type="image/jpeg",
    )
    with pytest.raises(DomainError, match="物件不存在"):
        await storage.get(
            scope=ObjectScope(organization_id),
            key="temporary/photo.jpg",
        )
