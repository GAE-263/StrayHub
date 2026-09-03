import os
from uuid import uuid4

import asyncpg
import pytest
from services.api.app.application.effective_observation_service import (
    EffectiveObservationService,
    EffectiveOption,
)


def _database_url() -> str:
    return os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )


async def _scope(connection, *, organization_id=None, platform=False) -> None:
    await connection.execute(
        "SELECT set_config('app.platform_scope', $1, true)", str(platform).lower()
    )
    await connection.execute(
        "SELECT set_config('app.current_org_id', $1, true)",
        "" if organization_id is None else str(organization_id),
    )


@pytest.mark.asyncio
async def test_effective_options_include_platform_extension_and_disabled_history() -> None:
    connection = await asyncpg.connect(_database_url())
    organization_id = uuid4()
    category_id = uuid4()
    platform_option_id = uuid4()
    extension_id = uuid4()
    code_suffix = uuid4().hex[:10]
    platform_code = f"us4.platform.{code_suffix}"
    extension_code = f"us4.extension.{code_suffix}"
    try:
        await connection.execute("BEGIN")
        await connection.execute("SET ROLE strayhub_runtime")
        await _scope(connection, platform=True)
        await connection.execute(
            """
            INSERT INTO organizations (id, name, code, status, created_at, updated_at)
            VALUES ($1, $2, $3, 'active', now(), now())
            """,
            organization_id,
            f"US4 {code_suffix}",
            f"US4-{code_suffix}",
        )
        await connection.execute(
            """
            INSERT INTO observation_categories
                (id, organization_id, code, display_name, description, status, display_order,
                 created_at, updated_at)
            VALUES ($1, NULL, $2, 'US4 類別', '', 'active', 0, now(), now())
            """,
            category_id,
            f"us4-category-{code_suffix}",
        )
        await connection.execute(
            """
            INSERT INTO observation_options
                (id, category_id, organization_id, code, display_name, description, status,
                 display_order, requires_note, created_at, updated_at)
            VALUES ($1, $2, NULL, $3, '平台選項', '', 'active', 0, false, now(), now())
            """,
            platform_option_id,
            category_id,
            platform_code,
        )
        await _scope(connection, organization_id=organization_id)
        await connection.execute(
            """
            INSERT INTO observation_options
                (id, category_id, organization_id, code, display_name, description, status,
                 display_order, requires_note, created_at, updated_at)
            VALUES ($1, $2, $3, $4, '收容所選項', '', 'active', 1, true, now(), now())
            """,
            extension_id,
            category_id,
            organization_id,
            extension_code,
        )
        effective = await connection.fetch(
            """
            SELECT code, display_name, organization_id, status
            FROM observation_options
            WHERE organization_id IS NULL OR organization_id = $1
            ORDER BY display_order, code
            """,
            organization_id,
        )
        visible_codes = {row["code"] for row in effective}
        assert {platform_code, extension_code} <= visible_codes

        await connection.execute(
            """
            UPDATE observation_options
            SET display_name = '收容所舊名稱', status = 'disabled'
            WHERE id = $1
            """,
            extension_id,
        )
        history = await connection.fetchrow(
            "SELECT code, display_name, status FROM observation_options WHERE id = $1",
            extension_id,
        )
        assert dict(history) == {
            "code": extension_code,
            "display_name": "收容所舊名稱",
            "status": "disabled",
        }
        service = EffectiveObservationService(
            {
                platform_code: EffectiveOption(platform_code, "平台選項"),
                extension_code: EffectiveOption(
                    extension_code, "收容所舊名稱", requires_note=True, active=False
                ),
            }
        )
        assert not service.is_valid(extension_code)
        with pytest.raises(Exception, match="無效或已停用"):
            service.validate_answer("appearance_special_status", extension_code)
        await connection.execute("ROLLBACK")
    finally:
        await connection.close()
