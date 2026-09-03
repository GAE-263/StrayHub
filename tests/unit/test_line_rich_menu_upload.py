import httpx
import pytest
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", ["image/png", "image/jpeg"])
async def test_rich_menu_upload_uses_data_host_and_caller_content_type(
    content_type: str,
) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await LineMessagingApiAdapter(client=client).upload_rich_menu_image(
            rich_menu_id="rich-menu-1",
            content=b"image",
            content_type=content_type,
        )

    assert requests[0].url.host == "api-data.line.me"
    assert requests[0].headers["content-type"] == content_type


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "content_type"),
    [(b"", "image/png"), (b"image", "image/gif")],
)
async def test_rich_menu_upload_rejects_empty_or_unsupported_image(
    content: bytes, content_type: str
) -> None:
    async with httpx.AsyncClient() as client:
        adapter = LineMessagingApiAdapter(client=client)
        with pytest.raises(ValueError, match="image"):
            await adapter.upload_rich_menu_image(
                rich_menu_id="rich-menu-1",
                content=content,
                content_type=content_type,
            )
