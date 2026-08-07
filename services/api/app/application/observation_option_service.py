from __future__ import annotations

from uuid import UUID

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.persistence.models.observation import ObservationOption
from services.api.app.persistence.repositories.observation_repository import ObservationRepository


class ObservationOptionService:
    def __init__(
        self, repository: ObservationRepository, *, audit: AuditService | None = None
    ) -> None:
        self.repository = repository
        self.audit = audit

    async def create(
        self,
        *,
        category_id: UUID,
        code: str,
        display_name: str,
        description: str = "",
        requires_note: bool = False,
        actor_user_id: UUID | None = None,
    ) -> ObservationOption:
        option = await self.repository.add_option(
            ObservationOption(
                category_id=category_id,
                organization_id=self.repository.organization_id,
                code=code,
                display_name=display_name,
                description=description,
                requires_note=requires_note,
                status="active",
            )
        )
        if self.audit is not None:
            await self.audit.record(
                organization_id=option.organization_id,
                actor_user_id=actor_user_id,
                action="observation_option.created",
                resource_type="ObservationOption",
                resource_id=option.id,
                source_channel="api",
                after={"code": option.code, "display_name": option.display_name},
            )
        return option

    async def update(
        self,
        option_id: UUID,
        *,
        display_name: str | None = None,
        description: str | None = None,
        display_order: int | None = None,
        enabled: bool | None = None,
        actor_user_id: UUID | None = None,
    ) -> ObservationOption:
        option = await self.repository.get_option(option_id)
        if option is None:
            raise DomainError("option_not_found", "觀察選項不存在或無法存取", 404)
        if display_name is not None:
            option.display_name = display_name
        if description is not None:
            option.description = description
        if display_order is not None:
            option.display_order = display_order
        if enabled is not None:
            option.status = "active" if enabled else "disabled"
        if self.audit is not None:
            await self.audit.record(
                organization_id=option.organization_id,
                actor_user_id=actor_user_id,
                action="observation_option.updated",
                resource_type="ObservationOption",
                resource_id=option.id,
                source_channel="api",
                after={
                    "display_name": option.display_name,
                    "description": option.description,
                    "display_order": option.display_order,
                    "status": option.status,
                },
            )
        return option

    async def disable(
        self, option_id: UUID, *, actor_user_id: UUID | None = None
    ) -> ObservationOption:
        option = await self.repository.get_option(option_id)
        if option is None:
            raise DomainError("option_not_found", "觀察選項不存在或無法存取", 404)
        option.status = "disabled"
        if self.audit is not None:
            await self.audit.record(
                organization_id=option.organization_id,
                actor_user_id=actor_user_id,
                action="observation_option.disabled",
                resource_type="ObservationOption",
                resource_id=option.id,
                source_channel="api",
                after={"status": option.status},
            )
        return option
