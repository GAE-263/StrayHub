import os
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.persistence.models.animal import Animal


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


@pytest.mark.asyncio
async def test_shelter_number_is_unique_within_org_but_not_across_orgs() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_a = uuid4()
    organization_b = uuid4()
    animal_a = uuid4()
    animal_b = uuid4()
    shelter_number = f"VAAAG-{uuid4().hex[:12]}"
    try:
        await connection.execute("BEGIN")
        await connection.execute("SET ROLE strayhub_runtime")
        await connection.execute("SELECT set_config('app.platform_scope', 'true', true)")
        for organization_id, code in (
            (organization_a, f"US1-A-{organization_a.hex[:10]}"),
            (organization_b, f"US1-B-{organization_b.hex[:10]}"),
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
            INSERT INTO animals
                (id, organization_id, name, shelter_number, status, created_at, updated_at)
            VALUES ($1, $2, 'A Animal', $3, 'active', now(), now()),
                   ($4, $5, 'B Animal', $3, 'active', now(), now())
            """,
            animal_a,
            organization_a,
            shelter_number,
            animal_b,
            organization_b,
        )
        await connection.execute("SAVEPOINT duplicate_number")
        with pytest.raises(asyncpg.UniqueViolationError):
            await connection.execute(
                """
                INSERT INTO animals
                    (id, organization_id, name, shelter_number, status, created_at, updated_at)
                VALUES ($1, $2, 'Duplicate', $3, 'active', now(), now())
                """,
                uuid4(),
                organization_a,
                shelter_number,
            )
        await connection.execute("ROLLBACK TO SAVEPOINT duplicate_number")
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM animals WHERE shelter_number = $1", shelter_number
            )
            == 2
        )
        assert Animal.__table__.c.shelter_number is not None
    finally:
        await connection.execute("ROLLBACK")
        await connection.close()
