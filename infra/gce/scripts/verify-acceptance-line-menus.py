"""Read-only LINE resource preflight for the volunteer acceptance checkpoint.

Run in the acceptance API environment, before human menu validation. This does
not create/link menus or emit credentials. Static Compose validation alone is
not evidence that the configured IDs belong to the intended LINE channel.
"""

import json
import os
import re
import sys
from urllib.parse import parse_qs
from urllib.request import Request, urlopen

MENUS = {
    "DEFAULT": ("strayhub-default", "浪浪森友島", "start_volunteer_application"),
    "VOLUNTEER": ("strayhub-volunteer", "志工選單", "walk_report"),
    "ADOPTER": ("strayhub-adopter", "領養選單", None),
    "ADOPTION_HUB": ("strayhub-adoption-hub", "領養與日記", "start_adoption_matching"),
    "STAFF": ("strayhub-staff", "工作人員", None),
}


def validate_menu(role, menu_id, resource):
    name, chat_bar, required_action = MENUS[role]
    if (
        resource.get("richMenuId") != menu_id
        or resource.get("name") != name
        or resource.get("chatBarText") != chat_bar
    ):
        raise ValueError(f"{role}: menu identity/semantic role mismatch")
    actions = {
        parse_qs(area.get("action", {}).get("data", "")).get("action", [""])[0]
        for area in resource.get("areas", [])
        if area.get("action", {}).get("type") == "postback"
    }
    if required_action and required_action not in actions:
        raise ValueError(f"{role}: required action missing")


def verify(environment, fetch):
    if environment.get("APP_ENV") != "acceptance":
        raise ValueError("acceptance environment required")
    if environment.get("LINE_ROLE_MENU_FEATURES_ENABLED") != "true":
        raise ValueError("role menus must be enabled")
    results = []
    for role in MENUS:
        menu_id = environment.get(f"LINE_RICH_MENU_{role}_ID", "").strip()
        if not menu_id and role not in {"DEFAULT", "VOLUNTEER"}:
            continue
        if not re.fullmatch(r"richmenu-[0-9a-f]{32}", menu_id):
            raise ValueError(f"{role}: missing or invalid menu ID")
        resource = fetch(menu_id)
        validate_menu(role, menu_id, resource)
        results.append(
            {
                "role": role,
                "id": menu_id,
                "name": resource["name"],
                "chatBarText": resource["chatBarText"],
            }
        )
    return results


def main():
    def fetch(menu_id):
        request = Request(
            "https://api.line.me/v2/bot/richmenu/" + menu_id,
            headers={"Authorization": "Bearer " + os.environ["LINE_CHANNEL_ACCESS_TOKEN"]},
        )
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    try:
        print(
            json.dumps({"result": "PASS", "menus": verify(os.environ, fetch)}, ensure_ascii=False)
        )
    except Exception:
        # Never print network exceptions/headers or environment contents.
        print(
            "[Acceptance LINE menu preflight] FAIL: configuration or LINE resource mismatch",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
