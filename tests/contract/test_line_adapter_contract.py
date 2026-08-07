import pytest
from services.api.app.application.ports.line_messaging import LineImageContent
from services.api.app.infrastructure.line.mock_adapter import MockLineAdapter


@pytest.mark.asyncio
async def test_mock_line_adapter_supports_reply_image_and_rich_menu_without_network() -> None:
    adapter = MockLineAdapter()
    adapter.images["image-1"] = LineImageContent("image-1", b"clean", "image/jpeg")
    await adapter.reply(reply_token="reply-token", messages=[{"type": "text", "text": "ok"}])
    image = await adapter.get_image_content(message_id="image-1")
    rich_menu_id = await adapter.create_rich_menu(rich_menu={"actions": ["start"]})

    assert adapter.replies[0][0] == "reply-token"
    assert image.content == b"clean"
    assert rich_menu_id.startswith("mock-rich-menu-")
