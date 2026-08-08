from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from services.api.app.application.ports.line_messaging import LineImageContent
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter
from services.api.app.infrastructure.storage.gcs import GcsStorageAdapter
from services.api.app.infrastructure.storage.memory import InMemoryStorageFake
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectMetadata, ObjectScope
from services.worker.app.infrastructure.ai_adapter import AIAdapter
from services.worker.app.infrastructure.ai_port import AIRequestVersion
from services.worker.app.infrastructure.mock_ai_adapter import MockAIAdapter


class _S3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.keys: list[str] = []

    def put_object(self, **kwargs):
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]
        self.keys.append(kwargs["Key"])

    def get_object(self, **kwargs):
        data = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        return {"Body": type("Body", (), {"read": lambda _self: data})()}

    def delete_object(self, **kwargs):
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)

    def generate_presigned_url(self, *_args, **_kwargs):
        return "https://minio.local/signed"


class _Blob:
    def __init__(self) -> None:
        self.data = b""
        self.metadata = None

    def upload_from_string(self, data, content_type=None):
        self.data = data

    def download_as_bytes(self):
        return self.data

    def delete(self):
        self.data = b""

    def generate_signed_url(self, **_kwargs):
        return "https://gcs.local/signed"


class _GcsClient:
    def __init__(self) -> None:
        self.blob_value = _Blob()

    def bucket(self, _name):
        return type("Bucket", (), {"blob": lambda _self, _key: self.blob_value})()


@pytest.mark.asyncio
async def test_storage_adapters_share_put_get_signed_url_contract() -> None:
    scope = ObjectScope(uuid4())
    metadata = ObjectMetadata("image/jpeg", 5, "a" * 64, True, datetime.now(timezone.utc))
    adapters = (
        InMemoryStorageFake(),
        MinioStorageAdapter(client=_S3Client(), bucket="private"),
        GcsStorageAdapter(client=_GcsClient(), bucket="private"),
    )
    for adapter in adapters:
        await adapter.put(scope=scope, key="reports/photo.jpg", data=b"clean", metadata=metadata)
        assert await adapter.get(scope=scope, key="reports/photo.jpg") == b"clean"
        assert await adapter.signed_url(scope=scope, key="reports/photo.jpg", expires_seconds=60)


@pytest.mark.asyncio
async def test_mock_and_formal_line_adapters_share_boundary_contract() -> None:
    rich_menu = {
        "size": {"width": 2500, "height": 1686},
        "areas": [{"bounds": {"x": 0, "y": 0, "width": 1, "height": 1}}],
        "actions": ["start"],
    }
    mock = MockLineAdapter()
    mock.images["image-1"] = LineImageContent("image-1", b"image", "image/jpeg")
    await mock.reply(reply_token="reply", messages=[{"type": "text", "text": "ok"}])
    assert (await mock.get_image_content(message_id="image-1")).content == b"image"
    assert await mock.create_rich_menu(rich_menu=rich_menu)

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/content") and request.method == "GET":
            return httpx.Response(200, content=b"image", headers={"content-type": "image/jpeg"})
        if request.url.path.endswith("/richmenu") and request.method == "POST":
            return httpx.Response(200, json={"richMenuId": "rich-1"})
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        formal = LineMessagingApiAdapter(client=client)
        await formal.reply(reply_token="reply", messages=[{"type": "text", "text": "ok"}])
        assert (await formal.get_image_content(message_id="image-1")).content == b"image"
        rich_menu_id = await formal.create_rich_menu(rich_menu=rich_menu)
        await formal.upload_rich_menu_image(rich_menu_id=rich_menu_id, content=b"png")
        await formal.link_rich_menu(rich_menu_id=rich_menu_id, user_id="line-user")
    assert len(requests) == 5
    assert all(request.headers["authorization"].startswith("Bearer ") for request in requests)


@pytest.mark.asyncio
async def test_mock_and_formal_ai_adapters_share_versioned_json_contract() -> None:
    version = AIRequestVersion("local", "model", "v1", "prompt-v1", "schema-v1")
    mock = MockAIAdapter(result={"observations": []})
    assert await mock.analyze(note="note", image_bytes=[b"image"], version=version) == {
        "observations": []
    }

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        assert b'"model_version":"v1"' in payload
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"output": {"observations": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        formal = AIAdapter(endpoint="https://ai.local/analyze", api_key="test-key", client=client)
        assert await formal.analyze(note="note", image_bytes=[b"image"], version=version) == {
            "observations": []
        }
