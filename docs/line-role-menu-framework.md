# StrayHub LINE 角色選單與公開流程

> 狀態：整合功能已完成；production 預設關閉，須通過真實 LINE smoke 才可啟用。

## 公開入口

任何加入官方帳號、尚未取得 shelter 身分的使用者只看到兩個入口：

| 選項 | postback | 行為 |
| --- | --- | --- |
| 志工服務 | `action=start_volunteer_application` | 開啟公開志工申請 LIFF；核准前不授予 shelter 權限 |
| 領養流程 | `action=start_adoption_matching&flow=adoption` | 進入正式 Bot 對話，不依賴 adopter mock page |

公開選單沒有工作人員入口。工作人員選單只會在後端確認 active
`STAFF`／`SHELTER_ADMIN` membership 並建立目前收容所 context 後綁定。

領養流程先選地區與收容所，再選「心有所屬」或「推薦我」。兩條路徑都以規則式
matching 為必要基線；AI 是可選增強，停用或失敗時仍可完成。流程支援返回、取消、
續接，送出後建立具 shelter scope 的 inquiry。送出 inquiry 不會自動綁 adopter menu；
完成領養後的 adopter lifecycle 不在本輪範圍。

## 選單狀態

```text
未綁定／未知角色／平台管理員／未選收容所的 staff
  └─ default（志工服務、領養流程）

active VOLUNTEER membership
  └─ volunteer（散步回報、志工報到、返回主選單）

active STAFF 或 SHELTER_ADMIN membership + server-side shelter context
  └─ staff（新增動物、更新健康、動物清單、變更狀態）

ADOPTER（僅 routing framework，無自動 lifecycle）
  └─ adopter（我想領養、返回主選單）
```

多收容所工作人員不能由 LINE UID 自動猜測收容所，必須先透過身分交換明確選定
membership。`PLATFORM_ADMIN` 是平台權限，不等同任何收容所工作人員。

「返回主選單」只把該 LINE UID link 回 default Rich Menu，不會刪除、降級或改寫
membership、grant、session 或 shelter context；權限仍以後端為準。再次進入受保護功能時，
後端會重新驗證身分與目前收容所。

## 設定與安全失敗

四份 menu 定義在 `infra/local/line-rich-menu-{default,volunteer,adopter,staff}.yaml`，
以 `scripts/sync_line_role_menus.py` 驗證或發佈。角色 ID 由下列環境變數提供：

```dotenv
LINE_RICH_MENU_DEFAULT_ID=
LINE_RICH_MENU_VOLUNTEER_ID=
LINE_RICH_MENU_ADOPTER_ID=
LINE_RICH_MENU_STAFF_ID=
```

全部缺少或只缺目標角色 ID 時，routing 是 no-op；不影響 webhook、身分綁定、核准或
資料 transaction。LINE Messaging API timeout、5xx 或 reply token 失效會記錄警告並安全
失敗，不會回滾已提交的 CRM mutation。Webhook signature 驗證及 duplicate-event
idempotency 不可關閉。

Production 另受 `LINE_ROLE_MENU_FEATURES_ENABLED` fail-closed gate 保護，預設 `false`。
只有全部必要 menu ID、公開 HTTPS origin、staff LIFF ID、LINE credential，以及格式為
`verified-YYYYMMDD-<40-char-tested-git-sha>` 的真實 smoke evidence 都通過 preflight，才可對
該已測 commit 設為 `true`。目前不要求 adopter menu ID，因為沒有完成領養 lifecycle。

## 權限與資料邊界

- LINE user ID 只是外部 identity，必須映射到內部 user/membership。
- 公開志工申請只會建立 pending application；管理員核准後才建立 active grant。
- 公開領養目錄使用專用 read-only RLS scope，只可讀 active shelter 的 adoptable animals。
- Staff LIFF/API 使用 server-side active organization；不信任 payload 中的 shelter/actor。
- 志工到期只撤銷該 shelter 的 membership/grant/menu context，不得影響其他 shelter。

實機設定見 [line-account-setup.md](line-account-setup.md)，staff contract 見
[staff-animal-line-input.md](staff-animal-line-input.md)，production gate 見
[deployment/production-config-contract.md](deployment/production-config-contract.md)。
