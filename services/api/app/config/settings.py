import re
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class UnsafeRuntimeConfigurationError(RuntimeError):
    """Raised when non-local runtime configuration is missing or unsafe."""


_PLACEHOLDER_SECRET_VALUES = frozenset(
    {
        "changeme",
        "change-me",
        "dev-secret",
        "dummy",
        "example",
        "local-access-key",
        "local-active-key",
        "local-active-public-key",
        "local-animal-confirmation-secret",
        "local-previous-public-key",
        "local-secret-key",
        "minioadmin",
        "placeholder",
        "test-secret",
    }
)
_PLACEHOLDER_SECRET_PREFIXES = ("fake-", "local-only-")
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_KMS_CRYPTO_KEY_PATTERN = re.compile(
    r"^projects/[^/\s]+/locations/[^/\s]+/keyRings/[^/\s]+/cryptoKeys/[^/\s]+$"
)


def is_placeholder_secret(value: str | None) -> bool:
    """Recognize documented, unmistakable development-only secret values."""

    if value is None or not value.strip():
        return True
    normalized = value.strip().lower()
    return normalized in _PLACEHOLDER_SECRET_VALUES or normalized.startswith(
        _PLACEHOLDER_SECRET_PREFIXES
    )


def is_loopback_url(value: str | None) -> bool:
    """Return whether a URL targets a local loopback host."""

    if value is None or not value.strip():
        return False
    return (urlparse(value).hostname or "").lower() in _LOOPBACK_HOSTS


def is_kms_crypto_key_name(value: str | None) -> bool:
    """Return whether a value is a full Cloud KMS CryptoKey resource name."""

    return bool(value and _KMS_CRYPTO_KEY_PATTERN.fullmatch(value.strip()))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_name: str = "strayhub"
    database_url: str = "postgresql+asyncpg://strayhub:strayhub@localhost:65432/strayhub"
    database_migration_url: str | None = None
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "local-access-key"
    minio_secret_key: str = "local-secret-key"
    minio_bucket: str = "strayhub-private"
    gcs_bucket: str = "strayhub-demo-private"
    gcs_project_id: str = "fake-strayhub-demo"
    line_channel_id: str = "fake-line-channel-id"
    line_channel_secret: str = "fake-line-channel-secret"
    line_channel_access_token: str = "fake-line-access-token"
    line_login_channel_id: str = ""
    line_login_channel_secret: str = ""
    liff_id: str = "fake-liff-id"
    # 對外可達的 web 網址（例如 demo-line.sh 的 NGROK_URL），用於回覆非 LIFF 的靜態
    # 假頁面連結（例如領養流程占位介面）。留空則退回純文字占位訊息。
    web_public_base_url: str = ""
    # 依角色 Rich Menu 的 richMenuId（由 scripts/sync_line_role_menus.py --apply 產生後填入）。
    # 任一有值時，綁定成功會依角色 link 對應選單；全空則此功能為 no-op。
    line_rich_menu_default_id: str = ""
    line_rich_menu_volunteer_id: str = ""
    line_rich_menu_adopter_id: str = ""
    line_rich_menu_staff_id: str = ""
    animal_confirmation_secret: str = "local-animal-confirmation-secret"
    auth_jwt_issuer: str = "strayhub-local"
    auth_jwt_audience: str = "strayhub-api"
    auth_jwt_active_private_key_reference: str = "local-active-key"
    auth_jwt_active_public_key_reference: str = "local-active-public-key"
    auth_jwt_previous_public_key_reference: str | None = "local-previous-public-key"
    auth_jwt_active_private_key: str | None = None
    auth_jwt_active_public_key: str | None = None
    auth_jwt_previous_public_key: str | None = None
    pii_encryption_provider: str = "local-aes-gcm"
    pii_allow_local_provider: bool = False
    pii_active_key_version: str = "local-v1"
    pii_local_key_base64: SecretStr | None = None
    pii_kms_key_name: str | None = None
    session_access_token_ttl_seconds: int = Field(default=900, ge=1)
    session_refresh_token_ttl_seconds: int = Field(default=604800, ge=1)
    draft_ttl_seconds: int = Field(default=86400, ge=1)
    ai_provider: str = "mock"
    ai_model_name: str = "mock-observation-model"
    ai_model_version: str = "local-v1"
    ai_prompt_template_id: str = "care-observation"
    ai_prompt_version: str = "local-v1"
    ai_output_schema_version: str = "v1"
    ai_endpoint: str | None = None
    ai_api_key: str | None = None
    ai_timeout_seconds: float = Field(default=30.0, gt=0)

    def validate_runtime_safety(self, *, process: str = "api") -> "Settings":
        """Reject unsafe defaults before a non-local process starts work."""

        environment = self.app_env.strip().lower()
        if environment in {"local", "test", "testing"}:
            return self

        problems: list[str] = []

        def missing(field_name: str, value: str | None) -> None:
            if value is None or not value.strip():
                problems.append(f"{field_name} is missing")

        def placeholder(field_name: str, value: str | None) -> None:
            if is_placeholder_secret(value):
                reason = (
                    "is missing" if value is None or not value.strip() else "uses a placeholder"
                )
                problems.append(f"{field_name} {reason}")

        missing("DATABASE_URL", self.database_url)
        if self.database_url and is_loopback_url(self.database_url):
            problems.append("DATABASE_URL uses a loopback host")
        parsed_database_url = urlparse(self.database_url)
        if (
            parsed_database_url.username == "strayhub"
            and parsed_database_url.password == "strayhub"
        ):
            problems.append("DATABASE_URL uses local development credentials")

        if process in {"worker", "migration"}:
            if problems:
                details = "\n".join(f"- {problem}" for problem in problems)
                raise UnsafeRuntimeConfigurationError(
                    f"Unsafe non-local configuration ({self.app_env}):\n{details}"
                )
            return self

        missing("MINIO_ENDPOINT", self.minio_endpoint)
        if self.minio_endpoint and is_loopback_url(self.minio_endpoint):
            problems.append("MINIO_ENDPOINT uses a loopback host")
        placeholder("MINIO_ACCESS_KEY", self.minio_access_key)
        placeholder("MINIO_SECRET_KEY", self.minio_secret_key)
        missing("MINIO_BUCKET", self.minio_bucket)

        placeholder("LINE_CHANNEL_ID", self.line_channel_id)
        placeholder("LINE_CHANNEL_SECRET", self.line_channel_secret)
        placeholder("LINE_CHANNEL_ACCESS_TOKEN", self.line_channel_access_token)
        placeholder("LIFF_ID", self.liff_id)
        if self.liff_id.strip().lower() == "gcp-demo-liff":
            problems.append("LIFF_ID uses a deployment placeholder")

        placeholder("ANIMAL_CONFIRMATION_SECRET", self.animal_confirmation_secret)

        missing("AUTH_JWT_ISSUER", self.auth_jwt_issuer)
        if self.auth_jwt_issuer.strip().lower() == "strayhub-local":
            problems.append("AUTH_JWT_ISSUER uses the local default")
        missing("AUTH_JWT_AUDIENCE", self.auth_jwt_audience)
        placeholder(
            "AUTH_JWT_ACTIVE_PRIVATE_KEY_REFERENCE",
            self.auth_jwt_active_private_key_reference,
        )
        placeholder(
            "AUTH_JWT_ACTIVE_PUBLIC_KEY_REFERENCE",
            self.auth_jwt_active_public_key_reference,
        )
        placeholder("AUTH_JWT_ACTIVE_PRIVATE_KEY", self.auth_jwt_active_private_key)
        placeholder("AUTH_JWT_ACTIVE_PUBLIC_KEY", self.auth_jwt_active_public_key)
        if self.auth_jwt_previous_public_key:
            placeholder(
                "AUTH_JWT_PREVIOUS_PUBLIC_KEY_REFERENCE",
                self.auth_jwt_previous_public_key_reference,
            )
            placeholder("AUTH_JWT_PREVIOUS_PUBLIC_KEY", self.auth_jwt_previous_public_key)

        provider = self.pii_encryption_provider.strip().lower()
        if provider != "gcp-kms":
            problems.append("PII_ENCRYPTION_PROVIDER must use a non-local provider")
        if provider == "gcp-kms":
            missing("PII_KMS_KEY_NAME", self.pii_kms_key_name)
            if self.pii_kms_key_name and not is_kms_crypto_key_name(self.pii_kms_key_name):
                problems.append("PII_KMS_KEY_NAME must be a full Cloud KMS CryptoKey resource name")
        if self.pii_allow_local_provider:
            problems.append("PII_ALLOW_LOCAL_PROVIDER must be false")

        ai_provider = self.ai_provider.strip().lower()
        if ai_provider != "mock":
            missing("AI_ENDPOINT", self.ai_endpoint)
            if self.ai_endpoint and is_loopback_url(self.ai_endpoint):
                problems.append("AI_ENDPOINT uses a loopback host")
            placeholder("AI_API_KEY", self.ai_api_key)
            missing("AI_MODEL_NAME", self.ai_model_name)

        if problems:
            details = "\n".join(f"- {problem}" for problem in problems)
            raise UnsafeRuntimeConfigurationError(
                f"Unsafe non-local configuration ({self.app_env}):\n{details}"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings().validate_runtime_safety()


@lru_cache(maxsize=1)
def get_worker_settings() -> Settings:
    return Settings().validate_runtime_safety(process="worker")
