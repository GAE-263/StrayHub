from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.shelter_area import ShelterArea


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

    async def list_adoptable(self) -> list[Animal]:
        result = await self.session.execute(
            select(Animal)
            .where(
                Animal.organization_id == self.organization_id,
                Animal.status == "active",
                Animal.is_adoptable.is_(True),
            )
            .order_by(Animal.name, Animal.shelter_number, Animal.id)
        )
        return list(result.scalars())

    async def list_adoptable_page(
        self, *, page: int = 1, query: str = "", limit: int = 12
    ) -> tuple[list[Animal], int]:
        predicates = [
            Animal.organization_id == self.organization_id,
            Animal.status == "active",
            Animal.is_adoptable.is_(True),
        ]
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            predicates.append(
                or_(
                    Animal.name.ilike(pattern, escape="\\"),
                    Animal.shelter_number.ilike(pattern, escape="\\"),
                )
            )
        total = int(
            await self.session.scalar(select(func.count(Animal.id)).where(*predicates)) or 0
        )
        last_page = max(1, (total + limit - 1) // limit)
        page = max(1, min(page, last_page))
        result = await self.session.execute(
            select(Animal)
            .where(*predicates)
            .order_by(Animal.name, Animal.shelter_number, Animal.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(result.scalars()), total

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

    async def list_active_with_area(self) -> list[tuple[Animal, ShelterArea | None]]:
        result = await self.session.execute(
            select(Animal, ShelterArea)
            .outerjoin(
                ShelterArea,
                and_(
                    ShelterArea.id == Animal.area_id,
                    ShelterArea.organization_id == Animal.organization_id,
                    ShelterArea.status == "active",
                ),
            )
            .where(
                Animal.organization_id == self.organization_id,
                Animal.status == "active",
            )
            .order_by(Animal.name, Animal.shelter_number, Animal.id)
        )
        return list(result.all())

    async def search_with_area(self, query: str) -> list[tuple[Animal, ShelterArea | None]]:
        pattern = f"%{query.strip()}%"
        result = await self.session.execute(
            select(Animal, ShelterArea)
            .outerjoin(
                ShelterArea,
                and_(
                    ShelterArea.id == Animal.area_id,
                    ShelterArea.organization_id == Animal.organization_id,
                    ShelterArea.status == "active",
                ),
            )
            .where(
                Animal.organization_id == self.organization_id,
                Animal.status == "active",
                or_(Animal.shelter_number.ilike(pattern), Animal.name.ilike(pattern)),
            )
            .order_by(Animal.name, Animal.shelter_number, Animal.id)
        )
        return list(result.all())

    async def search_with_area_page(
        self, query: str, *, offset: int, limit: int
    ) -> tuple[list[tuple[Animal, ShelterArea | None]], int]:
        normalized = query.strip()
        if not normalized:
            return [], 0
        predicate = and_(
            Animal.organization_id == self.organization_id,
            Animal.status == "active",
            or_(
                Animal.shelter_number.ilike(f"%{normalized}%"),
                Animal.name.ilike(f"%{normalized}%"),
            ),
        )
        total = int(
            (await self.session.scalar(select(func.count(Animal.id)).where(predicate))) or 0
        )
        result = await self.session.execute(
            select(Animal, ShelterArea)
            .outerjoin(
                ShelterArea,
                and_(
                    ShelterArea.id == Animal.area_id,
                    ShelterArea.organization_id == Animal.organization_id,
                    ShelterArea.status == "active",
                ),
            )
            .where(predicate)
            .order_by(Animal.name, Animal.shelter_number, Animal.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.all()), total

    async def get_with_area(self, animal_id: UUID) -> tuple[Animal, ShelterArea | None] | None:
        result = await self.session.execute(
            select(Animal, ShelterArea)
            .outerjoin(
                ShelterArea,
                and_(
                    ShelterArea.id == Animal.area_id,
                    ShelterArea.organization_id == Animal.organization_id,
                    ShelterArea.status == "active",
                ),
            )
            .where(
                Animal.id == animal_id,
                Animal.organization_id == self.organization_id,
            )
        )
        return result.first()

    async def add(self, animal: Animal) -> Animal:
        if animal.organization_id != self.organization_id:
            raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
        self.session.add(animal)
        await self.session.flush()
        return animal
