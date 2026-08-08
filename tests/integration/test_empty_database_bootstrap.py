from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _database_url(database: str | None = None) -> str:
    raw = os.getenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )
    parsed = urlsplit(raw.replace("postgresql+asyncpg://", "postgresql://"))
    target_database = database or parsed.path.lstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{target_database}", "", ""))


def _run(*args: str, env: dict[str, str]) -> None:
    subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.mark.asyncio
async def test_empty_database_bootstrap_seed_reset_and_reversible_upgrade() -> None:
    maintenance = await asyncpg.connect(_database_url("postgres"))
    database = f"strayhub_mvp_{uuid4().hex[:12]}"
    try:
        await maintenance.execute(f'CREATE DATABASE "{database}"')
    finally:
        await maintenance.close()

    env = os.environ.copy()
    env["DATABASE_URL"] = _database_url(database).replace("postgresql://", "postgresql+asyncpg://")
    try:
        _run("-m", "alembic", "upgrade", "0014_timeline_query_indexes", env=env)
        _run("-m", "alembic", "upgrade", "head", env=env)
        _run("-m", "scripts.seed_local", env=env)

        connection = await asyncpg.connect(_database_url(database))
        try:
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM organizations WHERE code IN ('ORG-A', 'ORG-B')"
                )
                == 2
            )
        finally:
            await connection.close()

        _run("-m", "scripts.reset_local", "--yes", env=env)
        connection = await asyncpg.connect(_database_url(database))
        try:
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM organizations WHERE code IN ('ORG-A', 'ORG-B')"
                )
                == 0
            )
        finally:
            await connection.close()

        _run("-m", "alembic", "downgrade", "0014_timeline_query_indexes", env=env)
        _run("-m", "alembic", "upgrade", "head", env=env)
    finally:
        maintenance = await asyncpg.connect(_database_url("postgres"))
        try:
            await maintenance.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
        finally:
            await maintenance.close()
