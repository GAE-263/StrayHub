"""Validate and optionally publish the versioned LINE Rich Menu definitions.

The YAML config declares a `menus:` list — one entry per Rich Menu the bot
switches between (the account-wide default, plus per-conversation menus like
the adoption region/path selectors). Each is published independently; only
the entry keyed `default` gets linked account-wide (`link_rich_menu` with no
`user_id`) — the others are linked to individual users at runtime by the
webhook layer as a conversation progresses.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

_PLACEHOLDER = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _substitute_env_placeholders(value: Any) -> Any:
    """Replace `${VAR_NAME}` in string values with `os.environ["VAR_NAME"]`.

    Raises a clear error instead of letting an unsubstituted placeholder
    (e.g. `${LIFF_QR_ENTRY_URL}`) reach LINE's API as a literal, invalid URI."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in os.environ:
                raise ValueError(f"Rich Menu 設定使用了未設定的環境變數：${{{name}}}")
            return os.environ[name]

        return _PLACEHOLDER.sub(replace, value)
    if isinstance(value, dict):
        return {key: _substitute_env_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute_env_placeholders(item) for item in value]
    return value


def load_definition(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    document = _substitute_env_placeholders(document)
    menus = document.get("menus")
    if not isinstance(menus, list) or not menus:
        raise ValueError("Rich Menu 設定必須包含至少一個 menus 項目")
    seen_keys: set[str] = set()
    for menu in menus:
        if not isinstance(menu, dict) or not menu.get("key") or not menu.get("name"):
            raise ValueError("每個 Rich Menu 都必須有 key 與 name")
        if menu["key"] in seen_keys:
            raise ValueError(f"重複的 Rich Menu key：{menu['key']}")
        seen_keys.add(menu["key"])
        actions = menu.get("actions")
        if not isinstance(actions, list) or not 1 <= len(actions) <= 20:
            raise ValueError(f"Rich Menu「{menu['key']}」必須包含 1～20 個 action")
        for action in actions:
            if (
                not isinstance(action, dict)
                or not action.get("label")
                or action.get("type") not in {"postback", "uri"}
            ):
                raise ValueError(f"Rich Menu「{menu['key']}」的 action 格式無效")
            if action["type"] == "postback" and not action.get("data"):
                raise ValueError("Postback action 必須有 data")
            if action["type"] == "uri" and not action.get("uri"):
                raise ValueError("URI action 必須有 uri")
    return document


def layout_areas(actions: list[dict]) -> list[dict]:
    """Map actions onto LINE's large (2500x1686) Rich Menu tap-region grid.

    4 actions use the 2x2 template (each 1250x843); anything else uses an
    N-column single-row template (2 actions -> 2x1 at 1250x1686 each, 3 -> 3x1
    at ~833x1686 each, and so on) — matching the exact large-layout pixel
    specs used for the adoption region/path selectors, while leaving the
    unrelated 6-button default menu's existing even-column layout unchanged."""
    count = len(actions)
    if count == 4:
        cell_width, cell_height = 1250, 843
        positions = [(col * cell_width, row * cell_height) for row in range(2) for col in range(2)]
    else:
        cell_width, cell_height = 2500 // count, 1686
        positions = [(index * cell_width, 0) for index in range(count)]

    areas = []
    for index, (action, (x, y)) in enumerate(zip(actions, positions, strict=True)):
        line_action = {"type": action["type"]}
        if action["type"] == "postback":
            line_action["data"] = action["data"]
            line_action["displayText"] = action["label"]
        else:
            line_action["uri"] = action["uri"]
        if count == 4:
            width, height = cell_width, cell_height
        else:
            width = cell_width if index < count - 1 else 2500 - index * cell_width
            height = cell_height
        bounds = {"x": x, "y": y, "width": width, "height": height}
        areas.append({"bounds": bounds, "action": line_action})
    return areas


def to_line_rich_menu(menu: dict) -> dict:
    return {
        "name": menu.get("name", "strayhub-rich-menu"),
        "chatBarText": menu.get("chat_bar_text", "StrayHub"),
        "selected": True,
        "size": {"width": 2500, "height": 1686},
        "areas": layout_areas(menu["actions"]),
    }


_IMAGE_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _find_menu_image(image_dir: Path, key: str) -> tuple[Path, str]:
    """A menu's art can be this project's own generated PNG placeholder or a
    supplied JPEG design (JPEG compresses photographic/gradient artwork far
    enough below LINE's 1MB image limit to matter); either extension works."""
    for suffix, content_type in _IMAGE_CONTENT_TYPES.items():
        candidate = image_dir / f"line-rich-menu-{key}{suffix}"
        if candidate.exists():
            return candidate, content_type
    raise SystemExit(
        f"找不到選單圖片：{image_dir / f'line-rich-menu-{key}.png'}（或 .jpg）"
        "（先執行 scripts/generate_rich_menu_image.py 或準備正式設計圖）"
    )


async def publish_all(document: dict, image_dir: Path) -> dict[str, str]:
    from services.api.app.infrastructure.line.messaging_api_adapter import (
        LineMessagingApiAdapter,
    )

    adapter = LineMessagingApiAdapter()
    results: dict[str, str] = {}
    try:
        for menu in document["menus"]:
            key = menu["key"]
            image_path, content_type = _find_menu_image(image_dir, key)
            rich_menu = to_line_rich_menu(menu)
            await adapter.validate_rich_menu(rich_menu=rich_menu)
            rich_menu_id = await adapter.create_rich_menu(rich_menu=rich_menu)
            await adapter.upload_rich_menu_image(
                rich_menu_id=rich_menu_id,
                content=image_path.read_bytes(),
                content_type=content_type,
            )
            results[key] = rich_menu_id
            if key == "default":
                await adapter.link_rich_menu(rich_menu_id=rich_menu_id)
    finally:
        await adapter.client.aclose()
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("infra/local/line-rich-menu.yaml"),
    )
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=None,
        help="Directory holding line-rich-menu-<key>.png files (defaults to --config's directory)",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    document = load_definition(args.config)
    if not args.apply:
        keys = "、".join(menu["key"] for menu in document["menus"])
        print(f"Rich Menu 設定有效：{keys}")
        return
    image_dir = args.image_dir or args.config.parent
    results = asyncio.run(publish_all(document, image_dir))
    for key, rich_menu_id in results.items():
        print(f"{key} -> {rich_menu_id}")


if __name__ == "__main__":
    main()
