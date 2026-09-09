from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.storage.ports import ObjectScope, ObjectStoragePort
from services.api.app.persistence.database.scope import set_organization_scope
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.care_report import MediaAsset
from services.api.app.persistence.repositories.animal_repository import AnimalRepository

PUBLIC_ADOPTION_PHOTO = "public_adoption_photo"
VOLUNTEER_WALK_PHOTO = "volunteer_walk_photo"
ANIMAL_PHOTO_PURPOSES = frozenset({PUBLIC_ADOPTION_PHOTO, VOLUNTEER_WALK_PHOTO})
LINE_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png"})
PUBLIC_OBJECT_STORAGE_HOSTS = frozenset(
    {
        "s3.amazonaws.com",
        "storage.cloud.google.com",
        "storage.googleapis.com",
    }
)


@dataclass(frozen=True)
class AnimalPhotoClaims:
    purpose: str
    organization_id: UUID
    animal_id: UUID
    object_key_digest: str


# Kept as a public alias for callers that imported the adoption-specific type.
AdoptionPhotoClaims = AnimalPhotoClaims


@dataclass(frozen=True)
class PublicAnimalPhoto:
    object_key: str
    content_type: str


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _object_key_digest(object_key: str) -> str:
    return hashlib.sha256(object_key.encode()).hexdigest()


def public_https_url_or_none(value: str | None, *, origin_only: bool = False) -> str | None:
    """Return a safe public HTTPS URL, or None for optional presentation media."""
    if not value:
        return None
    normalized = value.strip()
    if not normalized or any(character.isspace() for character in normalized):
        return None
    try:
        parsed = urlsplit(normalized)
        hostname = parsed.hostname
        # Accessing port also validates malformed values such as ':not-a-port'.
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    lowered = hostname.rstrip(".").lower()
    if (
        lowered in {"localhost", "minio"}
        or lowered.endswith((".localhost", ".local", ".internal"))
        or lowered.startswith("minio.")
        or lowered in PUBLIC_OBJECT_STORAGE_HOSTS
        or lowered.endswith((".storage.googleapis.com", ".storage-download.googleapis.com"))
        or (".s3." in lowered and lowered.endswith(".amazonaws.com"))
    ):
        return None
    try:
        if not ipaddress.ip_address(lowered).is_global:
            return None
    except ValueError:
        pass
    if origin_only and (parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        return None
    return normalized.rstrip("/") if origin_only else normalized


def issue_animal_photo_token(
    *,
    purpose: str,
    organization_id: UUID,
    animal_id: UUID,
    object_key: str,
    ttl_seconds: int = 300,
) -> str:
    if purpose not in ANIMAL_PHOTO_PURPOSES:
        raise ValueError("unsupported animal photo purpose")
    payload = {
        "purpose": purpose,
        "organization_id": str(organization_id),
        "animal_id": str(animal_id),
        "object_key_digest": _object_key_digest(object_key),
        "expires_at": int(time.time()) + max(1, ttl_seconds),
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(
        get_settings().animal_confirmation_secret.encode(), encoded.encode(), hashlib.sha256
    ).digest()
    return f"{encoded}.{_encode(signature)}"


def issue_adoption_photo_token(
    *, organization_id: UUID, animal_id: UUID, object_key: str, ttl_seconds: int = 300
) -> str:
    """Issue a short-lived capability for one adoptable animal's current photo."""
    return issue_animal_photo_token(
        purpose=PUBLIC_ADOPTION_PHOTO,
        organization_id=organization_id,
        animal_id=animal_id,
        object_key=object_key,
        ttl_seconds=ttl_seconds,
    )


def verify_animal_photo_token(
    token: str, *, animal_id: UUID, expected_purpose: str | None = None
) -> AnimalPhotoClaims:
    if expected_purpose is not None and expected_purpose not in ANIMAL_PHOTO_PURPOSES:
        raise DomainError("animal_photo_not_found", "照片不存在或連結已失效", 404)
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(
            get_settings().animal_confirmation_secret.encode(), encoded.encode(), hashlib.sha256
        ).digest()
        payload = json.loads(_decode(encoded))
        purpose = str(payload["purpose"])
        organization_id = UUID(payload["organization_id"])
        token_animal_id = UUID(payload["animal_id"])
        object_key_digest = str(payload["object_key_digest"])
        valid = (
            hmac.compare_digest(_decode(signature), expected)
            and purpose in ANIMAL_PHOTO_PURPOSES
            and (expected_purpose is None or purpose == expected_purpose)
            and token_animal_id == animal_id
            and int(payload["expires_at"]) >= int(time.time())
            and len(object_key_digest) == 64
        )
    except (
        AttributeError,
        binascii.Error,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ):
        valid = False
        purpose = ""
        organization_id = UUID(int=0)
        token_animal_id = UUID(int=0)
        object_key_digest = ""
    if not valid:
        raise DomainError("animal_photo_not_found", "照片不存在或連結已失效", 404)
    return AnimalPhotoClaims(purpose, organization_id, token_animal_id, object_key_digest)


def verify_adoption_photo_token(token: str, *, animal_id: UUID) -> AdoptionPhotoClaims:
    try:
        return verify_animal_photo_token(
            token,
            animal_id=animal_id,
            expected_purpose=PUBLIC_ADOPTION_PHOTO,
        )
    except DomainError as exc:
        raise DomainError("adoption_photo_not_found", "照片不存在或連結已失效", 404) from exc


def verify_animal_photo_object_key(claims: AnimalPhotoClaims, object_key: str) -> None:
    if not hmac.compare_digest(claims.object_key_digest, _object_key_digest(object_key)):
        raise DomainError("animal_photo_not_found", "照片不存在或連結已失效", 404)


def verify_adoption_photo_object_key(claims: AdoptionPhotoClaims, object_key: str) -> None:
    try:
        verify_animal_photo_object_key(claims, object_key)
    except DomainError as exc:
        raise DomainError("adoption_photo_not_found", "照片不存在或連結已失效", 404) from exc


class ExternalAnimalPhotoService:
    """Issue and resolve tenant-bound public animal-photo capabilities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _animal_allowed(animal: Animal, purpose: str, organization_id: UUID) -> bool:
        return (
            purpose in ANIMAL_PHOTO_PURPOSES
            and animal.organization_id == organization_id
            and animal.status == "active"
            and (purpose != PUBLIC_ADOPTION_PHOTO or animal.is_adoptable)
            and bool(animal.current_photo_key)
        )

    @staticmethod
    def _media_allowed(media: MediaAsset | None, purpose: str) -> bool:
        if media is None or media.status != "processed" or not media.exif_removed:
            return False
        if purpose == VOLUNTEER_WALK_PHOTO:
            return media.content_type in LINE_IMAGE_CONTENT_TYPES
        return media.content_type.startswith("image/")

    async def _eligible_photo(
        self, *, organization_id: UUID, animal: Animal, purpose: str
    ) -> PublicAnimalPhoto | None:
        if not self._animal_allowed(animal, purpose, organization_id):
            return None
        await set_organization_scope(self.session, organization_id)
        result = await self.session.execute(
            select(MediaAsset).where(
                MediaAsset.organization_id == organization_id,
                MediaAsset.object_key == animal.current_photo_key,
            )
        )
        media = result.scalar_one_or_none()
        if not self._media_allowed(media, purpose):
            return None
        return PublicAnimalPhoto(animal.current_photo_key, media.content_type)

    async def issue_url(
        self,
        *,
        public_base_url: str | None,
        organization_id: UUID,
        animal: Animal,
        purpose: str,
        ttl_seconds: int = 300,
    ) -> str | None:
        origin = public_https_url_or_none(public_base_url, origin_only=True)
        if origin is None:
            return None
        photo = await self._eligible_photo(
            organization_id=organization_id,
            animal=animal,
            purpose=purpose,
        )
        if photo is None:
            return None
        token = issue_animal_photo_token(
            purpose=purpose,
            organization_id=organization_id,
            animal_id=animal.id,
            object_key=photo.object_key,
            ttl_seconds=ttl_seconds,
        )
        return f"{origin}/v1/public/animals/{animal.id}/photo?token={token}"

    async def resolve(self, claims: AnimalPhotoClaims) -> PublicAnimalPhoto:
        await set_organization_scope(self.session, claims.organization_id)
        animal = await AnimalRepository(self.session, claims.organization_id).get(claims.animal_id)
        if animal is None or not self._animal_allowed(
            animal, claims.purpose, claims.organization_id
        ):
            raise DomainError("animal_photo_not_found", "照片不存在或連結已失效", 404)
        assert animal.current_photo_key is not None
        verify_animal_photo_object_key(claims, animal.current_photo_key)
        photo = await self._eligible_photo(
            organization_id=claims.organization_id,
            animal=animal,
            purpose=claims.purpose,
        )
        if photo is None:
            raise DomainError("animal_photo_not_found", "照片不存在或連結已失效", 404)
        return photo


@dataclass(frozen=True)
class GrowthDiaryPhotoClaims:
    organization_id: UUID
    entry_id: UUID
    object_key: str


def issue_growth_diary_photo_token(
    *, organization_id: UUID, entry_id: UUID, object_key: str, ttl_seconds: int = 300
) -> str:
    """Short-lived capability for one 毛孩日記 photo — unlike the adoption
    animal photo token (one fixed `current_photo_key` per animal, so only
    its digest needs to travel), an entry can hold several photos
    (photo_keys), so the object_key itself has to be in the token to know
    which one to serve; it's an internal storage path, not a secret, so
    carrying it in plaintext here is fine."""
    payload = {
        "purpose": "public_growth_diary_photo",
        "organization_id": str(organization_id),
        "entry_id": str(entry_id),
        "object_key": object_key,
        "expires_at": int(time.time()) + max(1, ttl_seconds),
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(
        get_settings().animal_confirmation_secret.encode(), encoded.encode(), hashlib.sha256
    ).digest()
    return f"{encoded}.{_encode(signature)}"


def verify_growth_diary_photo_token(token: str, *, entry_id: UUID) -> GrowthDiaryPhotoClaims:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(
            get_settings().animal_confirmation_secret.encode(), encoded.encode(), hashlib.sha256
        ).digest()
        payload = json.loads(_decode(encoded))
        valid = (
            hmac.compare_digest(_decode(signature), expected)
            and payload.get("purpose") == "public_growth_diary_photo"
            and payload.get("entry_id") == str(entry_id)
            and int(payload["expires_at"]) >= int(time.time())
        )
        organization_id = UUID(payload["organization_id"])
        object_key = str(payload["object_key"])
        if not object_key:
            valid = False
    except (
        AttributeError,
        binascii.Error,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ):
        valid = False
        organization_id = UUID(int=0)
        object_key = ""
    if not valid:
        raise DomainError("growth_diary_photo_not_found", "照片不存在或連結已失效", 404)
    return GrowthDiaryPhotoClaims(organization_id, entry_id, object_key)


class MediaAccessService:
    def __init__(self, storage: ObjectStoragePort, organization_id: UUID) -> None:
        self.storage = storage
        self.organization_id = organization_id

    async def signed_url(
        self, *, media_organization_id: UUID, object_key: str, expires_seconds: int = 300
    ) -> str:
        if media_organization_id != self.organization_id:
            raise DomainError("media_access_denied", "照片不存在或無法存取", 404)
        return await self.storage.signed_url(
            scope=ObjectScope(self.organization_id), key=object_key, expires_seconds=expires_seconds
        )
