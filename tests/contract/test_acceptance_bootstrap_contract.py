from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "scripts" / "bootstrap_acceptance.py"
DOC = ROOT / "docs" / "deployment" / "acceptance-bootstrap.md"
COMPOSE_OVERRIDE = ROOT / "infra" / "gce" / "docker-compose.acceptance.yml"
WRAPPER = ROOT / "infra" / "gce" / "scripts" / "run-acceptance-bootstrap.sh"
LIVE_VERIFIER = ROOT / "scripts" / "verify_acceptance_live.py"
LIVE_WRAPPER = ROOT / "infra" / "gce" / "scripts" / "run-acceptance-live-verification.sh"


def test_acceptance_bootstrap_is_operator_cli_without_auth_bypass_surface() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert "validate_execution_guard(" in source
    assert "--confirm-synthetic-data" in source
    assert "STRAYHUB_ALLOW_ACCEPTANCE_BOOTSTRAP" in source
    assert "Argon2PasswordHasher" in source
    assert "VolunteerAccessService" in source
    assert "OrganizationManagementService" in source
    assert "@router" not in source
    assert "debug-login" not in source.lower()
    assert "x-debug" not in source.lower()
    assert "JwtAccessTokenAdapter" not in source
    assert "private_key" not in source
    assert "INSERT INTO" not in source.upper()
    assert 'validate_runtime_safety(process="migration")' in source


def test_acceptance_bootstrap_documents_secret_and_tenant_boundaries() -> None:
    document = DOC.read_text(encoding="utf-8")

    for required in (
        "APP_ENV",
        "STRAYHUB_ALLOW_ACCEPTANCE_BOOTSTRAP=true",
        "--confirm-synthetic-data",
        "ACCEPTANCE_BOOTSTRAP_PASSWORD_FILE",
        "mode `0600`",
        "Tenant A only",
        "Tenant B only",
        "no raw SQL",
        "Never put real PII",
    ):
        assert required in document


def test_acceptance_compose_override_is_full_isolated_runtime() -> None:
    source = COMPOSE_OVERRIDE.read_text(encoding="utf-8")

    assert "DATABASE_URL: ${DATABASE_MIGRATION_URL:" in source
    assert "APP_ENV: acceptance" in source
    assert "name: strayhub-acceptance" in source
    assert "published: ${ACCEPTANCE_WEB_HOST_PORT:" in source
    assert "published: ${ACCEPTANCE_API_HOST_PORT:" in source
    assert "build: !reset null" in source
    assert 'CELERY_AI_ENABLED: "false"' in source
    assert "--concurrency=1" in source
    assert source.count("  api:") == 1


def test_acceptance_wrapper_keeps_runtime_keys_process_local() -> None:
    source = WRAPPER.read_text(encoding="utf-8")

    assert source.startswith("#!/bin/sh\nset -eu\n")
    assert "/run/secrets/runtime_jwt_private_key" in source
    assert "/run/secrets/runtime_jwt_public_key" in source
    assert 'exec python -m scripts.bootstrap_acceptance "$@"' in source
    assert "printenv" not in source
    assert 'echo "$AUTH_JWT' not in source


def test_live_verifier_uses_normal_login_without_printing_credentials() -> None:
    source = LIVE_VERIFIER.read_text(encoding="utf-8")

    assert '"/v1/auth/login"' in source
    assert '"Authorization": f"Bearer {access_token}"' in source
    assert '"/v1/qr-tokens/resolve"' in source
    assert '"/v1/care-reports"' in source
    assert "JwtAccessTokenAdapter" not in source
    assert "private_key" not in source
    assert '"password": password' in source
    assert '"password": password,' not in source.split("return {")[-1]
    assert "make_url(settings.database_url).username" in source
    assert "WHERE rolname = :runtime_role" in source
    assert '{"runtime_role": runtime_role_name}' in source
    assert "WHERE rolname = 'strayhub_app'" not in source

    wrapper = LIVE_WRAPPER.read_text(encoding="utf-8")
    assert 'exec python -m scripts.verify_acceptance_live "$@"' in wrapper
    assert "printenv" not in wrapper
    assert 'echo "$AUTH_JWT' not in wrapper
