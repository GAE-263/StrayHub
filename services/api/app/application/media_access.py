from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.config.settings import get_settings
from services.api.app.infrastructure.storage.ports import ObjectScope, ObjectStoragePort


@dataclass(frozen=True)
class AdoptionPhotoClaims:
    organization_id: UUID
    object_key_digest: str


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _object_key_digest(object_key: str) -> str:
    return hashlib.sha256(object_key.encode()).hexdigest()


def issue_adoption_photo_token(
    *, organization_id: UUID, animal_id: UUID, object_key: str, ttl_seconds: int = 300
) -> str:
    """Issue a short-lived capability for one adoptable animal's current photo."""
    payload = {
        "purpose": "public_adoption_photo",
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


def verify_adoption_photo_token(token: str, *, animal_id: UUID) -> AdoptionPhotoClaims:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(
            get_settings().animal_confirmation_secret.encode(), encoded.encode(), hashlib.sha256
        ).digest()
        payload = json.loads(_decode(encoded))
        valid = (
            hmac.compare_digest(_decode(signature), expected)
            and payload.get("purpose") == "public_adoption_photo"
            and payload.get("animal_id") == str(animal_id)
            and int(payload["expires_at"]) >= int(time.time())
        )
        organization_id = UUID(payload["organization_id"])
        object_key_digest = str(payload["object_key_digest"])
        if len(object_key_digest) != 64:
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
        object_key_digest = ""
    if not valid:
        raise DomainError("adoption_photo_not_found", "照片不存在或連結已失效", 404)
    return AdoptionPhotoClaims(organization_id, object_key_digest)


def verify_adoption_photo_object_key(claims: AdoptionPhotoClaims, object_key: str) -> None:
    if not hmac.compare_digest(claims.object_key_digest, _object_key_digest(object_key)):
        raise DomainError("adoption_photo_not_found", "照片不存在或連結已失效", 404)


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
