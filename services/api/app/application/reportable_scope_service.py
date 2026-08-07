from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from services.api.app.api.errors import DomainError


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
