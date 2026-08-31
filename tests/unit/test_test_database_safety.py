from __future__ import annotations

import asyncio

import pytest
from scripts import test_local
from scripts.seed_local import seed as legacy_seed
from scripts.seed_medical_care import validate_seed_environment
from scripts.seed_t255_timeline import seed_timeline
from scripts.seed_test_fixtures import seed as explicit_seed
from scripts.test_database import asyncpg_url, require_fixture_database, require_test_database


@pytest.mark.parametrize(
    "url",
    (
        "postgresql://user:secret@127.0.0.1:65432/strayhub_test",
        "postgresql+asyncpg://user:secret@localhost:5432/strayhub_test",
    ),
)
def test_guard_accepts_supported_local_postgres_test_urls(url: str) -> None:
    assert require_test_database(url).startswith("postgresql://")


@pytest.mark.parametrize(
    "url",
    (
        "postgresql://user:secret@127.0.0.1:65432/strayhub",
        "sqlite:///strayhub_test",
        "postgresql://user:secret@database.example/strayhub_test",
    ),
)
def test_guard_rejects_demo_non_postgres_and_remote_targets(url: str) -> None:
    with pytest.raises(RuntimeError, match="test_database_required"):
        require_test_database(url)


def test_ephemeral_test_database_requires_narrow_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ephemeral = "postgresql://user:secret@localhost:65432/strayhub_mvp_0123456789ab"
    with pytest.raises(RuntimeError, match="wrong database"):
        require_test_database(ephemeral)

    monkeypatch.setenv("STRAYHUB_ALLOW_EPHEMERAL_TEST_DATABASE", "1")
    with pytest.raises(RuntimeError, match="wrong database"):
        require_test_database(ephemeral)

    monkeypatch.setenv(
        "PYTEST_CURRENT_TEST",
        "tests/integration/test_empty_database_bootstrap.py::test_bootstrap (call)",
    )
    assert require_test_database(ephemeral) == ephemeral
    with pytest.raises(RuntimeError, match="wrong database"):
        require_test_database(
            "postgresql://user:secret@localhost:65432/strayhub_arbitrary_0123456789ab"
        )


def test_asyncpg_conversion_preserves_connection_details() -> None:
    url = "postgresql://user:secret@localhost:65432/strayhub_test?sslmode=disable"

    assert asyncpg_url(url) == (
        "postgresql+asyncpg://user:secret@localhost:65432/strayhub_test?sslmode=disable"
    )


def test_explicit_fixture_entry_preserves_legacy_seed_identity() -> None:
    assert explicit_seed is legacy_seed


def test_seed_local_fails_closed_before_database_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )

    with pytest.raises(RuntimeError, match="wrong database"):
        asyncio.run(legacy_seed())


def test_timeline_seed_fails_closed_before_database_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub",
    )

    with pytest.raises(RuntimeError, match="wrong database"):
        asyncio.run(seed_timeline())


@pytest.mark.parametrize("profile", ("base", "full"))
def test_medical_seed_profiles_reject_demo_database(profile: str) -> None:
    with pytest.raises(RuntimeError, match="wrong database"):
        validate_seed_environment(
            profile,
            "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub",
        )


def test_fixture_guard_rejects_declared_runtime_target_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "STRAYHUB_TEST_DATABASE_URL",
        "postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub_test",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://strayhub:strayhub@localhost:65433/strayhub_test",
    )

    with pytest.raises(RuntimeError, match="declared and runtime test targets differ"):
        require_fixture_database()


def test_local_respects_custom_test_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_url = "postgresql://custom:secret@localhost:65433/strayhub_test"
    calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []
    monkeypatch.setenv("STRAYHUB_TEST_DATABASE_URL", custom_url)
    monkeypatch.setattr(
        test_local,
        "ensure_test_database",
        lambda: pytest.fail("custom database must not start canonical Compose PostgreSQL"),
    )
    monkeypatch.setattr(
        test_local,
        "run",
        lambda *args, env=None: calls.append((args, env)),
    )
    monkeypatch.setattr(test_local.sys, "argv", ["test_local.py", "tests/unit/example.py"])

    test_local.main()

    assert [call[0] for call in calls] == [
        ("uv", "run", "alembic", "upgrade", "head"),
        ("uv", "run", "pytest", "tests/unit/example.py"),
    ]
    assert all(call[1]["STRAYHUB_TEST_DATABASE_URL"] == custom_url for call in calls)
    assert all(
        call[1]["DATABASE_URL"]
        == "postgresql+asyncpg://custom:secret@localhost:65433/strayhub_test"
        for call in calls
    )


def test_local_postgres_readiness_wait_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    class NotReady:
        returncode = 1

    def not_ready(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return NotReady()

    monkeypatch.setattr(test_local, "POSTGRES_READY_ATTEMPTS", 3)
    monkeypatch.setattr(test_local.subprocess, "run", not_ready)
    monkeypatch.setattr(test_local.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="did not become ready"):
        test_local.wait_for_postgres()

    assert attempts == 3
