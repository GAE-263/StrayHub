from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    app_name: str = "strayhub"
    database_url: str = "postgresql+asyncpg://strayhub:strayhub@localhost:5432/strayhub"
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
    liff_id: str = "fake-liff-id"
    animal_confirmation_secret: str = "local-animal-confirmation-secret"
    auth_jwt_issuer: str = "strayhub-local"
    auth_jwt_audience: str = "strayhub-api"
    auth_jwt_active_private_key_reference: str = "local-active-key"
    auth_jwt_active_public_key_reference: str = "local-active-public-key"
    auth_jwt_previous_public_key_reference: str | None = "local-previous-public-key"
    auth_jwt_active_private_key: str | None = None
    auth_jwt_active_public_key: str | None = None
    auth_jwt_previous_public_key: str | None = None
    session_access_token_ttl_seconds: int = Field(default=900, ge=1)
    session_refresh_token_ttl_seconds: int = Field(default=604800, ge=1)
    draft_ttl_seconds: int = Field(default=86400, ge=1)
    ai_provider: str = "mock"
    ai_model_name: str = "mock-observation-model"
    ai_model_version: str = "local-v1"
    ai_prompt_template_id: str = "care-observation"
    ai_prompt_version: str = "local-v1"
    ai_output_schema_version: str = "v1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
