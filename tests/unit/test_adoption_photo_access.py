from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from services.api.app.api import line_webhook
from services.api.app.api.errors import DomainError
from services.api.app.application import media_access


def test_adoption_photo_token_is_bound_to_animal_and_current_object_key() -> None:
    organization_id = uuid4()
    animal_id = uuid4()
    token = media_access.issue_adoption_photo_token(
        signing_secret=media_access.get_settings().animal_confirmation_secret,
        organization_id=organization_id,
        animal_id=animal_id,
        object_key="animals/a/primary.jpg",
    )

    claims = media_access.verify_adoption_photo_token(token, animal_id=animal_id)
    assert claims.organization_id == organization_id
    media_access.verify_adoption_photo_object_key(claims, "animals/a/primary.jpg")

    with pytest.raises(DomainError) as wrong_animal:
        media_access.verify_adoption_photo_token(token, animal_id=uuid4())
    assert wrong_animal.value.code == "adoption_photo_not_found"

    with pytest.raises(DomainError) as replaced_photo:
        media_access.verify_adoption_photo_object_key(claims, "animals/a/replacement.jpg")
    assert replaced_photo.value.code == "adoption_photo_not_found"


def test_adoption_photo_token_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media_access.time, "time", lambda: 1000)
    animal_id = uuid4()
    token = media_access.issue_adoption_photo_token(
        signing_secret=media_access.get_settings().animal_confirmation_secret,
        organization_id=uuid4(),
        animal_id=animal_id,
        object_key="animals/a/primary.jpg",
        ttl_seconds=5,
    )
    monkeypatch.setattr(media_access.time, "time", lambda: 1006)

    with pytest.raises(DomainError) as expired:
        media_access.verify_adoption_photo_token(token, animal_id=animal_id)
    assert expired.value.code == "adoption_photo_not_found"


def test_shared_photo_capability_preserves_purpose_and_rejects_cross_purpose() -> None:
    organization_id = uuid4()
    animal_id = uuid4()
    token = media_access.issue_animal_photo_token(
        signing_secret=media_access.get_settings().animal_confirmation_secret,
        purpose=media_access.VOLUNTEER_WALK_PHOTO,
        organization_id=organization_id,
        animal_id=animal_id,
        object_key="animals/a/primary.jpg",
    )

    claims = media_access.verify_animal_photo_token(token, animal_id=animal_id)

    assert claims.purpose == media_access.VOLUNTEER_WALK_PHOTO
    assert claims.organization_id == organization_id
    assert claims.animal_id == animal_id
    with pytest.raises(DomainError) as wrong_purpose:
        media_access.verify_animal_photo_token(
            token,
            animal_id=animal_id,
            expected_purpose=media_access.PUBLIC_ADOPTION_PHOTO,
        )
    assert wrong_purpose.value.code == "animal_photo_not_found"


def test_shared_photo_capability_rejects_unknown_purpose() -> None:
    with pytest.raises(ValueError, match="unsupported animal photo purpose"):
        media_access.issue_animal_photo_token(
            signing_secret=media_access.get_settings().animal_confirmation_secret,
            purpose="unknown_photo",
            organization_id=uuid4(),
            animal_id=uuid4(),
            object_key="animals/a/primary.jpg",
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://strayhub.example/photo.jpg",
        "https://localhost/photo.jpg",
        "https://127.0.0.1/photo.jpg",
        "https://[::1]/photo.jpg",
        "https://minio:9000/photo.jpg",
        "https://minio.internal/photo.jpg",
        "https://10.0.0.1/photo.jpg",
        "https://169.254.1.1/photo.jpg",
        "https://storage.googleapis.com/private-bucket/photo.jpg",
        "https://private-bucket.storage.googleapis.com/photo.jpg",
        "https://private-bucket.s3.ap-northeast-1.amazonaws.com/photo.jpg",
        "https://user:password@strayhub.example/photo.jpg",
    ],
)
def test_public_https_url_rejects_storage_and_private_addresses(url: str) -> None:
    assert media_access.public_https_url_or_none(url) is None


@pytest.mark.asyncio
async def test_walk_photo_builder_allows_active_non_adoptable_processed_jpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    animal = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        status="active",
        is_adoptable=False,
        current_photo_key="animals/a/primary.jpg",
    )
    media = SimpleNamespace(status="processed", exif_removed=True, content_type="image/jpeg")

    class Result:
        def scalar_one_or_none(self):
            return media

    class Session:
        async def execute(self, _statement):
            return Result()

    async def no_scope(_session, scoped_organization_id):
        assert scoped_organization_id == organization_id

    monkeypatch.setattr(media_access, "set_organization_scope", no_scope)
    url = await media_access.ExternalAnimalPhotoService(Session()).issue_url(
        public_base_url="https://strayhub.example",
        organization_id=organization_id,
        animal=animal,
        purpose=media_access.VOLUNTEER_WALK_PHOTO,
    )

    assert url is not None
    parsed = urlsplit(url)
    assert parsed.scheme == "https"
    assert parsed.hostname == "strayhub.example"
    assert parsed.path == f"/v1/public/animals/{animal.id}/photo"
    token = parse_qs(parsed.query)["token"][0]
    claims = media_access.verify_animal_photo_token(token, animal_id=animal.id)
    assert claims.purpose == media_access.VOLUNTEER_WALK_PHOTO


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "exif_removed", "content_type"),
    [
        ("pending", True, "image/jpeg"),
        ("processed", False, "image/jpeg"),
        ("processed", True, "image/webp"),
    ],
)
async def test_walk_photo_builder_omits_ineligible_media(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    exif_removed: bool,
    content_type: str,
) -> None:
    organization_id = uuid4()
    animal = SimpleNamespace(
        id=uuid4(),
        organization_id=organization_id,
        status="active",
        is_adoptable=False,
        current_photo_key="animals/a/primary.jpg",
    )
    media = SimpleNamespace(
        status=status,
        exif_removed=exif_removed,
        content_type=content_type,
    )

    class Result:
        def scalar_one_or_none(self):
            return media

    class Session:
        async def execute(self, _statement):
            return Result()

    async def no_scope(_session, _organization_id):
        return None

    monkeypatch.setattr(media_access, "set_organization_scope", no_scope)

    assert (
        await media_access.ExternalAnimalPhotoService(Session()).issue_url(
            public_base_url="https://strayhub.example",
            organization_id=organization_id,
            animal=animal,
            purpose=media_access.VOLUNTEER_WALK_PHOTO,
        )
        is None
    )


@pytest.mark.asyncio
async def test_line_adoption_photo_uses_public_api_instead_of_private_minio() -> None:
    organization_id = uuid4()
    animal = SimpleNamespace(id=uuid4(), current_photo_key="furkids-demo/animals/A-1/primary.jpg")

    url = await line_webhook._animal_photo_url("https://strayhub.example", organization_id, animal)

    assert url is not None
    assert url.startswith(
        f"https://strayhub.example/v1/public/adoption/animals/{animal.id}/photo?token="
    )
    token = url.split("token=", 1)[1]
    claims = media_access.verify_adoption_photo_token(token, animal_id=animal.id)
    assert claims.organization_id == organization_id
    media_access.verify_adoption_photo_object_key(claims, animal.current_photo_key)


@pytest.mark.asyncio
async def test_line_adoption_photo_is_omitted_without_https_public_origin() -> None:
    animal = SimpleNamespace(id=uuid4(), current_photo_key="animals/a/primary.jpg")

    assert await line_webhook._animal_photo_url(None, uuid4(), animal) is None
