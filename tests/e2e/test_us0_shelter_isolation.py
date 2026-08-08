import os
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest


def test_us0_vertical_surface_is_present():
    assert Path("apps/web/app/(management)/shelters/page.tsx").exists()
    assert Path("apps/web/features/shelter-context/ActiveShelterContext.tsx").exists()
    assert Path("services/api/app/api/organization_management.py").read_text().count("areas") >= 3


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


@pytest.mark.asyncio
async def test_real_postgres_a_b_organization_and_area_isolation():
    connection = await asyncpg.connect(_database_url())
    organization_a = uuid4()
    organization_b = uuid4()
    area_a = uuid4()
    area_b = uuid4()
    user_a = uuid4()
    user_b = uuid4()
    membership_a = uuid4()
    membership_b = uuid4()
    try:
        await connection.execute("BEGIN")
        for organization_id, code in (
            (organization_a, f"US0-A-{organization_a.hex[:10]}"),
            (organization_b, f"US0-B-{organization_b.hex[:10]}"),
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
        await connection.execute(
            """
            INSERT INTO shelter_areas
                (id, organization_id, name, area_type, status, created_at, updated_at)
            VALUES ($1, $2, 'A cage', 'cage', 'active', now(), now()),
                   ($3, $4, 'B cage', 'cage', 'active', now(), now())
            """,
            area_a,
            organization_a,
            area_b,
            organization_b,
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', now(), now()),
                   ($4, $5, $6, 'active', now(), now())
            """,
            user_a,
            f"us0-a-{user_a.hex[:10]}",
            "A User",
            user_b,
            f"us0-b-{user_b.hex[:10]}",
            "B User",
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'STAFF', 'active', now(), now()),
                   ($4, $5, $6, 'STAFF', 'active', now(), now())
            """,
            membership_a,
            organization_a,
            user_a,
            membership_b,
            organization_b,
            user_b,
        )
        await connection.execute("SET ROLE strayhub_runtime")
        await connection.execute("SELECT set_config('app.auth_user_id', $1, true)", str(user_a))
        await connection.execute("SELECT set_config('app.current_org_id', '', true)")
        await connection.execute("SELECT set_config('app.platform_scope', 'false', true)")
        auth_orgs = await connection.fetch("SELECT id FROM organizations ORDER BY id")
        assert [row["id"] for row in auth_orgs] == [organization_a]
        auth_memberships = await connection.fetch(
            "SELECT organization_id, user_id FROM organization_memberships"
        )
        assert [(row["organization_id"], row["user_id"]) for row in auth_memberships] == [
            (organization_a, user_a)
        ]
        await connection.execute("SELECT set_config('app.auth_user_id', '', true)")
        await connection.execute(
            "SELECT set_config('app.current_org_id', $1, true)", str(organization_a)
        )
        await connection.execute("SELECT set_config('app.platform_scope', 'false', true)")
        visible = await connection.fetch("SELECT id, name FROM shelter_areas ORDER BY name")
        assert [(row["id"], row["name"]) for row in visible] == [(area_a, "A cage")]
        assert (
            await connection.fetchrow("SELECT id FROM shelter_areas WHERE id = $1", area_b) is None
        )
        memberships = await connection.fetch(
            "SELECT organization_id, user_id FROM organization_memberships ORDER BY organization_id"
        )
        assert [(row["organization_id"], row["user_id"]) for row in memberships] == [
            (organization_a, user_a)
        ]
        assert (
            await connection.execute(
                "UPDATE shelter_areas SET name = 'tampered' WHERE id = $1", area_b
            )
            == "UPDATE 0"
        )
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()
