"""Global pytest safety guard: tests never use the normal local demo database."""

from __future__ import annotations

import os

import pytest
from scripts.test_database import asyncpg_url, require_test_database


def pytest_configure(config: pytest.Config) -> None:
    del config
    try:
        test_database_url = require_test_database()
    except RuntimeError as exc:
        raise pytest.UsageError(str(exc)) from exc

    # Set this before application modules are collected/imported so the module-level
    # SQLAlchemy AsyncEngine is always bound to the dedicated test database.
    os.environ["STRAYHUB_TEST_DATABASE_URL"] = test_database_url
    os.environ["DATABASE_URL"] = asyncpg_url(test_database_url)
