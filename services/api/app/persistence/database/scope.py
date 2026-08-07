from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError


async def set_organization_scope(session: AsyncSession, organization_id: UUID) -> None:
    if not organization_id:
        raise DomainError("organization_scope_required", "缺少收容所資料範圍", 403)
    await session.execute(
        text("SELECT set_config('app.current_org_id', :organization_id, true)"),
        {"organization_id": str(organization_id)},
    )
    await session.execute(text("SELECT set_config('app.platform_scope', 'false', true)"))


async def set_platform_scope(session: AsyncSession, enabled: bool = True) -> None:
    if not enabled:
        raise DomainError("platform_scope_denied", "不得關閉受控平台範圍", 403)
    await session.execute(text("SELECT set_config('app.current_org_id', '', true)"))
    await session.execute(text("SELECT set_config('app.platform_scope', 'true', true)"))
