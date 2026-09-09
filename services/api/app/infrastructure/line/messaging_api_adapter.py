from __future__ import annotations

import hashlib

import httpx

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.line_messaging import LineImageContent
from services.api.app.config.settings import Settings, get_settings
from services.api.app.observability.logging import get_logger

logger = get_logger(__name__)


_shared_client: httpx.AsyncClient | None = None


def shared_line_client() -> httpx.AsyncClient:
    """整個 process 共用一個 LINE HTTP client（連線池可重用，且只需關閉一次）。"""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=10)
    return _shared_client


async def close_shared_line_client() -> None:
    """由 app lifespan／一次性腳本在結束時呼叫。"""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
    _shared_client = None


class LineMessagingApiAdapter:
    def __init__(
        self, *, client: httpx.AsyncClient | None = None, settings: Settings | None = None
    ) -> None:
        settings = settings or get_settings()
        self.access_token = settings.line_channel_access_token
        self.app_env = settings.app_env.strip().lower()
        self.recipient_allowlist_sha256 = settings.line_notification_recipient_hashes()
        self.api_base = "https://api.line.me"
        self.data_base = "https://api-data.line.me"
        # 這個 adapter 在 per-request 的 DI 與 webhook handler 裡都會被建立，
        # 每次自建 AsyncClient 會漏掉一整個連線池（沒有人會去 close 它）。
        self.client = client or shared_line_client()

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def ensure_recipient_allowed(self, to_user_id: str) -> None:
        """Fail closed for every acceptance interaction with a LINE identity."""
        if self.app_env != "acceptance":
            return
        recipient_digest = hashlib.sha256(to_user_id.encode("utf-8")).hexdigest()
        if recipient_digest not in self.recipient_allowlist_sha256:
            logger.warning("Blocked non-allowlisted LINE interaction in acceptance")
            raise DomainError(
                "line_recipient_not_allowlisted",
                "Acceptance 環境禁止與未授權的 LINE 測試帳號互動",
                403,
            )

    @staticmethod
    def _raise_for_status(response, operation: str = "line_api") -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # The caller only ever sees a generic 503, so the actual reason LINE
            # gave (invalid reply token, expired access token, rate limit) has to
            # be recorded here or it is lost. The response body carries no
            # credentials; the access token travels in the request header.
            status = getattr(response, "status_code", None)
            try:
                body = response.text[:500]
            except Exception:  # pragma: no cover - defensive
                body = "<unreadable>"
            logger.error(
                "LINE API rejected %s: status=%s body=%s",
                operation,
                status,
                body,
            )
            raise DomainError("line_api_unavailable", "LINE 服務暫時無法使用", 503) from exc

    async def _post(self, url: str, **kwargs):
        try:
            return await self.client.post(url, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("LINE API POST transport failure: %s", type(exc).__name__)
            raise DomainError("line_api_unavailable", "LINE 服務暫時無法使用", 503) from exc

    async def _get(self, url: str, **kwargs):
        try:
            return await self.client.get(url, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("LINE API GET transport failure: %s", type(exc).__name__)
            raise DomainError("line_api_unavailable", "LINE 服務暫時無法使用", 503) from exc

    async def _delete(self, url: str, **kwargs):
        try:
            return await self.client.delete(url, **kwargs)
        except httpx.HTTPError as exc:
            logger.error("LINE API DELETE transport failure: %s", type(exc).__name__)
            raise DomainError("line_api_unavailable", "LINE 服務暫時無法使用", 503) from exc

    async def reply(self, *, reply_token: str, messages: list[dict]) -> None:
        response = await self._post(
            f"{self.api_base}/v2/bot/message/reply",
            headers=self._headers,
            json={"replyToken": reply_token, "messages": messages},
        )
        self._raise_for_status(response, "reply")

    async def push(
        self, *, to_user_id: str, messages: list[dict], retry_key: str | None = None
    ) -> None:
        self.ensure_recipient_allowed(to_user_id)
        headers = {**self._headers, "Content-Type": "application/json"}
        if retry_key is not None:
            headers["X-Line-Retry-Key"] = retry_key
        response = await self._post(
            f"{self.api_base}/v2/bot/message/push",
            headers=headers,
            json={"to": to_user_id, "messages": messages},
        )
        if retry_key is not None and response.status_code == 409:
            return
        self._raise_for_status(response, "push")

    async def get_image_content(self, *, message_id: str) -> LineImageContent:
        response = await self._get(
            f"{self.data_base}/v2/bot/message/{message_id}/content",
            headers=self._headers,
        )
        self._raise_for_status(response, "get_image_content")
        return LineImageContent(
            message_id=message_id,
            content=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream"),
        )

    async def validate_rich_menu(self, *, rich_menu: dict) -> None:
        if not rich_menu.get("size") or not rich_menu.get("areas"):
            raise ValueError("rich menu must contain size and areas")

    async def list_rich_menus(self) -> list[dict]:
        """回傳這個 channel 上所有已建立的 rich menu。"""
        response = await self._get(f"{self.api_base}/v2/bot/richmenu/list", headers=self._headers)
        self._raise_for_status(response, "list_rich_menus")
        return response.json().get("richmenus", [])

    async def delete_rich_menu(self, *, rich_menu_id: str) -> None:
        response = await self._delete(
            f"{self.api_base}/v2/bot/richmenu/{rich_menu_id}", headers=self._headers
        )
        self._raise_for_status(response, "delete_rich_menu")

    async def create_rich_menu(self, *, rich_menu: dict) -> str:
        await self.validate_rich_menu(rich_menu=rich_menu)
        response = await self._post(
            f"{self.api_base}/v2/bot/richmenu",
            headers={**self._headers, "Content-Type": "application/json"},
            json=rich_menu,
        )
        self._raise_for_status(response, "create_rich_menu")
        return response.json()["richMenuId"]

    async def upload_rich_menu_image(
        self, *, rich_menu_id: str, content: bytes, content_type: str = "image/png"
    ) -> None:
        if not content:
            raise ValueError("rich menu image must not be empty")
        if content_type not in {"image/png", "image/jpeg"}:
            raise ValueError("rich menu image must be PNG or JPEG")
        # 圖片上傳走 data endpoint（api-data.line.me）；api.line.me 對此路徑回 404。
        response = await self._post(
            f"{self.data_base}/v2/bot/richmenu/{rich_menu_id}/content",
            headers={**self._headers, "Content-Type": content_type},
            content=content,
        )
        self._raise_for_status(response, "upload_rich_menu_image")

    async def link_rich_menu(self, *, rich_menu_id: str, user_id: str | None = None) -> None:
        path = (
            f"/v2/bot/user/{user_id}/richmenu/{rich_menu_id}"
            if user_id
            else f"/v2/bot/user/all/richmenu/{rich_menu_id}"
        )
        response = await self._post(f"{self.api_base}{path}", headers=self._headers)
        self._raise_for_status(response, "link_rich_menu")

    async def unlink_rich_menu(self, *, user_id: str | None = None) -> None:
        path = f"/v2/bot/user/{user_id}/richmenu" if user_id else "/v2/bot/user/all/richmenu"
        response = await self._delete(f"{self.api_base}{path}", headers=self._headers)
        self._raise_for_status(response, "unlink_rich_menu")
