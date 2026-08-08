import hashlib
import os
from uuid import uuid4

import asyncpg
import pytest


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


@pytest.mark.asyncio
async def test_us1_a_volunteer_can_select_only_current_org_reportable_animals() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_a = uuid4()
    organization_b = uuid4()
    volunteer_a = uuid4()
    membership_a = uuid4()
    area_a = uuid4()
    area_b = uuid4()
    animal_a = uuid4()
    animal_b = uuid4()
    animal_archived = uuid4()
    qr_a = uuid4()
    qr_b = uuid4()
    token_a = f"us1-a-{uuid4().hex}"
    token_b = f"us1-b-{uuid4().hex}"
    shelter_number = f"US1-{uuid4().hex[:12]}"
    try:
        await connection.execute("BEGIN")
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, 'US1 A Shelter', $2, 'active', now(), now()),
                   ($3, 'US1 B Shelter', $4, 'active', now(), now())
            """,
            organization_a,
            f"US1-A-{organization_a.hex[:10]}",
            organization_b,
            f"US1-B-{organization_b.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO users (id, username, display_name, status, created_at, updated_at)
            VALUES ($1, $2, 'US1 Volunteer A', 'active', now(), now())
            """,
            volunteer_a,
            f"us1-volunteer-{volunteer_a.hex[:10]}",
        )
        await connection.execute(
            """
            INSERT INTO organization_memberships
                (id, organization_id, user_id, role, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'VOLUNTEER', 'active', now(), now())
            """,
            membership_a,
            organization_a,
            volunteer_a,
        )
        await connection.execute(
            """
            INSERT INTO shelter_areas
                (id, organization_id, name, area_type, status, created_at, updated_at)
            VALUES ($1, $2, 'A Cage', 'cage', 'active', now(), now()),
                   ($3, $4, 'B Cage', 'cage', 'active', now(), now())
            """,
            area_a,
            organization_a,
            area_b,
            organization_b,
        )
        await connection.execute(
            """
            INSERT INTO animals
                (id, organization_id, name, shelter_number, area_id, status, created_at, updated_at)
            VALUES ($1, $2, 'A Animal', $3, $4, 'active', now(), now()),
                   ($5, $6, 'B Animal', $3, $7, 'active', now(), now()),
                   ($8, $2, 'Archived A Animal', $9, $4, 'archived', now(), now())
            """,
            animal_a,
            organization_a,
            shelter_number,
            area_a,
            animal_b,
            organization_b,
            area_b,
            animal_archived,
            f"US1-ARCHIVED-{uuid4().hex[:8]}",
        )
        await connection.execute(
            """
            INSERT INTO animal_qr_codes
                (id, organization_id, animal_id, token_digest, status, revoked,
                 created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'active', false, now(), now()),
                   ($5, $6, $7, $8, 'active', false, now(), now())
            """,
            qr_a,
            organization_a,
            animal_a,
            hashlib.sha256(token_a.encode()).hexdigest(),
            qr_b,
            organization_b,
            animal_b,
            hashlib.sha256(token_b.encode()).hexdigest(),
        )
        await connection.execute(
            """
            INSERT INTO daily_reportable_scopes
                (id, organization_id, area_id, volunteer_user_id,
                 starts_at, ends_at, status, created_at, updated_at)
            VALUES ($1, $2, $3, $4, now() - interval '1 hour',
                    now() + interval '1 hour', 'active', now(), now())
            """,
            uuid4(),
            organization_a,
            area_a,
            volunteer_a,
        )

        await connection.execute("SET ROLE strayhub_runtime")
        await connection.execute(
            "SELECT set_config('app.current_org_id', $1, true)", str(organization_a)
        )
        await connection.execute(
            "SELECT set_config('app.auth_user_id', $1, true)", str(volunteer_a)
        )
        await connection.execute("SELECT set_config('app.platform_scope', 'false', true)")

        visible_animals = await connection.fetch(
            """
            SELECT id, name, shelter_number
            FROM animals
            WHERE status = 'active'
              AND shelter_number ILIKE $1
            ORDER BY id
            """,
            f"%{shelter_number}%",
        )
        assert [(row["id"], row["name"]) for row in visible_animals] == [(animal_a, "A Animal")]
        assert await connection.fetchrow("SELECT id FROM animals WHERE id = $1", animal_b) is None
        assert (
            await connection.fetchrow("SELECT id FROM animals WHERE id = $1", animal_archived)
            is not None
        )

        reportable = await connection.fetch(
            """
            SELECT animal.id
            FROM daily_reportable_scopes scope
            JOIN animals animal
              ON animal.organization_id = scope.organization_id
             AND (scope.animal_id = animal.id OR scope.area_id = animal.area_id)
            WHERE scope.organization_id = $1
              AND scope.volunteer_user_id = $2
              AND scope.status = 'active'
              AND scope.starts_at <= now()
              AND scope.ends_at >= now()
              AND animal.status = 'active'
            """,
            organization_a,
            volunteer_a,
        )
        assert [row["id"] for row in reportable] == [animal_a]

        active_qr_sql = """
            SELECT animal_id
            FROM animal_qr_codes
            WHERE token_digest = $1 AND status = 'active' AND NOT revoked
        """
        assert (
            await connection.fetchval(active_qr_sql, hashlib.sha256(token_a.encode()).hexdigest())
            == animal_a
        )
        assert (
            await connection.fetchval(active_qr_sql, hashlib.sha256(token_b.encode()).hexdigest())
            is None
        )
        assert (
            await connection.fetchval(
                active_qr_sql,
                hashlib.sha256(f"{token_a}-tampered".encode()).hexdigest(),
            )
            is None
        )
        await connection.execute(
            "UPDATE animal_qr_codes SET revoked = true, status = 'revoked' WHERE id = $1", qr_a
        )
        assert (
            await connection.fetchval(active_qr_sql, hashlib.sha256(token_a.encode()).hexdigest())
            is None
        )
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM care_report_drafts WHERE animal_id IN ($1, $2)",
                animal_a,
                animal_b,
            )
            == 0
        )
    finally:
        await connection.execute("ROLLBACK")
        await connection.close()
