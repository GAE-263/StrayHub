from pathlib import Path

import pytest
from scripts.sync_line_rich_menu import layout_areas, load_definition, to_line_rich_menu

_DEFAULT_MENU = """version: 2
menus:
  - key: default
    name: test-default
    chat_bar_text: 領養媒合
    actions:
      - label: 領養媒合
        type: postback
        data: action=start_adoption_matching&flow=adoption
      - label: 掃描 QR Code
        type: uri
        uri: ${LIFF_QR_ENTRY_URL}
"""


def _write(tmp_path: Path, body: str) -> Path:
    config = tmp_path / "rich-menu.yaml"
    config.write_text(body, encoding="utf-8")
    return config


def test_load_definition_expands_environment_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIFF_QR_ENTRY_URL", "https://liff.line.me/123-test/qr")
    document = load_definition(_write(tmp_path, _DEFAULT_MENU))

    assert document["menus"][0]["actions"][1]["uri"] == "https://liff.line.me/123-test/qr"


def test_load_definition_fails_fast_for_unresolved_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIFF_QR_ENTRY_URL", raising=False)

    with pytest.raises(ValueError, match="LIFF_QR_ENTRY_URL"):
        load_definition(_write(tmp_path, _DEFAULT_MENU))


def test_load_definition_requires_at_least_one_menu(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="menus"):
        load_definition(_write(tmp_path, "version: 2\nmenus: []\n"))


def test_load_definition_rejects_duplicate_menu_keys(tmp_path: Path) -> None:
    body = """version: 2
menus:
  - key: default
    name: a
    actions:
      - label: A
        type: postback
        data: action=a
  - key: default
    name: b
    actions:
      - label: B
        type: postback
        data: action=b
"""
    with pytest.raises(ValueError, match="重複"):
        load_definition(_write(tmp_path, body))


def test_load_definition_rejects_postback_without_data(tmp_path: Path) -> None:
    body = """version: 2
menus:
  - key: default
    name: a
    actions:
      - label: A
        type: postback
"""
    with pytest.raises(ValueError, match="data"):
        load_definition(_write(tmp_path, body))


def test_load_definition_rejects_unknown_action_type(tmp_path: Path) -> None:
    body = """version: 2
menus:
  - key: default
    name: a
    actions:
      - label: A
        type: message
        text: hi
"""
    with pytest.raises(ValueError, match="格式無效"):
        load_definition(_write(tmp_path, body))


def test_layout_areas_uses_2x2_grid_for_four_actions() -> None:
    actions = [{"label": f"A{i}", "type": "postback", "data": f"action=a{i}"} for i in range(4)]
    areas = layout_areas(actions)

    assert [area["bounds"] for area in areas] == [
        {"x": 0, "y": 0, "width": 1250, "height": 843},
        {"x": 1250, "y": 0, "width": 1250, "height": 843},
        {"x": 0, "y": 843, "width": 1250, "height": 843},
        {"x": 1250, "y": 843, "width": 1250, "height": 843},
    ]


def test_layout_areas_single_row_covers_full_width() -> None:
    actions = [
        {"label": "A", "type": "postback", "data": "action=a"},
        {"label": "B", "type": "uri", "uri": "https://liff.line.me/test"},
        {"label": "C", "type": "postback", "data": "action=c"},
    ]
    areas = layout_areas(actions)

    assert areas[0]["bounds"]["x"] == 0
    assert areas[-1]["bounds"]["x"] + areas[-1]["bounds"]["width"] == 2500
    assert all(area["bounds"]["height"] == 1686 for area in areas)
    assert areas[1]["action"] == {"type": "uri", "uri": "https://liff.line.me/test"}


def test_to_line_rich_menu_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFF_QR_ENTRY_URL", "https://liff.line.me/test/qr")
    document = load_definition(_write(tmp_path, _DEFAULT_MENU))
    rich_menu = to_line_rich_menu(document["menus"][0])

    assert rich_menu["name"] == "test-default"
    assert rich_menu["chatBarText"] == "領養媒合"
    assert rich_menu["size"] == {"width": 2500, "height": 1686}
    assert len(rich_menu["areas"]) == 2
