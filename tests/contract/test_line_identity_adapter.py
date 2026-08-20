from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest
from services.api.app.infrastructure.line.identity_verification_adapter import LineIdentityVerifier


@pytest.mark.asyncio
async def test_line_identity_adapter_returns_verified_sub_without_sdk_dependency() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert parse_qs(request.content.decode()) == {
            "client_id": ["channel"],
            "id_token": ["id-token"],
        }
        return httpx.Response(
            200,
            json={
                "iss": "https://access.line.me",
                "aud": "channel",
                "exp": int(datetime.now(timezone.utc).timestamp()) + 300,
                "sub": "line-user",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    user_id = await LineIdentityVerifier("channel", client=client).verify("id-token")
    await client.aclose()

    assert user_id == "line-user"
