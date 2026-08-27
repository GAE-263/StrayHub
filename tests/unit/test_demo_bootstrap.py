from pathlib import Path

import pytest


def test_normal_demo_never_seeds_test_universe():
    script = Path("scripts/demo.sh").read_text()
    assert "scripts.seed_local" not in script
    assert "\nuv run python -m scripts.seed_test_fixtures" not in script
    assert "scripts.bootstrap_demo" in script
    assert "scripts.configure_runtime_role --apply" in script
    assert "pytest" not in script


def test_three_shelter_demo_exposes_only_dynamic_new_taipei_region() -> None:
    accounts = Path("scripts/seed_demo_accounts.py").read_text()
    furkids = Path("scripts/seed_furkids_demo.py").read_text()

    assert 'organization.service_area = "新北市"' in accounts
    assert 'organization.service_area = "新北市"' in furkids
    assert "DailyReportableScope" not in accounts


@pytest.mark.parametrize("environment", ["production", "staging", "prod", "demo", ""])
def test_demo_guard_denies_nonlocal_environments(environment):
    from scripts.local_demo import require_local_demo

    with pytest.raises(ValueError):
        require_local_demo(environment, "postgresql+asyncpg://u:p@127.0.0.1:65432/strayhub")


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:p@shared.example/strayhub",
        "postgresql+asyncpg://u:p@127.0.0.1/production",
        "postgresql+asyncpg://u:p@127.0.0.1/strayhub?host=remote.example",
        "sqlite:///strayhub",
    ],
)
def test_demo_guard_denies_remote_or_ambiguous_database(url):
    from scripts.local_demo import require_local_demo

    with pytest.raises(ValueError):
        require_local_demo("local", url)


def test_demo_guard_allows_local_dedicated_database():
    from scripts.local_demo import require_local_demo

    require_local_demo("local", "postgresql+asyncpg://u:p@127.0.0.1:65432/strayhub")
    require_local_demo("test", "postgresql+asyncpg://u:p@localhost/strayhub_demo_test")


def test_explicit_fixture_entry_reuses_legacy_implementation():
    from scripts.seed_local import seed
    from scripts.seed_test_fixtures import seed as explicit_seed

    assert seed is explicit_seed


def test_cleanup_targets_only_known_codes_and_usernames():
    from scripts.cleanup_legacy_demo_fixtures import LEGACY_CODES, fixture_usernames

    assert set(LEGACY_CODES) == {"ORG-A", "ORG-B", "ORG-DISABLED"}
    names = fixture_usernames()
    assert "local-staff-a" in names and "local-applicant-all-filtered-1200" in names
    assert "local-real-person" not in names and "demo-furkids-admin" not in names
    assert not any("%" in name for name in names)


async def test_moa_failure_reuses_only_verified_existing_data():
    from scripts.bootstrap_demo import import_or_reuse

    calls = []

    async def failed_import(**kwargs):
        return 1

    async def valid_existing(code):
        calls.append(code)
        return {"animals": 60, "valid": True}

    result = await import_or_reuse(
        "MOA-SHELTER-51", run_import=failed_import, verify=valid_existing
    )
    assert result["sync"] == "reused_existing" and calls == ["MOA-SHELTER-51"]


async def test_moa_failure_without_valid_data_stops():
    from scripts.bootstrap_demo import import_or_reuse

    async def failed_import(**kwargs):
        return 1

    async def invalid_existing(code):
        return {"animals": 0, "valid": False}

    with pytest.raises(RuntimeError, match="no_valid_local_dataset"):
        await import_or_reuse("MOA-SHELTER-58", run_import=failed_import, verify=invalid_existing)
