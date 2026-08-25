from __future__ import annotations

import base64
import hashlib
import hmac
from uuid import UUID, uuid4

from services.api.app.api.errors import DomainError
from services.api.app.config.settings import get_settings
from services.api.app.persistence.models.qr_code import AnimalQrCode
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository


def issue_printable_qr_token(qr_code_id: UUID) -> str:
    identifier = qr_code_id.bytes
    signature = hmac.new(
        get_settings().animal_confirmation_secret.encode(),
        b"strayhub:animal-care-qr:v1:" + identifier,
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(identifier + signature).rstrip(b"=").decode("ascii")


def printable_token_for(qr_code: AnimalQrCode) -> str | None:
    token = issue_printable_qr_token(qr_code.id)
    digest = hashlib.sha256(token.encode()).hexdigest()
    return token if hmac.compare_digest(digest, qr_code.token_digest) else None


class QrTokenService:
    def __init__(self, animals: AnimalRepository, qr_codes: QrCodeRepository) -> None:
        self.animals = animals
        self.qr_codes = qr_codes

    async def create_or_reuse(self, *, animal_id: UUID) -> tuple[AnimalQrCode, str | None, bool]:
        animal = await self.animals.get(animal_id)
        if (
            animal is None
            or animal.status != "active"
            or animal.organization_id != self.qr_codes.organization_id
        ):
            raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
        await self.qr_codes.lock_animal(animal_id)
        existing = await self.qr_codes.active_for_animal(animal_id)
        if existing is not None:
            return existing, printable_token_for(existing), False

        qr_code_id = uuid4()
        raw_token = issue_printable_qr_token(qr_code_id)
        qr_code = await self.qr_codes.create(
            AnimalQrCode(
                id=qr_code_id,
                organization_id=animal.organization_id,
                animal_id=animal.id,
                token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
                status="active",
                revoked=False,
            )
        )
        return qr_code, raw_token, True

    async def create(self, *, animal_id: UUID) -> tuple[AnimalQrCode, str | None]:
        qr_code, raw_token, _created = await self.create_or_reuse(animal_id=animal_id)
        return qr_code, raw_token

    async def regenerate(self, *, qr_code_id: UUID) -> tuple[AnimalQrCode, str]:
        candidate = await self.qr_codes.get(qr_code_id)
        if candidate is None:
            raise DomainError("qr_code_not_found", "QR Code 不存在或無法存取", 404)
        animal = await self.animals.get(candidate.animal_id)
        if (
            animal is None
            or animal.status != "active"
            or animal.organization_id != self.qr_codes.organization_id
            or candidate.organization_id != self.qr_codes.organization_id
        ):
            raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
        await self.qr_codes.lock_animal(animal.id)
        current = await self.qr_codes.get(qr_code_id)
        active = await self.qr_codes.active_for_animal(animal.id)
        if (
            current is None
            or current.status != "active"
            or current.revoked
            or active is None
            or active.id != current.id
        ):
            raise DomainError("qr_code_not_found", "QR Code 不存在或無法存取", 404)
        await self.qr_codes.revoke(current.id)
        replacement_id = uuid4()
        raw_token = issue_printable_qr_token(replacement_id)
        replacement = await self.qr_codes.create(
            AnimalQrCode(
                id=replacement_id,
                organization_id=animal.organization_id,
                animal_id=animal.id,
                token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
                status="active",
                revoked=False,
            )
        )
        return replacement, raw_token

    async def revoke(self, *, qr_code_id: UUID) -> AnimalQrCode:
        return await self.qr_codes.revoke(qr_code_id)

    async def resolve(self, *, raw_token: str) -> tuple[AnimalQrCode, UUID]:
        qr_code = await self.qr_codes.resolve(raw_token)
        if qr_code is None:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        animal = await self.animals.get(qr_code.animal_id)
        if animal is None or animal.status != "active":
            raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
        if animal.organization_id != qr_code.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        return qr_code, animal.id
