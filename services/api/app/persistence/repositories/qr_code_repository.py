from __future__ import annotations

from hashlib import sha256
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.qr_code import AnimalQrCode


class QrCodeRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def resolve(self, raw_token: str) -> AnimalQrCode | None:
        digest = sha256(raw_token.encode("utf-8")).hexdigest()
        result = await self.session.execute(
            select(AnimalQrCode).where(
                AnimalQrCode.token_digest == digest,
                AnimalQrCode.organization_id == self.organization_id,
                AnimalQrCode.status == "active",
                AnimalQrCode.revoked.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def lock_animal(self, animal_id: UUID) -> None:
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"animal-care-qr:{self.organization_id}:{animal_id}"},
        )

    async def active_for_animal(self, animal_id: UUID) -> AnimalQrCode | None:
        result = await self.session.execute(
            select(AnimalQrCode)
            .where(
                AnimalQrCode.organization_id == self.organization_id,
                AnimalQrCode.animal_id == animal_id,
                AnimalQrCode.status == "active",
                AnimalQrCode.revoked.is_(False),
            )
            .order_by(AnimalQrCode.created_at.desc(), AnimalQrCode.id.desc())
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get(self, qr_code_id: UUID) -> AnimalQrCode | None:
        result = await self.session.execute(
            select(AnimalQrCode).where(
                AnimalQrCode.id == qr_code_id,
                AnimalQrCode.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, qr_code: AnimalQrCode) -> AnimalQrCode:
        if qr_code.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        self.session.add(qr_code)
        await self.session.flush()
        return qr_code

    async def revoke(self, qr_code_id: UUID) -> AnimalQrCode:
        result = await self.session.execute(
            select(AnimalQrCode).where(
                AnimalQrCode.id == qr_code_id,
                AnimalQrCode.organization_id == self.organization_id,
            )
        )
        qr_code = result.scalar_one_or_none()
        if qr_code is None:
            raise DomainError("qr_token_not_found", "QR Token 不存在或無法存取", 404)
        qr_code.revoked = True
        qr_code.status = "revoked"
        await self.session.flush()
        return qr_code
