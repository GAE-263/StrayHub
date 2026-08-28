"""驗證並（可選）發佈「依角色」的多個 LINE Rich Menu。

與既有 sync_line_rich_menu.py 的差異：
  - 這支處理「多份、依角色」的選單（default/volunteer/adopter/staff），全為 postback。
  - --apply 會逐一建立每個選單並印出「角色 -> richMenuId」對應，
    供 line_rich_menu_routing.RichMenuRegistry 使用（綁定時依角色 link 給 UID）。

用法：
  # 只驗證（不需憑證/圖片）
  uv run python -m scripts.sync_line_role_menus

  # 實際建立（需 .env 的 LINE_CHANNEL_ACCESS_TOKEN，且每個角色一張圖）
  uv run python -m scripts.sync_line_role_menus --apply --image-dir infra/local/rich-menu-images
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import os
from pathlib import Path

import yaml  # type: ignore[import-untyped]

VALID_ROLES = {"default", "volunteer", "adopter", "staff"}
CONFIG_GLOB = "infra/local/line-rich-menu-*.yaml"


def load_role_definition(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    role = document.get("role")
    if role not in VALID_ROLES:
        raise ValueError(f"{path.name}: role 必須是 {sorted(VALID_ROLES)} 之一，得到 {role!r}")
    actions = document.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 20:
        raise ValueError(f"{path.name}: 必須包含 1～20 個 action")
    for action in actions:
        if not isinstance(action, dict) or not action.get("label"):
            raise ValueError(f"{path.name}: action 缺少 label")
        if action.get("type") != "postback":
            raise ValueError(
                f"{path.name}: 本框架的角色選單只支援 postback（{action.get('label')!r}）"
            )
        if not action.get("data"):
            raise ValueError(f"{path.name}: postback action 必須有 data（{action.get('label')!r}）")
    return document


def to_line_rich_menu(document: dict) -> dict:
    actions = document["actions"]
    cell_width = 2500 // len(actions)
    areas = []
    for index, action in enumerate(actions):
        width = cell_width if index < len(actions) - 1 else 2500 - index * cell_width
        areas.append(
            {
                "bounds": {"x": index * cell_width, "y": 0, "width": width, "height": 1686},
                "action": {
                    "type": "postback",
                    "data": action["data"],
                    "displayText": action["label"],
                },
            }
        )
    return {
        "name": document.get("name", f"strayhub-{document['role']}"),
        "chatBarText": document.get("chatBarText", document["role"]),
        "selected": document["role"] == "default",
        "size": {"width": 2500, "height": 1686},
        "areas": areas,
    }


def discover_definitions() -> dict[str, dict]:
    by_role: dict[str, dict] = {}
    for file_path in sorted(glob.glob(CONFIG_GLOB)):
        document = load_role_definition(Path(file_path))
        role = document["role"]
        if role in by_role:
            raise ValueError(f"角色 {role} 有重複設定檔")
        by_role[role] = document
    if not by_role:
        raise ValueError(f"找不到任何設定檔（{CONFIG_GLOB}）")
    return by_role


async def apply(by_role: dict[str, dict], image_dir: Path) -> dict[str, str]:
    from services.api.app.infrastructure.line.messaging_api_adapter import (
        LineMessagingApiAdapter,
    )

    adapter = LineMessagingApiAdapter()
    result: dict[str, str] = {}
    try:
        for role, document in by_role.items():
            image_path = image_dir / f"{role}.png"
            if not image_path.is_file():
                raise ValueError(f"缺少角色圖片：{image_path}")
            content = image_path.read_bytes()
            if not content:
                raise ValueError(f"角色圖片為空：{image_path}")
            rich_menu = to_line_rich_menu(document)
            await adapter.validate_rich_menu(rich_menu=rich_menu)
            rich_menu_id = await adapter.create_rich_menu(rich_menu=rich_menu)
            await adapter.upload_rich_menu_image(rich_menu_id=rich_menu_id, content=content)
            result[role] = rich_menu_id
        # default 綁給所有人作為基準；其餘角色於綁定時由 RichMenuRoutingService 依 UID link。
        if "default" in result:
            await adapter.link_rich_menu(rich_menu_id=result["default"])
    finally:
        await adapter.client.aclose()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--image-dir", type=Path, default=Path("infra/local/rich-menu-images"))
    args = parser.parse_args()

    by_role = discover_definitions()
    for role, document in by_role.items():
        _ = to_line_rich_menu(document)  # 轉換驗證
        print(f"[OK] {role}: {document.get('name')}（{len(document['actions'])} 個項目）")

    if not args.apply:
        print("驗證通過（dry-run，未發佈）。加 --apply --image-dir <dir> 才會實際建立。")
        return

    if not os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") and "fake" in (
        os.environ.get("LINE_CHANNEL_ID", "")
    ):
        parser.error("--apply 需要真實的 LINE_CHANNEL_ACCESS_TOKEN")
    mapping = asyncio.run(apply(by_role, args.image_dir))
    print("角色 -> richMenuId：")
    for role, rid in mapping.items():
        print(f"  {role}: {rid}")


if __name__ == "__main__":
    main()
