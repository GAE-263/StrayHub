from __future__ import annotations

from pathlib import Path

from scripts.sync_line_role_menus import ENV_KEYS, write_env

MAPPING = {
    "default": "richmenu-new-default",
    "volunteer": "richmenu-new-volunteer",
    "adopter": "richmenu-new-adopter",
    "staff": "richmenu-new-staff",
}


def _read(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )


def test_existing_ids_are_replaced_in_place(tmp_path: Path) -> None:
    """--apply 每次都產生新 id；沒回寫的話 link 會拿舊 id 打 LINE 然後靜默失敗。"""
    env = tmp_path / ".env"
    env.write_text(
        "LINE_CHANNEL_ID=123\n"
        "LINE_RICH_MENU_DEFAULT_ID=richmenu-old-default\n"
        "LINE_RICH_MENU_VOLUNTEER_ID=richmenu-old-volunteer\n"
        "LINE_RICH_MENU_ADOPTER_ID=richmenu-old-adopter\n"
        "LINE_RICH_MENU_STAFF_ID=richmenu-old-staff\n",
        encoding="utf-8",
    )

    updated = write_env(MAPPING, env)

    assert sorted(updated) == sorted(ENV_KEYS.values())
    values = _read(env)
    assert values["LINE_RICH_MENU_DEFAULT_ID"] == "richmenu-new-default"
    assert values["LINE_RICH_MENU_STAFF_ID"] == "richmenu-new-staff"
    assert values["LINE_CHANNEL_ID"] == "123", "其他設定不可被動到"


def test_missing_keys_are_appended(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("LINE_CHANNEL_ID=123\n", encoding="utf-8")

    updated = write_env(MAPPING, env)

    assert sorted(updated) == sorted(ENV_KEYS.values())
    assert _read(env)["LINE_RICH_MENU_ADOPTER_ID"] == "richmenu-new-adopter"


def test_absent_env_file_is_reported_not_created(tmp_path: Path) -> None:
    env = tmp_path / ".env"

    assert write_env(MAPPING, env) == []
    assert not env.exists()
