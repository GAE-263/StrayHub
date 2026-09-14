# 收容所工作人員帳號與權限治理

本文供維運與工程交接使用，集中記錄工作人員入口、加入申請及授權責任。

## 決策

收容所管理員與工作人員的正式預設入口是 Google 驗證的 Web 管理介面。LINE Rich Menu
不是建立 staff 身分、核准權限或管理組織的必要入口；Staff LINE 功能屬選配，production
預設 `LINE_STAFF_MENU_ENABLED=false`。本次工作人員只使用 Google 登入 Web 後台；
先上線一般使用者領養、毛孩日記與志工功能，Staff LINE 延後，不列入本次發布驗收條件。

## 建立與授權流程

```text
一次性平台管理員 bootstrap
  → 平台管理員建立收容所與首位 SHELTER_ADMIN
  → 人員以 Google 帳號登入／連結 StrayHub 帳號
  → 人員向指定收容所提出加入申請
  → 該收容所 SHELTER_ADMIN 在自身 organization scope 內審核並指定核准角色
  → 核准後建立該 organization 的 active membership
```

- 平台管理員 bootstrap 只用於建立最初的平台治理身分，不應成為日常 staff 建立流程。
- 平台管理員可建立收容所及其首位 `SHELTER_ADMIN`，作為 tenant 的第一位權限管理者。
- 後續人員透過既有 Google 帳號流程建立／連結內部帳號，自行向指定收容所申請加入，
  由該收容所管理員核准。申請送出或 Google 登入成功都不會直接授予 staff 權限。
- `SHELTER_ADMIN` 只能審核與管理目前 server-side organization context 內的人員。
- `STAFF` 不能核准其他人、提升自己或跨收容所授權。
- 平台管理員保留平台治理與例外復原能力，但不應代替收容所日常人員管理。

現有 organization 建立流程也支援由平台管理員產生首位管理員的臨時帳密；該帳號可在
登入後依既有安全流程連結 Google。臨時帳密不得透過 LINE、URL、Git 或一般日誌傳遞。

## 安全邊界

實作接線：`/v1/auth/join-applications` 建立申請；收容所的 application decision API 由管理員核准並指定 `STAFF`／`SHELTER_ADMIN`。一般申請者不能自行選擇角色取得權限。

- Google 身分只證明外部登入者；實際權限仍來自 server-side `User`、
  `OrganizationMembership`、session active organization 與 PostgreSQL RLS。
- client 提供的 organization、role 或 email 不可直接授權。
- 同一使用者在不同收容所的 membership 分別管理；核准 A 不得授權 B。
- 停用、封存、角色變更與管理員上限沿用既有 transaction、audit 與 optimistic version
  檢查，不以 LINE 綁定狀態取代。
- LINE user ID／Rich Menu 綁定僅是外部互動入口，不建立、延長或提升 staff membership。

## Staff LINE 選配能力

如未來需要工作人員從 LINE 進入管理功能，必須另行完成下列條件：

1. 明確設定 `LINE_STAFF_MENU_ENABLED=true`，且一般 role-menu global/test gate 已啟用。
2. 提供已回讀驗證的 `LINE_RICH_MENU_STAFF_ID` 與 HTTPS `LINE_STAFF_LIFF_ID`。
3. 完成 Staff LINE 真人 smoke evidence；一般領養者與志工案例不能替代。
4. Webhook 仍須驗證 LINE 簽章，並在 server side 驗證 active `STAFF`／
   `SHELTER_ADMIN` membership 與目前 organization context。

當 `LINE_STAFF_MENU_ENABLED=false` 時，即使先行放入 staff ID／LIFF，API 與 Legacy Worker
也不會路由 staff 選單；staff postback fail closed。這不影響 Google Web 管理入口。

## 操作責任

| 操作 | 主要責任角色 | 範圍 |
| --- | --- | --- |
| 建立／替換平台管理員 | 受控 production operator | 平台；依 bootstrap／replacement runbook |
| 建立收容所與首位管理員 | `PLATFORM_ADMIN` | 指定新收容所 |
| 審核 STAFF／SHELTER_ADMIN 加入申請 | 該收容所 `SHELTER_ADMIN` | 僅目前收容所 |
| 日常 staff 停用、封存、角色調整 | 該收容所 `SHELTER_ADMIN` | 僅目前收容所 |
| 啟用 Staff LINE 選配能力 | Release + LINE 管理者另行批准 | 設定、資源、smoke、部署分開審核 |

平台管理員 bootstrap 操作見
[Production Platform Administrator Bootstrap](deployment/platform-admin-bootstrap.md)；Google
帳號與 LINE 帳號是不同 identity plane，不應互相推導或自動合併。
