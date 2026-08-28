# StrayHub LINE 依角色選單框架

> 狀態：**框架已建（先做結構，內容由後續接手者實作）**
> 建立日期：2026-08-26
> 前提：實際把選單推上 LINE、依 UID 切換，需真實 LINE channel 憑證；本框架可在本機／mock 驗證。

---

## 1. 目標行為

```
LINE 官方帳號（未綁定）── 預設選單：看基本資訊 + 綁定
        │
        ▼ 底部選單「綁定身分」
   後端依綁定後的角色，把對應 Rich Menu 綁到該使用者的 LINE UID
        ├─ 工作人員（STAFF / SHELTER_ADMIN / PLATFORM_ADMIN）→ 工作人員選單
        ├─ 志工（VOLUNTEER）→ 志工選單：散步回報 / 志工報到
        └─ 領養人（ADOPTER，新角色）→ 領養選單：我想領養 / 領養回報
```

## 2. 選單定義（已建）

四份 YAML 位於 `infra/local/`，全部為 postback 動作（dry-run 不需憑證）：

| 檔案 | role | chatBarText | 項目（action 代碼） |
|---|---|---|---|
| `line-rich-menu-default.yaml` | default | 收容所資訊 | 收容所基本資訊(`shelter_info`)、綁定身分(`start_binding`) |
| `line-rich-menu-volunteer.yaml` | volunteer | 志工選單 | 散步回報(`walk_report`)、志工報到(`volunteer_checkin`) |
| `line-rich-menu-adopter.yaml` | adopter | 領養選單 | 我想領養(`want_to_adopt`)、領養回報(`adoption_report`) |
| `line-rich-menu-staff.yaml` | staff | 工作人員 | 新增動物(`staff_create_animal`)、更新健康紀錄(`staff_update_health`)、動物清單(`staff_animal_list`)、變更動物狀態(`staff_change_status`) |

> 既有的 `infra/local/line-rich-menu.yaml`（單一志工照護選單）**未更動**，仍可獨立使用。

## 3. 角色路由（已建）

`services/api/app/application/line_rich_menu_routing.py`

- `LineRole`：角色常數，含**新增的 `ADOPTER`**。
- `menu_key_for_role(role, bound)`：
  - 未綁定 / 角色未知 → `default`
  - `STAFF` / `SHELTER_ADMIN` / `PLATFORM_ADMIN` → `staff`
  - `VOLUNTEER` → `volunteer`；`ADOPTER` → `adopter`
- `RichMenuRegistry`：選單 key → 已建立的 `richMenuId` 對應（由 sync 腳本 `--apply` 產生後填入）。
- `RichMenuRoutingService.link_for_user(line_user_id, role)`：依角色把對應 rich menu 綁到該 UID（用既有 `LineMessagingPort.link_rich_menu(rich_menu_id, user_id=...)`）。選單尚未註冊時為 no-op。

## 4. 選單動作占位（已建 + 已接線）

- `services/api/app/application/line_menu_actions.py`：`MENU_PLACEHOLDER_ACTIONS`，每個新選單項目對應一句「開發中」占位回覆。
- `services/api/app/api/line_webhook.py`：在 `_handle_postback` 解析 action 後，additive 加入兩個分支：
  - `start_binding` → 回覆 LIFF 綁定連結（沿用 `_liff_binding_message()`）。
  - 命中 `MENU_PLACEHOLDER_ACTIONS` → 回覆對應占位訊息。
- 既有 postback 動作（`start_care_report`、`resume_draft`、`contact_staff` 等）**行為不變**。

## 5. 發佈腳本（已建）

`scripts/sync_line_role_menus.py`

- 不帶參數：驗證四份設定（dry-run），輸出每個角色的項目數。已實測通過。
- `--apply --image-dir <dir>`：逐一建立每個選單、上傳圖片，印出「角色 → richMenuId」，並把 `default` 綁給所有人作為基準。需真實 `LINE_CHANNEL_ACCESS_TOKEN` 與每角色一張圖（`<role>.png`）。

## 6. 接手者要做的事（TODO，內容層）

**綁定時切換選單（關鍵接點）— ✅ 已接（2026-08-26）**
在綁定成功處（`SessionService.bind_line_identity`，`services/api/app/application/authentication/session_service.py`）取得使用者角色後，呼叫：
```python
await RichMenuRoutingService(line_adapter, registry).link_for_user(
    line_user_id=line_user_id, role=role
)
```
`registry` 來自 `sync_line_role_menus.py --apply` 的輸出（建議存為設定 / 環境變數）。

> 已實作：`SessionService.bind_line_identity` 綁定成功後會 best-effort 呼叫 `_link_role_rich_menu(line_user_id, role)`（link 失敗不影響綁定）。`get_session_service` 會在 settings 有設 `line_rich_menu_*_id` 時自動組出 router。
> 只要 `.env` 填入 `LINE_RICH_MENU_DEFAULT_ID` / `_VOLUNTEER_ID` / `_ADOPTER_ID` / `_STAFF_ID`（由 sync `--apply` 產生），綁定就會依角色切換選單；全空則為 no-op。

**各選單項目的實作**（目前都是占位）
- 志工：`walk_report`、`volunteer_checkin`
- 領養人：`want_to_adopt`、`adoption_report`
- 工作人員（重點）：
  - `staff_create_animal` / `staff_update_health`：✅ 已建 LIFF 介面 `line-liff/staff-animal/`（由 paw-village 衍生），選單點按會回覆 LIFF 連結。後端合約見 `docs/staff-animal-line-input.md`。⚠️ 其中 `POST /v1/management/animals` 與 `.../health-records` 為 **[後端待實作]**（StrayHub 目前無建立動物 API）。
  - `staff_animal_list` / `staff_change_status`：接既有 `management_animals`（列表 / PATCH 狀態，`require_staff_or_admin`）。

**ADOPTER 角色正式化**
本框架只在選單路由層引入 `ADOPTER`。若要正式成為後端角色，需擴充 membership role 體系與相關權限白名單（`services/api/app/api/management_access.py` 等），並決定領養人如何綁定（可能不屬於任何收容所 membership）。

**圖片素材**
四張 rich menu 底圖（2500×1686，`default.png`/`volunteer.png`/`adopter.png`/`staff.png`）放進 `--image-dir`。

## 7. 本輪未改動 / 限制

- 未接觸 auth 綁定核心流程（只留接點）。
- 未新增/修改任何後端角色權限邏輯（ADOPTER 僅選單路由層）。
- 未實際發佈 rich menu（無真實憑證）。
- 未跑完整品質 Gate；新增/修改檔已通過 Python 語法檢查與 sync dry-run。
