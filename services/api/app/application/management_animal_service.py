from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.shelter_area import ShelterArea


class ManagementAnimalService:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @staticmethod
    def payload(animal: Animal, area: ShelterArea | None) -> dict:
        return {
            "id": str(animal.id),
            "organization_id": str(animal.organization_id),
            "name": animal.name,
            "shelter_number": animal.shelter_number,
            "photo_key": animal.current_photo_key,
            "status": animal.status,
            "area_id": str(area.id) if area else None,
            "area_name": area.name if area else None,
            "area_type": area.area_type if area else None,
        }

    async def list(
        self,
        *,
        query: str | None,
        area_id: UUID | None,
        status: str,
        page: int,
        page_size: int,
    ) -> dict:
        filters = [Animal.organization_id == self.organization_id]
        if status != "all":
            filters.append(Animal.status == status)
        if area_id is not None:
            filters.append(Animal.area_id == area_id)
        if query:
            pattern = f"%{query}%"
            filters.append(or_(Animal.name.ilike(pattern), Animal.shelter_number.ilike(pattern)))
        total = await self.session.scalar(select(func.count(Animal.id)).where(*filters))
        rows = await self.session.execute(
            select(Animal, ShelterArea)
            .outerjoin(
                ShelterArea,
                and_(
                    ShelterArea.id == Animal.area_id,
                    ShelterArea.organization_id == self.organization_id,
                ),
            )
            .where(*filters)
            .order_by(Animal.name, Animal.shelter_number, Animal.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [self.payload(animal, area) for animal, area in rows.all()],
            "page": page,
            "page_size": page_size,
            "total": int(total or 0),
        }

    async def get(self, animal_id: UUID) -> dict:
        row = await self.session.execute(
            select(Animal, ShelterArea)
            .outerjoin(
                ShelterArea,
                and_(
                    ShelterArea.id == Animal.area_id,
                    ShelterArea.organization_id == self.organization_id,
                ),
            )
            .where(Animal.id == animal_id, Animal.organization_id == self.organization_id)
        )
        pair = row.one_or_none()
        if pair is None:
            raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        animal, area = pair
        return {"animal": self.payload(animal, area)}
