"""Helpers that keep test fixtures out of the normal local demo database."""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

DEFAULT_LOCAL_TEST_DATABASE_URL = "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test"
REQUIRED_TEST_DATABASE_NAME = "strayhub_test"
APPROVED_TEST_DATABASE_HOSTS = frozenset({"127.0.0.1", "localhost"})
POSTGRES_SCHEMES = frozenset({"postgresql", "postgresql+asyncpg"})
EPHEMERAL_TEST_DATABASE_ENV = "STRAYHUB_ALLOW_EPHEMERAL_TEST_DATABASE"
EPHEMERAL_TEST_DATABASE_PATTERN = re.compile(r"strayhub_(?:cleanup_test|mvp)_[0-9a-f]{10,12}")
EPHEMERAL_TEST_CALLER_PREFIXES = (
    "tests/integration/test_demo_cleanup.py::",
    "tests/integration/test_empty_database_bootstrap.py::",
)


def _ephemeral_test_database_allowed(target_name: str) -> bool:
    pytest_caller = os.environ.get("PYTEST_CURRENT_TEST", "")
    return (
        os.environ.get(EPHEMERAL_TEST_DATABASE_ENV) == "1"
        and EPHEMERAL_TEST_DATABASE_PATTERN.fullmatch(target_name) is not None
        and pytest_caller.startswith(EPHEMERAL_TEST_CALLER_PREFIXES)
    )


def normalise_postgres_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in POSTGRES_SCHEMES:
        raise RuntimeError(
            "test_database_required: expected PostgreSQL scheme, "
            f"got '{parsed.scheme or '<empty>'}'"
        )
    if parsed.scheme == "postgresql+asyncpg":
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def database_name(url: str) -> str:
    parsed = urlsplit(normalise_postgres_url(url))
    return parsed.path.lstrip("/")


def asyncpg_url(url: str) -> str:
    sync_url = normalise_postgres_url(url)
    return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)


def configured_test_database_url() -> str:
    return os.environ.get("STRAYHUB_TEST_DATABASE_URL", DEFAULT_LOCAL_TEST_DATABASE_URL)


def require_test_database(url: str | None = None) -> str:
    configured_url = configured_test_database_url() if url is None else url
    parsed = urlsplit(configured_url)
    target_name = parsed.path.lstrip("/")
    target_host = parsed.hostname or "<empty>"
    if parsed.scheme not in POSTGRES_SCHEMES:
        raise RuntimeError(
            "test_database_required: expected PostgreSQL scheme; "
            f"host='{target_host}', database='{target_name or '<empty>'}'"
        )
    ephemeral_allowed = _ephemeral_test_database_allowed(target_name)
    if target_name != REQUIRED_TEST_DATABASE_NAME and not ephemeral_allowed:
        raise RuntimeError(
            "test_database_required: wrong database; "
            f"host='{target_host}', database='{target_name or '<empty>'}', "
            f"required='{REQUIRED_TEST_DATABASE_NAME}'"
        )
    if parsed.hostname not in APPROVED_TEST_DATABASE_HOSTS:
        raise RuntimeError(
            "test_database_required: host is not an approved local test target; "
            f"host='{target_host}', database='{target_name}'"
        )
    return normalise_postgres_url(configured_url)


def require_fixture_database() -> str:
    """Validate both the fixture declaration and the URL used by the DB engine."""
    declared_url = os.environ.get("STRAYHUB_TEST_DATABASE_URL")
    runtime_url = os.environ.get("DATABASE_URL")
    if not declared_url or not runtime_url:
        raise RuntimeError(
            "test_database_required: fixture mutation requires explicit "
            "STRAYHUB_TEST_DATABASE_URL and DATABASE_URL"
        )

    declared = urlsplit(require_test_database(declared_url))
    runtime = urlsplit(require_test_database(runtime_url))
    declared_target = (declared.hostname, declared.port, declared.path)
    runtime_target = (runtime.hostname, runtime.port, runtime.path)
    if declared_target != runtime_target:
        raise RuntimeError(
            "test_database_required: declared and runtime test targets differ; "
            f"declared_host='{declared.hostname}', runtime_host='{runtime.hostname}', "
            f"database='{runtime.path.lstrip('/')}'"
        )
    return normalise_postgres_url(runtime_url)
