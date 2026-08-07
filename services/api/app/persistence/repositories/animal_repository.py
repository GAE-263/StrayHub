from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.animal import Animal


class AnimalRepository:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def get(self, animal_id: UUID) -> Animal | None:
        result = await self.session.execute(
            select(Animal).where(
                Animal.id == animal_id, Animal.organization_id == self.organization_id
            )
        )
        return result.scalar_one_or_none()

    async def search(self, query: str) -> list[Animal]:
        pattern = f"%{query}%"
        result = await self.session.execute(
            select(Animal).where(
                Animal.organization_id == self.organization_id,
                Animal.status == "active",
                or_(Animal.shelter_number.ilike(pattern), Animal.name.ilike(pattern)),
            )
        )
        return list(result.scalars())

    async def list_active(self) -> list[Animal]:
        result = await self.session.execute(
            select(Animal)
            .where(
                Animal.organization_id == self.organization_id,
                Animal.status == "active",
            )
            .order_by(Animal.name, Animal.shelter_number, Animal.id)
        )
        return list(result.scalars())

    async def add(self, animal: Animal) -> Animal:
        if animal.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        self.session.add(animal)
        await self.session.flush()
        return animal
