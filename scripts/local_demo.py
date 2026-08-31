"""Shared safety boundary and identities for local-only demo tooling."""

from urllib.parse import urlsplit

from scripts.test_database import require_test_database
from services.api.app.config.settings import get_settings
from sqlalchemy.engine import make_url

DEMO_SHELTERS = {
    "FURKIDS-ASIA": "毛小孩幸福聯盟協會",
    "MOA-SHELTER-51": "新北市新店區公立動物之家",
    "MOA-SHELTER-58": "新北市五股區公立動物之家",
}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def require_local_demo(app_env: str, database_url: str) -> None:
    url = make_url(database_url)
    if (
        app_env not in {"local", "test"}
        or url.drivername not in {"postgresql", "postgresql+asyncpg"}
        or url.host not in LOCAL_HOSTS
        or url.database != "strayhub"
        or url.query
    ):
        raise ValueError(
            "local_demo_only: require APP_ENV=local/test and loopback strayhub database"
        )


def guard(*, storage: bool = False, allow_isolation_test: bool = False) -> None:
    settings = get_settings()
    try:
        require_local_demo(settings.app_env, settings.database_url)
    except ValueError:
        if not allow_isolation_test:
            raise
        require_test_database(settings.database_url)
    # The repository's Alembic env reads DATABASE_URL, not database_migration_url.
    # Validate the actual target instead of rejecting an unrelated unused setting.
    if storage and urlsplit(settings.minio_endpoint).hostname not in LOCAL_HOSTS:
        raise ValueError("local_minio_required")


if __name__ == "__main__":
    guard(storage=True)
    print("Local demo database/storage guard: PASS")
