import os
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.persistence.database.scope import (
    set_authentication_user_organization_scope,
    set_authentication_user_scope,
    set_organization_scope,
    set_platform_scope,
    set_platform_support_scope,
    set_public_volunteer_directory_scope,
)


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict]] = []

    async def execute(self, statement, parameters=None):
        self.statements.append((str(statement), parameters or {}))


@pytest.mark.asyncio
async def test_scope_setter_uses_transaction_local_parameterized_settings() -> None:
    session = RecordingSession()
    organization_id = uuid4()

    await set_organization_scope(session, organization_id)

    assert "set_config('app.current_org_id'" in session.statements[0][0]
    assert ":organization_id" in session.statements[0][0]
    assert session.statements[0][1] == {"organization_id": str(organization_id)}
    assert "true" in session.statements[0][0].lower()
    assert "app.platform_scope" in session.statements[1][0]


@pytest.mark.asyncio
async def test_scope_setter_rejects_non_uuid_and_untrusted_platform_toggle() -> None:
    session = RecordingSession()

    with pytest.raises(DomainError, match="缺少收容所資料範圍"):
        await set_organization_scope(session, "org-from-request")  # type: ignore[arg-type]
    with pytest.raises(DomainError, match="不得關閉受控平台範圍"):
        await set_platform_scope(session, enabled=False)
    assert session.statements == []


@pytest.mark.asyncio
async def test_generic_scope_setters_clear_public_directory_capability_in_same_transaction() -> (
    None
):
    organization_id = uuid4()
    user_id = uuid4()

    for setter in (
        lambda session: set_organization_scope(session, organization_id),
        lambda session: set_platform_scope(session),
        lambda session: set_platform_support_scope(session, organization_id),
        lambda session: set_authentication_user_scope(session, user_id),
        lambda session: set_authentication_user_organization_scope(
            session, user_id, organization_id
        ),
    ):
        session = RecordingSession()
        await set_public_volunteer_directory_scope(session)
        await setter(session)
        public_statements = [
            statement
            for statement, _parameters in session.statements
            if "app.public_volunteer_directory" in statement
        ]
        assert public_statements[-1] == (
            "SELECT set_config('app.public_volunteer_directory', 'false', true)"
        )


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


@pytest.mark.asyncio
async def test_real_postgres_scope_is_transaction_local_and_missing_scope_is_empty() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_id = uuid4()
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Scope Test', $2, 'active', now(), now())
            """,
            organization_id,
            f"SCOPE-{organization_id.hex[:12]}",
        )
        await connection.execute("SET ROLE strayhub_runtime")
        assert not await connection.fetchval("SELECT current_setting('app.current_org_id', true)")
        assert await connection.fetch("SELECT id FROM organizations") == []
        await connection.execute(
            "SELECT set_config('app.current_org_id', $1, true)", str(organization_id)
        )
        assert await connection.fetchval("SELECT count(*) FROM organizations") == 1
        await connection.execute("ROLLBACK")
        await connection.execute("RESET ROLE")
        assert not await connection.fetchval("SELECT current_setting('app.current_org_id', true)")
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_real_postgres_pool_connection_does_not_retain_scope() -> None:
    pool = await asyncpg.create_pool(_database_url(), min_size=1, max_size=1)
    organization_id = str(uuid4())
    try:
        async with pool.acquire() as connection:
            await connection.execute("BEGIN")
            await connection.execute(
                "SELECT set_config('app.current_org_id', $1, true)", organization_id
            )
            await connection.execute("COMMIT")
        async with pool.acquire() as connection:
            assert not await connection.fetchval(
                "SELECT current_setting('app.current_org_id', true)"
            )
    finally:
        await pool.close()
