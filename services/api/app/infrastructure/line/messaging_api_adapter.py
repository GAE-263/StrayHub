from __future__ import annotations

import httpx

from services.api.app.application.ports.line_messaging import LineImageContent
from services.api.app.config.settings import get_settings


class LineMessagingApiAdapter:
    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self.access_token = settings.line_channel_access_token
        self.api_base = "https://api.line.me"
        self.data_base = "https://api-data.line.me"
        self.client = client or httpx.AsyncClient(timeout=10)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def reply(self, *, reply_token: str, messages: list[dict]) -> None:
        response = await self.client.post(
            f"{self.api_base}/v2/bot/message/reply",
            headers=self._headers,
            json={"replyToken": reply_token, "messages": messages},
        )
        response.raise_for_status()

    async def get_image_content(self, *, message_id: str) -> LineImageContent:
        response = await self.client.get(
            f"{self.data_base}/v2/bot/message/{message_id}/content",
            headers=self._headers,
        )
        response.raise_for_status()
        return LineImageContent(
            message_id=message_id,
            content=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream"),
        )

    async def validate_rich_menu(self, *, rich_menu: dict) -> None:
        if not rich_menu.get("size") or not rich_menu.get("areas"):
            raise ValueError("rich menu must contain size and areas")

    async def create_rich_menu(self, *, rich_menu: dict) -> str:
        await self.validate_rich_menu(rich_menu=rich_menu)
        response = await self.client.post(
            f"{self.api_base}/v2/bot/richmenu",
            headers={**self._headers, "Content-Type": "application/json"},
            json=rich_menu,
        )
        response.raise_for_status()
        return response.json()["richMenuId"]

    async def upload_rich_menu_image(self, *, rich_menu_id: str, content: bytes) -> None:
        response = await self.client.post(
            f"{self.api_base}/v2/bot/richmenu/{rich_menu_id}/content",
            headers={**self._headers, "Content-Type": "image/png"},
            content=content,
        )
        response.raise_for_status()

    async def link_rich_menu(self, *, rich_menu_id: str, user_id: str | None = None) -> None:
        path = (
            f"/v2/bot/user/{user_id}/richmenu/{rich_menu_id}"
            if user_id
            else f"/v2/bot/user/all/richmenu/{rich_menu_id}"
        )
        response = await self.client.post(f"{self.api_base}{path}", headers=self._headers)
        response.raise_for_status()
