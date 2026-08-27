"""Explicit opt-in round-trip: only a disposable strayhub_moa_* database is allowed."""

import asyncio
import hashlib
import os
import subprocess

import asyncpg
import pytest
from sqlalchemy.engine import make_url


def test_populated_moa_migration_round_trip():
    dsn = os.getenv("STRAYHUB_MOA_MIGRATION_TEST_URL")
    if not dsn:
        pytest.skip("Set STRAYHUB_MOA_MIGRATION_TEST_URL to a disposable populated test DB")
    url = make_url(dsn)
    assert url.host in {"localhost", "127.0.0.1"}
    assert url.database.startswith("strayhub_moa_")
    env = dict(
        os.environ,
        DATABASE_URL=url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False),
    )

    async def inspect():
        conn = await asyncpg.connect(dsn)
        try:
            async with conn.transaction(readonly=True):
                await conn.execute("SELECT set_config('app.platform_scope', 'true', true)")
                revision = await conn.fetchval("SELECT version_num FROM alembic_version")
                tables = await conn.fetch(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                )
                hashes = {}
                for row in tables:
                    table = row["tablename"]
                    if table in {"alembic_version", "animal_external_sources"}:
                        continue
                    values = await conn.fetch(
                        f'SELECT to_jsonb(t)::text AS value FROM "{table}" t ORDER BY 1'
                    )
                    hashes[table] = hashlib.sha256(
                        "\n".join(r["value"] for r in values).encode()
                    ).hexdigest()
                mappings = (
                    await conn.fetch("SELECT * FROM animal_external_sources")
                    if revision == "0037_animal_external_sources"
                    else []
                )
                return revision, hashes, mappings
        finally:
            await conn.close()

    def migrate(*args):
        result = subprocess.run(["uv", "run", "alembic", *args], env=env, capture_output=True)
        assert result.returncode == 0, "migration failed (connection details intentionally omitted)"

    before_revision, before, mappings = asyncio.run(inspect())
    assert before_revision == "0037_animal_external_sources"
    assert mappings, "Use a populated disposable fixture so history preservation is tested"
    migrate("downgrade", "0036_animal_profile")
    revision, after, _ = asyncio.run(inspect())
    assert revision == "0036_animal_profile" and after == before
    migrate("upgrade", "head")
    revision, after, empty_mappings = asyncio.run(inspect())
    assert revision == "0037_animal_external_sources" and after == before
    assert not empty_mappings  # Downgrade intentionally drops only synchronization metadata.

    async def restore_mapping_backup():
        conn = await asyncpg.connect(dsn)
        try:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.platform_scope', 'true', true)")
                await conn.copy_records_to_table(
                    "animal_external_sources",
                    records=[tuple(r.values()) for r in mappings],
                    columns=list(mappings[0].keys()),
                )
                flags = await conn.fetchrow(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname='animal_external_sources'"
                )
                assert flags["relrowsecurity"] and flags["relforcerowsecurity"]
        finally:
            await conn.close()

    asyncio.run(restore_mapping_backup())
