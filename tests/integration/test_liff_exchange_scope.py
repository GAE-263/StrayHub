import os
from uuid import uuid4

import asyncpg
import pytest


def _database_url() -> str:
    return os.environ["STRAYHUB_TEST_DATABASE_URL"]


@pytest.mark.asyncio
async def test_real_postgres_liff_scope_sees_only_exact_user_organization() -> None:
    connection = await asyncpg.connect(_database_url())
    user_id = uuid4()
    organization_a = uuid4()
    organization_b = uuid4()
    membership_a = uuid4()
    membership_b = uuid4()
    application_a = uuid4()
    application_b = uuid4()
    try:
        await connection.execute("BEGIN")
        for organization_id, code in (
            (organization_a, f"LIFF-A-{organization_a.hex[:10]}"),
            (organization_b, f"LIFF-B-{organization_b.hex[:10]}"),
        ):
            await connection.execute(
                """
                INSERT INTO organizations (id, name, code, status, created_at, updated_at)
                VALUES ($1, $2, $2, 'active', now(), now())
                """,
                organization_id,
                code,
            )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'LIFF scope user', 'active', now(), now())
            """,
            user_id,
            f"liff-scope-{user_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
              (id, organization_id, user_id, role, status, valid_from, expires_at,
               created_at, updated_at)
            VALUES
              ($1, $2, $3, 'VOLUNTEER', 'active', now() - interval '1 hour',
               now() + interval '7 days', now(), now()),
              ($4, $5, $3, 'VOLUNTEER', 'active', now() - interval '1 hour',
               now() + interval '7 days', now(), now())
            """,
            membership_a,
            organization_a,
            user_id,
            membership_b,
            organization_b,
        )
        await connection.execute(
            """
            INSERT INTO volunteer_applications
              (id, organization_id, user_id, status, source_channel,
               submitted_at, created_at, updated_at)
            VALUES
              ($1, $2, $3, 'pending', 'liff', now(), now(), now()),
              ($4, $5, $3, 'pending', 'liff', now(), now(), now())
            """,
            application_a,
            organization_a,
            user_id,
            application_b,
            organization_b,
        )

        await connection.execute("SET ROLE strayhub_runtime")
        await connection.execute("SELECT set_config('app.auth_user_id', $1, true)", str(user_id))
        await connection.execute(
            "SELECT set_config('app.auth_exact_org_id', $1, true)", str(organization_a)
        )
        await connection.execute("SELECT set_config('app.current_org_id', '', true)")
        await connection.execute("SELECT set_config('app.platform_scope', 'false', true)")

        organizations = await connection.fetch("SELECT id FROM organizations ORDER BY id")
        memberships = await connection.fetch(
            "SELECT organization_id FROM organization_memberships ORDER BY organization_id"
        )
        applications = await connection.fetch(
            "SELECT organization_id FROM volunteer_applications ORDER BY organization_id"
        )
        assert [row["id"] for row in organizations] == [organization_a]
        assert [row["organization_id"] for row in memberships] == [organization_a]
        assert [row["organization_id"] for row in applications] == [organization_a]
        assert (
            await connection.execute(
                "UPDATE volunteer_applications SET submitted_at = now() WHERE id = $1",
                application_b,
            )
            == "UPDATE 0"
        )
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_real_postgres_liff_scope_can_classify_disabled_exact_membership() -> None:
    connection = await asyncpg.connect(_database_url())
    user_id = uuid4()
    organization_id = uuid4()
    membership_id = uuid4()
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'Disabled membership shelter', $2, 'active', now(), now())
            """,
            organization_id,
            f"LIFF-DISABLED-{organization_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'Disabled membership user', 'active', now(), now())
            """,
            user_id,
            f"liff-disabled-{user_id.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
              (id, organization_id, user_id, role, status, valid_from, expires_at,
               created_at, updated_at)
            VALUES
              ($1, $2, $3, 'VOLUNTEER', 'disabled', now() - interval '1 hour',
               now() + interval '7 days', now(), now())
            """,
            membership_id,
            organization_id,
            user_id,
        )

        await connection.execute("SET ROLE strayhub_runtime")
        await connection.execute("SELECT set_config('app.auth_user_id', $1, true)", str(user_id))
        await connection.execute(
            "SELECT set_config('app.auth_exact_org_id', $1, true)", str(organization_id)
        )
        await connection.execute("SELECT set_config('app.current_org_id', '', true)")
        await connection.execute("SELECT set_config('app.platform_scope', 'false', true)")

        membership = await connection.fetchrow(
            "SELECT id, status FROM organization_memberships WHERE id = $1",
            membership_id,
        )
        assert membership is not None
        assert membership["status"] == "disabled"
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()
