import subprocess
from pathlib import Path

import pytest


def test_normal_demo_never_seeds_test_universe():
    script = Path("scripts/demo.sh").read_text()
    assert "scripts.seed_local" not in script
    assert "\nuv run python -m scripts.seed_test_fixtures" not in script
    assert "scripts.bootstrap_demo" in script
    assert "scripts.configure_runtime_role --apply" in script
    assert "pytest" not in script


def test_demo_cli_documents_and_rejects_modes() -> None:
    help_result = subprocess.run(
        ["bash", "scripts/demo.sh", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "check|refresh|serve" in help_result.stdout
    assert "沿用已驗證" in help_result.stdout
    assert "強制同步最新 MOA" in help_result.stdout

    invalid_result = subprocess.run(
        ["bash", "scripts/demo.sh", "invalid-mode"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid_result.returncode == 2
    assert "check|refresh|serve" in invalid_result.stderr


def test_demo_cli_keeps_default_check_and_refresh_semantics() -> None:
    script = Path("scripts/demo.sh").read_text()

    assert 'MODE="${1:-serve}"' in script
    assert 'if [[ "$MODE" == "check" ]]' in script
    assert 'if [[ "$MODE" == "refresh" ]]' in script
    assert "scripts.bootstrap_demo --refresh" in script


def test_demo_password_must_be_explicit_or_generated_and_rejects_exposed_value(
    monkeypatch,
) -> None:
    from scripts.demo_credentials import require_demo_password

    monkeypatch.delenv("STRAYHUB_DEMO_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="STRAYHUB_DEMO_PASSWORD"):
        require_demo_password()
    with pytest.raises(ValueError, match="exposed"):
        require_demo_password("local-only-password")
    with pytest.raises(ValueError, match="at least 16"):
        require_demo_password("too-short")
    assert require_demo_password("unique-synthetic-password") == "unique-synthetic-password"


def test_demo_runtime_paths_do_not_restore_the_exposed_password() -> None:
    for path in (
        "scripts/demo.sh",
        "scripts/seed_furkids_demo.py",
        "scripts/seed_demo_accounts.py",
    ):
        assert "local-only-password" not in Path(path).read_text()

    script = Path("scripts/demo.sh").read_text()
    assert "STRAYHUB_DEMO_PASSWORD" in script
    assert "openssl rand" in script


def test_three_shelter_demo_exposes_only_dynamic_new_taipei_region() -> None:
    accounts = Path("scripts/seed_demo_accounts.py").read_text()
    furkids = Path("scripts/seed_furkids_demo.py").read_text()

    assert 'organization.service_area = "新北市"' in accounts
    assert 'organization.service_area = "新北市"' in furkids
    assert 'organization.region = "north"' in accounts
    assert 'organization.region = "north"' in furkids
    assert "animal.is_adoptable = True" in accounts
    assert "animal.is_adoptable = True" in furkids
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
        "postgresql+asyncpg://u:p@127.0.0.1/strayhub_test",
        "postgresql+asyncpg://u:p@127.0.0.1/strayhub_demo_test",
        "postgresql+asyncpg://u:p@127.0.0.1/strayhub?host=remote.example",
        "sqlite:///strayhub",
    ],
)
def test_demo_guard_denies_remote_or_ambiguous_database(url):
    from scripts.local_demo import require_local_demo

    with pytest.raises(ValueError):
        require_local_demo("local", url)


def test_demo_guard_allows_only_canonical_local_database():
    from scripts.local_demo import require_local_demo

    require_local_demo("local", "postgresql+asyncpg://u:p@127.0.0.1:65432/strayhub")


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


async def test_valid_local_moa_data_skips_live_import():
    from scripts.bootstrap_demo import import_or_reuse

    import_calls = []

    async def forbidden_import(**kwargs):
        import_calls.append(kwargs)
        raise AssertionError("valid local data must not contact MOA")

    async def valid_existing(code):
        return {"animals": 60, "valid": True, "photos_checked": True}

    result = await import_or_reuse(
        "MOA-SHELTER-51", run_import=forbidden_import, verify=valid_existing
    )
    assert result["sync"] == "reused_existing"
    assert import_calls == []


async def test_invalid_local_moa_data_imports_and_requires_final_verification():
    from scripts.bootstrap_demo import import_or_reuse

    verification_results = iter(
        [
            {"animals": 12, "valid": False, "photos_checked": True},
            {"animals": 60, "valid": True, "photos_checked": True},
        ]
    )
    import_calls = []

    async def successful_import(**kwargs):
        import_calls.append(kwargs)
        return 0

    async def verify(_code):
        return next(verification_results)

    result = await import_or_reuse("MOA-SHELTER-51", run_import=successful_import, verify=verify)

    assert result["sync"] == "completed"
    assert len(import_calls) == 1


async def test_forced_refresh_imports_even_with_valid_local_data():
    from scripts.bootstrap_demo import import_or_reuse

    import_calls = []

    async def successful_import(**kwargs):
        import_calls.append(kwargs)
        return 0

    async def valid_existing(_code):
        return {"animals": 60, "valid": True, "photos_checked": True}

    result = await import_or_reuse(
        "MOA-SHELTER-58",
        refresh=True,
        run_import=successful_import,
        verify=valid_existing,
    )

    assert result["sync"] == "completed"
    assert len(import_calls) == 1


async def test_normal_startup_is_network_independent_with_valid_local_data():
    from scripts.bootstrap_demo import import_or_reuse

    async def unavailable_network(**_kwargs):
        raise ConnectionError("MOA unavailable")

    async def valid_existing(_code):
        return {"animals": 60, "valid": True, "photos_checked": True}

    result = await import_or_reuse(
        "MOA-SHELTER-51",
        run_import=unavailable_network,
        verify=valid_existing,
    )

    assert result["sync"] == "reused_existing"


async def test_broken_photo_dataset_uses_import_repair_path():
    from scripts.bootstrap_demo import import_or_reuse

    verification_results = iter(
        [
            {"animals": 60, "valid": False, "photos_checked": True},
            {"animals": 60, "valid": True, "photos_checked": True},
        ]
    )
    imported = False

    async def repair_import(**_kwargs):
        nonlocal imported
        imported = True
        return 0

    async def verify(_code):
        return next(verification_results)

    result = await import_or_reuse("MOA-SHELTER-58", run_import=repair_import, verify=verify)

    assert imported is True
    assert result["sync"] == "completed"


async def test_explicit_refresh_failure_is_nonzero_with_verified_data_available():
    from scripts.bootstrap_demo import import_or_reuse

    async def failed_import(**kwargs):
        return 1

    async def valid_existing(_code):
        return {"animals": 60, "valid": True, "photos_checked": True}

    with pytest.raises(RuntimeError, match="refresh_failed:MOA-SHELTER-58"):
        await import_or_reuse(
            "MOA-SHELTER-58",
            refresh=True,
            run_import=failed_import,
            verify=valid_existing,
        )
