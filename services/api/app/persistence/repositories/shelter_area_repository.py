from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.shelter_area import ShelterArea


class ShelterAreaRepository:
    """All area/cage queries are scoped to one organization by construction."""

    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def list(self, *, include_inactive: bool = False) -> list[ShelterArea]:
        query = select(ShelterArea).where(ShelterArea.organization_id == self.organization_id)
        if not include_inactive:
            query = query.where(ShelterArea.status == "active")
        result = await self.session.execute(query.order_by(ShelterArea.name))
        return list(result.scalars())

    async def get(self, area_id: UUID) -> ShelterArea | None:
        result = await self.session.execute(
            select(ShelterArea).where(
                ShelterArea.id == area_id,
                ShelterArea.organization_id == self.organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, *, name: str, area_type: str, parent_id: UUID | None = None) -> ShelterArea:
        if area_type not in {"area", "cage"}:
            raise DomainError("invalid_area_type", "區域類型必須是 area 或 cage", 422)
        if parent_id is not None:
            parent = await self.get(parent_id)
            if parent is None:
                raise DomainError("parent_area_not_found", "上層區域不存在或不屬於此收容所", 422)
        area = ShelterArea(
            organization_id=self.organization_id,
            name=name,
            area_type=area_type,
            parent_id=parent_id,
            status="active",
        )
        self.session.add(area)
        await self.session.flush()
        return area

    async def update(
        self,
        area_id: UUID,
        *,
        name: str | None = None,
        area_type: str | None = None,
        parent_id: UUID | None = None,
        status: str | None = None,
    ) -> ShelterArea:
        area = await self.get(area_id)
        if area is None:
            raise DomainError("area_not_found", "區域不存在或無法存取", 404)
        if area_type is not None and area_type not in {"area", "cage"}:
            raise DomainError("invalid_area_type", "區域類型必須是 area 或 cage", 422)
        if status is not None and status not in {"active", "inactive"}:
            raise DomainError("invalid_area_status", "區域狀態無效", 422)
        if parent_id is not None and await self.get(parent_id) is None:
            raise DomainError("parent_area_not_found", "上層區域不存在或不屬於此收容所", 422)
        updates = (
            ("name", name),
            ("area_type", area_type),
            ("parent_id", parent_id),
            ("status", status),
        )
        for key, value in updates:
            if value is not None:
                setattr(area, key, value)
        await self.session.flush()
        return area
