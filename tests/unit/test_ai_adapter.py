import json

import httpx
import pytest
from services.worker.app.infrastructure.ai_adapter import AIAdapter, AIAdapterError
from services.worker.app.infrastructure.ai_port import AIRequestVersion


def _version() -> AIRequestVersion:
    return AIRequestVersion(
        provider="formal",
        model_name="descriptive-model",
        model_version="snapshot-2026-08-08",
        prompt_template_id="care-observation",
        prompt_version="prompt-3",
        output_schema_version="v1",
    )


@pytest.mark.asyncio
async def test_formal_adapter_sends_versions_and_cleaned_images() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer secret-value"
        return httpx.Response(200, json={"output": {"observations": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AIAdapter(
            endpoint="https://ai.example.test/analyze",
            api_key="secret-value",
            timeout_seconds=2,
            client=client,
        ).analyze(note="心得", image_bytes=[b"cleaned"], version=_version())

    assert result == {"observations": []}
    assert seen["model_version"] == "snapshot-2026-08-08"
    assert seen["prompt_template_id"] == "care-observation"
    assert seen["prompt_version"] == "prompt-3"
    assert seen["output_schema_version"] == "v1"
    assert seen["images"]


@pytest.mark.asyncio
async def test_formal_adapter_converts_timeout_without_secret_or_response_body() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timed out", request=_request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AIAdapterError) as caught:
            await AIAdapter(
                endpoint="https://ai.example.test/analyze",
                api_key="secret-value",
                client=client,
            ).analyze(note="private note", image_bytes=[], version=_version())

    assert str(caught.value) == "timeout"
    assert "secret-value" not in str(caught.value)
    assert "private note" not in str(caught.value)
