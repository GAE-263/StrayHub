from uuid import uuid4

import pytest
from services.api.app.api.errors import DomainError
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.infrastructure.storage.ports import ObjectScope


@pytest.mark.asyncio
async def test_storage_contract_requires_clean_media_and_tenant_scope() -> None:
    storage = InMemoryStorageFake()
    org_a = ObjectScope(uuid4())
    org_b = ObjectScope(uuid4())
    metadata = storage.metadata_for(b"clean", content_type="image/jpeg", checksum="abc")

    await storage.put(scope=org_a, key="care/photo.jpg", data=b"clean", metadata=metadata)
    assert await storage.get(scope=org_a, key="care/photo.jpg") == b"clean"
    assert "https://storage.fake" in await storage.signed_url(
        scope=org_a, key="care/photo.jpg", expires_seconds=60
    )

    with pytest.raises(DomainError, match="不存在或無法存取"):
        await storage.get(scope=org_b, key="care/photo.jpg")

    unsafe = metadata.__class__(
        content_type=metadata.content_type,
        size=metadata.size,
        checksum=metadata.checksum,
        exif_removed=False,
        created_at=metadata.created_at,
    )
    with pytest.raises(DomainError, match="清理過 EXIF"):
        await storage.put(scope=org_a, key="care/raw.jpg", data=b"raw", metadata=unsafe)
