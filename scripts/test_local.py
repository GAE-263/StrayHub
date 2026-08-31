"""Prepare the dedicated local test database and run pytest without touching demo data."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from scripts.test_database import (
    DEFAULT_LOCAL_TEST_DATABASE_URL,
    REQUIRED_TEST_DATABASE_NAME,
    asyncpg_url,
    configured_test_database_url,
    require_test_database,
)

TEST_DB = REQUIRED_TEST_DATABASE_NAME
COMPOSE = ["docker", "compose", "-f", "infra/local/docker-compose.yml"]
POSTGRES_READY_ATTEMPTS = 30


def run(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, check=True, env=env)


def wait_for_postgres() -> None:
    for _ in range(POSTGRES_READY_ATTEMPTS):
        result = subprocess.run(
            [*COMPOSE, "exec", "-T", "postgres", "pg_isready", "-U", "strayhub"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError("local PostgreSQL did not become ready within 30 seconds")


def ensure_test_database() -> None:
    run(*COMPOSE, "up", "-d", "postgres")
    wait_for_postgres()
    exists = subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "strayhub",
            "-d",
            "postgres",
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname = '{TEST_DB}'",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if exists != "1":
        run(
            *COMPOSE,
            "exec",
            "-T",
            "postgres",
            "createdb",
            "-U",
            "strayhub",
            TEST_DB,
        )


def main() -> None:
    configured_url = configured_test_database_url()
    test_database_url = require_test_database(configured_url)
    if test_database_url == DEFAULT_LOCAL_TEST_DATABASE_URL:
        ensure_test_database()
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["DATABASE_URL"] = asyncpg_url(test_database_url)
    env["STRAYHUB_TEST_DATABASE_URL"] = test_database_url

    run("uv", "run", "alembic", "upgrade", "head", env=env)
    run("uv", "run", "pytest", *sys.argv[1:], env=env)


if __name__ == "__main__":
    main()
