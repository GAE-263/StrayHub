import os
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.domain.tenant_context import TenantContext


def test_tenant_context_denies_other_organization_without_platform_scope() -> None:
    context = TenantContext(user_id=uuid4(), organization_id=uuid4(), role="STAFF")

    with pytest.raises(DomainError, match="無法存取此收容所資料"):
        context.require_organization(uuid4())


def test_platform_scope_can_be_used_only_by_explicit_platform_context() -> None:
    shelter_context = TenantContext(user_id=uuid4(), organization_id=uuid4(), role="STAFF")
    platform_context = TenantContext(
        user_id=uuid4(), organization_id=None, role="PLATFORM_ADMIN", platform_scope=True
    )

    with pytest.raises(DomainError):
        shelter_context.require_organization(uuid4())
    platform_context.require_organization(uuid4())


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


@pytest.mark.asyncio
async def test_real_postgres_a_b_rows_are_isolated_by_scope_and_platform_scope() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_a = uuid4()
    organization_b = uuid4()
    try:
        await connection.execute("BEGIN")
        for organization_id, code in (
            (organization_a, f"A-{organization_a.hex[:12]}"),
            (organization_b, f"B-{organization_b.hex[:12]}"),
        ):
            await connection.execute(
                """
                INSERT INTO organizations (id, name, code, status, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', now(), now())
                """,
                organization_id,
                code,
                code,
            )
        await connection.execute("SET ROLE strayhub_runtime")
        await connection.execute(
            "SELECT set_config('app.current_org_id', $1, true)", str(organization_a)
        )
        rows = await connection.fetch(
            "SELECT id FROM organizations WHERE id = ANY($1::uuid[]) ORDER BY id",
            [organization_a, organization_b],
        )
        assert [row["id"] for row in rows] == [organization_a]
        assert (
            await connection.fetchrow("SELECT id FROM organizations WHERE id = $1", organization_b)
            is None
        )

        await connection.execute("SELECT set_config('app.platform_scope', 'true', true)")
        rows = await connection.fetch(
            "SELECT id FROM organizations WHERE id = ANY($1::uuid[]) ORDER BY id",
            [organization_a, organization_b],
        )
        assert {row["id"] for row in rows} == {organization_a, organization_b}
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()
