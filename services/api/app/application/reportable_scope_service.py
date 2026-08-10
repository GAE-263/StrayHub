from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError
from services.api.app.persistence.models.animal import Animal
from services.api.app.persistence.models.identity import OrganizationMembership
from services.api.app.persistence.models.shelter_area import ShelterArea


def can_report(
    *, organization_id: UUID, animal_organization_id: UUID, animal_status: str, scope_active: bool
) -> bool:
    if organization_id != animal_organization_id:
        raise DomainError("cross_tenant_access", "無法存取其他收容所資料", 404)
    if animal_status != "active" or not scope_active:
        return False
    return True


def scope_is_current(
    *, starts_at: datetime, ends_at: datetime, now: datetime | None = None
) -> bool:
    current = now or datetime.now(timezone.utc)
    return starts_at <= current <= ends_at


async def require_reportable_scope(
    repository,
    *,
    animal_id: UUID,
    volunteer_user_id: UUID,
) -> None:
    if not await repository.is_animal_reportable(
        animal_id=animal_id,
        volunteer_user_id=volunteer_user_id,
    ):
        raise DomainError("animal_not_reportable", "動物目前不在你的今日可回報範圍", 403)


class ReportableScopeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def validate_target(
        self,
        *,
        organization_id: UUID,
        animal_id: UUID | None,
        area_id: UUID | None,
        volunteer_user_id: UUID | None,
        starts_at: datetime,
        ends_at: datetime,
    ) -> None:
        if animal_id is None and area_id is None:
            raise DomainError("scope_target_required", "必須指定動物或區域", 422)
        if ends_at <= starts_at:
            raise DomainError("invalid_scope_window", "可回報範圍的時間區間無效", 422)
        if animal_id is not None:
            animal = await self.session.scalar(
                select(Animal).where(
                    Animal.id == animal_id,
                    Animal.organization_id == organization_id,
                    Animal.status == "active",
                )
            )
            if animal is None:
                raise DomainError("animal_not_found", "動物不存在或無法存取", 404)
        if area_id is not None:
            area = await self.session.scalar(
                select(ShelterArea).where(
                    ShelterArea.id == area_id,
                    ShelterArea.organization_id == organization_id,
                    ShelterArea.status == "active",
                )
            )
            if area is None:
                raise DomainError("area_not_found", "Cage／Area 不存在或無法存取", 404)
        if volunteer_user_id is not None:
            volunteer = await self.session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.user_id == volunteer_user_id,
                    OrganizationMembership.role == "VOLUNTEER",
                    OrganizationMembership.status == "active",
                )
            )
            if volunteer is None:
                raise DomainError("volunteer_not_found", "指定志工不存在或無法存取", 404)
