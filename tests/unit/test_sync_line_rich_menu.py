from pathlib import Path

import pytest
from scripts.sync_line_rich_menu import load_definition, publish


def test_load_definition_expands_environment_variables(tmp_path: Path) -> None:
    config = tmp_path / "rich-menu.yaml"
    config.write_text(
        """version: 1
name: test
liff_url_reference: ${LIFF_BASE_URL}
actions:
  - label: 開啟志工入口
    type: uri
    uri: ${LIFF_BASE_URL}?entry=${SHELTER_ENTRY_REFERENCE}
""",
        encoding="utf-8",
    )

    document = load_definition(
        config,
        environ={
            "LIFF_BASE_URL": "https://liff.line.me/123-test",
            "SHELTER_ENTRY_REFERENCE": "opaque-entry-reference-0123456789abcdef-extra",
        },
    )

    assert document["liff_url_reference"] == "https://liff.line.me/123-test"
    assert document["actions"][0]["uri"] == (
        "https://liff.line.me/123-test?entry=opaque-entry-reference-0123456789abcdef-extra"
    )


def test_load_definition_fails_fast_for_unresolved_placeholder(tmp_path: Path) -> None:
    config = tmp_path / "rich-menu.yaml"
    config.write_text(
        """version: 1
name: test
actions:
  - label: 開啟志工入口
    type: uri
    uri: ${LIFF_BASE_URL}/volunteer-entry
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="LIFF_BASE_URL"):
        load_definition(config, environ={})


def test_load_definition_rejects_placeholder_inside_environment_value(
    tmp_path: Path,
) -> None:
    config = tmp_path / "rich-menu.yaml"
    config.write_text(
        """version: 1
name: test
actions:
  - label: 開啟志工入口
    type: uri
    uri: ${LIFF_BASE_URL}?entry=${SHELTER_ENTRY_REFERENCE}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="未解析"):
        load_definition(
            config,
            environ={
                "LIFF_BASE_URL": "https://liff.line.me/test",
                "SHELTER_ENTRY_REFERENCE": "${UNRESOLVED}",
            },
        )


def test_load_definition_rejects_control_character_inside_environment_value(
    tmp_path: Path,
) -> None:
    config = tmp_path / "rich-menu.yaml"
    config.write_text(
        """version: 1
name: test
actions:
  - label: 開啟志工入口
    type: uri
    uri: ${LIFF_BASE_URL}?entry=${SHELTER_ENTRY_REFERENCE}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="控制字元"):
        load_definition(
            config,
            environ={
                "LIFF_BASE_URL": "https://liff.line.me/test",
                "SHELTER_ENTRY_REFERENCE": "opaque-entry-reference-0123456789abcdef\n",
            },
        )


def test_load_definition_rejects_non_https_published_uri(tmp_path: Path) -> None:
    config = tmp_path / "rich-menu.yaml"
    config.write_text(
        """version: 1
name: test
liff_url_reference: https://liff.line.me/test
actions:
  - label: 開啟志工入口
    type: uri
    uri: http://localhost:3000/volunteer-entry
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="HTTPS"):
        load_definition(config, environ={})


@pytest.mark.parametrize(
    "uri",
    [
        "https://localhost/volunteer-entry?entry=opaque-entry",
        "https:///volunteer-entry?entry=opaque-entry",
        "https://liff.line.me.evil/volunteer-entry?entry=opaque-entry",
        "https://liff.line.me/attacker/volunteer-entry?entry=opaque-entry-reference-0123456789abcdef-extra",
        "https://liff.line.me/wrong-route",
        "https://liff.line.me/volunteer-entry",
        "https://liff.line.me/test?entry=short",
        "https://liff.line.me/test?entry=opaque-entry-reference-0123456789abcdef-extra&entry=second",
        "https://liff.line.me/test?entry=opaque-entry-reference-0123456789abcdef-extra#fragment",
        "https://liff.line.me/test//volunteer-entry?entry=opaque-entry-reference-0123456789abcdef-extra",
        "https://liff.line.me/test/volunteer-entry/?entry=opaque-entry-reference-0123456789abcdef-extra",
        "https://liff.line.me:0/test?entry=opaque-entry-reference-0123456789abcdef-extra",
        "https://liff.line.me:444/test?entry=opaque-entry-reference-0123456789abcdef-extra",
    ],
)
def test_load_definition_rejects_invalid_volunteer_entry_uri(tmp_path: Path, uri: str) -> None:
    config = tmp_path / "rich-menu.yaml"
    config.write_text(
        f"""version: 1
name: test
liff_url_reference: https://liff.line.me/test
actions:
  - label: 開啟志工入口
    type: uri
    uri: {uri}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_definition(config, environ={})


@pytest.mark.asyncio
async def test_publish_rejects_missing_image_before_any_remote_publish(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="image"):
        await publish(
            {
                "name": "test",
                "actions": [
                    {
                        "label": "開啟志工入口",
                        "type": "uri",
                        "uri": "https://liff.line.me/test?entry=opaque-entry",
                    }
                ],
            },
            tmp_path / "missing.png",
        )
