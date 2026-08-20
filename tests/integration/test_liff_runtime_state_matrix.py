import os
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.application.authentication.session_service import SessionService
from services.api.app.persistence.repositories.authentication_repository import (
    AuthenticationRepository,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class LineVerifier:
    async def verify(self, _id_token: str) -> str:
        return "U-runtime-state-matrix"


class EntryResolver:
    def __init__(self, organization_id) -> None:
        self.organization_id = organization_id

    async def resolve(self, _raw_reference: str):
        return SimpleNamespace(
            organization_id=self.organization_id,
            organization_code="RUNTIME-MATRIX",
            organization_name="Runtime matrix shelter",
        )


class TokenMustNotIssue:
    def issue(self, _claims):
        raise AssertionError("SUSPENDED exchange must not issue an access token")


def database_url() -> str:
    return os.environ["STRAYHUB_TEST_DATABASE_URL"]


def async_database_url() -> str:
    return database_url().replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("membership_status", "membership_period", "grant_status"),
    [
        ("active", "future", "active"),
        ("active", "expired", "active"),
        ("active", "current", "revoked"),
        ("active", "current", "expired"),
    ],
    ids=["future-membership", "expired-membership", "revoked-grant", "expired-grant"],
)
async def test_real_runtime_invalid_access_is_suspended_without_credentials(
    membership_status: str, membership_period: str, grant_status: str
) -> None:
    setup = await asyncpg.connect(database_url())
    engine = create_async_engine(async_database_url())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid4()
    organization_id = uuid4()
    membership_id = uuid4()
    application_id = uuid4()
    grant_id = uuid4()
    binding_id = uuid4()
    try:
        await setup.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Runtime matrix shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"MATRIX-{organization_id.hex[:12]}",
        )
        await setup.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Runtime matrix user', 'active', now(), now())
            """,
            user_id,
            f"runtime-matrix-{user_id.hex}",
        )
        await setup.execute(
            """
            INSERT INTO line_user_bindings
              (id, line_user_id, user_id, status, created_at, updated_at)
            VALUES ($1, 'U-runtime-state-matrix', $2, 'active', now(), now())
            """,
            binding_id,
            user_id,
        )
        membership_period_sql = {
            "future": "now() + interval '1 day', now() + interval '2 days'",
            "expired": "now() - interval '2 days', now() - interval '1 day'",
            "current": "now() - interval '1 day', now() + interval '1 day'",
        }[membership_period]
        await setup.execute(
            f"""
            INSERT INTO organization_memberships
              (id, organization_id, user_id, role, status, valid_from, expires_at,
               created_at, updated_at)
            VALUES ($1, $2, $3, 'VOLUNTEER', $4, {membership_period_sql}, now(), now())
            """,
            membership_id,
            organization_id,
            user_id,
            membership_status,
        )
        await setup.execute(
            """
            INSERT INTO volunteer_applications
              (id, organization_id, user_id, status, source_channel, submitted_at,
               decided_at, decided_by_user_id, created_at, updated_at)
            VALUES ($1, $2, $3, 'approved', 'liff', now(), now(), $3, now(), now())
            """,
            application_id,
            organization_id,
            user_id,
        )
        await setup.execute(
            """
            INSERT INTO volunteer_access_grants
              (id, organization_id, user_id, membership_id, application_id, status,
               valid_from, expires_at, approved_at, source_type,
               revoked_at, revoked_by_user_id, revocation_reason, created_at, updated_at)
            VALUES
              ($1, $2, $3::uuid, $4, $5, $6::varchar, now() - interval '1 day',
               now() + interval '1 day', now(), 'manager_approval',
               CASE WHEN $6::varchar = 'revoked' THEN now() ELSE NULL END,
               CASE WHEN $6::varchar = 'revoked' THEN $3::uuid ELSE NULL END,
               CASE WHEN $6::varchar = 'revoked' THEN 'runtime matrix' ELSE NULL END,
               now(), now())
            """,
            grant_id,
            organization_id,
            user_id,
            membership_id,
            application_id,
            grant_status,
        )

        async with session_factory() as session:
            result = await SessionService(
                AuthenticationRepository(session),
                password_hasher=SimpleNamespace(),
                access_token=TokenMustNotIssue(),
                line_verifier=LineVerifier(),
                entry_resolver=EntryResolver(organization_id),
            ).exchange_line_identity(
                id_token="valid-runtime-token",
                shelter_entry_reference="runtime-entry-reference",
            )
            await session.rollback()

        assert result["state"] == "SUSPENDED"
        assert "access_token" not in result
        assert (
            await setup.fetchval("SELECT count(*) FROM session_records WHERE user_id = $1", user_id)
            == 0
        )
        assert (
            await setup.fetchval(
                """
                SELECT count(*)
                FROM refresh_token_records refresh
                JOIN session_records session ON session.id = refresh.session_id
                WHERE session.user_id = $1
                """,
                user_id,
            )
            == 0
        )
    finally:
        await setup.execute("DELETE FROM volunteer_access_grants WHERE id = $1", grant_id)
        await setup.execute("DELETE FROM volunteer_applications WHERE id = $1", application_id)
        await setup.execute("DELETE FROM organization_memberships WHERE id = $1", membership_id)
        await setup.execute("DELETE FROM line_user_bindings WHERE id = $1", binding_id)
        await setup.execute("DELETE FROM organizations WHERE id = $1", organization_id)
        await setup.execute("DELETE FROM users WHERE id = $1", user_id)
        await setup.close()
        await engine.dispose()
