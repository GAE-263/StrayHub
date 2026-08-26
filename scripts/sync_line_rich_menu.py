"""Validate and optionally publish the versioned LINE Rich Menu definition."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml  # type: ignore[import-untyped]

WIDTH = 2500
HEIGHT = 1686
ENV_PLACEHOLDER = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
ENTRY_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,512}$")
LIFF_RICH_MENU_HOST = "liff.line.me"


def load_definition(path: Path, *, environ: Mapping[str, str] | None = None) -> dict:
    environment = os.environ if environ is None else environ
    raw = path.read_text(encoding="utf-8")
    placeholder_names = sorted(set(ENV_PLACEHOLDER.findall(raw)))
    missing = [name for name in placeholder_names if not environment.get(name)]
    if missing:
        raise ValueError(f"Rich Menu 缺少環境變數：{', '.join(missing)}")
    if any(
        ord(character) < 32 or ord(character) == 127
        for name in placeholder_names
        for character in environment[name]
    ):
        raise ValueError("Rich Menu 環境變數不可包含控制字元")
    rendered = ENV_PLACEHOLDER.sub(lambda match: environment[match.group(1)], raw)
    if ENV_PLACEHOLDER.search(rendered):
        raise ValueError("Rich Menu 仍包含未解析的環境變數")
    document = yaml.safe_load(rendered) or {}
    liff_base_url = document.get("liff_url_reference") or environment.get("LIFF_BASE_URL")
    liff_base = urlparse(liff_base_url or "")
    liff_base_segments = liff_base.path.split("/")
    if (
        liff_base.scheme != "https"
        or liff_base.hostname != LIFF_RICH_MENU_HOST
        or len(liff_base_segments) != 2
        or not liff_base_segments[1]
        or liff_base.query
        or liff_base.fragment
    ):
        raise ValueError("LIFF_BASE_URL 必須是 canonical HTTPS LIFF URL")
    expected_liff_path = ["", liff_base_segments[1], "volunteer-entry"]
    actions = document.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 20:
        raise ValueError("Rich Menu 必須包含 1～20 個 action")
    for action in actions:
        if (
            not isinstance(action, dict)
            or not action.get("label")
            or action.get("type")
            not in {
                "postback",
                "uri",
            }
        ):
            raise ValueError("Rich Menu action 格式無效")
        if action["type"] == "postback" and not action.get("data"):
            raise ValueError("Postback action 必須有 data")
        if action["type"] == "uri" and not action.get("uri"):
            raise ValueError("URI action 必須有 uri")
        if action["type"] == "uri":
            parsed = urlparse(action["uri"])
            try:
                _ = parsed.port
            except ValueError as exc:
                raise ValueError("Rich Menu URI 的 port 無效") from exc
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.hostname.lower() != LIFF_RICH_MENU_HOST
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Rich Menu URI 必須使用有效的 HTTPS host")
            query = parse_qs(parsed.query, keep_blank_values=True)
            entry_values = query.get("entry", [])
            path_segments = parsed.path.split("/")
            if (
                path_segments != expected_liff_path
                or parsed.fragment
                or set(query) != {"entry"}
                or len(entry_values) != 1
                or not ENTRY_REFERENCE_PATTERN.fullmatch(entry_values[0])
                or parsed.port not in {None, 443}
            ):
                raise ValueError("Rich Menu URI 必須導向含 entry 的 volunteer-entry")
    return document


def _line_action(action: dict) -> dict:
    line_action = {"type": action["type"]}
    if action["type"] == "postback":
        line_action["data"] = action["data"]
        line_action["displayText"] = action["label"]
    else:
        line_action["uri"] = action["uri"]
    return line_action


def _layout_bounds(layout: object) -> dict:
    """``layout`` is [x, y, w, h] as fractions of the menu image (0~1)."""
    if not (isinstance(layout, list) and len(layout) == 4):
        raise ValueError("layout 必須是 [x, y, w, h] 四個分數座標")
    x, y, w, h = layout
    if not all(isinstance(value, (int, float)) for value in (x, y, w, h)):
        raise ValueError("layout 座標必須是數字")
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1):
        raise ValueError(f"layout 座標超出範圍：{layout}")
    if x + w > 1 + 1e-9 or y + h > 1 + 1e-9:
        raise ValueError(f"layout 範圍超出圖片邊界：{layout}")
    return {
        "x": round(x * WIDTH),
        "y": round(y * HEIGHT),
        "width": round(w * WIDTH),
        "height": round(h * HEIGHT),
    }


def to_line_rich_menu(document: dict) -> dict:
    actions = document["actions"]
    if any("layout" in action for action in actions):
        # Explicit per-action bounds for a non-uniform layout (e.g. one big
        # hero cell plus smaller cells below it) — takes over from `columns`
        # entirely when any action uses it, so a definition cannot mix the
        # two schemes by accident.
        if not all("layout" in action for action in actions):
            raise ValueError("layout 若使用，每個 action 都必須提供")
        areas = [
            {"bounds": _layout_bounds(action["layout"]), "action": _line_action(action)}
            for action in actions
        ]
    else:
        # ``columns`` lets a definition lay actions out as a grid; omitting it
        # keeps the original behaviour of one full-height row.
        columns = int(document.get("columns") or len(actions))
        if columns < 1:
            raise ValueError("columns 必須大於 0")
        rows = -(-len(actions) // columns)
        cell_width = WIDTH // columns
        cell_height = HEIGHT // rows
        areas = []
        for index, action in enumerate(actions):
            column, row = index % columns, index // columns
            # The last cell in each direction absorbs the rounding remainder
            # so the areas tile the image exactly.
            areas.append(
                {
                    "bounds": {
                        "x": column * cell_width,
                        "y": row * cell_height,
                        "width": (
                            cell_width if column < columns - 1 else WIDTH - column * cell_width
                        ),
                        "height": cell_height if row < rows - 1 else HEIGHT - row * cell_height,
                    },
                    "action": _line_action(action),
                }
            )
    return {
        "name": document.get("name", "strayhub-volunteer-care"),
        "chatBarText": "志工照護回報",
        "selected": True,
        "size": {"width": WIDTH, "height": HEIGHT},
        "areas": areas,
    }


IMAGE_CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _image_content_type(path: Path) -> str:
    """LINE rejects the upload when Content-Type disagrees with the bytes."""
    try:
        return IMAGE_CONTENT_TYPES[path.suffix.lower()]
    except KeyError:
        raise ValueError(f"Rich Menu 底圖只支援 PNG 或 JPEG：{path.name}") from None


async def publish(document: dict, image_path: Path | None) -> str:
    if image_path is None or not image_path.is_file():
        raise ValueError("Rich Menu image 必須是可讀取的檔案")
    try:
        image_content = image_path.read_bytes()
    except OSError as exc:
        raise ValueError("Rich Menu image 無法讀取") from exc
    if not image_content:
        raise ValueError("Rich Menu image 不可為空")

    from services.api.app.infrastructure.line.messaging_api_adapter import (
        LineMessagingApiAdapter,
    )

    adapter = LineMessagingApiAdapter()
    rich_menu = to_line_rich_menu(document)
    await adapter.validate_rich_menu(rich_menu=rich_menu)
    rich_menu_id = await adapter.create_rich_menu(rich_menu=rich_menu)
    await adapter.upload_rich_menu_image(
        rich_menu_id=rich_menu_id,
        content=image_content,
        content_type=_image_content_type(image_path),
    )
    await adapter.link_rich_menu(rich_menu_id=rich_menu_id)
    await adapter.client.aclose()
    return rich_menu_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("infra/local/line-rich-menu.yaml"),
    )
    parser.add_argument("--image", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    document = load_definition(args.config)
    if not args.apply:
        print(f"Rich Menu 設定有效：{document.get('name', 'unnamed')}")
        return
    if args.image is None:
        parser.error("--apply 必須同時提供 --image")
    print(asyncio.run(publish(document, args.image)))


if __name__ == "__main__":
    main()
