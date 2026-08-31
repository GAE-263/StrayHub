"""Prepare the dedicated local test database and run pytest without touching demo data."""

from __future__ import annotations

import os
import subprocess
import sys

TEST_DB = "strayhub_test"
TEST_DATABASE_URL = f"postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/{TEST_DB}"
TEST_DATABASE_URL_SYNC = f"postgresql://strayhub:strayhub@127.0.0.1:65432/{TEST_DB}"
COMPOSE = ["docker", "compose", "-f", "infra/local/docker-compose.yml"]


def run(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, check=True, env=env)


def ensure_test_database() -> None:
    run(*COMPOSE, "up", "-d", "postgres")
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
    ensure_test_database()
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["DATABASE_URL"] = TEST_DATABASE_URL
    env["STRAYHUB_TEST_DATABASE_URL"] = TEST_DATABASE_URL_SYNC

    run("uv", "run", "alembic", "upgrade", "head", env=env)
    run("uv", "run", "pytest", *sys.argv[1:], env=env)


if __name__ == "__main__":
    main()
