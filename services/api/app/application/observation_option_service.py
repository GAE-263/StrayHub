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
        code = code.strip()
        display_name = display_name.strip()
        if not code or not display_name:
            raise DomainError("invalid_observation_option", "Code 與顯示名稱不可為空", 422)
        category = await self.repository.get_category(category_id)
        if category is None or category.status != "active":
            raise DomainError("category_not_found", "觀察類別不存在或已停用", 404)
        if await self.repository.option_code_exists(code):
            raise DomainError("option_code_conflict", "觀察選項 Code 已存在", 409)
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
        before = {
            "code": option.code,
            "display_name": option.display_name,
            "description": option.description,
            "display_order": option.display_order,
            "status": option.status,
        }
        if display_name is not None and not display_name.strip():
            raise DomainError("invalid_observation_option", "顯示名稱不可為空", 422)
        if display_order is not None and display_order < 0:
            raise DomainError("invalid_observation_option", "排序不可小於 0", 422)
        if display_name is not None:
            option.display_name = display_name.strip()
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
                before=before,
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

    async def reorder(
        self,
        option_ids: list[UUID],
        *,
        actor_user_id: UUID | None = None,
    ) -> list[ObservationOption]:
        if not option_ids or len(option_ids) != len(set(option_ids)):
            raise DomainError("invalid_observation_order", "排序清單不可為空或包含重複選項", 422)
        options = []
        for option_id in option_ids:
            option = await self.repository.get_option(option_id)
            if option is None:
                raise DomainError("option_not_found", "觀察選項不存在或無法存取", 404)
            options.append(option)
        for display_order, option in enumerate(options):
            before = option.display_order
            option.display_order = display_order
            if self.audit is not None:
                await self.audit.record(
                    organization_id=option.organization_id,
                    actor_user_id=actor_user_id,
                    action="observation_option.reordered",
                    resource_type="ObservationOption",
                    resource_id=option.id,
                    source_channel="api",
                    before={"display_order": before},
                    after={"display_order": display_order},
                )
        return options
