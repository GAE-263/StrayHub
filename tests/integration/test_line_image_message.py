from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from services.api.app.api.errors import DomainError
from services.api.app.application.line_image_service import LineImageService
from services.api.app.application.media_service import MediaProcessingService
from services.api.app.application.ports.line_messaging import LineImageContent
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.models.care_report_draft import DraftMediaAsset


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_line_image_is_cleaned_before_draft_storage() -> None:
    image = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(image, format="JPEG")
    line = MockLineAdapter()
    line.images["message-1"] = LineImageContent("message-1", image.getvalue(), "image/jpeg")
    storage = InMemoryStorageFake()
    organization_id = uuid4()

    stored = await LineImageService(line, storage).attach_to_draft(
        message_id="message-1",
        organization_id=organization_id,
        object_key="drafts/photo.jpg",
    )

    assert b"Exif" not in await storage.get(scope=stored.scope, key=stored.key)


@pytest.mark.asyncio
async def test_promote_cleaned_media_removes_temporary_object() -> None:
    image = BytesIO()
    Image.new("RGB", (2, 2), "green").save(image, format="JPEG")
    storage = InMemoryStorageFake()
    service = MediaProcessingService(storage)
    organization_id = uuid4()

    await service.store_cleaned(
        organization_id=organization_id,
        object_key="temporary/draft-1.jpg",
        data=image.getvalue(),
        declared_content_type="image/jpeg",
    )
    formal = await service.promote_cleaned(
        organization_id=organization_id,
        temporary_key="temporary/draft-1.jpg",
        formal_key="reports/report-1.jpg",
        content_type="image/jpeg",
    )

    assert formal.key == "reports/report-1.jpg"
    with pytest.raises(DomainError, match="物件不存在"):
        await storage.get(scope=formal.scope, key="temporary/draft-1.jpg")


@pytest.mark.asyncio
async def test_line_image_creates_scoped_draft_media_link() -> None:
    image = BytesIO()
    Image.new("RGB", (2, 2), "red").save(image, format="JPEG")
    line = MockLineAdapter()
    line.images["message-2"] = LineImageContent("message-2", image.getvalue(), "image/jpeg")
    session = FakeSession()

    await LineImageService(line, InMemoryStorageFake()).attach_to_draft(
        message_id="message-2",
        organization_id=uuid4(),
        object_key="drafts/draft-2/photo.jpg",
        draft_id=uuid4(),
        source_event_id="event-2",
        session=session,
    )

    assert any(isinstance(item, MediaAsset) for item in session.added)
    link = next(item for item in session.added if isinstance(item, DraftMediaAsset))
    assert link.source_event_id == "event-2"
