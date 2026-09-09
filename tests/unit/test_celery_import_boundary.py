"""Fresh-process, non-local configuration tests; never read operator .env files."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_worker_photo_card_does_not_initialize_api_settings(tmp_path: Path) -> None:
    environment = worker_environment()
    environment.update(
        WEB_PUBLIC_BASE_URL="https://photos.boundary.example",
        ANIMAL_CONFIRMATION_SECRET="boundary-synthetic-signing-material-2026",
    )
    result = run_child(
        tmp_path,
        """
import sys
from types import SimpleNamespace
from uuid import uuid4
from services.worker.app.tasks.adoption import _curation_card
candidate = SimpleNamespace(animal_id=uuid4(), name='Synthetic', shelter_number='BOUNDARY',
                            current_photo_key='synthetic/photo.jpg', score=80,
                            reasons=('synthetic',))
card = _curation_card(uuid4(), candidate, rank=1)
assert card.photo_url and '?token=' in card.photo_url
assert 'services.api.app.persistence.database.engine' not in sys.modules
from services.api.app.config.settings import get_settings
assert get_settings.cache_info().misses == 0
""",
        environment,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("secret", ["", "local-animal-confirmation-secret"])
def test_worker_signing_configuration_fails_closed(tmp_path: Path, secret: str) -> None:
    environment = worker_environment()
    environment["ANIMAL_CONFIRMATION_SECRET"] = secret
    result = run_child(
        tmp_path,
        "from services.api.app.config.settings import get_worker_photo_signing_secret; "
        "get_worker_photo_signing_secret()",
        environment,
    )
    assert result.returncode != 0
    assert "ANIMAL_CONFIRMATION_SECRET" in result.stderr


def test_non_signing_processes_load_registry_without_signing_authority(tmp_path: Path) -> None:
    environment = worker_environment()
    environment.pop("ANIMAL_CONFIRMATION_SECRET", None)
    result = run_child(
        tmp_path,
        "from services.worker.app.import_smoke import main; raise SystemExit(main())",
        environment,
    )
    assert result.returncode == 0, result.stderr


def test_photo_card_without_signing_authority_fails_before_issuing_token(tmp_path: Path) -> None:
    environment = worker_environment()
    environment.update(ANIMAL_CONFIRMATION_SECRET="", WEB_PUBLIC_BASE_URL="https://photos.example")
    result = run_child(
        tmp_path,
        """
from types import SimpleNamespace
from uuid import uuid4
from services.worker.app.tasks.adoption import _curation_card
candidate = SimpleNamespace(animal_id=uuid4(), current_photo_key='synthetic/photo.jpg')
_curation_card(uuid4(), candidate, rank=1)
""",
        environment,
    )
    assert result.returncode != 0
    assert "ANIMAL_CONFIRMATION_SECRET is missing or unsafe" in result.stderr


def test_worker_tokens_match_api_verifier_and_reject_tampering(tmp_path: Path) -> None:
    environment = worker_environment()
    producer = run_child(
        tmp_path,
        """
import json
from uuid import uuid4
from services.api.app.config.settings import get_worker_settings, get_settings
from services.api.app.application import media_access as media
org, animal = uuid4(), uuid4()
key = get_worker_settings().animal_confirmation_secret
token = media.issue_adoption_photo_token(signing_secret=key, organization_id=org,
                                        animal_id=animal, object_key='synthetic.jpg')
assert get_settings.cache_info().misses == 0
print(json.dumps(dict(token=token, org=str(org), animal=str(animal))))
""",
        environment,
    )
    assert producer.returncode == 0, producer.stderr
    environment.update(APP_ENV="test", PHOTO_CASE=producer.stdout.strip())
    result = run_child(
        tmp_path,
        """
import base64, hashlib, hmac, json, os
from uuid import UUID, uuid4
from services.api.app.api.errors import DomainError
from services.api.app.application import media_access as media
data = json.loads(os.environ['PHOTO_CASE'])
animal = UUID(data['animal'])
claims = media.verify_adoption_photo_token(data['token'], animal_id=animal)
assert str(claims.organization_id) == data['org']
media.verify_adoption_photo_object_key(claims, 'synthetic.jpg')
def denied(token, animal_id):
    try:
        media.verify_adoption_photo_token(token, animal_id=animal_id)
    except DomainError:
        return
    raise AssertionError('unsafe token accepted')
denied(data['token'], uuid4())
encoded, sig = data['token'].split('.')
payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
payload['organization_id'] = str(uuid4())
changed = media._encode(json.dumps(payload).encode())
denied(changed + '.' + sig, animal)
wrong = hmac.new(b'wrong-synthetic-key', encoded.encode(), hashlib.sha256).digest()
denied(encoded + '.' + media._encode(wrong), animal)
payload['expires_at'] = 1
expired = media._encode(json.dumps(payload).encode())
signature = hmac.new(os.environ['ANIMAL_CONFIRMATION_SECRET'].encode(),
                     expired.encode(), hashlib.sha256).digest()
denied(expired + '.' + media._encode(signature), animal)
try:
    media.verify_adoption_photo_object_key(claims, 'other.jpg')
except DomainError:
    pass
else:
    raise AssertionError('wrong object accepted')
""",
        environment,
    )
    assert result.returncode == 0, result.stderr


def worker_environment() -> dict[str, str]:
    rendered = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            "infra/gce/.env.production.example",
            "-f",
            "infra/gce/docker-compose.production.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=True,
    )
    environment = json.loads(rendered.stdout)["services"]["celery-worker"]["environment"]
    return {
        **{key: str(value) for key, value in environment.items() if value is not None},
        "APP_ENV": "production",
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_child(tmp_path: Path, code: str, environment: dict[str, str]):
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_full_task_registry_does_not_initialize_api_engine(tmp_path: Path) -> None:
    environment = worker_environment()
    assert "AUTH_JWT_ACTIVE_PRIVATE_KEY" not in environment
    assert "LOGIN_ABUSE_HMAC_SECRET" not in environment
    result = run_child(
        tmp_path,
        """
import sys
def deny_network(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise RuntimeError('unexpected network access during task import')
sys.addaudithook(deny_network)
from services.api.app.infrastructure.celery_app import celery_app
celery_app.loader.import_default_modules()
assert 'services.api.app.persistence.database.engine' not in sys.modules
assert 'system.reconcile_ai_dispatch' in celery_app.tasks
assert 'adoption.analyze_suitability' in celery_app.tasks
assert not any(name.startswith('boundary.') for name in celery_app.tasks)
print('task_registry_import=PASS')
""",
        environment,
    )
    assert result.returncode == 0, result.stderr


def test_api_still_requires_api_credentials(tmp_path: Path) -> None:
    result = run_child(
        tmp_path,
        "from services.api.app.config.settings import get_settings; get_settings()",
        worker_environment(),
    )
    assert result.returncode != 0
    assert "UnsafeRuntimeConfigurationError" in result.stderr
    assert "AUTH_JWT_ACTIVE_PRIVATE_KEY" in result.stderr


def test_worker_still_requires_its_database(tmp_path: Path) -> None:
    environment = worker_environment()
    environment.pop("DATABASE_URL")
    result = run_child(
        tmp_path,
        "from services.api.app.config.settings import get_worker_settings; get_worker_settings()",
        environment,
    )
    assert result.returncode != 0
    assert "UnsafeRuntimeConfigurationError" in result.stderr
    assert "DATABASE_URL" in result.stderr


@pytest.mark.parametrize("valid", [True, False])
def test_import_smoke_exit_status_and_safe_diagnostics(tmp_path: Path, valid: bool) -> None:
    environment = worker_environment()
    if not valid:
        environment.pop("DATABASE_URL")
    result = run_child(
        tmp_path,
        "from services.worker.app.import_smoke import main; raise SystemExit(main())",
        environment,
    )
    assert result.returncode == (0 if valid else 1)
    assert ("PASS" in result.stdout) is valid
    if not valid:
        assert "UnsafeRuntimeConfigurationError" in result.stderr
    for key in ("CELERY_BROKER_URL", "LINE_CHANNEL_ACCESS_TOKEN", "MINIO_SECRET_KEY"):
        assert environment[key] not in result.stdout + result.stderr


# Prefork is a required deployment contract, not an optional platform test.
def test_runtime_replaces_inherited_factory_and_loop_after_fork(tmp_path: Path) -> None:
    result = run_child(
        tmp_path,
        """
import asyncio
import os
from services.worker.app.celery_runtime import CeleryAsyncRuntime
runtime = CeleryAsyncRuntime()
async def identity(factory):
    return factory, asyncio.get_running_loop()
parent_factory, parent_loop = runtime.run(identity)
pid = os.fork()
if pid == 0:
    factory, loop = runtime.run(identity)
    ok = factory is not parent_factory and loop is not parent_loop
    runtime.close()
    os._exit(0 if ok else 1)
_, status = os.waitpid(pid, 0)
assert os.waitstatus_to_exitcode(status) == 0
factory, loop = runtime.run(identity)
assert factory is parent_factory and loop is parent_loop
runtime.close()
""",
        worker_environment(),
    )
    assert result.returncode == 0, result.stderr
