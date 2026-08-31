"""Global pytest safety guard: tests never use the normal local demo database."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

_DEFAULT_LOCAL_TEST_DATABASE_URL = (
    "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test"
)
_REQUIRED_TEST_DATABASE_NAME = "strayhub_test"


def _normalise_postgres_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _database_name(url: str) -> str:
    parsed = urlsplit(_normalise_postgres_url(url))
    return parsed.path.lstrip("/")


def _asyncpg_url(url: str) -> str:
    sync_url = _normalise_postgres_url(url)
    return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)


def pytest_configure(config: pytest.Config) -> None:
    del config
    test_database_url = os.environ.get(
        "STRAYHUB_TEST_DATABASE_URL", _DEFAULT_LOCAL_TEST_DATABASE_URL
    )
    database_name = _database_name(test_database_url)
    if database_name != _REQUIRED_TEST_DATABASE_NAME:
        raise pytest.UsageError(
            "STRAYHUB_TEST_DATABASE_URL must target the dedicated "
            f"'{_REQUIRED_TEST_DATABASE_NAME}' database; got '{database_name or '<empty>'}'."
        )

    # Set this before application modules are collected/imported so the module-level
    # SQLAlchemy AsyncEngine is always bound to the dedicated test database.
    os.environ["STRAYHUB_TEST_DATABASE_URL"] = _normalise_postgres_url(test_database_url)
    os.environ["DATABASE_URL"] = _asyncpg_url(test_database_url)
