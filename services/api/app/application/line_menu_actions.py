"""角色選單各項目的 postback 動作占位。

先做框架：每個新選單項目對應一句占位回覆，讓「底部選單 → 點按 → 有回應」的
接線可用 mock adapter 驗證。實際內容由後續接手者實作（例如開 LIFF 表單、
接 management_animals API 等）。

start_binding 不在這裡（它要回覆 LIFF 綁定連結，由 webhook 特別處理）。
"""

from __future__ import annotations

# action 代碼 → 占位回覆文字
MENU_PLACEHOLDER_ACTIONS: dict[str, str] = {
    # 預設選單
    "shelter_info": "這裡將顯示收容所基本資訊（開發中）。",
    # 志工選單
    "volunteer_checkin": "線上報到尚未開放，請向現場工作人員確認報到方式。",
}


# 這些工作人員動作應開啟 LIFF 輸入介面（webhook 回覆 LIFF 連結，優先於占位訊息）。
MENU_LIFF_ACTIONS: dict[str, str] = {
    "staff_create_animal": "staff-animal",
    "staff_update_health": "staff-animal",
}
STAFF_MENU_ACTIONS: frozenset[str] = frozenset(
    {*MENU_LIFF_ACTIONS, "staff_animal_list", "staff_change_status"}
)

# 志工／領養人選單都有的「返回主選單」：切回 default，讓有個別身份的人自由換入口。
BACK_TO_DEFAULT_MENU_ACTION = "back_to_default_menu"


def is_menu_action(action: str) -> bool:
    return (
        action in MENU_PLACEHOLDER_ACTIONS
        or action in STAFF_MENU_ACTIONS
        or action == BACK_TO_DEFAULT_MENU_ACTION
    )
