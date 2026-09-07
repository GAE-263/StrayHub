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
        "login_abuse_hmac_secret": "synthetic-login-abuse-hmac-secret-material",
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


def test_line_role_menu_features_are_local_by_default_and_fail_closed_nonlocal() -> None:
    assert Settings(_env_file=None, app_env="local").line_role_menu_features_active() is True
    assert safe_non_local_settings().line_role_menu_features_active() is False
    assert (
        safe_non_local_settings(
            line_role_menu_features_enabled=True
        ).line_role_menu_features_active()
        is True
    )


def test_enabled_line_role_menu_features_require_complete_release_evidence() -> None:
    with pytest.raises(UnsafeRuntimeConfigurationError) as caught:
        safe_non_local_settings(line_role_menu_features_enabled=True).validate_runtime_safety()

    message = str(caught.value)
    for field in (
        "WEB_PUBLIC_BASE_URL",
        "LINE_RICH_MENU_DEFAULT_ID",
        "LINE_RICH_MENU_VOLUNTEER_ID",
        "LINE_RICH_MENU_STAFF_ID",
        "LINE_STAFF_LIFF_ID",
        "LINE_ROLE_MENU_SMOKE_EVIDENCE",
    ):
        assert field in message


def test_enabled_line_role_menu_features_accept_complete_safe_contract() -> None:
    settings = safe_non_local_settings(
        line_role_menu_features_enabled=True,
        web_public_base_url="https://strayhub.enadv.quest",
        line_rich_menu_default_id="richmenu-default-production",
        line_rich_menu_volunteer_id="richmenu-volunteer-production",
        line_rich_menu_staff_id="richmenu-staff-production",
        line_staff_liff_id="1234567890-StaffLiff",
        line_role_menu_smoke_evidence=f"verified-20260901-{'a' * 40}",
    )

    assert settings.validate_runtime_safety() is settings


def test_enabled_worker_requires_only_post_commit_line_menu_inputs() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://worker:synthetic@database.internal/strayhub",
        minio_endpoint="https://objects.internal",
        minio_access_key="synthetic-access-credential",
        minio_secret_key="synthetic-secret-credential",
        line_role_menu_features_enabled=True,
        line_channel_access_token="production-line-access-token",
        line_rich_menu_default_id="richmenu-default-production",
        line_rich_menu_volunteer_id="richmenu-volunteer-production",
    )

    assert settings.validate_runtime_safety(process="worker") is settings


def test_migration_process_policy_requires_only_its_database() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://worker:synthetic@database.internal/strayhub",
    )

    assert settings.validate_runtime_safety(process="migration").app_env == "production"


def test_worker_process_requires_database_and_object_storage() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://worker:synthetic@database.internal/strayhub",
        minio_endpoint="https://objects.internal",
        minio_access_key="synthetic-access-credential",
        minio_secret_key="synthetic-secret-credential",
        minio_bucket="strayhub-private",
    )

    assert settings.validate_runtime_safety(process="worker").app_env == "production"


def test_worker_process_rejects_unsafe_object_storage_defaults() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://worker:synthetic@database.internal/strayhub",
    )

    with pytest.raises(UnsafeRuntimeConfigurationError) as caught:
        settings.validate_runtime_safety(process="worker")

    assert "MINIO_ENDPOINT" in str(caught.value)


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
        (
            {"login_abuse_hmac_secret": "local-only-login-abuse-hmac-secret-material"},
            "LOGIN_ABUSE_HMAC_SECRET",
        ),
        ({"login_abuse_hmac_secret": "short-secret"}, "LOGIN_ABUSE_HMAC_SECRET"),
        ({"login_abuse_hmac_secret": ""}, "LOGIN_ABUSE_HMAC_SECRET"),
        ({"pii_kms_key_name": None}, "PII_KMS_KEY_NAME"),
        (
            {"pii_kms_key_name": "projects/synthetic/locations/global/keyRings/pii"},
            "PII_KMS_KEY_NAME",
        ),
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


def test_worker_stool_provider_requires_complete_nonlocal_secret_pair() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://worker:synthetic@database.internal/strayhub",
        minio_endpoint="https://objects.internal",
        minio_access_key="synthetic-access-credential",
        minio_secret_key="synthetic-secret-credential",
        stool_api_url="https://stool.internal/analyze",
        stool_api_key=None,
    )

    with pytest.raises(UnsafeRuntimeConfigurationError) as caught:
        settings.validate_runtime_safety(process="worker")

    assert "STOOL_API_URL and STOOL_API_KEY" in str(caught.value)


def test_worker_stool_provider_accepts_safe_url_and_secret_without_leaking_it() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://worker:synthetic@database.internal/strayhub",
        minio_endpoint="https://objects.internal",
        minio_access_key="synthetic-access-credential",
        minio_secret_key="synthetic-secret-credential",
        stool_api_url="https://stool.internal/analyze",
        stool_api_key="synthetic-provider-credential",
    )

    assert settings.validate_runtime_safety(process="worker") is settings


def test_enabled_celery_worker_requires_broker_line_and_gemini_credentials() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+asyncpg://worker:synthetic@database.internal/strayhub",
        minio_endpoint="https://objects.internal",
        minio_access_key="synthetic-access-credential",
        minio_secret_key="synthetic-secret-credential",
        celery_ai_enabled=True,
        celery_broker_url="redis://redis.internal:6379/0",
        line_channel_access_token="",
        gemini_api_key=None,
    )

    with pytest.raises(UnsafeRuntimeConfigurationError) as caught:
        settings.validate_runtime_safety(process="worker")

    message = str(caught.value)
    assert "LINE_CHANNEL_ACCESS_TOKEN" in message
    assert "GEMINI_API_KEY or GEMINI_SERVICE_ACCOUNT_PATH" in message
