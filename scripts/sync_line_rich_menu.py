"""Validate and optionally publish the versioned LINE Rich Menu definition."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml  # type: ignore[import-untyped]


def load_definition(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
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
    from services.api.app.infrastructure.line.messaging_api_adapter import (
        LineMessagingApiAdapter,
    )

    adapter = LineMessagingApiAdapter()
    rich_menu = to_line_rich_menu(document)
    await adapter.validate_rich_menu(rich_menu=rich_menu)
    rich_menu_id = await adapter.create_rich_menu(rich_menu=rich_menu)
    if image_path is not None:
        await adapter.upload_rich_menu_image(
            rich_menu_id=rich_menu_id,
            content=image_path.read_bytes(),
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
