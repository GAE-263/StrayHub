from __future__ import annotations

from unittest.mock import Mock

import httpx
import pytest
from services.api.app.infrastructure.ai.gemini_client import GeminiClient, TransientAiError

PROJECT = "synthetic-project"
ACCOUNT = "runtime@synthetic-project.iam.gserviceaccount.com"


@pytest.mark.asyncio
async def test_runtime_identity_uses_vertex_and_never_api_key(monkeypatch):
    captured = []
    credentials = Mock(valid=False, token=None, service_account_email=ACCOUNT)

    def refresh(request):
        credentials.valid = True
        credentials.token = "synthetic-short-lived-token"

    credentials.refresh.side_effect = refresh
    monkeypatch.setattr("google.auth.compute_engine.Credentials", lambda **kwargs: credentials)

    def handle(request):
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": '{"score":80,"explanation":"ok"}'}]}}
                ]
            },
        )

    client = GeminiClient(
        model_name="gemini-test",
        use_runtime_identity=True,
        project_id=PROJECT,
        runtime_service_account=ACCOUNT,
        api_key="legacy-key-must-not-be-used",
        service_account_path="/must-not-read/service.json",
        location="global",
        transport=httpx.MockTransport(handle),
    )
    try:
        for _ in range(2):
            await client.analyze_suitability_strict("synthetic prompt")
        assert credentials.refresh.call_count == 1
        assert all(r.url.host == "aiplatform.googleapis.com" for r in captured)
        assert all("/projects/synthetic-project/locations/global/" in r.url.path for r in captured)
        assert all(
            r.headers["Authorization"] == "Bearer synthetic-short-lived-token" for r in captured
        )
        assert all("key" not in r.url.params for r in captured)
        credentials.valid = False
        await client.analyze_suitability_strict("synthetic prompt")
        assert credentials.refresh.call_count == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_metadata_failure_never_falls_back_or_leaks(monkeypatch):
    credentials = Mock(valid=False, service_account_email=ACCOUNT)
    credentials.refresh.side_effect = RuntimeError("secret-value-must-not-escape")
    monkeypatch.setattr("google.auth.compute_engine.Credentials", lambda **kwargs: credentials)
    requests = []
    client = GeminiClient(
        model_name="gemini-test",
        use_runtime_identity=True,
        project_id=PROJECT,
        runtime_service_account=ACCOUNT,
        api_key="old-api-key",
        transport=httpx.MockTransport(lambda request: requests.append(request)),
    )
    try:
        with pytest.raises(TransientAiError, match="^runtime_identity_unavailable$") as exc:
            await client.analyze_suitability_strict("synthetic prompt")
        assert exc.value.__suppress_context__
        assert requests == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_wrong_runtime_account_denied_before_model_call(monkeypatch):
    from services.api.app.infrastructure.ai.gemini_client import PermanentAiError

    credentials = Mock(
        valid=True,
        token="synthetic-token",
        service_account_email="other@synthetic-project.iam.gserviceaccount.com",
    )
    monkeypatch.setattr("google.auth.compute_engine.Credentials", lambda **kwargs: credentials)
    calls = []
    client = GeminiClient(
        model_name="gemini-test",
        use_runtime_identity=True,
        project_id=PROJECT,
        runtime_service_account=ACCOUNT,
        transport=httpx.MockTransport(lambda request: calls.append(request)),
    )
    try:
        with pytest.raises(PermanentAiError, match="runtime_identity_mismatch"):
            await client.analyze_suitability_strict("synthetic prompt")
        assert calls == []
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    "project,account",
    [("", ACCOUNT), ("../unsafe", ACCOUNT), (PROJECT, ""), (PROJECT, "https://example.test")],
)
def test_invalid_runtime_identity_configuration_denied(project, account):
    with pytest.raises(ValueError, match="invalid_runtime_identity_configuration"):
        GeminiClient(
            model_name="gemini-test",
            use_runtime_identity=True,
            project_id=project,
            runtime_service_account=account,
        )


def test_runtime_identity_does_not_load_ambient_adc_file(monkeypatch, tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text("not valid credentials")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(path))
    client = GeminiClient(
        model_name="gemini-test",
        use_runtime_identity=True,
        project_id=PROJECT,
        runtime_service_account=ACCOUNT,
    )
    assert client.api_key is None
    assert client._service_account_info is None


def test_all_production_ai_processes_receive_same_public_identity():
    from pathlib import Path

    import yaml  # type: ignore[import-untyped]

    services = yaml.safe_load(Path("infra/gce/docker-compose.production.yml").read_text())[
        "services"
    ]
    for key in [
        "GEMINI_USE_RUNTIME_IDENTITY",
        "GEMINI_VERTEX_PROJECT",
        "GEMINI_RUNTIME_SERVICE_ACCOUNT",
        "GEMINI_VERTEX_LOCATION",
    ]:
        values = [
            services[name]["environment"][key]
            for name in ["api", "worker", "celery-worker", "celery-beat"]
        ]
        assert len(set(values)) == 1
    assert "service.json" in Path(".dockerignore").read_text().splitlines()
