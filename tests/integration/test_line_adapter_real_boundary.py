import pytest
from services.api.app.infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter


class Response:
    def __init__(self, payload=None, content=b"image", headers=None):
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {"content-type": "image/jpeg"}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class Client:
    def __init__(self):
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/richmenu"):
            return Response({"richMenuId": "rich-1"})
        return Response()

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return Response()

    async def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url, kwargs))
        return Response()


@pytest.mark.asyncio
async def test_real_adapter_uses_reply_token_and_message_content_endpoints() -> None:
    client = Client()
    adapter = LineMessagingApiAdapter(client=client)
    await adapter.reply(reply_token="reply-1", messages=[{"type": "text", "text": "ok"}])
    content = await adapter.get_image_content(message_id="message-1")
    assert content.message_id == "message-1"
    assert client.calls[0][1].endswith("/v2/bot/message/reply")
    assert client.calls[0][2]["json"]["replyToken"] == "reply-1"
    assert client.calls[1][1].endswith("/v2/bot/message/message-1/content")


@pytest.mark.asyncio
async def test_real_adapter_rich_menu_flow_is_repeatable_and_validated() -> None:
    client = Client()
    adapter = LineMessagingApiAdapter(client=client)
    rich_menu_id = await adapter.create_rich_menu(
        rich_menu={
            "size": {"width": 2500, "height": 1686},
            "areas": [{"bounds": {"x": 0, "y": 0, "width": 2500, "height": 1686}}],
        }
    )
    await adapter.upload_rich_menu_image(rich_menu_id=rich_menu_id, content=b"png")
    await adapter.link_rich_menu(rich_menu_id=rich_menu_id)
    await adapter.unlink_rich_menu(user_id="U-user")
    assert rich_menu_id == "rich-1"
    assert len(client.calls) == 4
    # 建立與綁定走 api.line.me，圖片上傳必須走 api-data.line.me（打錯 host 會 404）。
    assert client.calls[0][1] == "https://api.line.me/v2/bot/richmenu"
    assert client.calls[1][1] == f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content"
    assert client.calls[2][1] == f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}"
    assert client.calls[3][0:2] == (
        "DELETE",
        "https://api.line.me/v2/bot/user/U-user/richmenu",
    )
