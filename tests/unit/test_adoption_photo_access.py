from types import SimpleNamespace
from uuid import uuid4

import pytest
from services.api.app.api import line_webhook
from services.api.app.api.errors import DomainError
from services.api.app.application import media_access


def test_adoption_photo_token_is_bound_to_animal_and_current_object_key() -> None:
    organization_id = uuid4()
    animal_id = uuid4()
    token = media_access.issue_adoption_photo_token(
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
        organization_id=uuid4(),
        animal_id=animal_id,
        object_key="animals/a/primary.jpg",
        ttl_seconds=5,
    )
    monkeypatch.setattr(media_access.time, "time", lambda: 1006)

    with pytest.raises(DomainError) as expired:
        media_access.verify_adoption_photo_token(token, animal_id=animal_id)
    assert expired.value.code == "adoption_photo_not_found"


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
