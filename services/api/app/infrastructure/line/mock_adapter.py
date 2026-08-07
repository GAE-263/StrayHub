from __future__ import annotations

from services.api.app.application.ports.line_messaging import LineImageContent


class MockLineAdapter:
    def __init__(self) -> None:
        self.replies: list[tuple[str, list[dict]]] = []
        self.images: dict[str, LineImageContent] = {}
        self.rich_menus: list[dict] = []

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

    async def upload_rich_menu_image(self, *, rich_menu_id: str, content: bytes) -> None:
        if not content:
            raise ValueError("rich menu image is empty")

    async def link_rich_menu(self, *, rich_menu_id: str, user_id: str | None = None) -> None:
        if not rich_menu_id:
            raise ValueError("rich menu id is required")
