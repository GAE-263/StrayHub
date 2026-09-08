#!/usr/bin/env python3
"""Validate the fully rendered acceptance Compose model without starting it."""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urlparse


class PolicyError(RuntimeError):
    pass


DIGEST_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*[a-z0-9]@sha256:[0-9a-f]{64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
APP_SERVICES = {"api", "worker", "celery-worker", "celery-beat", "web", "migration"}
ALL_SERVICES = APP_SERVICES | {"postgres", "redis", "minio", "minio-bootstrap"}
PUSH_SERVICES = {"api", "worker", "celery-worker", "celery-beat"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyError(message)


def validate(model: dict) -> None:
    require(model.get("name") == "strayhub-acceptance", "project name is not isolated")
    services = model.get("services", {})
    require(set(services) == ALL_SERVICES, "unexpected acceptance service topology")

    published: set[tuple[str, int]] = set()
    for name, service in services.items():
        require(service.get("restart") == "no", f"{name} restart policy must be no")
        require(float(service.get("cpus", 0)) > 0, f"{name} CPU limit is missing")
        require(int(service.get("mem_limit", 0)) > 0, f"{name} memory limit is missing")
        for port in service.get("ports", []):
            host_ip = port.get("host_ip")
            host_port = int(port.get("published"))
            require(host_ip == "127.0.0.1", f"{name} port is not loopback-only")
            require(host_port not in {3000, 8080}, f"{name} reuses a production port")
            require((host_ip, host_port) not in published, "duplicate host port")
            published.add((host_ip, host_port))

    require(
        published == {("127.0.0.1", 13000), ("127.0.0.1", 18080)},
        "acceptance host ports differ from the approved ingress boundary",
    )

    for name in APP_SERVICES:
        service = services[name]
        require(not service.get("build"), f"{name} must not have a build context")
        image = service.get("image", "")
        require(bool(DIGEST_IMAGE.fullmatch(image)), f"{name} image is not immutable")

    for name in APP_SERVICES - {"web", "migration"}:
        env = services[name].get("environment", {})
        require(env.get("APP_ENV") == "acceptance", f"{name} APP_ENV is not acceptance")
        require(env.get("CELERY_AI_ENABLED") == "false", f"{name} AI must be disabled")
        require(str(env.get("CELERY_WORKER_CONCURRENCY")) == "1", f"{name} concurrency is not 1")

    for name in PUSH_SERVICES:
        values = (
            services[name]
            .get("environment", {})
            .get("LINE_NOTIFICATION_RECIPIENT_ALLOWLIST_SHA256", "")
            .split(",")
        )
        hashes = {value.strip() for value in values if value.strip()}
        require(len(hashes) >= 2, f"{name} needs two controlled LINE identities")
        require(all(SHA256.fullmatch(value) for value in hashes), f"{name} allowlist is invalid")

    api_env = services["api"].get("environment", {})
    database = urlparse(api_env.get("DATABASE_URL", ""))
    broker = urlparse(api_env.get("CELERY_BROKER_URL", ""))
    minio = urlparse(api_env.get("MINIO_ENDPOINT", ""))
    require(database.hostname == "postgres", "API database is not acceptance-internal")
    require(database.path == "/strayhub_acceptance", "API database name is not isolated")
    require(database.username == "strayhub_acceptance_app", "API database role is not isolated")
    migration_database = urlparse(
        services["migration"].get("environment", {}).get("DATABASE_URL", "")
    )
    require(
        migration_database.hostname == "postgres"
        and migration_database.path == "/strayhub_acceptance"
        and migration_database.username == "strayhub_acceptance_migration",
        "migration database boundary is not isolated",
    )
    require(broker.hostname == "redis" and bool(broker.password), "broker is not private Redis")
    require(minio.hostname == "minio", "MinIO endpoint is not internal")
    require(api_env.get("MINIO_BUCKET") == "strayhub-acceptance-private", "bucket is not isolated")
    require(
        api_env.get("CELERY_QUEUE_AI", "").startswith("acceptance-"), "AI queue is not isolated"
    )
    require(
        api_env.get("CELERY_QUEUE_SYSTEM", "").startswith("acceptance-"),
        "system queue is not isolated",
    )

    volumes = model.get("volumes", {})
    expected_volumes = {
        "strayhub-acceptance-postgres-data",
        "strayhub-acceptance-minio-data",
        "strayhub-acceptance-redis-data",
    }
    require(
        {item.get("name") for item in volumes.values()} == expected_volumes,
        "volume names are not isolated",
    )
    networks = model.get("networks", {})
    require(
        {item.get("name") for item in networks.values()} == {"strayhub-acceptance-runtime"},
        "network name is not isolated",
    )

    serialized = json.dumps(model, sort_keys=True).lower()
    for forbidden in (
        "strayhub-production",
        "/var/lib/strayhub/secrets/current",
        "strayhub.enadv.quest",
        'gemini_service_account_path": "/',
    ):
        require(
            forbidden not in serialized, f"rendered model contains forbidden boundary: {forbidden}"
        )


def main() -> int:
    try:
        validate(json.load(sys.stdin))
    except (json.JSONDecodeError, PolicyError, TypeError, ValueError) as exc:
        print(f"[Acceptance compose policy] FAIL: {exc}", file=sys.stderr)
        return 1
    print("[Acceptance compose policy] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
