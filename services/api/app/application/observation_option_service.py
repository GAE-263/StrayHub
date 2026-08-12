from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID, uuid4

from services.api.app.api.errors import DomainError
from services.api.app.application.audit_service import AuditService
from services.api.app.persistence.models.observation import ObservationOption
from services.api.app.persistence.repositories.observation_repository import ObservationRepository

STABLE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.]*$")
OPTION_STATUSES = {"active", "disabled", "archived"}


def _option_snapshot(option: ObservationOption) -> dict:
    return {
        "category_id": str(option.category_id),
        "code": option.code,
        "display_name": option.display_name,
        "description": option.description,
        "display_order": option.display_order,
        "requires_note": option.requires_note,
        "status": option.status,
        "source": "platform_default"
        if option.organization_id is None
        else "organization_extension",
    }


def _changed_payload(before: dict, after: dict) -> tuple[dict, dict]:
    changed = {key for key in after if before.get(key) != after.get(key)}
    return (
        {key: before[key] for key in changed if key in before},
        {key: after[key] for key in changed if key in after},
    )


class ObservationOptionService:
    def __init__(
        self,
        repository: ObservationRepository,
        *,
        audit: AuditService | None = None,
        usage=None,
    ) -> None:
        self.repository = repository
        self.audit = audit
        self.usage = usage

    @staticmethod
    def _validate_code(code: str) -> str:
        value = code.strip()
        if not value or len(value) > 120 or not STABLE_CODE_PATTERN.fullmatch(value):
            raise DomainError(
                "invalid_observation_code",
                "stable code 必須在 120 字元內，以小寫英文字母開頭，"
                "只能包含小寫英文字母、數字、底線或句點",
                422,
            )
        return value

    @staticmethod
    def _check_version(option: ObservationOption, expected_updated_at: datetime | None) -> None:
        if expected_updated_at is None or getattr(option, "updated_at", None) is None:
            return
        current = option.updated_at
        if current is not None and current != expected_updated_at:
            raise DomainError(
                "data_changed",
                "資料已由其他人更新，請重新確認最新內容後再儲存",
                409,
            )

    async def _audit_mutation(
        self,
        *,
        option: ObservationOption,
        action: str,
        before: dict | None,
        after: dict,
        actor_user_id: UUID | None,
        operation_id: UUID,
        reason: str | None = None,
    ) -> None:
        if self.audit is None:
            return
        if option.organization_id is None or actor_user_id is None:
            raise DomainError("audit_scope_required", "觀察選項異動缺少稽核範圍", 500)
        await self.audit.record(
            organization_id=option.organization_id,
            actor_user_id=actor_user_id,
            operation_id=operation_id,
            action=action,
            resource_type="ObservationOption",
            resource_id=option.id,
            source_channel="api",
            before=before,
            after=after,
            reason=reason,
            result="success",
        )

    async def create(
        self,
        *,
        category_id: UUID,
        code: str,
        display_name: str,
        description: str = "",
        display_order: int = 0,
        requires_note: bool = False,
        actor_user_id: UUID | None = None,
    ) -> ObservationOption:
        code = self._validate_code(code)
        display_name = display_name.strip()
        if not display_name:
            raise DomainError("invalid_observation_option", "中文名稱不可為空白", 422)
        if len(display_name) > 200:
            raise DomainError("invalid_observation_option", "中文名稱不可超過 200 字元", 422)
        if len(description.strip()) > 500:
            raise DomainError("invalid_observation_option", "說明不可超過 500 字元", 422)
        if display_order < 0:
            raise DomainError("invalid_observation_option", "排序不可小於 0", 422)
        category = await self.repository.get_category(category_id)
        if category is None or category.status != "active":
            raise DomainError("category_not_found", "觀察類別不存在或已停用", 404)
        if await self.repository.option_code_exists(code):
            raise DomainError(
                "option_code_conflict", "目前收容所已有相同 stable code（Code 已存在）", 409
            )
        option = await self.repository.add_option(
            ObservationOption(
                category_id=category_id,
                organization_id=self.repository.organization_id,
                code=code,
                display_name=display_name,
                description=description.strip(),
                display_order=display_order,
                requires_note=requires_note,
                status="active",
            )
        )
        operation_id = uuid4()
        await self._audit_mutation(
            option=option,
            action="observation_option.created",
            before=None,
            after=_option_snapshot(option),
            actor_user_id=actor_user_id,
            operation_id=operation_id,
        )
        return option

    async def update(
        self,
        option_id: UUID,
        *,
        code: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        display_order: int | None = None,
        requires_note: bool | None = None,
        enabled: bool | None = None,
        expected_updated_at: datetime | None = None,
        actor_user_id: UUID | None = None,
    ) -> ObservationOption:
        option = await self.repository.get_option(option_id)
        if option is None:
            raise DomainError("option_not_found", "觀察選項不存在或無法存取", 404)
        if option.organization_id is None:
            raise DomainError("platform_option_read_only", "平台預設觀察選項不可修改", 403)
        self._check_version(option, expected_updated_at)
        if code is not None:
            code = self._validate_code(code)
            if code != option.code:
                if self.usage is not None and await self.usage.has_usage(option.id):
                    raise DomainError(
                        "stable_code_locked",
                        "此選項已有歷史回報使用，stable code 已鎖定",
                        409,
                    )
                if await self.repository.option_code_exists_for_update(code, exclude_id=option.id):
                    raise DomainError(
                        "option_code_conflict", "目前收容所已有相同 stable code（Code 已存在）", 409
                    )
        if display_name is not None:
            if not display_name.strip():
                raise DomainError("invalid_observation_option", "中文名稱不可為空白", 422)
            if len(display_name.strip()) > 200:
                raise DomainError("invalid_observation_option", "中文名稱不可超過 200 字元", 422)
        if description is not None and len(description.strip()) > 500:
            raise DomainError("invalid_observation_option", "說明不可超過 500 字元", 422)
        if display_order is not None and display_order < 0:
            raise DomainError("invalid_observation_option", "排序不可小於 0", 422)
        before_full = _option_snapshot(option)
        if code is not None:
            option.code = code
        if display_name is not None:
            option.display_name = display_name.strip()
        if description is not None:
            option.description = description.strip()
        if display_order is not None:
            option.display_order = display_order
        if requires_note is not None:
            option.requires_note = requires_note
        if enabled is not None:
            option.status = "active" if enabled else "disabled"
        after_full = _option_snapshot(option)
        before, after = _changed_payload(before_full, after_full)
        if not after:
            return option
        await self._audit_mutation(
            option=option,
            action="observation_option.updated",
            before=before,
            after=after,
            actor_user_id=actor_user_id,
            operation_id=uuid4(),
        )
        return option

    async def _transition(
        self,
        option_id: UUID,
        *,
        target: str,
        action: str,
        actor_user_id: UUID | None,
        reason: str | None = None,
    ) -> ObservationOption:
        if target not in OPTION_STATUSES:
            raise DomainError("invalid_option_status", "觀察選項狀態無效", 422)
        option = await self.repository.get_option(option_id)
        if option is None:
            raise DomainError("option_not_found", "觀察選項不存在或無法存取", 404)
        if option.organization_id is None:
            raise DomainError("platform_option_read_only", "平台預設觀察選項不可變更狀態", 403)
        if option.status == target:
            return option
        before_full = _option_snapshot(option)
        option.status = target
        after_full = _option_snapshot(option)
        before, after = _changed_payload(before_full, after_full)
        await self._audit_mutation(
            option=option,
            action=action,
            before=before,
            after=after,
            actor_user_id=actor_user_id,
            operation_id=uuid4(),
            reason=reason,
        )
        return option

    async def disable(
        self, option_id: UUID, *, actor_user_id: UUID | None = None
    ) -> ObservationOption:
        return await self._transition(
            option_id,
            target="disabled",
            action="observation_option.disabled",
            actor_user_id=actor_user_id,
        )

    async def restore(
        self, option_id: UUID, *, actor_user_id: UUID | None = None
    ) -> ObservationOption:
        return await self._transition(
            option_id,
            target="active",
            action="observation_option.restored",
            actor_user_id=actor_user_id,
        )

    async def archive(
        self,
        option_id: UUID,
        *,
        actor_user_id: UUID | None = None,
        reason: str | None = None,
    ) -> ObservationOption:
        return await self._transition(
            option_id,
            target="archived",
            action="observation_option.archived",
            actor_user_id=actor_user_id,
            reason=reason,
        )

    async def reorder(
        self,
        option_ids: list[UUID],
        *,
        display_orders: dict[UUID, int] | None = None,
        actor_user_id: UUID | None = None,
    ) -> list[ObservationOption]:
        if not option_ids or len(option_ids) != len(set(option_ids)):
            raise DomainError("invalid_observation_order", "排序清單不可為空或包含重複選項", 422)
        options: list[ObservationOption] = []
        for option_id in option_ids:
            option = await self.repository.get_option(option_id)
            if option is None:
                raise DomainError("option_not_found", "觀察選項不存在或無法存取", 404)
            if option.organization_id is None:
                raise DomainError("platform_option_read_only", "平台預設觀察選項不可排序", 403)
            options.append(option)
        category_ids = {option.category_id for option in options}
        if len(category_ids) != 1:
            raise DomainError("invalid_observation_order", "只能排序同一觀察類別的自訂選項", 422)
        orders = display_orders or {option_id: index for index, option_id in enumerate(option_ids)}
        if any(value < 0 for value in orders.values()):
            raise DomainError("invalid_observation_order", "排序不可小於 0", 422)
        operation_id = uuid4()
        changed: list[ObservationOption] = []
        for option in options:
            target = orders.get(option.id, option.display_order)
            if target == option.display_order:
                continue
            before = {"display_order": option.display_order, "category_id": str(option.category_id)}
            option.display_order = target
            after = {"display_order": target, "category_id": str(option.category_id)}
            await self._audit_mutation(
                option=option,
                action="observation_option.reordered",
                before=before,
                after=after,
                actor_user_id=actor_user_id,
                operation_id=operation_id,
            )
            changed.append(option)
        return options
