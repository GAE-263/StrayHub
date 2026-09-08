from __future__ import annotations

import importlib.util
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[2]
GCE = ROOT / "infra" / "gce"
BASE = GCE / "docker-compose.production.yml"
OVERRIDE = GCE / "docker-compose.acceptance.yml"
TEMPLATE = GCE / ".env.acceptance.template"
MAP = GCE / "secrets" / "acceptance-secret-map.tsv"
PREFLIGHT = GCE / "scripts" / "acceptance-preflight.sh"
CLEANUP = GCE / "scripts" / "cleanup-acceptance.sh"
POLICY_PATH = GCE / "scripts" / "acceptance-compose-policy.py"

SPEC = importlib.util.spec_from_file_location("acceptance_compose_policy", POLICY_PATH)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def _env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            result[key] = value
    return result


def _rendered_model() -> dict:
    env = {**os.environ, **_env_file(GCE / ".env.production.example"), **_env_file(TEMPLATE)}
    env.update(
        {
            "LINE_CHANNEL_ID": "acceptance-line-channel",
            "LINE_LOGIN_CHANNEL_ID": "2000000002",
            "LIFF_ID": "2000000002-acceptance",
            "WEB_PUBLIC_BASE_URL": "https://acceptance.invalid-runtime.example.net",
            "LINE_NOTIFICATION_RECIPIENT_ALLOWLIST_SHA256": f"{'a' * 64},{'b' * 64}",
            "PII_KMS_KEY_NAME": "projects/p/locations/global/keyRings/acceptance/cryptoKeys/pii",
            "STRAYHUB_API_IMAGE": f"registry.example/api@sha256:{'1' * 64}",
            "STRAYHUB_WORKER_IMAGE": f"registry.example/worker@sha256:{'2' * 64}",
            "STRAYHUB_WEB_IMAGE": f"registry.example/web@sha256:{'3' * 64}",
            "DATABASE_URL": "postgresql+asyncpg://strayhub_acceptance_app:secret@postgres:5432/strayhub_acceptance",
            "DATABASE_MIGRATION_URL": "postgresql+asyncpg://strayhub_acceptance_migration:secret@postgres:5432/strayhub_acceptance",
            "CELERY_BROKER_URL": "redis://:secret@redis:6379/0",
        }
    )
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "strayhub-acceptance",
            "--profile",
            "tools",
            "--file",
            BASE,
            "--file",
            OVERRIDE,
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    import json

    return json.loads(completed.stdout)


def test_rendered_acceptance_model_passes_isolation_policy() -> None:
    policy.validate(_rendered_model())


def test_acceptance_inventory_and_template_are_dedicated() -> None:
    mapping = MAP.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "LINE_CHANNEL_SECRET" in mapping
    assert "LINE_CHANNEL_ACCESS_TOKEN" in mapping
    assert "LOGIN_ABUSE_HMAC_SECRET" in mapping
    assert "ACCEPTANCE_BOOTSTRAP_PASSWORD" in mapping
    assert "APP_ENV=acceptance" in template
    assert "CELERY_AI_ENABLED=false" in template
    assert "CELERY_WORKER_CONCURRENCY=1" in template
    assert "ACCEPTANCE_WEB_HOST_PORT=13000" in template
    assert "ACCEPTANCE_API_HOST_PORT=18080" in template
    assert "ACCEPTANCE_INGRESS_UPSTREAM=http://127.0.0.1:13000" in template
    assert "LINE_NOTIFICATION_RECIPIENT_ALLOWLIST_SHA256=" in template
    assert "strayhub.enadv.quest" not in template


def test_gate3_preflight_is_static_and_cleanup_is_strictly_scoped() -> None:
    preflight = PREFLIGHT.read_text(encoding="utf-8")
    cleanup = CLEANUP.read_text(encoding="utf-8")
    assert "config --quiet" in preflight
    assert "config --format json" in preflight
    assert "static only; no runtime started" in preflight
    assert " compose up" not in preflight
    assert " run --rm" not in preflight
    assert "CLEAN_STRAYHUB_ACCEPTANCE" in cleanup
    assert "--project-name strayhub-acceptance" in cleanup
    assert "down --volumes --remove-orphans" in cleanup
    for forbidden in ("system prune", "volume prune", "rm -rf"):
        assert forbidden not in cleanup


def test_acceptance_line_identity_guard_covers_inbound_and_outbound_paths() -> None:
    adapter = (ROOT / "services/api/app/infrastructure/line/messaging_api_adapter.py").read_text(
        encoding="utf-8"
    )
    webhook = (ROOT / "services/api/app/api/line_webhook.py").read_text(encoding="utf-8")
    assert "self.ensure_recipient_allowed(to_user_id)" in adapter
    assert "line.ensure_recipient_allowed(line_user_id)" in webhook
    assert '"line_recipient_not_allowlisted",' in webhook


def test_release_bundle_contains_acceptance_gate_assets() -> None:
    source = (ROOT / "scripts" / "build-release-bundle.sh").read_text(encoding="utf-8")
    for path in (
        "infra/gce/docker-compose.acceptance.yml",
        "infra/gce/.env.acceptance.template",
        "infra/gce/secrets/acceptance-secret-map.tsv",
        "docs/deployment/acceptance-isolation.md",
        "docs/deployment/acceptance-bootstrap.md",
    ):
        assert path in source


def test_acceptance_secret_materialization_and_static_preflight() -> None:
    with tempfile.TemporaryDirectory(prefix="strayhub-acceptance-", dir="/tmp") as temporary:
        temp = Path(temporary)
        source = temp / "source"
        source.mkdir()
        output = temp / "secrets"
        scalar_values = {
            "postgres-password": "AcceptanceMigrationPassword-2026",
            "postgres-runtime-password": "AcceptanceRuntimePassword-2026",
            "database-url": "postgresql+asyncpg://strayhub_acceptance_app:secret@postgres:5432/strayhub_acceptance",
            "database-migration-url": "postgresql+asyncpg://strayhub_acceptance_migration:secret@postgres:5432/strayhub_acceptance",
            "minio-access-key": "acceptance-storage-user",
            "minio-secret-key": "AcceptanceStoragePassword-2026",
            "line-channel-secret": "acceptance-line-secret-material",
            "line-channel-access-token": "acceptance-line-token-material",
            "animal-confirmation-secret": "acceptance-confirmation-secret-material",
            "login-abuse-hmac-secret": "acceptance-login-abuse-secret-material",
            "redis-password": "AcceptanceRedisPassword-2026",
            "celery-broker-url": "redis://:AcceptanceRedisPassword-2026@redis:6379/0",
            "bootstrap-password": "AcceptanceBootstrapPassword-2026",
        }
        for suffix, value in scalar_values.items():
            (source / f"strayhub-acceptance-{suffix}").write_text(value, encoding="utf-8")

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        (source / "strayhub-acceptance-jwt-private-key").write_bytes(
            private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        (source / "strayhub-acceptance-jwt-public-key").write_bytes(
            private_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        fetched = subprocess.run(
            [
                GCE / "scripts" / "fetch-secrets.sh",
                "--environment",
                "acceptance",
                "--source-dir",
                source,
                "--output-root",
                output,
                "--secret-map",
                MAP,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert fetched.returncode == 0, fetched.stdout + fetched.stderr

        config = temp / "acceptance.env"
        config_values = _env_file(TEMPLATE)
        acceptance_kms_key = (
            "projects/p/locations/global/keyRings/strayhub-acceptance/cryptoKeys/pii"
        )
        config_values.update(
            {
                "LINE_CHANNEL_ID": "2000000001",
                "PRODUCTION_LINE_CHANNEL_ID_FOR_ISOLATION_CHECK": "2999999999",
                "LINE_LOGIN_CHANNEL_ID": "2000000002",
                "LIFF_ID": "2000000002-acceptance",
                "WEB_PUBLIC_BASE_URL": "https://acceptance.strayhub.internal",
                "LINE_NOTIFICATION_RECIPIENT_ALLOWLIST_SHA256": f"{'a' * 64},{'b' * 64}",
                "PII_KMS_KEY_NAME": acceptance_kms_key,
            }
        )
        config.write_text(
            "".join(f"{key}={value}\n" for key, value in config_values.items()),
            encoding="utf-8",
        )
        config.chmod(0o600)
        images = temp / "image-digests.env"
        images.write_text(
            f"STRAYHUB_API_IMAGE=registry.example/api@sha256:{'1' * 64}\n"
            f"STRAYHUB_WORKER_IMAGE=registry.example/worker@sha256:{'2' * 64}\n"
            f"STRAYHUB_WEB_IMAGE=registry.example/web@sha256:{'3' * 64}\n",
            encoding="utf-8",
        )
        images.chmod(0o600)

        real_docker = shutil.which("docker")
        assert real_docker
        fake_bin = temp / "bin"
        fake_bin.mkdir()
        docker_wrapper = fake_bin / "docker"
        docker_wrapper.write_text(
            "#!/bin/sh\n"
            'case "$1" in ps|volume|network) exit 0 ;; esac\n'
            f'exec {shlex.quote(real_docker)} "$@"\n',
            encoding="utf-8",
        )
        docker_wrapper.chmod(0o700)

        preflight = subprocess.run(
            [
                PREFLIGHT,
                "--config-env",
                config,
                "--image-env",
                images,
                "--secrets-root",
                output,
            ],
            cwd=ROOT,
            env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert preflight.returncode == 0, preflight.stdout + preflight.stderr
        assert "static only; no runtime started" in preflight.stdout
