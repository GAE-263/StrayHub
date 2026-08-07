from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.qr_code import AnimalQrCode
from services.api.app.persistence.repositories.animal_repository import AnimalRepository
from services.api.app.persistence.repositories.qr_code_repository import QrCodeRepository


class QrTokenService:
    def __init__(self, animals: AnimalRepository, qr_codes: QrCodeRepository) -> None:
        self.animals = animals
        self.qr_codes = qr_codes

    async def create(self, *, animal_id: UUID) -> tuple[AnimalQrCode, str]:
        animal = await self.animals.get(animal_id)
        if animal is None or animal.status != "active":
            raise DomainError("animal_not_found", "動物不存在或無法回報", 404)
        raw_token = secrets.token_urlsafe(32)
        qr_code = await self.qr_codes.create(
            AnimalQrCode(
                organization_id=animal.organization_id,
                animal_id=animal.id,
                token_digest=hashlib.sha256(raw_token.encode()).hexdigest(),
            )
        )
        return qr_code, raw_token

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
