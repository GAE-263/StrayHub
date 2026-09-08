from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import yaml
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from services.api.app.config.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
GCE_ROOT = ROOT / "infra" / "gce"
COMPOSE_PATH = GCE_ROOT / "docker-compose.production.yml"
ENV_PATH = GCE_ROOT / ".env.production.example"
CONFIG_CONTRACT_PATH = ROOT / "docs" / "deployment" / "production-config-contract.md"


def _environment() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_canonical_compose_has_runtime_services_and_bounded_helpers() -> None:
    services = _compose()["services"]

    assert {"postgres", "minio", "api", "worker", "web"} <= services.keys()
    assert set(services) == {
        "postgres",
        "minio",
        "minio-bootstrap",
        "api",
        "migration",
        "worker",
        "redis",
        "celery-worker",
        "celery-beat",
        "web",
    }
    assert services["minio-bootstrap"]["restart"] == "no"
    assert services["migration"]["restart"] == "no"
    assert services["migration"]["profiles"] == ["tools"]


def test_phase_b1_uses_internal_database_and_minio_dns_with_persistence() -> None:
    compose = _compose()
    services = compose["services"]
    environment = _environment()

    database_url = urlparse(environment["DATABASE_URL"])
    migration_url = urlparse(environment["DATABASE_MIGRATION_URL"])
    minio_url = urlparse(environment["MINIO_ENDPOINT"])
    assert environment["APP_ENV"] == "gcp-demo"
    assert database_url.hostname == "postgres"
    assert database_url.port == 5432
    assert (database_url.username, database_url.password) != ("strayhub", "strayhub")
    assert migration_url.hostname == "postgres"
    assert migration_url.username != database_url.username
    assert services["migration"]["environment"]["DATABASE_URL"].startswith(
        "${DATABASE_MIGRATION_URL"
    )
    assert minio_url.hostname == "minio"
    assert minio_url.port == 9000
    assert services["web"]["environment"]["API_BASE_URL"] == "http://api:8080"
    assert "ports" not in services["postgres"]
    assert "ports" not in services["minio"]
    assert "ports" not in services["redis"]
    assert services["web"]["ports"] == [
        {
            "target": 8080,
            "published": "${E4_WEB_UPSTREAM_HOST_PORT:?E4_WEB_UPSTREAM_HOST_PORT is required}",
            "protocol": "tcp",
        }
    ]
    assert services["api"]["ports"] == [
        {
            "target": 8080,
            "published": "${E4_API_UPSTREAM_HOST_PORT:?E4_API_UPSTREAM_HOST_PORT is required}",
            "protocol": "tcp",
        }
    ]
    assert services["api"]["environment"]["LOGIN_ABUSE_HMAC_SECRET"] == (
        "${LOGIN_ABUSE_HMAC_SECRET:?LOGIN_ABUSE_HMAC_SECRET is required}"
    )
    assert "postgres_data:/var/lib/postgresql/data" in services["postgres"]["volumes"]
    assert services["minio"]["volumes"] == ["minio_data:/data"]
    assert services["redis"]["volumes"] == ["redis_data:/data"]
    assert {"postgres_data", "minio_data", "redis_data"} == compose["volumes"].keys()


def test_phase_b1_dependencies_wait_for_health_and_bucket_bootstrap() -> None:
    services = _compose()["services"]

    assert "healthcheck" in services["postgres"]
    assert "healthcheck" in services["minio"]
    assert services["api"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert (
        services["api"]["depends_on"]["minio-bootstrap"]["condition"]
        == "service_completed_successfully"
    )
    assert services["worker"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert (
        services["worker"]["depends_on"]["minio-bootstrap"]["condition"]
        == "service_completed_successfully"
    )
    assert services["celery-worker"]["depends_on"]["redis"]["condition"] == "service_healthy"
    assert services["celery-beat"]["depends_on"]["celery-worker"]["condition"] == "service_healthy"
    assert services["web"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_celery_and_redis_runtime_are_bounded_and_use_one_configured_topology() -> None:
    services = _compose()["services"]
    redis = services["redis"]
    api = services["api"]
    worker = services["celery-worker"]
    beat = services["celery-beat"]

    assert "--appendonly yes" in redis["command"][-1]
    assert "--appendfsync everysec" in redis["command"][-1]
    assert "--maxmemory" in redis["command"][-1]
    assert "--maxmemory-policy noeviction" in redis["command"][-1]
    assert "--requirepass" in redis["command"][-1]
    redis_healthcheck = redis["healthcheck"]["test"]
    assert redis_healthcheck[0] == "CMD-SHELL"
    assert "REDISCLI_AUTH=$${REDIS_PASSWORD}" in redis_healthcheck[1]
    assert "redis-cli -a" not in redis_healthcheck[1]
    assert "ports" not in redis
    assert api["environment"]["CELERY_QUEUE_AI"] == "${CELERY_QUEUE_AI:-ai}"
    assert api["environment"]["CELERY_QUEUE_SYSTEM"] == "${CELERY_QUEUE_SYSTEM:-system}"
    assert "--queues=${CELERY_QUEUE_AI:-ai},${CELERY_QUEUE_SYSTEM:-system}" in worker["command"]
    assert "--concurrency=${CELERY_WORKER_CONCURRENCY:-2}" in worker["command"]
    assert "--pidfile=/tmp/celerybeat.pid" in beat["command"]


def test_postgres_bootstrap_separates_migration_and_rls_runtime_roles() -> None:
    bootstrap = (GCE_ROOT / "postgres" / "init-runtime-role.sh").read_text(encoding="utf-8")

    assert "CREATE ROLE strayhub_runtime NOLOGIN NOSUPERUSER" in bootstrap
    assert 'CREATE ROLE :"runtime_user" LOGIN PASSWORD' in bootstrap
    assert 'GRANT strayhub_runtime TO :"runtime_user"' in bootstrap
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public" in bootstrap
    assert "BYPASSRLS" not in bootstrap.replace("NOBYPASSRLS", "")


def test_verification_environment_passes_nonlocal_api_fail_fast(tmp_path: Path) -> None:
    environment = _environment()
    generated_dir = tmp_path / "generated"
    result = subprocess.run(
        [GCE_ROOT / "scripts" / "generate-verification-jwt-keys.sh"],
        cwd=ROOT,
        env={**os.environ, "STRAYHUB_VERIFICATION_JWT_DIR": str(generated_dir)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    private_pem = (generated_dir / "jwt-private.pem").read_text(encoding="utf-8")
    public_pem = (generated_dir / "jwt-public.pem").read_text(encoding="utf-8")
    settings_values = {key.lower(): value for key, value in environment.items()}
    settings_values["auth_jwt_active_private_key"] = private_pem
    settings_values["auth_jwt_active_public_key"] = public_pem

    assert Settings(_env_file=None, **settings_values).validate_runtime_safety() is not None
    load_pem_private_key(private_pem.encode(), password=None)
    load_pem_public_key(public_pem.encode())


def test_verification_environment_contains_no_blocked_local_values() -> None:
    environment = _environment()
    normalized_values = "\n".join(environment.values()).lower()

    for blocked in (
        "fake-",
        "local-only-",
        "changeme",
        "example",
        "dummy",
        "placeholder",
        "minioadmin",
        "localhost",
        "127.0.0.1",
        "strayhub:strayhub",
    ):
        assert blocked not in normalized_values
    template = ENV_PATH.read_text(encoding="utf-8")
    assert "SYNTHETIC VERIFICATION ONLY" in template
    assert "NOT FOR REAL DEPLOYMENT" in template


def test_phase_b1_has_no_legacy_cloud_runtime_dependency() -> None:
    compose_text = COMPOSE_PATH.read_text(encoding="utf-8").lower()

    for forbidden in ("cloud run", "cloud sql", "gcs", "migrate.sh", "apply.sh"):
        assert forbidden not in compose_text
    assert "infra/gce/images/dockerfile.api" in compose_text
    assert "infra/gce/images/dockerfile.worker" in compose_text
    assert "infra/gce/images/dockerfile.web" in compose_text


def test_migration_and_persistence_operations_are_documented() -> None:
    contract = CONFIG_CONTRACT_PATH.read_text(encoding="utf-8")

    assert "run --rm migration" in contract
    assert 'command: ["alembic", "-c", "services/api/alembic.ini", "upgrade", "head"]' in (
        COMPOSE_PATH.read_text(encoding="utf-8")
    )
    assert "docker compose down` retains" in contract
    assert "docker compose down -v` destroys" in contract
    assert "strayhub-b2-verify" in contract
