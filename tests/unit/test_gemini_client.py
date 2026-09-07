from __future__ import annotations

import base64
import json

import httpx
import pytest
from services.api.app.infrastructure.ai.gemini_client import GeminiClient


def _gemini_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
    )


def _client(handler) -> GeminiClient:
    return GeminiClient(
        model_name="gemini-test",
        api_key="fake-key",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_analyze_growth_diary_entry_sends_text_only_when_no_image() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _gemini_response(
            {"mood": "positive", "adopter_reply": "太棒了！", "staff_summary": "狀況良好"}
        )

    client = _client(handler)

    result = await client.analyze_growth_diary_entry("純文字 prompt")

    assert result is not None
    assert result.mood == "positive"
    parts = captured["body"]["contents"][0]["parts"]
    assert parts == [{"text": "純文字 prompt"}]


@pytest.mark.asyncio
async def test_analyze_growth_diary_entry_includes_inline_image_data() -> None:
    captured: dict = {}
    image_bytes = b"\xff\xd8\xff\xe0fake-jpeg-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _gemini_response(
            {"mood": "neutral", "adopter_reply": "收到照片了", "staff_summary": "無異常"}
        )

    client = _client(handler)

    result = await client.analyze_growth_diary_entry(
        "看看這張照片", image=image_bytes, image_mime_type="image/jpeg"
    )

    assert result is not None
    parts = captured["body"]["contents"][0]["parts"]
    assert parts[0] == {"text": "看看這張照片"}
    assert parts[1]["inlineData"]["mimeType"] == "image/jpeg"
    assert base64.b64decode(parts[1]["inlineData"]["data"]) == image_bytes


@pytest.mark.asyncio
async def test_analyze_growth_diary_entry_defaults_mime_type_when_not_given() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _gemini_response(
            {"mood": "neutral", "adopter_reply": "收到了", "staff_summary": "無異常"}
        )

    client = _client(handler)

    await client.analyze_growth_diary_entry("prompt", image=b"bytes")

    parts = captured["body"]["contents"][0]["parts"]
    assert parts[1]["inlineData"]["mimeType"] == "image/jpeg"


@pytest.mark.asyncio
async def test_analyze_growth_diary_entry_invalid_mood_defaults_to_neutral() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _gemini_response(
            {"mood": "hallucinated", "adopter_reply": "回覆", "staff_summary": "摘要"}
        )

    client = _client(handler)

    result = await client.analyze_growth_diary_entry("prompt")

    assert result is not None
    assert result.mood == "neutral"


@pytest.mark.asyncio
async def test_analyze_growth_diary_entry_returns_none_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = _client(handler)

    result = await client.analyze_growth_diary_entry("prompt")

    assert result is None


@pytest.mark.asyncio
async def test_analyze_growth_diary_entry_returns_none_on_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "not json"}]}}]},
        )

    client = _client(handler)

    result = await client.analyze_growth_diary_entry("prompt")

    assert result is None


@pytest.mark.asyncio
async def test_extract_adoption_profile_pins_a_low_temperature() -> None:
    """A high default temperature was observed hallucinating a field the
    input text never mentioned (see line_webhook.py discussion) — this
    strict classification task pins a low temperature to make Gemini more
    conservative, unlike the warm-reply-generating calls elsewhere."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _gemini_response({"housing_type": "apartment_small"})

    client = _client(handler)

    await client.extract_adoption_profile(
        "prompt", valid_values={"housing_type": {"apartment_small", "house"}}
    )

    assert captured["body"]["generationConfig"]["temperature"] == 0.1


@pytest.mark.asyncio
async def test_extract_adoption_profile_drops_values_outside_the_allowed_set() -> None:
    """A value outside `valid_values[key]` — malformed, or a hallucinated
    code that doesn't even exist — must never reach the caller as if it
    were a real answer."""

    def handler(_: httpx.Request) -> httpx.Response:
        return _gemini_response(
            {
                "housing_type": "apartment_small",
                "dog_experience": "made_up_code",
                "other_pets": None,
            }
        )

    client = _client(handler)

    result = await client.extract_adoption_profile(
        "prompt",
        valid_values={
            "housing_type": {"apartment_small", "house"},
            "dog_experience": {"first_time", "experienced"},
            "other_pets": {"none", "has_cats"},
        },
    )

    assert result == {"housing_type": "apartment_small"}


@pytest.mark.asyncio
async def test_extract_adoption_profile_returns_empty_dict_on_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = _client(handler)

    result = await client.extract_adoption_profile("prompt", valid_values={})

    assert result == {}
