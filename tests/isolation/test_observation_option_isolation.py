import os
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.api.dependencies import RequestContext
from services.api.app.api.errors import DomainError
from services.api.app.api.observation_options import _require_option_manager


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


async def _scope(connection, organization_id=None, platform=False) -> None:
    await connection.execute(
        "SELECT set_config('app.platform_scope', $1, true)", str(platform).lower()
    )
    await connection.execute(
        "SELECT set_config('app.current_org_id', $1, true)",
        "" if organization_id is None else str(organization_id),
    )


def _context(organization_id, role: str) -> RequestContext:
    return RequestContext(
        user_id=uuid4(),
        organization_id=organization_id,
        membership_id=uuid4(),
        role=role,
    )


@pytest.mark.asyncio
async def test_a_and_b_only_see_and_update_their_own_extension() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_a = uuid4()
    organization_b = uuid4()
    category_id = uuid4()
    option_a = uuid4()
    option_b = uuid4()
    suffix = uuid4().hex[:10]
    try:
        await connection.execute("BEGIN")
        await connection.execute("SET ROLE strayhub_runtime")
        await _scope(connection, platform=True)
        for organization_id, label in ((organization_a, "A"), (organization_b, "B")):
            await connection.execute(
                """
                INSERT INTO organizations (id, name, code, status, created_at, updated_at)
                VALUES ($1, $2, $3, 'active', now(), now())
                """,
                organization_id,
                f"US4 隔離 {label} {suffix}",
                f"US4-ISO-{label}-{suffix}",
            )
        await connection.execute(
            """
            INSERT INTO observation_categories
                (id, organization_id, code, display_name, description, status, display_order,
                 created_at, updated_at)
            VALUES ($1, NULL, $2, '隔離類別', '', 'active', 0, now(), now())
            """,
            category_id,
            f"us4-isolation-category-{suffix}",
        )
        for organization_id, option_id, label in (
            (organization_a, option_a, "A"),
            (organization_b, option_b, "B"),
        ):
            await _scope(connection, organization_id=organization_id)
            await connection.execute(
                """
                INSERT INTO observation_options
                    (id, category_id, organization_id, code, display_name, description, status,
                     display_order, requires_note, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, '', 'active', 0, false, now(), now())
                """,
                option_id,
                category_id,
                organization_id,
                f"us4.isolation.{label.lower()}.{suffix}",
                f"A/B {label}",
            )

        await _scope(connection, organization_id=organization_a)
        visible_a = await connection.fetch(
            """
            SELECT id, display_name
            FROM observation_options
            WHERE id IN ($1, $2)
            ORDER BY display_name
            """,
            option_a,
            option_b,
        )
        assert [(row["id"], row["display_name"]) for row in visible_a] == [
            (option_a, "A/B A")
        ]
        assert await connection.execute(
            "UPDATE observation_options SET display_name = '越權' WHERE id = $1", option_b
        ) == "UPDATE 0"

        with pytest.raises(DomainError, match="無法管理觀察選項"):
            _require_option_manager(_context(organization_a, "VOLUNTEER"))
        _require_option_manager(_context(organization_a, "SHELTER_ADMIN"))
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()
