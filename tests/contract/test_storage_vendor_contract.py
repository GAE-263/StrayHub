from uuid import uuid4

import pytest
from services.api.app.infrastructure.storage.gcs import GcsStorageAdapter
from services.api.app.infrastructure.storage.minio import MinioStorageAdapter
from services.api.app.infrastructure.storage.ports import ObjectMetadata, ObjectScope


class FakeS3:
    def __init__(self) -> None:
        self.objects = {}

    def put_object(self, **kwargs):
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]

    def get_object(self, **kwargs):
        return {
            "Body": type(
                "Body", (), {"read": lambda _self: self.objects[(kwargs["Bucket"], kwargs["Key"])]}
            )()
        }

    def delete_object(self, **kwargs):
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)

    def generate_presigned_url(self, *_args, **_kwargs):
        return "https://minio.test/signed"


class FakeBlob:
    def __init__(self) -> None:
        self.content = b""

    def upload_from_string(self, content, content_type=None):
        self.content = content

    def download_as_bytes(self):
        return self.content

    def delete(self):
        self.content = b""

    def generate_signed_url(self, **_kwargs):
        return "https://gcs.test/signed"


class FakeGcsClient:
    def __init__(self) -> None:
        self.blob = FakeBlob()

    def bucket(self, _name):
        return type("Bucket", (), {"blob": lambda _self, _key: self.blob})()


@pytest.mark.asyncio
async def test_minio_and_gcs_share_scope_and_signed_url_contract() -> None:
    scope = ObjectScope(uuid4())
    metadata = ObjectMetadata("image/jpeg", 4, "hash", True, __import__("datetime").datetime.now())
    minio = MinioStorageAdapter(client=FakeS3(), bucket="private")
    gcs = GcsStorageAdapter(client=FakeGcsClient(), bucket="private")

    await minio.put(scope=scope, key="photo", data=b"data", metadata=metadata)
    await gcs.put(scope=scope, key="photo", data=b"data", metadata=metadata)
    assert await minio.get(scope=scope, key="photo") == b"data"
    assert await gcs.get(scope=scope, key="photo") == b"data"
    assert await minio.signed_url(scope=scope, key="photo", expires_seconds=60)
    assert await gcs.signed_url(scope=scope, key="photo", expires_seconds=60)
