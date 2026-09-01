from __future__ import annotations

import os
from pathlib import Path

import pytest
from scripts.bootstrap_platform_admin import (
    CONFIRMATION_ENV,
    DEFAULT_USERNAME,
    MINIMUM_PASSWORD_LENGTH,
    PASSWORD_FILE_ENV,
    bootstrap_platform_admin,
    read_bootstrap_password,
    validate_execution_guard,
)
from services.api.app.persistence.database.engine import engine, session_factory
from services.api.app.persistence.database.scope import set_platform_scope
from services.api.app.persistence.models.audit import AuditRecord
from services.api.app.persistence.models.identity import OrganizationMembership, User
from sqlalchemy import func, select

PASSWORD = "production-platform-admin-test-password"


def test_platform_admin_bootstrap_guard_is_production_only() -> None:
    validate_execution_guard(
        app_env="production",
        allow_value="true",
        confirmed_username=DEFAULT_USERNAME,
    )
    with pytest.raises(RuntimeError, match="environment_denied"):
        validate_execution_guard(
            app_env="local", allow_value="true", confirmed_username=DEFAULT_USERNAME
        )
    with pytest.raises(RuntimeError, match="not_allowed"):
        validate_execution_guard(
            app_env="production", allow_value=None, confirmed_username=DEFAULT_USERNAME
        )
    with pytest.raises(RuntimeError, match="confirmation_required"):
        validate_execution_guard(
            app_env="production", allow_value="true", confirmed_username="wrong-user"
        )
    assert CONFIRMATION_ENV == "STRAYHUB_ALLOW_PLATFORM_ADMIN_BOOTSTRAP"


def test_platform_admin_bootstrap_requires_protected_password_file(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="password_file_required"):
        read_bootstrap_password({})

    password_file = tmp_path / "platform-admin-password"
    password_file.write_text(PASSWORD, encoding="utf-8")
    password_file.chmod(0o644)
    with pytest.raises(RuntimeError, match="permissions_must_be_0600"):
        read_bootstrap_password({PASSWORD_FILE_ENV: os.fspath(password_file)})

    password_file.chmod(0o600)
    assert read_bootstrap_password({PASSWORD_FILE_ENV: os.fspath(password_file)}) == PASSWORD
    assert len(PASSWORD) >= MINIMUM_PASSWORD_LENGTH


@pytest.mark.asyncio
async def test_platform_admin_bootstrap_is_idempotent_audited_and_tenantless() -> None:
    await engine.dispose(close=False)
    async with session_factory() as session:
        await set_platform_scope(session)
        existing = await session.scalar(select(User).where(User.username == DEFAULT_USERNAME))
        if existing is not None:
            await session.delete(existing)
            await session.flush()

        first = await bootstrap_platform_admin(session, password=PASSWORD)
        second = await bootstrap_platform_admin(session, password=PASSWORD)
        with pytest.raises(RuntimeError, match="account_collision"):
            await bootstrap_platform_admin(
                session,
                password="different-production-platform-password",
            )

        assert first.status == "created"
        assert second.status == "reused"
        assert first.user_id == second.user_id
        user = await session.get(User, first.user_id)
        assert user is not None
        assert user.status == "active"
        assert user.platform_role == "PLATFORM_ADMIN"
        assert (
            await session.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.user_id == user.id
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count(AuditRecord.id)).where(
                    AuditRecord.resource_id == user.id,
                    AuditRecord.action == "platform_admin.created",
                    AuditRecord.actor_reference == "platform-admin-bootstrap",
                )
            )
            == 1
        )
        await session.rollback()
