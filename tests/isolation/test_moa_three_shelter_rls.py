"""Read-only opt-in checks against the three imported local demo shelters."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    os.getenv("MOA_THREE_SHELTER_TEST") != "1",
    reason="Requires FurKids, Xindian and Wugu imported into the selected test database",
)
CODES = ("FURKIDS-ASIA", "MOA-SHELTER-51", "MOA-SHELTER-58")
TABLES = ("animals", "animal_external_sources", "media_assets", "animal_qr_codes")


async def test_six_directions_four_resources_and_reused_runtime_connection():
    url = os.environ["STRAYHUB_TEST_DATABASE_URL"].replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            await connection.execute(text("SELECT set_config('app.platform_scope','true',true)"))
            organizations = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT code,id FROM organizations WHERE code IN "
                            "('FURKIDS-ASIA','MOA-SHELTER-51','MOA-SHELTER-58')"
                        )
                    )
                ).all()
            )
            inventory = {
                code: {
                    table: await connection.scalar(
                        text(f"SELECT count(*) FROM {table} WHERE organization_id=:org"),
                        {"org": organization_id},
                    )
                    for table in TABLES
                }
                for code, organization_id in organizations.items()
            }
        assert set(organizations) == set(CODES)
        assert inventory["FURKIDS-ASIA"] == {
            "animals": 5,
            "animal_external_sources": 0,
            "media_assets": 5,
            "animal_qr_codes": 5,
        }
        for code in ("MOA-SHELTER-51", "MOA-SHELTER-58"):
            assert inventory[code]["animals"] > 0
            assert len(set(inventory[code].values())) == 1
        first_pid = None
        for code in (*CODES, CODES[0]):
            async with engine.connect() as connection, connection.begin():
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                assert not await connection.scalar(
                    text("SELECT nullif(current_setting('app.current_org_id',true),'')")
                )
                assert (
                    await connection.scalar(
                        text("SELECT coalesce(current_setting('app.platform_scope',true),'')")
                    )
                    != "true"
                )
                await connection.execute(text("SET LOCAL ROLE strayhub_runtime"))
                assert await connection.scalar(text("SELECT current_user")) == "strayhub_runtime"
                assert not await connection.scalar(
                    text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")
                )
                pid = await connection.scalar(text("SELECT pg_backend_pid()"))
                first_pid = first_pid or pid
                assert pid == first_pid
                await connection.execute(
                    text("SELECT set_config('app.current_org_id',:org,true)"),
                    {"org": str(organizations[code])},
                )
                for table in TABLES:
                    # No application-side tenant WHERE: this proves database RLS itself.
                    rows = (
                        (await connection.execute(text(f"SELECT organization_id FROM {table}")))
                        .scalars()
                        .all()
                    )
                    expected = inventory[code][table]
                    assert len(rows) == expected, (code, table, len(rows))
                    assert set(rows) <= {organizations[code]}
                    for foreign in CODES:
                        if foreign != code:
                            assert (
                                await connection.scalar(
                                    text(
                                        f"SELECT count(*) FROM {table} WHERE organization_id=:org"
                                    ),
                                    {"org": organizations[foreign]},
                                )
                                == 0
                            )
    finally:
        await engine.dispose()
