from __future__ import annotations

import logging

import httpx

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.line_messaging import LineImageContent
from services.api.app.config.settings import get_settings

logger = logging.getLogger(__name__)


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

    @staticmethod
    def _raise_for_status(response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # The caller only ever sees a generic 503, so record what LINE
            # actually rejected; without this a malformed message body is
            # indistinguishable from LINE being down.
            body = ""
            try:
                body = response.text[:2000]
            except Exception:  # pragma: no cover - defensive
                pass
            logger.error(
                "LINE API rejected %s %s -> %s %s",
                getattr(response.request, "method", "?"),
                getattr(response.request, "url", "?"),
                getattr(response, "status_code", "?"),
                body,
            )
            raise DomainError("line_api_unavailable", "LINE 服務暫時無法使用", 503) from exc

    async def _post(self, url: str, **kwargs):
        try:
            return await self.client.post(url, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("LINE API POST %s failed: %r", url, exc)
            raise DomainError("line_api_unavailable", "LINE 服務暫時無法使用", 503) from exc

    async def _get(self, url: str, **kwargs):
        try:
            return await self.client.get(url, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("LINE API GET %s failed: %r", url, exc)
            raise DomainError("line_api_unavailable", "LINE 服務暫時無法使用", 503) from exc

    async def reply(self, *, reply_token: str, messages: list[dict]) -> None:
        response = await self._post(
            f"{self.api_base}/v2/bot/message/reply",
            headers=self._headers,
            json={"replyToken": reply_token, "messages": messages},
        )
        self._raise_for_status(response)

    async def push(self, *, to_user_id: str, messages: list[dict]) -> None:
        response = await self._post(
            f"{self.api_base}/v2/bot/message/push",
            headers={**self._headers, "Content-Type": "application/json"},
            json={"to": to_user_id, "messages": messages},
        )
        self._raise_for_status(response)

    async def get_image_content(self, *, message_id: str) -> LineImageContent:
        response = await self._get(
            f"{self.data_base}/v2/bot/message/{message_id}/content",
            headers=self._headers,
        )
        self._raise_for_status(response)
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
        response = await self._post(
            f"{self.api_base}/v2/bot/richmenu",
            headers={**self._headers, "Content-Type": "application/json"},
            json=rich_menu,
        )
        self._raise_for_status(response)
        return response.json()["richMenuId"]

    async def upload_rich_menu_image(self, *, rich_menu_id: str, content: bytes) -> None:
        # Binary uploads go to the data host, not the API host.
        response = await self._post(
            f"{self.data_base}/v2/bot/richmenu/{rich_menu_id}/content",
            headers={**self._headers, "Content-Type": "image/png"},
            content=content,
        )
        self._raise_for_status(response)

    async def link_rich_menu(self, *, rich_menu_id: str, user_id: str | None = None) -> None:
        path = (
            f"/v2/bot/user/{user_id}/richmenu/{rich_menu_id}"
            if user_id
            else f"/v2/bot/user/all/richmenu/{rich_menu_id}"
        )
        response = await self._post(f"{self.api_base}{path}", headers=self._headers)
        self._raise_for_status(response)
