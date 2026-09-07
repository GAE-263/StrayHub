from __future__ import annotations

import base64
import json
from uuid import uuid4

import httpx
import pytest
from services.api.app.infrastructure.ai.gemini_client import (
    GeminiClient,
    MalformedAiResponse,
    PermanentAiError,
    TransientAiError,
)


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
async def test_strict_suitability_classifies_retryable_http_failure() -> None:
    client = _client(lambda _: httpx.Response(503, json={"error": "busy"}))

    with pytest.raises(TransientAiError):
        await client.analyze_suitability_strict("prompt")


@pytest.mark.asyncio
async def test_strict_suitability_rejects_malformed_output() -> None:
    client = _client(lambda _: _gemini_response({"score": "not-a-number"}))

    with pytest.raises(MalformedAiResponse):
        await client.analyze_suitability_strict("prompt")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_strict_suitability_retries_only_retryable_http_statuses(status: int) -> None:
    client = _client(lambda _: httpx.Response(status, json={"error": "unavailable"}))

    with pytest.raises(TransientAiError):
        await client.analyze_suitability_strict("prompt")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403])
async def test_strict_suitability_rejects_permanent_http_statuses(status: int) -> None:
    client = _client(lambda _: httpx.Response(status, json={"error": "invalid"}))

    with pytest.raises(PermanentAiError):
        await client.analyze_suitability_strict("prompt")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectTimeout("connect timeout"),
        httpx.ReadTimeout("read timeout"),
        httpx.ConnectError("connection reset"),
    ],
)
async def test_strict_suitability_retries_transport_failures(failure: Exception) -> None:
    def fail(_: httpx.Request) -> httpx.Response:
        raise failure

    client = _client(fail)

    with pytest.raises(TransientAiError):
        await client.analyze_suitability_strict("prompt")


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [-1, 101])
async def test_strict_suitability_rejects_out_of_range_score(score: int) -> None:
    client = _client(lambda _: _gemini_response({"score": score, "explanation": "理由"}))

    with pytest.raises(MalformedAiResponse):
        await client.analyze_suitability_strict("prompt")


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


@pytest.mark.asyncio
async def test_strict_profile_extraction_accepts_allowed_partial_values() -> None:
    client = _client(
        lambda _: _gemini_response({"housing_type": "apartment_small", "dog_experience": None})
    )

    result = await client.extract_adoption_profile_strict(
        "prompt",
        valid_values={
            "housing_type": {"house", "apartment_small"},
            "dog_experience": {"first_time", "experienced"},
        },
    )

    assert result == {"housing_type": "apartment_small"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ({"unknown": "value"}, "unknown key"),
        ({"housing_type": "castle"}, "invalid enum"),
        ({"housing_type": 7}, "wrong type"),
        ({"housing_type": "x" * 101}, "oversized value"),
        (["not", "an", "object"], "wrong schema"),
    ],
)
async def test_strict_profile_extraction_rejects_invalid_schema(payload, reason: str) -> None:
    client = _client(lambda _: _gemini_response(payload))

    with pytest.raises(MalformedAiResponse, match="profile"):
        await client.extract_adoption_profile_strict(
            "prompt", valid_values={"housing_type": {"house", "apartment_small"}}
        )


@pytest.mark.asyncio
async def test_strict_profile_extraction_accepts_empty_object_as_safe_noop() -> None:
    client = _client(lambda _: _gemini_response({}))

    assert (
        await client.extract_adoption_profile_strict(
            "prompt", valid_values={"housing_type": {"house"}}
        )
        == {}
    )


@pytest.mark.asyncio
async def test_strict_followups_accepts_allowed_ids_and_deduplicates_in_order() -> None:
    first, second = str(uuid4()), str(uuid4())
    client = _client(
        lambda _: _gemini_response(
            {
                "recommendations": [
                    {"animal_id": first, "reason": "安靜親人"},
                    {"animal_id": first, "reason": "重複推薦"},
                    {"animal_id": second, "reason": "活動量適中"},
                ]
            }
        )
    )

    result = await client.recommend_alternatives_strict("prompt", valid_animal_ids={first, second})

    assert [(item.animal_id, item.reason) for item in result] == [
        (first, "安靜親人"),
        (second, "活動量適中"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"recommendations": [{"animal_id": str(uuid4()), "reason": "未知"}]},
        {"recommendations": [{"animal_id": 123, "reason": "型別錯誤"}]},
        {"recommendations": [{"animal_id": "allowed", "reason": ""}]},
        {
            "recommendations": [
                {"animal_id": "allowed", "reason": "ok"},
                {"animal_id": "allowed", "reason": "ok"},
                {"animal_id": "allowed", "reason": "ok"},
                {"animal_id": "allowed", "reason": "ok"},
            ]
        },
        {"recommendations": [], "unknown": True},
        {"recommendations": "not-a-list"},
    ],
)
async def test_strict_followups_rejects_invalid_schema_or_allowlist(payload) -> None:
    client = _client(lambda _: _gemini_response(payload))

    with pytest.raises(MalformedAiResponse, match="followup"):
        await client.recommend_alternatives_strict("prompt", valid_animal_ids={"allowed"})


@pytest.mark.asyncio
async def test_strict_curation_preserves_order_and_deduplicates() -> None:
    first, second, third = str(uuid4()), str(uuid4()), str(uuid4())
    client = _client(
        lambda _: _gemini_response(
            {
                "recommendations": [
                    {"animal_id": third, "score": 91, "explanation": "最適合"},
                    {"animal_id": first, "score": 82, "explanation": "次適合"},
                    {"animal_id": third, "score": 70, "explanation": "重複"},
                ]
            }
        )
    )

    result = await client.rank_recommendations_strict(
        "prompt", valid_animal_ids={first, second, third}
    )

    assert [item.animal_id for item in result] == [third, first]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"recommendations": [{"animal_id": str(uuid4()), "score": 80, "explanation": "invented"}]},
        {"recommendations": [{"animal_id": "allowed", "score": 101, "explanation": "bad score"}]},
        {"recommendations": [{"animal_id": "allowed", "score": True, "explanation": "bad type"}]},
        {"recommendations": [{"animal_id": "allowed", "score": 80, "explanation": ""}]},
        {"recommendations": [], "unknown": True},
        {"recommendations": "not-a-list"},
    ],
)
async def test_strict_curation_rejects_invalid_schema_or_allowlist(payload) -> None:
    client = _client(lambda _: _gemini_response(payload))

    with pytest.raises(MalformedAiResponse, match="curation"):
        await client.rank_recommendations_strict("prompt", valid_animal_ids={"allowed"})


@pytest.mark.asyncio
async def test_strict_growth_diary_accepts_exact_schema() -> None:
    client = _client(
        lambda _: _gemini_response(
            {
                "mood": "concern",
                "adopter_reply": "建議聯繫獸醫確認。",
                "staff_summary": "食慾下降，需追蹤。",
            }
        )
    )

    result = await client.analyze_growth_diary_entry_strict("prompt")

    assert result.mood == "concern"
    assert result.adopter_reply == "建議聯繫獸醫確認。"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"mood": "unknown", "adopter_reply": "回覆", "staff_summary": "摘要"},
        {"mood": "neutral", "adopter_reply": 7, "staff_summary": "摘要"},
        {"mood": "neutral", "adopter_reply": "", "staff_summary": "摘要"},
        {"mood": "neutral", "adopter_reply": "回覆", "staff_summary": ""},
        {"mood": "neutral", "adopter_reply": "x" * 1001, "staff_summary": "摘要"},
        {"mood": "neutral", "adopter_reply": "回覆", "staff_summary": "x" * 1001},
        {
            "mood": "neutral",
            "adopter_reply": "回覆",
            "staff_summary": "摘要",
            "unknown": True,
        },
        {},
    ],
)
async def test_strict_growth_diary_rejects_invalid_schema(payload) -> None:
    client = _client(lambda _: _gemini_response(payload))

    with pytest.raises(MalformedAiResponse, match="growth_diary"):
        await client.analyze_growth_diary_entry_strict("prompt")


@pytest.mark.asyncio
async def test_strict_growth_diary_rejects_malformed_json() -> None:
    client = _client(lambda _: _gemini_response("not-json"))

    with pytest.raises(MalformedAiResponse, match="growth_diary"):
        await client.analyze_growth_diary_entry_strict("prompt")
