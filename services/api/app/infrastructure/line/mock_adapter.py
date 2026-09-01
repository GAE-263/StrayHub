from __future__ import annotations

from services.api.app.api.errors import DomainError
from services.api.app.application.ports.line_messaging import LineImageContent


class MockLineAdapter:
    def __init__(self, *, push_failure_mode: str | None = None) -> None:
        self.replies: list[tuple[str, list[dict]]] = []
        self.pushes: list[tuple[str, list[dict]]] = []
        self.push_failure_mode = push_failure_mode
        self.images: dict[str, LineImageContent] = {}
        self.rich_menus: list[dict] = []
        self.unlinked_users: list[str | None] = []

    async def push(self, *, to_user_id: str, messages: list[dict]) -> None:
        if self.push_failure_mode == "transient":
            raise DomainError("line_push_transient", "LINE 暫時無法投遞", 503)
        if self.push_failure_mode == "terminal":
            raise DomainError("line_push_terminal", "LINE 收件者無法接收", 422)
        self.pushes.append((to_user_id, messages))

    async def reply(self, *, reply_token: str, messages: list[dict]) -> None:
        self.replies.append((reply_token, messages))

    async def get_image_content(self, *, message_id: str) -> LineImageContent:
        return self.images[message_id]

    async def validate_rich_menu(self, *, rich_menu: dict) -> None:
        if not rich_menu.get("actions"):
            raise ValueError("rich menu must contain actions")

    async def create_rich_menu(self, *, rich_menu: dict) -> str:
        await self.validate_rich_menu(rich_menu=rich_menu)
        self.rich_menus.append(rich_menu)
        return f"mock-rich-menu-{len(self.rich_menus)}"

    async def upload_rich_menu_image(
        self, *, rich_menu_id: str, content: bytes, content_type: str = "image/png"
    ) -> None:
        if not content:
            raise ValueError("rich menu image is empty")
        if content_type not in {"image/png", "image/jpeg"}:
            raise ValueError("rich menu image must be PNG or JPEG")

    async def link_rich_menu(self, *, rich_menu_id: str, user_id: str | None = None) -> None:
        if not rich_menu_id:
            raise ValueError("rich menu id is required")

    async def unlink_rich_menu(self, *, user_id: str | None = None) -> None:
        self.unlinked_users.append(user_id)
