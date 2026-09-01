from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LineImageContent:
    message_id: str
    content: bytes
    content_type: str


class LineMessagingPort(Protocol):
    async def push(self, *, to_user_id: str, messages: list[dict]) -> None: ...

    async def reply(self, *, reply_token: str, messages: list[dict]) -> None: ...

    async def get_image_content(self, *, message_id: str) -> LineImageContent: ...

    async def validate_rich_menu(self, *, rich_menu: dict) -> None: ...

    async def create_rich_menu(self, *, rich_menu: dict) -> str: ...

    async def upload_rich_menu_image(
        self, *, rich_menu_id: str, content: bytes, content_type: str = "image/png"
    ) -> None: ...

    async def link_rich_menu(self, *, rich_menu_id: str, user_id: str | None = None) -> None: ...

    async def unlink_rich_menu(self, *, user_id: str | None = None) -> None: ...
