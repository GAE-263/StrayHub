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
    "walk_report": "散步回報功能開發中，稍後開放。",
    "volunteer_checkin": "志工報到功能開發中，稍後開放。",
    # 領養人選單
    "want_to_adopt": "「我想領養」功能開發中，稍後開放。",
    "adoption_report": "領養回報功能開發中，稍後開放。",
    # 工作人員選單（重點：透過 LINE 輸入/管理動物資訊，流程參考 paw-village）
    "staff_create_animal": (
        "新增動物功能開發中：將以 LIFF 表單輸入動物基本資料與照片"
        "（參考 paw-village addAnimal）。"
    ),
    "staff_update_health": (
        "更新動物健康紀錄功能開發中：將以 LIFF 表單更新"
        "（參考 paw-village updateAnimal）。"
    ),
    "staff_animal_list": "動物清單功能開發中：將接 management_animals 列表 API。",
    "staff_change_status": "變更動物狀態功能開發中：將接 management_animals PATCH 狀態 API。",
}


# 這些工作人員動作應開啟 LIFF 輸入介面（webhook 回覆 LIFF 連結，優先於占位訊息）。
MENU_LIFF_ACTIONS: dict[str, str] = {
    "staff_create_animal": "staff-animal",
    "staff_update_health": "staff-animal",
}


def is_menu_action(action: str) -> bool:
    return action in MENU_PLACEHOLDER_ACTIONS or action in MENU_LIFF_ACTIONS
