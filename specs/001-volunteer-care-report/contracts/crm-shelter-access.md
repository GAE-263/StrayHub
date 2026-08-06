# CRM 與 Shelter 存取契約

## 目的

所有通道與服務都透過 CRM 邊界讀寫正式資料。每一個操作都必須以已驗證的 Actor Context 與 Shelter Scope 執行。

## 操作輸入

- 已驗證使用者識別與角色。
- 有效的 Shelter Membership／Authorization Scope。
- 目標資源識別或候選查詢條件。
- 操作類型：read、create、update、search、archive、photo access 或 draft／temporary media delete。
- 來源通道：web、LIFF、QR、worker 或管理後台。

## 強制規則

1. 不信任前端提交的 Shelter 識別、Animal 識別、Shelter Number、QR Token 或 Object Key。
2. 由 CRM 依 Actor Context 重新判定資源 Shelter 與角色能力。
3. 資源 Shelter 不在 Scope 時，回傳一致的無權限或無法存取結果，不洩漏資源存在、筆數、圖片或設定。
4. Shelter Number 只在授權 Shelter 範圍內搜尋；不同 Shelter 的相同編號不得互相衝突。
5. QR 解析必須同時驗證 QR Shelter、Actor Scope 與 Animal Shelter。
6. 所有跨 Shelter 操作都要有平台管理員授權與 Audit Record。
7. Timeline 是 CRM 資料的讀取檢視，不得成為獨立正式資料來源。
8. Volunteer 可有多個有效 Shelter Membership，但同一時間只能有一個 Active Shelter Context；正常切換 Shelter 不視為異常。Draft、Animal、QR Token、Reportable Scope 與 Active Shelter Context 不一致時，系統必須阻擋送出，且不能讓單筆回報同時歸屬多個 Shelter。不得使用 GPS、IP、裝置、時間重疊或地理距離推測服務地點。
9. Daily Reportable Scope 第一階段支援個別 Animal、Cage／Area 與指定 Volunteer，不包含完整班次排班。
10. Volunteer 可在建立後 24 小時內修改自己的回報內容、Photo 與 Note；正式 Care Report 不得 Hard Delete，只能由授權角色 Correction 或 Archive；Animal 綁定只能由 Shelter Administrator 或授權 Staff Member 更正，並保留 Audit Record。

## Database Access 規則

- FastAPI API 與 Background Worker 使用 SQLAlchemy 2.x `AsyncSession`，PostgreSQL Driver 使用 `asyncpg`。
- Pydantic Request／Response Model、SQLAlchemy Model 與 Domain／Application Layer 分離；不使用 SQLModel。
- 所有租戶資料查詢與寫入都必須經過受控 Repository，並強制套用 `Organization Scope`（對應 Shelter Scope）。
- Repository 不能接受呼叫端任意覆寫 Scope；Scope 必須由已驗證的 Actor Context 與有效 Membership 產生。
- 租戶隔離由 Repository、Composite Constraint、PostgreSQL Row-Level Security（RLS）、交易內 Organization Scope 與自動化隔離測試共同提供 Defense in Depth。Runtime Role 不得擁有資料表或具備 `BYPASSRLS`，租戶資料表必須使用 `FORCE ROW LEVEL SECURITY`。
- 一般 Request／Worker 只能由後端在交易內設定單一 `app.current_org_id`；只有重新驗證為 `PLATFORM_ADMIN` 的交易能設定 `app.platform_scope`，且同一交易必須留下 Audit Record。使用者輸入、Token、QR Code 與 Postback 不得直接設定 Database Scope；Worker 不得使用平台級 Scope。
- Database Scope Setter 固定由 Application Service 在開始 `AsyncSession` transaction 且完成 Actor／Session 驗證後呼叫；一般 scope 使用參數化 `set_config('app.current_org_id', :org_id, true)`，平台 scope 使用受控 `set_config('app.platform_scope', 'true', true)`。`is_local=true` 不得改成 session-level 設定；transaction 結束與 pooled connection 重用後都不得保留上一個 scope。
- 所有 Schema、資料表、Constraint、Index 與 Row-Level Security Policy 變更都必須透過 Alembic Migration；不得以手動資料庫操作作為唯一建置方式。

## 失敗結果

- 身分未綁定：導向綁定或求助，不建立匿名正式回報。
- 帳號或 Membership 停用：拒絕讀取與寫入。
- Shelter 停用：一般帳號拒絕登入與新資料建立。
- 資源不存在或未授權：使用不洩漏存在性的統一結果。
- 送出前重新驗證失敗：阻止寫入並保留 Draft。

## 驗證重點

- Organization／Shelter A、B 使用相同 Shelter Number 時可各自查詢。
- A 使用者使用 B 識別、網址、QR 或 Object Key 時不取得 B 資料。
- 後端直接收到偽造 Shelter 識別時仍依已驗證 Actor Scope 判定。
- 空 PostgreSQL 可由 Alembic 完整建立 Schema，且 migration 後的 Composite Constraint 與 PostgreSQL 防護可被測試驗證。
- API 與 Worker 的 AsyncSession 交易在 Scope 驗證與正式寫入之間不會改用其他 Organization Scope。
- 真實 PostgreSQL 測試直接驗證一般 Scope 不能跨租戶、`PLATFORM` Scope 可執行受控跨租戶操作、偽造 Request 不能設定 Database Scope，且 Runtime Role 無法繞過 RLS。
- 真實 PostgreSQL 測試直接驗證缺少 Scope 時預設拒絕、transaction 結束自動清除 Scope、pooled connection 不繼承前一個 Organization，以及 Worker 無法取得 `PLATFORM` Scope。
