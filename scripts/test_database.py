"""Helpers that keep test fixtures out of the normal local demo database."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

DEFAULT_LOCAL_TEST_DATABASE_URL = (
    "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test"
)
REQUIRED_TEST_DATABASE_NAME = "strayhub_test"


def normalise_postgres_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def database_name(url: str) -> str:
    parsed = urlsplit(normalise_postgres_url(url))
    return parsed.path.lstrip("/")


def asyncpg_url(url: str) -> str:
    sync_url = normalise_postgres_url(url)
    return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)


def configured_test_database_url() -> str:
    return os.environ.get("STRAYHUB_TEST_DATABASE_URL", DEFAULT_LOCAL_TEST_DATABASE_URL)


def require_test_database(url: str | None = None) -> str:
    target = normalise_postgres_url(url or configured_test_database_url())
    target_name = database_name(target)
    if target_name != REQUIRED_TEST_DATABASE_NAME:
        raise RuntimeError(
            "test_database_required: STRAYHUB_TEST_DATABASE_URL must target "
            f"'{REQUIRED_TEST_DATABASE_NAME}', got '{target_name or '<empty>'}'"
        )
    return target
