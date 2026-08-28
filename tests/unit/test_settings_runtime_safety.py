import pytest
from services.api.app.config.settings import Settings, UnsafeRuntimeConfigurationError


def safe_non_local_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "app_env": "production",
        "database_url": "postgresql+asyncpg://runtime:synthetic@database.internal/strayhub",
        "minio_endpoint": "https://objects.internal",
        "minio_access_key": "synthetic-access-credential",
        "minio_secret_key": "synthetic-secret-credential",
        "minio_bucket": "strayhub-private",
        "line_channel_id": "synthetic-line-channel",
        "line_channel_secret": "synthetic-line-channel-secret",
        "line_channel_access_token": "synthetic-line-access-token",
        "liff_id": "synthetic-liff-id",
        "animal_confirmation_secret": "synthetic-confirmation-secret",
        "auth_jwt_issuer": "strayhub-production",
        "auth_jwt_audience": "strayhub-api",
        "auth_jwt_active_private_key_reference": "active-private-v1",
        "auth_jwt_active_public_key_reference": "active-public-v1",
        "auth_jwt_active_private_key": "synthetic-private-key-material",
        "auth_jwt_active_public_key": "synthetic-public-key-material",
        "pii_encryption_provider": "gcp-kms",
        "pii_allow_local_provider": False,
        "pii_kms_key_name": (
            "projects/synthetic/locations/global/keyRings/strayhub/cryptoKeys/volunteer-pii"
        ),
        "ai_provider": "mock",
        "ai_endpoint": None,
        "ai_api_key": None,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("app_env", ["local", "test", "testing"])
def test_local_and_test_modes_allow_repository_defaults(app_env: str) -> None:
    assert Settings(_env_file=None, app_env=app_env).validate_runtime_safety().app_env == app_env


def test_safe_non_local_configuration_passes_with_optional_ai_disabled() -> None:
    assert safe_non_local_settings().validate_runtime_safety().app_env == "production"


@pytest.mark.parametrize("process", ["worker", "migration"])
def test_non_api_process_policy_requires_only_its_database(process: str) -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://worker:synthetic@database.internal/strayhub",
    )

    assert settings.validate_runtime_safety(process=process).app_env == "production"


@pytest.mark.parametrize("process", ["worker", "migration"])
def test_non_api_process_rejects_unsafe_database(process: str) -> None:
    settings = Settings(_env_file=None, app_env="production", database_url="")

    with pytest.raises(UnsafeRuntimeConfigurationError) as caught:
        settings.validate_runtime_safety(process=process)

    assert "DATABASE_URL" in str(caught.value)


@pytest.mark.parametrize(
    ("overrides", "field_name"),
    [
        ({"database_url": ""}, "DATABASE_URL"),
        ({"auth_jwt_active_private_key": None}, "AUTH_JWT_ACTIVE_PRIVATE_KEY"),
        ({"auth_jwt_active_public_key": "fake-jwt-key"}, "AUTH_JWT_ACTIVE_PUBLIC_KEY"),
        ({"pii_kms_key_name": None}, "PII_KMS_KEY_NAME"),
        ({"line_channel_secret": "fake-line-secret"}, "LINE_CHANNEL_SECRET"),
        ({"minio_access_key": "local-access-key"}, "MINIO_ACCESS_KEY"),
        (
            {"ai_provider": "external", "ai_endpoint": None, "ai_api_key": None},
            "AI_ENDPOINT",
        ),
    ],
)
def test_non_local_configuration_aggregates_unsafe_fields(overrides, field_name: str) -> None:
    with pytest.raises(UnsafeRuntimeConfigurationError) as caught:
        safe_non_local_settings(**overrides).validate_runtime_safety()

    assert field_name in str(caught.value)


def test_error_does_not_expose_secret_contents() -> None:
    secret_value = "fake-super-secret-leak-marker"

    with pytest.raises(UnsafeRuntimeConfigurationError) as caught:
        safe_non_local_settings(
            line_channel_secret=secret_value,
            auth_jwt_active_private_key=secret_value,
        ).validate_runtime_safety()

    message = str(caught.value)
    assert "LINE_CHANNEL_SECRET" in message
    assert "AUTH_JWT_ACTIVE_PRIVATE_KEY" in message
    assert secret_value not in message


def test_external_ai_provider_requires_safe_key_but_mock_does_not() -> None:
    safe_non_local_settings(ai_provider="mock", ai_api_key=None).validate_runtime_safety()

    with pytest.raises(UnsafeRuntimeConfigurationError) as caught:
        safe_non_local_settings(
            ai_provider="external",
            ai_endpoint="https://ai.internal/analyze",
            ai_api_key="placeholder",
        ).validate_runtime_safety()

    assert "AI_API_KEY" in str(caught.value)
