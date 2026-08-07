import httpx
import pytest
from services.api.app.infrastructure.line.identity_verification_adapter import LineIdentityVerifier


@pytest.mark.asyncio
async def test_line_identity_adapter_returns_verified_sub_without_sdk_dependency() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["client_id"] == "channel"
        return httpx.Response(200, json={"sub": "line-user"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    user_id = await LineIdentityVerifier("channel", client=client).verify("id-token")
    await client.aclose()

    assert user_id == "line-user"
