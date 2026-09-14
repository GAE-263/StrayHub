# StrayHub LINE 角色選單與公開流程

> 狀態：整合功能已完成；production 預設關閉，須通過真實 LINE smoke 才可啟用。

## 公開入口

任何加入官方帳號、尚未取得 shelter 身分的使用者只看到兩個入口：

| 選項 | postback | 行為 |
| --- | --- | --- |
| 志工服務 | `action=start_volunteer_application` | 開啟公開志工申請 LIFF；核准前不授予 shelter 權限 |
| 領養流程 | `action=open_adoption_hub` | 切換到領養／毛孩日記選單，再選擇各自流程 |

Adoption Hub 的兩個入口為 `action=start_adoption_matching&flow=adoption` 與
`action=start_growth_diary&flow=growth_diary`。

公開選單沒有工作人員入口。收容所工作人員預設使用 Google 驗證的 Web 管理介面；LINE
staff 選單是獨立且預設關閉的選配能力，本次延後。只有 `LINE_STAFF_MENU_ENABLED=true`，且後端確認
active `STAFF`／`SHELTER_ADMIN` membership 與目前收容所 context 後，才可綁定 staff 選單。

領養流程先選地區與收容所，再選「心有所屬」或「推薦我」。兩條路徑都以規則式
matching 為必要基線；AI 是可選增強，停用或失敗時仍可完成。流程支援返回、取消、
續接，送出後建立具 shelter scope 的 inquiry。送出 inquiry 不會自動綁 adopter menu；
完成領養後的 adopter lifecycle 不在本輪範圍。

## 選單狀態

```text
未綁定／未知角色／平台管理員／未選收容所的 staff
  └─ default（志工服務、領養流程）

active VOLUNTEER membership
  └─ volunteer（散步回報、返回主選單）

active STAFF 或 SHELTER_ADMIN membership + server-side shelter context
  ├─ 預設：Google 驗證的 Web 管理介面
  └─ LINE staff 選配開啟：staff（新增動物、更新健康、動物清單、變更狀態）

ADOPTER（僅 routing framework，無自動 lifecycle）
  └─ adopter（我想領養、返回主選單）
```

多收容所工作人員不能由 LINE UID 自動猜測收容所，必須先透過身分交換明確選定
membership。`PLATFORM_ADMIN` 是平台權限，不等同任何收容所工作人員。

「返回主選單」只把該 LINE UID link 回 default Rich Menu，不會刪除、降級或改寫
membership、grant、session 或 shelter context；權限仍以後端為準。再次進入受保護功能時，
後端會重新驗證身分與目前收容所。

## 設定與安全失敗

五份 menu 定義在 `infra/local/line-rich-menu-{default,volunteer,adopter,staff,adoption-hub}.yaml`，
以 `scripts/sync_line_role_menus.py` 驗證或發佈。角色 ID 由下列環境變數提供：

```dotenv
LINE_RICH_MENU_DEFAULT_ID=
LINE_RICH_MENU_VOLUNTEER_ID=
LINE_RICH_MENU_ADOPTER_ID=
LINE_RICH_MENU_STAFF_ID=
LINE_RICH_MENU_ADOPTION_HUB_ID=
LINE_STAFF_MENU_ENABLED=false
```

本機或功能未啟用時，缺目標角色 ID 的 routing 是 no-op；非本機啟用時必要 ID
缺漏會由 settings/preflight 拒絕（含 API adoption hub）。不影響身分綁定、核准或
資料 transaction。LINE Messaging API timeout、5xx 或 reply token 失效會記錄警告並安全
失敗，不會回滾已提交的 CRM mutation。Webhook signature 驗證及 duplicate-event
idempotency 不可關閉。

Production 另受 `LINE_ROLE_MENU_FEATURES_ENABLED` fail-closed gate 保護，預設 `false`。
一般領養者／志工啟用只要求其必要 menu ID、公開 HTTPS origin、LINE credential 與受保護
的真實 smoke evidence。Staff ID、Staff LIFF 與 staff smoke 只有在獨立設定
`LINE_STAFF_MENU_ENABLED=true` 時才成為必要條件；不能把該開關當成 staff 授權。
目前不要求 adopter menu ID，因為沒有完成領養 lifecycle。

資源發布與啟用必須分開；`--apply` 不再刪舊選單或自動設定 default／回寫 env。
受限真人 smoke 與後續啟用步驟見 [安全發布計畫](line-rich-menu-safe-publication.md)。

## 權限與資料邊界

- LINE user ID 只是外部 identity，必須映射到內部 user/membership。
- 公開志工申請只會建立 pending application；管理員核准後才建立 active grant。
- 公開領養目錄使用專用 read-only RLS scope，只可讀 active shelter 的 adoptable animals。
- Staff LIFF/API 使用 server-side active organization；不信任 payload 中的 shelter/actor。
- Staff 帳號與權限治理以 [Web 人員存取治理](staff-access-governance.md) 為準；LINE 綁定
  只是一個外部入口，不能建立或提升 membership。
- 志工到期只撤銷該 shelter 的 membership/grant/menu context，不得影響其他 shelter。

實機設定見 [line-account-setup.md](line-account-setup.md)，staff contract 見
[staff-animal-line-input.md](staff-animal-line-input.md)，production gate 見
[deployment/production-config-contract.md](deployment/production-config-contract.md)。


## 志工選單更新（2026-09-06）

線上報到尚未開放，志工選單已移除報到入口。舊選單的 `volunteer_checkin`
仍回覆請向現場工作人員確認報到方式，不建立報到紀錄。

可用 `node scripts/rich_menu_images/render.mjs volunteer` 只重繪志工圖片。
本次僅更新程式、定義與圖片，尚未發布至 LINE。部署時先套用
`0048_line_current_flow` migration，再載入新版 API；依既有選單同步流程發布
新定義與圖片，更新 `LINE_RICH_MENU_VOLUNTEER_ID` 並確認重新進入志工服務後
兩個按鈕的點擊範圍正確。
