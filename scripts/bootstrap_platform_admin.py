"""Guarded one-shot bootstrap for the first production platform administrator."""

from __future__ import annotations

import argparse
import asyncio
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

ALLOWED_ENVIRONMENTS = frozenset({"production"})
CONFIRMATION_ENV = "STRAYHUB_ALLOW_PLATFORM_ADMIN_BOOTSTRAP"
PASSWORD_FILE_ENV = "PLATFORM_ADMIN_BOOTSTRAP_PASSWORD_FILE"
DEFAULT_USERNAME = "platform-admin"
DEFAULT_DISPLAY_NAME = "平台管理員"
MINIMUM_PASSWORD_LENGTH = 20

BootstrapStatus = Literal["created", "reused", "would_create"]


@dataclass(frozen=True)
class PlatformAdminBootstrapResult:
    status: BootstrapStatus
    user_id: UUID
    username: str


def validate_execution_guard(
    *, app_env: str | None, allow_value: str | None, confirmed_username: str | None
) -> None:
    environment = (app_env or "").strip().lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        raise RuntimeError("platform_admin_bootstrap_environment_denied")
    if (allow_value or "").strip().lower() != "true":
        raise RuntimeError(f"platform_admin_bootstrap_not_allowed: set {CONFIRMATION_ENV}=true")
    if (confirmed_username or "").strip() != DEFAULT_USERNAME:
        raise RuntimeError(
            f"platform_admin_bootstrap_confirmation_required: confirm {DEFAULT_USERNAME}"
        )


def read_bootstrap_password(environ: dict[str, str] | os._Environ[str]) -> str:
    raw_path = environ.get(PASSWORD_FILE_ENV, "").strip()
    if not raw_path:
        raise RuntimeError(
            f"platform_admin_bootstrap_password_file_required: set {PASSWORD_FILE_ENV}"
        )
    path = Path(raw_path)
    file_stat = path.stat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise RuntimeError("platform_admin_bootstrap_password_file_not_regular")
    if stat.S_IMODE(file_stat.st_mode) & 0o077:
        raise RuntimeError("platform_admin_bootstrap_password_file_permissions_must_be_0600")
    password = path.read_text(encoding="utf-8").rstrip("\r\n")
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise RuntimeError(
            f"platform_admin_bootstrap_password_too_short: minimum "
            f"{MINIMUM_PASSWORD_LENGTH} characters"
        )
    return password


async def bootstrap_platform_admin(
    session: AsyncSession,
    *,
    password: str,
    username: str = DEFAULT_USERNAME,
    display_name: str = DEFAULT_DISPLAY_NAME,
) -> PlatformAdminBootstrapResult:
    from services.api.app.application.audit_service import AuditService
    from services.api.app.application.platform_admin_management import (
        PlatformAdminManagementService,
    )
    from services.api.app.infrastructure.auth.password_hasher import Argon2PasswordHasher
    from services.api.app.persistence.database.scope import set_platform_scope
    from services.api.app.persistence.models.identity import OrganizationMembership
    from services.api.app.persistence.repositories.platform_admin_repository import (
        PlatformAdminRepository,
    )
    from sqlalchemy import func, select

    if username != DEFAULT_USERNAME:
        raise RuntimeError("platform_admin_bootstrap_username_denied")
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise RuntimeError("platform_admin_bootstrap_password_too_short")

    await set_platform_scope(session)
    repository = PlatformAdminRepository(session)
    policy = await repository.lock_policy()
    active_count = await repository.active_count()
    if active_count > policy.max_active_admins:
        raise RuntimeError("platform_admin_policy_invalid")

    hasher = Argon2PasswordHasher()
    existing = await repository.user_by_username(username)
    if existing is not None:
        membership_count = await session.scalar(
            select(func.count(OrganizationMembership.id)).where(
                OrganizationMembership.user_id == existing.id
            )
        )
        if (
            existing.platform_role != "PLATFORM_ADMIN"
            or existing.status != "active"
            or not existing.password_hash
            or not hasher.verify(password, existing.password_hash)
            or membership_count != 0
        ):
            raise RuntimeError("platform_admin_bootstrap_account_collision")
        return PlatformAdminBootstrapResult("reused", existing.id, username)

    if active_count >= policy.max_active_admins:
        raise RuntimeError("platform_admin_limit_reached")

    result = await PlatformAdminManagementService(repository, hasher).create(
        username=username,
        display_name=display_name,
        temporary_password=password,
    )
    await AuditService(session).record(
        organization_id=None,
        actor_user_id=None,
        actor_reference="platform-admin-bootstrap",
        action=result.action,
        resource_type="platform",
        resource_id=result.user.id,
        operation_id=result.operation_id,
        source_channel="operator_cli",
        before=result.before,
        after=result.after,
        reason="Create the initial production platform administrator",
    )
    return PlatformAdminBootstrapResult("created", result.user.id, username)


async def _run(args: argparse.Namespace) -> int:
    validate_execution_guard(
        app_env=os.getenv("APP_ENV"),
        allow_value=os.getenv(CONFIRMATION_ENV),
        confirmed_username=args.confirm_username,
    )
    password = read_bootstrap_password(os.environ)

    from services.api.app.config.settings import Settings
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    settings = Settings().validate_runtime_safety(process="migration")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            try:
                result = await bootstrap_platform_admin(session, password=password)
                if args.dry_run:
                    await session.rollback()
                else:
                    await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()

    status = "would_create" if args.dry_run and result.status == "created" else result.status
    print(
        f"Platform administrator bootstrap complete: {result.username} ({result.user_id}, {status})"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-username",
        required=True,
        help=f"must be exactly {DEFAULT_USERNAME}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and report the planned action, then roll back",
    )
    raise SystemExit(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
