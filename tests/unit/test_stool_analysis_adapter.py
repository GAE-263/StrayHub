"""便便判讀轉接器：完整判讀進 raw、正式建議只留非診斷描述。

治理邊界是這裡的重點：validate_ai_output 禁止 score／評估／建議進正式
Observation，但對方 API 的價值正是這些欄位。信封（AIAnalysisEnvelope）把
兩者分開——raw 給授權覆核、formal 走驗證——這些測試釘住這條界線，避免
未來有人「順手」把分數塞進正式建議。
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from services.api.app.api.errors import DomainError
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
        provider="stool",
        model_name="gemini-3.5-flash-lite",
        model_version="external",
        prompt_template_id="stool-analysis",
        prompt_version="external",
        output_schema_version="v1",
    )


def _payload(**overrides) -> dict:
    payload = {
        "recognized": True,
        "score": 3,
        "score_label": "理想",
        "consistency": "濕潤成形的原木狀，表面平滑。",
        "color": "深褐色",
        "has_abnormalities": False,
        "abnormality_details": "未見明顯異常",
        "assessment": "外觀與成形度落在理想範圍。",
        "recommendation": "維持現有飲食與飲水量。",
        "model": "gemini-3.5-flash-lite",
    }
    payload.update(overrides)
    return payload


def _adapter(handler, timeout: float = 2) -> tuple[StoolAnalysisAdapter, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = StoolAnalysisAdapter(
        endpoint="https://stool.example.test",
        api_key="stool-secret",
        timeout_seconds=timeout,
        client=client,
    )
    return adapter, client


@pytest.mark.asyncio
async def test_sends_base64_json_with_api_key_header() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["x_api_key"] = request.headers.get("x-api-key")
        seen["content_type"] = request.headers.get("content-type")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_payload())

    adapter, client = _adapter(handler)
    async with client:
        result = await adapter.analyze(note=None, image_bytes=[b"jpeg"], version=_version())

    assert seen["path"] == "/v1/analyze/base64"
    assert seen["x_api_key"] == "stool-secret"
    # 對方文件特別警告：不是 application/json 會被當 text 拒收。
    assert seen["content_type"] == "application/json"
    assert seen["body"] == {"image_base64": base64.b64encode(b"jpeg").decode()}
    assert isinstance(result, AIAnalysisEnvelope)


@pytest.mark.asyncio
async def test_full_payload_stays_raw_and_formal_passes_governance() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_payload())

    adapter, client = _adapter(handler)
    async with client:
        result = await adapter.analyze(note=None, image_bytes=[b"jpeg"], version=_version())

    assert result.raw["score"] == 3
    assert result.raw["recommendation"]
    validated = validate_ai_output(result.formal, allowed_codes=_ALLOWED)
    assert validated["observations"][0]["code"] == "defecation.normal"


@pytest.mark.parametrize(
    ("score", "has_abnormalities", "expected"),
    [
        (3, False, "defecation.normal"),
        (4, False, "defecation.soft"),
        (5, False, "defecation.soft"),
        (1, False, "defecation.abnormal"),
        (7, False, "defecation.abnormal"),
        # 血絲/黏液蓋過成形度：理想分數照樣標「有異狀」。
        (3, True, "defecation.abnormal"),
    ],
)
@pytest.mark.asyncio
async def test_score_maps_to_the_volunteer_facing_defecation_codes(
    score: int, has_abnormalities: bool, expected: str
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_payload(score=score, has_abnormalities=has_abnormalities)
        )

    adapter, client = _adapter(handler)
    async with client:
        result = await adapter.analyze(note=None, image_bytes=[b"jpeg"], version=_version())

    assert result.formal["observations"][0]["code"] == expected


@pytest.mark.asyncio
async def test_unrecognized_photo_yields_no_formal_suggestion() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_payload(recognized=False, score=None, score_label="無法判斷"),
        )

    adapter, client = _adapter(handler)
    async with client:
        result = await adapter.analyze(note=None, image_bytes=[b"jpeg"], version=_version())

    assert result.formal == {"observations": []}
    assert result.raw["recognized"] is False


@pytest.mark.asyncio
async def test_report_without_stool_photo_never_spends_quota() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no HTTP call expected")

    adapter, client = _adapter(handler)
    async with client:
        result = await adapter.analyze(note=None, image_bytes=[], version=_version())

    assert result.formal == {"observations": []}
    assert result.raw == {"skipped": "no_stool_media"}


@pytest.mark.asyncio
async def test_deterministic_rejections_are_terminal_not_retried() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"code": "invalid_image", "message": "圖片無法解碼"}}
        )

    adapter, client = _adapter(handler)
    async with client:
        with pytest.raises(DomainError) as caught:
            await adapter.analyze(note=None, image_bytes=[b"x"], version=_version())

    assert caught.value.code == "invalid_image"


@pytest.mark.asyncio
async def test_quota_and_upstream_failures_stay_retryable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"code": "rate_limited", "message": "額度用完"}})

    adapter, client = _adapter(handler)
    async with client:
        with pytest.raises(StoolAnalysisError) as caught:
            await adapter.analyze(note=None, image_bytes=[b"x"], version=_version())

    assert caught.value.code == "rate_limited"


@pytest.mark.asyncio
async def test_timeout_error_carries_no_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timed out", request=request)

    adapter, client = _adapter(handler)
    async with client:
        with pytest.raises(StoolAnalysisError) as caught:
            await adapter.analyze(note=None, image_bytes=[b"x"], version=_version())

    assert str(caught.value) == "timeout"
    assert "stool-secret" not in str(caught.value)
