from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.api.errors import DomainError


async def set_organization_scope(session: AsyncSession, organization_id: UUID) -> None:
    if not isinstance(organization_id, UUID):
        raise DomainError("organization_scope_required", "缺少收容所資料範圍", 403)
    await session.execute(
        text("SELECT set_config('app.current_org_id', :organization_id, true)"),
        {"organization_id": str(organization_id)},
    )
    await session.execute(text("SELECT set_config('app.platform_scope', 'false', true)"))
    await session.execute(text("SELECT set_config('app.platform_support', 'false', true)"))
    await session.execute(text("SELECT set_config('app.auth_user_id', '', true)"))
    await session.execute(text("SELECT set_config('app.auth_exact_org_id', '', true)"))
    await session.execute(
        text("SELECT set_config('app.public_volunteer_directory', 'false', true)")
    )
    await session.execute(text("SELECT set_config('app.public_adoption_directory', 'false', true)"))


async def set_platform_scope(session: AsyncSession, enabled: bool = True) -> None:
    if not enabled:
        raise DomainError("platform_scope_denied", "不得關閉受控平台範圍", 403)
    await session.execute(text("SELECT set_config('app.current_org_id', '', true)"))
    await session.execute(text("SELECT set_config('app.platform_scope', 'true', true)"))
    await session.execute(text("SELECT set_config('app.platform_support', 'false', true)"))
    await session.execute(text("SELECT set_config('app.auth_user_id', '', true)"))
    await session.execute(text("SELECT set_config('app.auth_exact_org_id', '', true)"))
    await session.execute(
        text("SELECT set_config('app.public_volunteer_directory', 'false', true)")
    )
    await session.execute(text("SELECT set_config('app.public_adoption_directory', 'false', true)"))


async def set_public_volunteer_directory_scope(session: AsyncSession) -> None:
    """Allow only the public volunteer directory projection for this transaction."""
    await set_platform_scope(session)
    await session.execute(text("SELECT set_config('app.public_volunteer_directory', 'true', true)"))


async def set_public_adoption_directory_scope(session: AsyncSession) -> None:
    """Expose only active shelters and their active adoptable-animal projection."""
    await session.execute(text("SELECT set_config('app.current_org_id', '', true)"))
    await session.execute(text("SELECT set_config('app.platform_scope', 'false', true)"))
    await session.execute(text("SELECT set_config('app.platform_support', 'false', true)"))
    await session.execute(text("SELECT set_config('app.auth_user_id', '', true)"))
    await session.execute(text("SELECT set_config('app.auth_exact_org_id', '', true)"))
    await session.execute(
        text("SELECT set_config('app.public_volunteer_directory', 'false', true)")
    )
    await session.execute(text("SELECT set_config('app.public_adoption_directory', 'true', true)"))


async def set_platform_support_scope(session: AsyncSession, target_organization_id: UUID) -> None:
    """Constrain a platform-support request to exactly one organization."""
    if not isinstance(target_organization_id, UUID):
        raise DomainError("platform_target_required", "平台支援必須指定單一收容所", 422)
    await session.execute(
        text("SELECT set_config('app.current_org_id', :organization_id, true)"),
        {"organization_id": str(target_organization_id)},
    )
    await session.execute(text("SELECT set_config('app.platform_scope', 'false', true)"))
    await session.execute(text("SELECT set_config('app.platform_support', 'true', true)"))
    await session.execute(text("SELECT set_config('app.auth_user_id', '', true)"))
    await session.execute(text("SELECT set_config('app.auth_exact_org_id', '', true)"))
    await session.execute(
        text("SELECT set_config('app.public_volunteer_directory', 'false', true)")
    )
    await session.execute(text("SELECT set_config('app.public_adoption_directory', 'false', true)"))


async def set_authentication_user_scope(session: AsyncSession, user_id: UUID) -> None:
    """Allow pre-context authentication queries to see only this user's membership."""
    if not isinstance(user_id, UUID):
        raise DomainError("invalid_scope", "使用者範圍無效", 400)
    await session.execute(
        text("SELECT set_config('app.auth_user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )
    await session.execute(text("SELECT set_config('app.current_org_id', '', true)"))
    await session.execute(text("SELECT set_config('app.auth_exact_org_id', '', true)"))
    await session.execute(text("SELECT set_config('app.platform_scope', 'false', true)"))
    await session.execute(text("SELECT set_config('app.platform_support', 'false', true)"))
    await session.execute(
        text("SELECT set_config('app.public_volunteer_directory', 'false', true)")
    )
    await session.execute(text("SELECT set_config('app.public_adoption_directory', 'false', true)"))


async def set_authentication_user_organization_scope(
    session: AsyncSession, user_id: UUID, organization_id: UUID
) -> None:
    """Constrain authentication queries to one user in one resolved organization."""
    if not isinstance(user_id, UUID) or not isinstance(organization_id, UUID):
        raise DomainError("invalid_scope", "使用者或收容所範圍無效", 400)
    await session.execute(
        text("SELECT set_config('app.auth_user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )
    await session.execute(
        text("SELECT set_config('app.auth_exact_org_id', :organization_id, true)"),
        {"organization_id": str(organization_id)},
    )
    await session.execute(text("SELECT set_config('app.current_org_id', '', true)"))
    await session.execute(text("SELECT set_config('app.platform_scope', 'false', true)"))
    await session.execute(text("SELECT set_config('app.platform_support', 'false', true)"))
    await session.execute(
        text("SELECT set_config('app.public_volunteer_directory', 'false', true)")
    )
    await session.execute(text("SELECT set_config('app.public_adoption_directory', 'false', true)"))
