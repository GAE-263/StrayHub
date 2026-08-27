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
    expected_liff_path = ["", liff_base_segments[1]]
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
                raise ValueError("Rich Menu URI 必須導向含 entry 的 canonical LIFF endpoint")
    return document


def to_line_rich_menu(document: dict) -> dict:
    actions = document["actions"]
    cell_width = 2500 // len(actions)
    areas = []
    for index, action in enumerate(actions):
        line_action = {"type": action["type"]}
        if action["type"] == "postback":
            line_action["data"] = action["data"]
            line_action["displayText"] = action["label"]
        else:
            line_action["uri"] = action["uri"]
        areas.append(
            {
                "bounds": {
                    "x": index * cell_width,
                    "y": 0,
                    "width": cell_width if index < len(actions) - 1 else 2500 - index * cell_width,
                    "height": 1686,
                },
                "action": line_action,
            }
        )
    return {
        "name": document.get("name", "strayhub-volunteer-care"),
        "chatBarText": "志工照護回報",
        "selected": True,
        "size": {"width": 2500, "height": 1686},
        "areas": areas,
    }


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
