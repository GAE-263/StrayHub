"""依角色切換 LINE Rich Menu 的路由框架。

背景：原本的 sync_line_rich_menu.py 只處理「單一志工選單」並綁給所有人
(link_rich_menu 不帶 user_id)。這支模組把它擴充成「依綁定後的角色，綁不同選單
給該使用者的 LINE UID」的框架。

範圍（先做框架，內容由後續補）：
  - 角色 → 選單 key 的對應
  - 新增 ADOPTER 角色常數（後端角色體系尚未正式納入，見設計文件）
  - RichMenuRoutingService.link_for_user()：依角色把對應 rich menu 綁到該 UID

尚未做（刻意留給接手者）：
  - 綁定成功後呼叫 link_for_user 的接點（在 SessionService.bind_line_identity）
  - 各 rich menu 的實際 richMenuId 來源（由 scripts/sync_line_role_menus.py --apply 產生後填入）
"""

from __future__ import annotations

from dataclasses import dataclass

from services.api.app.application.ports.line_messaging import LineMessagingPort


class LineRole:
    """LINE 選單路由用到的角色常數。

    VOLUNTEER / STAFF / SHELTER_ADMIN / PLATFORM_ADMIN 是後端既有角色；
    ADOPTER 為本次新增（框架層），正式權限邏輯尚未納入。
    """

    VOLUNTEER = "VOLUNTEER"
    STAFF = "STAFF"
    SHELTER_ADMIN = "SHELTER_ADMIN"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    ADOPTER = "ADOPTER"  # 新增角色（框架用），後端角色體系尚未正式支援


# 選單 key（對應 infra/local/line-rich-menu-<key>.yaml 的 role 欄位）
MENU_DEFAULT = "default"
MENU_VOLUNTEER = "volunteer"
MENU_ADOPTER = "adopter"
MENU_STAFF = "staff"

MENU_KEYS = (MENU_DEFAULT, MENU_VOLUNTEER, MENU_ADOPTER, MENU_STAFF)

# 具管理權的角色一律導向工作人員選單。
_STAFF_ROLES = frozenset({LineRole.STAFF, LineRole.SHELTER_ADMIN, LineRole.PLATFORM_ADMIN})

_ROLE_TO_MENU = {
    LineRole.VOLUNTEER: MENU_VOLUNTEER,
    LineRole.ADOPTER: MENU_ADOPTER,
}


def menu_key_for_role(role: str | None, *, bound: bool = True) -> str:
    """回傳該角色應綁定的選單 key。

    - 未綁定（bound=False）或角色未知 → default（可看基本資訊 + 綁定入口）
    - 具管理權角色 → staff
    - VOLUNTEER / ADOPTER → 對應選單
    """
    if not bound or not role:
        return MENU_DEFAULT
    normalized = role.upper()
    if normalized in _STAFF_ROLES:
        return MENU_STAFF
    return _ROLE_TO_MENU.get(normalized, MENU_DEFAULT)


@dataclass(frozen=True)
class RichMenuRegistry:
    """選單 key → 已建立的 richMenuId 對應。

    來源：scripts/sync_line_role_menus.py --apply 產生後，填入設定/環境變數。
    在 mock/本機驗證時可用占位 id。
    """

    menu_ids: dict[str, str]

    def get(self, menu_key: str) -> str | None:
        return self.menu_ids.get(menu_key)


def build_registry(
    *, default: str = "", volunteer: str = "", adopter: str = "", staff: str = ""
) -> RichMenuRegistry:
    """從各角色的 richMenuId 建立 registry；只收非空值。"""
    pairs = {
        MENU_DEFAULT: default,
        MENU_VOLUNTEER: volunteer,
        MENU_ADOPTER: adopter,
        MENU_STAFF: staff,
    }
    return RichMenuRegistry({key: value for key, value in pairs.items() if value})


class RichMenuRoutingService:
    """依角色把對應 rich menu 綁到單一使用者的 LINE UID。"""

    def __init__(self, line: LineMessagingPort, registry: RichMenuRegistry) -> None:
        self.line = line
        self.registry = registry

    async def link_for_user(
        self, *, line_user_id: str, role: str | None, bound: bool = True
    ) -> str | None:
        """綁定對應選單，回傳所綁定的 richMenuId；若尚未註冊該選單則回傳 None。"""
        menu_key = menu_key_for_role(role, bound=bound)
        rich_menu_id = self.registry.get(menu_key)
        if rich_menu_id is None:
            # 尚未建立該角色選單（例如還沒 --apply）；框架階段視為 no-op。
            return None
        await self.line.link_rich_menu(rich_menu_id=rich_menu_id, user_id=line_user_id)
        return rich_menu_id
