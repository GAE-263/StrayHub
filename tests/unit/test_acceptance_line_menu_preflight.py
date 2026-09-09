import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "menu_preflight",
    Path(__file__).resolve().parents[2] / "infra/gce/scripts/verify-acceptance-line-menus.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture_config():
    return {
        "APP_ENV": "acceptance",
        "LINE_ROLE_MENU_FEATURES_ENABLED": "true",
        "LINE_RICH_MENU_DEFAULT_ID": "richmenu-" + "a" * 32,
        "LINE_RICH_MENU_VOLUNTEER_ID": "richmenu-" + "b" * 32,
    }


def resource(menu_id):
    role = "DEFAULT" if menu_id.endswith("a" * 32) else "VOLUNTEER"
    name, bar, action = module.MENUS[role]
    return {
        "richMenuId": menu_id,
        "name": name,
        "chatBarText": bar,
        "areas": [{"action": {"type": "postback", "data": "action=" + action}}],
    }


def test_volunteer_preflight_does_not_require_staff_liff():
    assert len(module.verify(fixture_config(), resource)) == 2


@pytest.mark.parametrize("key", ["LINE_ROLE_MENU_FEATURES_ENABLED", "LINE_RICH_MENU_VOLUNTEER_ID"])
def test_missing_volunteer_config_fails(key):
    config = fixture_config()
    config.pop(key)
    with pytest.raises(ValueError):
        module.verify(config, resource)


def test_existing_but_wrong_menu_fails():
    config = fixture_config()
    config["LINE_RICH_MENU_VOLUNTEER_ID"] = config["LINE_RICH_MENU_DEFAULT_ID"]
    with pytest.raises(ValueError, match="semantic role mismatch"):
        module.verify(config, resource)


def test_wrong_action_fails():
    value = resource("richmenu-" + "b" * 32)
    value["areas"] = []
    with pytest.raises(ValueError, match="action missing"):
        module.validate_menu("VOLUNTEER", value["richMenuId"], value)
