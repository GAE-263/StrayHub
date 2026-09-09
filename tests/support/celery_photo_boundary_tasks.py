"""Explicit --include probe for the disposable boundary project, never production.

Only the LINE transport is stubbed. All three Worker photo-card paths use their
real signing implementation. Results expire in the dedicated synthetic Redis.
"""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from redis import Redis
from services.api.app.config.settings import get_settings, get_worker_settings
from services.api.app.infrastructure.celery_app import celery_app
from services.worker.app.celery_runtime import runtime
from services.worker.app.tasks import adoption


def broker() -> Redis:
    settings = get_worker_settings()
    assert os.environ.get("BOUNDARY_TEST_PROJECT") == "strayhub-celery-boundary-local"
    database = urlsplit(settings.database_url)
    assert database.hostname == "postgres" and database.path == "/strayhub_test"
    assert database.username == "boundary"
    assert urlsplit(settings.celery_broker_url).hostname == "redis"
    assert settings.app_env == "production" and not settings.celery_ai_enabled
    return Redis.from_url(settings.celery_broker_url, socket_timeout=5)


@celery_app.task(bind=True, name="test.photo_boundary", soft_time_limit=15, time_limit=20)
def photo_boundary(self) -> str:
    client = broker()
    org, animal = uuid4(), uuid4()
    candidate = SimpleNamespace(
        animal_id=animal,
        name="Synthetic",
        shelter_number="BOUNDARY-PHOTO",
        current_photo_key="synthetic/photo.jpg",
        score=80,
        reasons=("synthetic",),
    )
    try:
        cards = [
            adoption._curation_card(org, candidate, rank=1),
            adoption._followup_card(org, candidate, reason="synthetic", label="synthetic"),
        ]
        snapshot = SimpleNamespace(
            animal_id=animal,
            animal_name="Synthetic",
            shelter_number="BOUNDARY-PHOTO",
            current_photo_key="synthetic/photo.jpg",
        )
        notification = SimpleNamespace(
            line_user_id="synthetic-not-a-line-identity",
            outcome=SimpleNamespace(
                snapshot=snapshot, score=80, explanation="synthetic", asks_followup=False
            ),
        )
        with patch.object(adoption.LineMessagingApiAdapter, "push", new_callable=AsyncMock) as push:
            runtime.run(
                lambda factory: adoption._push_suitability_result(
                    organization_id=org, job_id=uuid4(), notification=notification
                )
            )
            push.assert_awaited_once()
            messages = push.await_args.kwargs["messages"]

        # A real photo URL must be present in the real Flex payload as well.
        def urls(value):
            if isinstance(value, dict):
                return [url for item in value.values() for url in urls(item)]
            if isinstance(value, list):
                return [url for item in value for url in urls(item)]
            return [value] if isinstance(value, str) and "?token=" in value else []

        photo_urls = [card.photo_url for card in cards] + urls(messages)
        assert len(photo_urls) >= 3
        tokens = [parse_qs(urlsplit(url).query)["token"][0] for url in photo_urls]
        assert get_settings.cache_info().misses == 0
        assert "services.api.app.persistence.database.engine" not in sys.modules
        client.setex(
            f"boundary:photo:{self.request.id}",
            300,
            json.dumps(
                {
                    "organization": str(org),
                    "animal": str(animal),
                    "tokens": tokens,
                    "api_settings_calls": 0,
                    "line_transport": "stubbed",
                }
            ),
        )
        return "photo_boundary_pass"
    finally:
        client.close()


def verify_result(task_id: str) -> None:
    import subprocess

    UUID(task_id)
    with broker() as client:
        payload = client.get(f"boundary:photo:{task_id}")
    assert payload, "bounded photo task has not completed"
    # Independent API verifier process; no settings-cache manipulation or mocked signer.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json, sys
from uuid import UUID
from services.api.app.application.media_access import (
    verify_adoption_photo_token, verify_adoption_photo_object_key)
data = json.load(sys.stdin)
for token in data['tokens']:
    claims = verify_adoption_photo_token(token, animal_id=UUID(data['animal']))
    assert str(claims.organization_id) == data['organization']
    verify_adoption_photo_object_key(claims, 'synthetic/photo.jpg')
print('PASS: broker photo task, three card paths, API token interoperability')
""",
        ],
        input=payload,
        capture_output=True,
        timeout=15,
        env={**os.environ, "APP_ENV": "test"},
    )
    assert result.returncode == 0, "API verifier rejected synthetic Worker token"
    print(result.stdout.decode().strip())


if __name__ == "__main__":
    verify_result(sys.argv[1])
