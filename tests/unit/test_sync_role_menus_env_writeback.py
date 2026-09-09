from __future__ import annotations

from pathlib import Path

import pytest
from scripts.sync_line_role_menus import (
    ENV_KEYS,
    load_role_definition,
    resolve_role_image,
    to_line_rich_menu,
    write_env,
)

MAPPING = {
    "default": "richmenu-new-default",
    "volunteer": "richmenu-new-volunteer",
    "adopter": "richmenu-new-adopter",
    "staff": "richmenu-new-staff",
    "adoption_hub": "richmenu-new-adoption-hub",
}


def _read(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines() if "=" in line
    )


def test_existing_ids_are_replaced_in_place(tmp_path: Path) -> None:
    """--apply 每次都產生新 id；沒回寫的話 link 會拿舊 id 打 LINE 然後靜默失敗。"""
    env = tmp_path / ".env"
    env.write_text(
        "LINE_CHANNEL_ID=123\n"
        "LINE_RICH_MENU_DEFAULT_ID=richmenu-old-default\n"
        "LINE_RICH_MENU_VOLUNTEER_ID=richmenu-old-volunteer\n"
        "LINE_RICH_MENU_ADOPTER_ID=richmenu-old-adopter\n"
        "LINE_RICH_MENU_STAFF_ID=richmenu-old-staff\n"
        "LINE_RICH_MENU_ADOPTION_HUB_ID=richmenu-old-adoption-hub\n",
        encoding="utf-8",
    )

    updated = write_env(MAPPING, env)

    assert sorted(updated) == sorted(ENV_KEYS.values())
    values = _read(env)
    assert values["LINE_RICH_MENU_DEFAULT_ID"] == "richmenu-new-default"
    assert values["LINE_RICH_MENU_STAFF_ID"] == "richmenu-new-staff"
    assert values["LINE_RICH_MENU_ADOPTION_HUB_ID"] == "richmenu-new-adoption-hub"
    assert values["LINE_CHANNEL_ID"] == "123", "其他設定不可被動到"


def test_missing_keys_are_appended(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("LINE_CHANNEL_ID=123\n", encoding="utf-8")

    updated = write_env(MAPPING, env)

    assert sorted(updated) == sorted(ENV_KEYS.values())
    assert _read(env)["LINE_RICH_MENU_ADOPTER_ID"] == "richmenu-new-adopter"
    assert _read(env)["LINE_RICH_MENU_ADOPTION_HUB_ID"] == "richmenu-new-adoption-hub"


def test_absent_env_file_is_reported_not_created(tmp_path: Path) -> None:
    env = tmp_path / ".env"

    assert write_env(MAPPING, env) == []
    assert not env.exists()


def test_public_menu_has_only_volunteer_and_adoption_hub_entries() -> None:
    """「領養流程」只是入口，切到領養媒合／毛孩日記共用的兩格選單——見
    line-rich-menu-adoption-hub.yaml 與 line_webhook.py 的 open_adoption_hub。"""
    document = load_role_definition(Path("infra/local/line-rich-menu-default.yaml"))

    assert [action["data"] for action in document["actions"]] == [
        "action=start_volunteer_application",
        "action=open_adoption_hub",
    ]
    rich_menu = to_line_rich_menu(document)
    assert sum(area["bounds"]["width"] for area in rich_menu["areas"]) == 2500
    assert rich_menu["areas"][0]["bounds"]["x"] == 0
    assert rich_menu["areas"][1]["bounds"]["x"] == 1250


def test_role_image_resolves_png_and_jpeg_content_types(tmp_path: Path) -> None:
    (tmp_path / "default.png").write_bytes(b"png")
    (tmp_path / "volunteer.jpeg").write_bytes(b"jpeg")

    assert resolve_role_image(tmp_path, "default") == (
        tmp_path / "default.png",
        "image/png",
    )
    assert resolve_role_image(tmp_path, "volunteer") == (
        tmp_path / "volunteer.jpeg",
        "image/jpeg",
    )


def test_role_image_rejects_empty_or_ambiguous_files(tmp_path: Path) -> None:
    (tmp_path / "default.png").write_bytes(b"")
    with pytest.raises(ValueError, match="為空"):
        resolve_role_image(tmp_path, "default")

    (tmp_path / "default.png").write_bytes(b"png")
    (tmp_path / "default.jpg").write_bytes(b"jpeg")
    with pytest.raises(ValueError, match="重複"):
        resolve_role_image(tmp_path, "default")
