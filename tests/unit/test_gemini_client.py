from __future__ import annotations

import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from services.api.app.infrastructure.ai.gemini_client import (
    GeminiAnimalRecommendation,
    GeminiClient,
)


def _client(handler) -> GeminiClient:
    return GeminiClient(
        api_key="fake-key", model_name="fake-model", transport=httpx.MockTransport(handler)
    )


def _gemini_response(text: str) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


def _fake_service_account_file(tmp_path) -> str:
    """A throwaway RSA key + service-account-shaped JSON, written to a temp
    file — the client reads this from disk exactly like a real downloaded
    key, but nothing here is a real Google credential."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    info = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": pem,
        "client_email": "test-bot@test-project.iam.gserviceaccount.com",
        "client_id": "123456789",
    }
    path = tmp_path / "fake-service-account.json"
    path.write_text(json.dumps(info), encoding="utf-8")
    return str(path)


@pytest.mark.asyncio
async def test_analyze_suitability_parses_score_and_explanation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "fake-key"
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return _gemini_response(json.dumps({"score": 82, "explanation": "很適合喔"}))

    result = await _client(handler).analyze_suitability("prompt")

    assert result is not None
    assert result.score == 82
    assert result.explanation == "很適合喔"


@pytest.mark.asyncio
async def test_analyze_suitability_clamps_out_of_range_score() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _gemini_response(json.dumps({"score": 150, "explanation": "太適合了"}))

    result = await _client(handler).analyze_suitability("prompt")

    assert result is not None
    assert result.score == 100


@pytest.mark.asyncio
async def test_analyze_suitability_returns_none_on_malformed_json() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _gemini_response("this is not json")

    result = await _client(handler).analyze_suitability("prompt")

    assert result is None


@pytest.mark.asyncio
async def test_analyze_suitability_returns_none_on_http_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    result = await _client(handler).analyze_suitability("prompt")

    assert result is None


@pytest.mark.asyncio
async def test_analyze_suitability_returns_none_on_missing_field() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _gemini_response(json.dumps({"score": 82}))

    result = await _client(handler).analyze_suitability("prompt")

    assert result is None


@pytest.mark.asyncio
async def test_recommend_alternatives_returns_valid_recommendations_only() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _gemini_response(
            json.dumps(
                {
                    "recommendations": [
                        {"animal_id": "animal-1", "reason": "個性安靜"},
                        {"animal_id": "hallucinated-id", "reason": "不存在的動物"},
                        {"animal_id": "animal-2", "reason": "母的小型犬"},
                    ]
                }
            )
        )

    result = await _client(handler).recommend_alternatives(
        "prompt", valid_animal_ids={"animal-1", "animal-2"}
    )

    assert result == [
        GeminiAnimalRecommendation(animal_id="animal-1", reason="個性安靜"),
        GeminiAnimalRecommendation(animal_id="animal-2", reason="母的小型犬"),
    ]


@pytest.mark.asyncio
async def test_recommend_alternatives_caps_at_three() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _gemini_response(
            json.dumps(
                {
                    "recommendations": [
                        {"animal_id": f"animal-{i}", "reason": f"理由{i}"} for i in range(5)
                    ]
                }
            )
        )

    result = await _client(handler).recommend_alternatives(
        "prompt", valid_animal_ids={f"animal-{i}" for i in range(5)}
    )

    assert result is not None
    assert len(result) == 3


@pytest.mark.asyncio
async def test_recommend_alternatives_returns_none_on_http_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    result = await _client(handler).recommend_alternatives("prompt", valid_animal_ids=set())

    assert result is None


def test_constructor_requires_api_key_or_service_account() -> None:
    with pytest.raises(ValueError):
        GeminiClient(model_name="fake-model")


@pytest.mark.asyncio
async def test_vertex_mode_global_location_uses_unprefixed_host(tmp_path) -> None:
    """The "global" Vertex AI location (needed for some models — e.g.
    gemini-3.5-flash-lite, which 404s from region-pinned hosts) does NOT
    take a location-prefixed hostname the way "us-central1" etc. do."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "fake-token", "expires_in": 3600})
        assert request.url.host == "aiplatform.googleapis.com"
        assert "/projects/test-project/locations/global/" in str(request.url)
        return _gemini_response(json.dumps({"score": 70, "explanation": "ok"}))

    client = GeminiClient(
        model_name="gemini-3.5-flash-lite",
        service_account_path=_fake_service_account_file(tmp_path),
        location="global",
        transport=httpx.MockTransport(handler),
    )

    result = await client.analyze_suitability("prompt")

    assert result is not None
    assert result.score == 70


@pytest.mark.asyncio
async def test_vertex_mode_exchanges_token_then_calls_generate_content(tmp_path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            assert request.url.path == "/token"
            body = request.content.decode()
            assert "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer" in body
            return httpx.Response(
                200, json={"access_token": "fake-access-token", "expires_in": 3600}
            )
        assert request.headers["authorization"] == "Bearer fake-access-token"
        assert request.url.host == "us-central1-aiplatform.googleapis.com"
        assert "/projects/test-project/locations/us-central1/" in str(request.url)
        return _gemini_response(json.dumps({"score": 91, "explanation": "很棒的一組"}))

    client = GeminiClient(
        model_name="gemini-pro",
        service_account_path=_fake_service_account_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    result = await client.analyze_suitability("prompt")

    assert result is not None
    assert result.score == 91
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_vertex_mode_reuses_cached_token_across_calls(tmp_path) -> None:
    token_exchanges = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            token_exchanges.append(request)
            return httpx.Response(200, json={"access_token": "cached-token", "expires_in": 3600})
        return _gemini_response(json.dumps({"score": 50, "explanation": "普通"}))

    client = GeminiClient(
        model_name="gemini-pro",
        service_account_path=_fake_service_account_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    await client.analyze_suitability("prompt 1")
    await client.analyze_suitability("prompt 2")

    assert len(token_exchanges) == 1


@pytest.mark.asyncio
async def test_vertex_mode_returns_none_on_token_exchange_failure(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(400, json={"error": "invalid_grant"})
        raise AssertionError("generateContent should not be reached without a token")

    client = GeminiClient(
        model_name="gemini-pro",
        service_account_path=_fake_service_account_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    result = await client.analyze_suitability("prompt")

    assert result is None


@pytest.mark.asyncio
async def test_analyze_growth_diary_entry_parses_mood_and_both_replies() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _gemini_response(
            json.dumps(
                {
                    "mood": "positive",
                    "adopter_reply": "看起來牠適應得很好！",
                    "staff_summary": "適應良好，無需介入。",
                }
            )
        )

    result = await _client(handler).analyze_growth_diary_entry("prompt")

    assert result is not None
    assert result.mood == "positive"
    assert result.adopter_reply == "看起來牠適應得很好！"
    assert result.staff_summary == "適應良好，無需介入。"


@pytest.mark.asyncio
async def test_analyze_growth_diary_entry_normalizes_unexpected_mood_to_neutral() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _gemini_response(
            json.dumps(
                {
                    "mood": "SOMETHING_ELSE",
                    "adopter_reply": "謝謝分享！",
                    "staff_summary": "例行回報。",
                }
            )
        )

    result = await _client(handler).analyze_growth_diary_entry("prompt")

    assert result is not None
    assert result.mood == "neutral"


@pytest.mark.asyncio
async def test_analyze_growth_diary_entry_returns_none_on_missing_field() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _gemini_response(json.dumps({"mood": "positive", "adopter_reply": "謝謝分享！"}))

    result = await _client(handler).analyze_growth_diary_entry("prompt")

    assert result is None


@pytest.mark.asyncio
async def test_analyze_growth_diary_entry_returns_none_on_http_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    result = await _client(handler).analyze_growth_diary_entry("prompt")

    assert result is None
