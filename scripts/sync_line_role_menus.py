"""Dry-run by default; --apply only creates/verifies resources, never activates.

Requires explicit expected Bot and durable manifest for publication. Credentials
come only from the process environment, not .env or API settings. See
docs/line-rich-menu-safe-publication.md for the separately approved rollout.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import os
from pathlib import Path

import httpx
import yaml  # type: ignore[import-untyped]
from PIL import Image
from scripts.line_menu_publication import (
    PublicationError,
    ResourcePublisher,
    canonical,
    digest,
)

VALID_ROLES = {"default", "volunteer", "adopter", "staff", "adoption_hub"}
CONFIG_GLOB = "infra/local/line-rich-menu-*.yaml"
IMAGE_CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


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


def resolve_role_image(image_dir: Path, role: str) -> tuple[Path, str]:
    matches = [
        image_dir / f"{role}{suffix}"
        for suffix in IMAGE_CONTENT_TYPES
        if (image_dir / f"{role}{suffix}").is_file()
    ]
    if not matches:
        raise ValueError(f"缺少角色圖片：{image_dir / role}.[png|jpg|jpeg]")
    if len(matches) > 1:
        raise ValueError(f"角色圖片格式重複：{', '.join(str(path) for path in matches)}")
    path = matches[0]
    content = path.read_bytes()
    if not content:
        raise ValueError(f"角色圖片為空：{path}")
    return path, IMAGE_CONTENT_TYPES[path.suffix.lower()]


def publication_plan(by_role: dict[str, dict], image_dir: Path) -> dict:
    plan = {}
    for role, document in sorted(by_role.items()):
        path, content_type = resolve_role_image(image_dir, role)
        content = path.read_bytes()
        with Image.open(path) as image:
            if image.size != (2500, 1686) or image.format not in {"PNG", "JPEG"}:
                raise ValueError(f"{role}: expected 2500x1686 PNG/JPEG")
            if IMAGE_CONTENT_TYPES[path.suffix.lower()] != Image.MIME[image.format]:
                raise ValueError(f"{role}: image extension/content type mismatch")
            image.verify()
        if len(content) > 1024 * 1024:
            raise ValueError(f"{role}: image exceeds 1 MiB")
        definition = to_line_rich_menu(document)
        definition_hash = digest(canonical(definition))
        image_hash = digest(content)
        fingerprint = digest(
            canonical({"role": role, "definition": definition_hash, "image": image_hash})
        )
        # Name helps reconciliation but is NEVER sufficient proof of equivalence.
        definition["name"] = f"strayhub-{role}-{fingerprint}"
        plan[role] = {
            "definition": definition,
            "definition_sha256": digest(canonical(definition)),
            "image_sha256": image_hash,
            "fingerprint": fingerprint,
            "image": content,
            "content_type": content_type,
        }
    return plan


async def apply(
    by_role: dict[str, dict],
    image_dir: Path,
    *,
    manifest: Path,
    expected_bot: str,
    client: httpx.AsyncClient,
) -> dict[str, str]:
    """Resource publication only. No environment writes or menu activation."""
    return await ResourcePublisher(client).publish(
        publication_plan(by_role, image_dir), manifest, expected_bot
    )


ENV_KEYS = {
    "default": "LINE_RICH_MENU_DEFAULT_ID",
    "volunteer": "LINE_RICH_MENU_VOLUNTEER_ID",
    "adopter": "LINE_RICH_MENU_ADOPTER_ID",
    "staff": "LINE_RICH_MENU_STAFF_ID",
    "adoption_hub": "LINE_RICH_MENU_ADOPTION_HUB_ID",
}


def write_env(mapping: dict[str, str], env_path: Path) -> list[str]:
    """Legacy explicit export helper; never called by the publication CLI.

    Caller must separately authorize configuration changes. Existing resources
    remain valid; publishing resources alone does not change active mappings.
    """
    if not env_path.is_file():
        return []
    updated = []
    lines = env_path.read_text(encoding="utf-8").splitlines()
    pending = {ENV_KEYS[role]: rid for role, rid in mapping.items() if role in ENV_KEYS}
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else None
        if key in pending:
            out.append(f"{key}={pending.pop(key)}")
            updated.append(key)
        else:
            out.append(line)
    for key, value in pending.items():
        out.append(f"{key}={value}")
        updated.append(key)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--image-dir", type=Path, default=Path("infra/local/rich-menu-images"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--expected-bot", help="Explicit expected Bot basicId, e.g. @approved-bot")
    parser.add_argument(
        "--roles",
        nargs="+",
        choices=sorted(VALID_ROLES),
        default=["default", "volunteer", "adoption_hub"],
    )
    parser.add_argument("--env-file", type=Path, help="Removed: export IDs separately after review")
    parser.add_argument(
        "--no-write-env", action="store_true", help="Compatibility no-op; env is never written"
    )
    args = parser.parse_args()

    if args.env_file:
        parser.error("--env-file no longer writes configuration; review manifest IDs separately")
    definitions = discover_definitions()
    by_role = {role: definitions[role] for role in args.roles}
    plan = publication_plan(by_role, args.image_dir)
    for role, item in plan.items():
        print(f"[PLAN] {role}: definition={item['definition_sha256']} image={item['image_sha256']}")

    if not args.apply:
        print("DRY RUN: no network, no writes; create/reuse resources only; no activation.")
        return

    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    if not token or not args.manifest or not args.expected_bot:
        parser.error("--apply requires token env, --manifest and --expected-bot")

    async def publish():
        async with httpx.AsyncClient(
            timeout=20, trust_env=False, headers={"Authorization": f"Bearer {token}"}
        ) as client:
            return await ResourcePublisher(client).publish(plan, args.manifest, args.expected_bot)

    try:
        mapping = asyncio.run(publish())
    except PublicationError as exc:
        parser.exit(1, f"{exc}\nNo activation performed.\n")
    except (OSError, ValueError, KeyError):
        # Do not print exception bodies (may contain server text or local configuration).
        parser.exit(1, "Publication stopped; inspect sanitized manifest stages; no activation.\n")
    print("角色 -> richMenuId：")
    for role, rid in mapping.items():
        print(f"  {role}: {rid}")

    print(
        "Resources verified. Existing menus/bindings/config unchanged; "
        "activation requires separate approval."
    )


if __name__ == "__main__":
    main()
