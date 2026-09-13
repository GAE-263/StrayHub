import json
from hashlib import sha256
from pathlib import Path

import pytest
from services.api.app.config.line_menu_smoke import validate_report
from tests.support.line_menu_smoke import real_report_fixture
from tests.unit.test_settings_runtime_safety import safe_non_local_settings


def _settings(tmp_path: Path, *, app_env: str):
    settings = safe_non_local_settings(
        app_env=app_env,
        line_role_menu_features_enabled=True,
        web_public_base_url="https://runtime.example.invalid",
        line_rich_menu_default_id="richmenu-default",
        line_rich_menu_volunteer_id="richmenu-volunteer",
        line_rich_menu_adoption_hub_id="richmenu-hub",
    )
    report = real_report_fixture(settings, tmp_path)
    return settings, report


@pytest.mark.parametrize(
    ("app_env", "expected_environment"),
    [("production", "production"), ("acceptance", "production-like")],
)
def test_real_line_evidence_is_bound_to_runtime_environment(
    tmp_path: Path, app_env: str, expected_environment: str
) -> None:
    settings, report = _settings(tmp_path, app_env=app_env)

    assert report["environment"] == expected_environment
    validate_report(settings)


@pytest.mark.parametrize(
    ("app_env", "wrong_environment"),
    [("production", "production-like"), ("acceptance", "production")],
)
def test_cross_environment_real_line_evidence_is_rejected(
    tmp_path: Path, app_env: str, wrong_environment: str
) -> None:
    settings, report = _settings(tmp_path, app_env=app_env)
    report["environment"] = wrong_environment
    report_path = Path(settings.line_role_menu_report_file)
    report_path.write_text(json.dumps(report))
    settings.line_role_menu_report_sha256 = sha256(report_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)


def test_unknown_runtime_cannot_claim_production_evidence(tmp_path: Path) -> None:
    settings, _ = _settings(tmp_path, app_env="staging")

    with pytest.raises(ValueError, match="report invalid"):
        validate_report(settings)
