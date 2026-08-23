from datetime import datetime, timezone

import httpx
import pytest
from services.api.app.api.errors import DomainError
from services.api.app.infrastructure.line.identity_verification_adapter import (
    LineIdentityVerifier,
    MockLineIdentityVerifier,
)


def response(payload: dict, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "https://api.line.me/oauth2/v2.1/verify")
    return httpx.Response(status_code, json=payload, request=request)


@pytest.mark.asyncio
async def test_line_verifier_posts_raw_token_and_validates_verified_claims() -> None:
    now = int(datetime.now(timezone.utc).timestamp())

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
        assert request.content == b"id_token=raw-id-token&client_id=channel-123"
        return response(
            {
                "iss": "https://access.line.me",
                "sub": "U123",
                "aud": "channel-123",
                "exp": now + 300,
            }
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    verifier = LineIdentityVerifier("channel-123", client=client)

    assert await verifier.verify("raw-id-token") == "U123"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim,value",
    [
        ("iss", "https://attacker.example"),
        ("aud", "wrong-channel"),
        ("exp", 1),
        ("sub", ""),
    ],
)
async def test_line_verifier_rejects_invalid_verified_claims(claim: str, value: object) -> None:
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "iss": "https://access.line.me",
        "sub": "U123",
        "aud": "channel-123",
        "exp": now + 300,
        claim: value,
    }
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response(payload)))
    verifier = LineIdentityVerifier("channel-123", client=client)

    with pytest.raises(DomainError) as error:
        await verifier.verify("raw-id-token")

    assert error.value.code == "invalid_line_id_token"
    assert error.value.status_code == 401
    await client.aclose()


@pytest.mark.asyncio
async def test_line_verifier_maps_provider_rejection_without_exposing_token() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: response(
                {"error": "invalid_request", "error_description": "Invalid IdToken."},
                400,
            )
        )
    )
    verifier = LineIdentityVerifier("channel-123", client=client)

    with pytest.raises(DomainError) as error:
        await verifier.verify("sensitive-raw-token")

    assert error.value.code == "invalid_line_id_token"
    assert "sensitive-raw-token" not in str(error.value)
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["", "not-a-local-token", "local-id-token:"])
async def test_mock_line_verifier_maps_invalid_tokens_to_401(token: str) -> None:
    with pytest.raises(DomainError) as error:
        await MockLineIdentityVerifier().verify(token)

    assert error.value.code == "invalid_line_id_token"
    assert error.value.status_code == 401
