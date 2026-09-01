from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from services.api.app.api.errors import DomainError
from services.worker.app.handlers import ai_job_runner
from services.worker.app.handlers.ai_validation import validate_ai_output
from services.worker.app.infrastructure.ai_port import AIAnalysisEnvelope, AIRequestVersion
from services.worker.app.infrastructure.stool_analysis_adapter import (
    StoolAnalysisAdapter,
    StoolAnalysisError,
)

_ALLOWED = {
    "defecation.normal",
    "defecation.soft",
    "defecation.none",
    "defecation.abnormal",
}


def _version() -> AIRequestVersion:
    return AIRequestVersion(
        provider="stool-analysis",
        model_name="stool-model",
        model_version="external",
        prompt_version="external",
        output_schema_version="v1",
        prompt_template_id="stool-analysis",
    )


def _payload(**overrides) -> dict:
    payload = {
        "recognized": True,
        "score": 3,
        "consistency": "濕潤成形",
        "color": "深褐色",
        "has_abnormalities": False,
        "abnormality_details": "未見明顯異常",
        "assessment": "完整原始評估",
        "recommendation": "完整原始建議",
    }
    payload.update(overrides)
    return payload


def _adapter(handler) -> tuple[StoolAnalysisAdapter, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        StoolAnalysisAdapter(
            endpoint="https://stool.example.test",
            api_key="provider-secret",
            timeout_seconds=2,
            client=client,
        ),
        client,
    )


@pytest.mark.asyncio
async def test_sends_base64_with_api_key_and_preserves_raw_envelope() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers["x-api-key"]
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_payload())

    adapter, client = _adapter(handler)
    async with client:
        result = await adapter.analyze(
            note="not transmitted", image_bytes=[b"jpeg"], version=_version()
        )

    assert seen == {
        "path": "/v1/analyze/base64",
        "key": "provider-secret",
        "content_type": "application/json",
        "body": {"image_base64": base64.b64encode(b"jpeg").decode()},
    }
    assert isinstance(result, AIAnalysisEnvelope)
    assert result.raw["recommendation"] == "完整原始建議"
    assert validate_ai_output(result.formal, allowed_codes=_ALLOWED)["observations"][0][
        "code"
    ] == "defecation.normal"


@pytest.mark.parametrize(
    ("score", "abnormal", "expected"),
    [
        (3, False, "defecation.normal"),
        (4, False, "defecation.soft"),
        (5, False, "defecation.soft"),
        (1, False, "defecation.abnormal"),
        (7, False, "defecation.abnormal"),
        (3, True, "defecation.abnormal"),
    ],
)
@pytest.mark.asyncio
async def test_maps_only_to_canonical_defecation_codes(
    score: int, abnormal: bool, expected: str
) -> None:
    adapter, client = _adapter(
        lambda _request: httpx.Response(
            200, json=_payload(score=score, has_abnormalities=abnormal)
        )
    )
    async with client:
        result = await adapter.analyze(note=None, image_bytes=[b"jpeg"], version=_version())
    assert result.formal["observations"][0]["code"] == expected


@pytest.mark.asyncio
async def test_unrecognized_photo_has_no_formal_suggestion() -> None:
    adapter, client = _adapter(
        lambda _request: httpx.Response(200, json=_payload(recognized=False, score=None))
    )
    async with client:
        result = await adapter.analyze(note=None, image_bytes=[b"jpeg"], version=_version())
    assert result.raw["recognized"] is False
    assert result.formal == {"observations": []}


@pytest.mark.asyncio
async def test_no_image_returns_safe_skip_without_http() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("provider must not be called")

    adapter, client = _adapter(handler)
    async with client:
        result = await adapter.analyze(note=None, image_bytes=[], version=_version())
    assert result == AIAnalysisEnvelope(
        raw={"skipped": "no_stool_media"}, formal={"observations": []}
    )


@pytest.mark.asyncio
async def test_timeout_is_retryable_and_redacts_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timed out with provider-secret", request=request)

    adapter, client = _adapter(handler)
    async with client:
        with pytest.raises(StoolAnalysisError) as caught:
            await adapter.analyze(note=None, image_bytes=[b"jpeg"], version=_version())
    assert caught.value.code == "timeout"
    assert "provider-secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_4xx_is_terminal_but_5xx_and_rate_limit_are_retryable() -> None:
    terminal, terminal_client = _adapter(lambda _request: httpx.Response(401, json={}))
    async with terminal_client:
        with pytest.raises(DomainError):
            await terminal.analyze(note=None, image_bytes=[b"x"], version=_version())

    for status in (429, 503):
        retryable, retry_client = _adapter(
            lambda _request, status=status: httpx.Response(status, json={})
        )
        async with retry_client:
            with pytest.raises(StoolAnalysisError):
                await retryable.analyze(note=None, image_bytes=[b"x"], version=_version())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [httpx.Response(200, text="not-json"), httpx.Response(200, json={"recognized": "yes"})],
)
async def test_invalid_provider_response_is_retryable(response: httpx.Response) -> None:
    adapter, client = _adapter(lambda _request: response)
    async with client:
        with pytest.raises(StoolAnalysisError, match="invalid_json"):
            await adapter.analyze(note=None, image_bytes=[b"x"], version=_version())


def test_incomplete_configuration_is_rejected_without_exposing_key() -> None:
    with pytest.raises(ValueError, match="configuration") as caught:
        StoolAnalysisAdapter(endpoint="", api_key="provider-secret")
    assert "provider-secret" not in str(caught.value)


def test_worker_uses_safe_mock_when_stool_provider_is_not_fully_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_job_runner,
        "get_worker_settings",
        lambda: SimpleNamespace(
            stool_api_url="https://stool.example.test",
            stool_api_key=None,
            stool_timeout_seconds=30,
            ai_provider="mock",
            ai_endpoint=None,
            ai_api_key=None,
            ai_timeout_seconds=30,
        ),
    )

    assert ai_job_runner.build_ai_client().__class__.__name__ == "MockAIAdapter"


def test_worker_selects_stool_provider_only_with_url_and_secret(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_job_runner,
        "get_worker_settings",
        lambda: SimpleNamespace(
            stool_api_url="https://stool.example.test",
            stool_api_key=SecretStr("provider-secret"),
            stool_timeout_seconds=12,
            ai_provider="mock",
            ai_endpoint=None,
            ai_api_key=None,
            ai_timeout_seconds=30,
        ),
    )

    client = ai_job_runner.build_ai_client()
    assert isinstance(client, StoolAnalysisAdapter)
    assert client.timeout_seconds == 12
