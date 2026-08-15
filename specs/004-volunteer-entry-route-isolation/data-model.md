# 資料模型：志工角色導向入口與管理路由隔離

本功能不新增 CRM table、API entity 或正式前端資料副本。以下模型是 route 判斷與驗收所需的 runtime view；所有 Session、User、Membership、Active Shelter Context、Animal 與 Draft 仍以既有後端服務及 CRM 為唯一事實來源。

## EffectiveRole（有效角色）

### 值域

- `PLATFORM_ADMIN`
- `SHELTER_ADMIN`
- `STAFF`
- `VOLUNTEER`

### 推導規則

1. `user.platform_role` 為 `PLATFORM_ADMIN` 時，有效角色為 `PLATFORM_ADMIN`。
2. 其他使用者必須在目前 Active Shelter Context 找到 status 為 active 的 Membership，並以該 Membership role 為有效角色。
3. 找不到目前 context、Membership 不存在／停用或 organization id 不一致時，不得使用預設 `STAFF`；結果為 context／authorization failure。
4. 登入後第一次導向可使用後端 Login response 中已選定 organization 的 role；後續 reload、deep link 與 back 必須重新依 profile/context 推導。

### 不變條件

- pathname、query string、sessionStorage 與 UI state 不能產生或提升角色。
- 前端有效角色只決定可見入口；不能取代後端 API authorization。
- `VOLUNTEER` 不能通過 management route policy。

## AuthenticatedRouteContext（已驗證路由情境）

| 欄位 | 型別／值 | 來源與規則 |
| --- | --- | --- |
| `sessionState` | `authenticated` | 既有 access token 對應的 server-side Session 已通過 `/auth/me` 驗證 |
| `userId` | user id | `/auth/me`；只用於目前使用者 view，不由 client 建立 |
| `activeOrganizationId` | organization id | `/auth/active-shelter-context`；必須是非空且後端已驗證 |
| `effectiveRole` | `EffectiveRole` | 依平台角色或目前 context 的 active Membership 推導 |
| `profile` | current user + memberships | `/auth/me` 的既有回應；僅保留目前 render 所需資料 |
| `pathname` | current pathname | 只用於 route policy 與避免導向相同目的地，不作授權來源 |

### 驗證規則

- 缺少 access token：不建立此 view，結果為 `redirect-login`。
- `/auth/me` 或 Active Context 回應 401：清除既有 client auth cache，結果為 `redirect-login`。
- Active Context organization id 為空、Membership 不一致或 context response 表示需要選擇：結果為 `context-required`，不掛載受保護 children。
- 暫時 network／5xx error：結果為 `error`，保留安全重試與返回／重新登入操作。
- View 只存在於目前頁面生命週期，不持久化為新的 auth record。

## ProtectedRoutePolicy（受保護路由政策）

| `area` | Route patterns | 允許條件 | Role mismatch 結果 |
| --- | --- | --- | --- |
| `management` | `/`、`/animals`、`/animals/*`、`/reports`、`/reports/*`、`/ai-review`、`/settings/*`、`/shelters` | Session/context 有效且角色為 `PLATFORM_ADMIN`、`SHELTER_ADMIN` 或 `STAFF` | `VOLUNTEER` → `redirect-volunteer` |
| `volunteer` | `/animal-confirmation`、`/care-report` | Session/context 有效；頁面內的資料操作仍由後端 role/scope 判定 | 不新增管理角色反向 redirect |
| `public-auth` | `/login` | 不要求既有 Session；成功登入後依 selected organization role 決定目的地 | 不適用 |

### 管理 route normalization

- Query string、hash 與尾端斜線不改變 route area。
- `/settings/*` 的所有既有與未來巢狀頁面預設屬於 management。
- 動態 `animalId`／`reportId` 不參與角色判斷，也不能改變 policy。
- 未知 route 仍由既有 Next.js not-found 行為處理；本功能不建立全域公開錯誤 route。

## RouteAccessDecision（路由存取決策）

| 狀態 | 必要條件 | 可見內容 | 下一步 |
| --- | --- | --- | --- |
| `checking` | token/profile/context 尚在確認 | 安全且繁中 loading/status | 等待；不掛載 page children |
| `allow-management` | management policy 通過 | Management Shell 與 page children | 載入 organizations 與頁面資料 |
| `allow-volunteer` | volunteer policy 通過 | volunteer page children；不顯示管理 Shell | 載入動物／draft 等志工資料 |
| `redirect-login` | token 缺少或 Session 401 | 安全 redirect status | `replace('/login')` |
| `redirect-volunteer` | management route 的有效角色為 `VOLUNTEER` | 安全 redirect status；無管理內容 | `replace('/animal-confirmation')` |
| `context-required` | Session 有效但 Active Context 缺少／不一致 | 不含資料的繁中錯誤狀態 | 返回登入／context 選擇、重試或聯絡管理者 |
| `error` | network、5xx 或不可分類錯誤 | 不含受保護資料的繁中錯誤狀態 | 重試、返回或重新登入 |

### 狀態轉換

| From | Event | To |
| --- | --- | --- |
| `checking` | 無 token | `redirect-login` |
| `checking` | profile/context 401 | `redirect-login` |
| `checking` | context 缺少或 Membership 不一致 | `context-required` |
| `checking` | management + `VOLUNTEER` | `redirect-volunteer` |
| `checking` | management + management role | `allow-management` |
| `checking` | volunteer + valid context | `allow-volunteer` |
| `checking` | network／5xx | `error` |
| `error` | 使用者選擇重試 | `checking` |
| 任一 allow state | pathname、auth event 或 context 變更 | `checking` |

### Loop 防護

- Destination 與目前 pathname 相同時不得再次 redirect。
- Redirect state 不掛載 children，也不啟動頁面資料查詢。
- `context-required` 與 `error` 是終止狀態，不自動在 `/login`、`/` 與 `/animal-confirmation` 間來回。
- Browser back／reload 重新從 `checking` 開始，不能沿用先前 allow decision。

## ActiveDraftResumeView（active draft 恢復 view）

此 view 只在 volunteer boundary 通過後，由目前草稿與今日可回報動物資料組合；不新增持久化 entity。

| 欄位 | 來源 | 規則／用途 |
| --- | --- | --- |
| `draftId` | current draft | 只作既有草稿識別；後端仍重新驗證使用者與 context |
| `organizationId` | current draft | 必須等於 `AuthenticatedRouteContext.activeOrganizationId` |
| `animalId` | current draft | 用於與今日可回報動物名單比對 |
| `animalName` | `/v1/animals` match | 可辨識的動物名稱；沒有授權 match 時不顯示詳細資料 |
| `shelterNumber` | `/v1/animals` match | 可選的收容編號，用於避免同名動物混淆 |
| `currentStep` | current draft | 轉為台灣繁體中文進度文案，不直接把 wire value 當主要文案 |
| `expiresAt` | current draft | 必須晚於目前時間，否則不可恢復 |
| `status` | current draft | P0 只有 `active` 可恢復 |
| `resumeState` | derived | `available`、`unavailable` 或 `none` |

### 可恢復條件

`resumeState = available` 必須同時符合：

1. current draft 存在。
2. `status` 為 `active`。
3. `expiresAt` 尚未到期。
4. `organizationId` 等於目前 Active Shelter Context。
5. `animalId` 能在目前 `/v1/animals` 授權結果中找到且 `can_report` 為 true。

任一條件不符合時，不得載入草稿答案或動物詳細資訊。使用者只看到安全的 unavailable／聯絡管理者下一步。

### 使用者動作

- `continue`：前往既有 `/care-report`；該頁再次由後端取得目前草稿並驗證。
- `later`：只關閉本次頁面的提示，留在 `/animal-confirmation`；不修改 Draft 狀態。
- `retry`：重新取得 current draft 與今日動物名單；不得使用前一次失敗的資料冒充成功。

### P1 邊界

P0 沿用每位志工、每個 Active Shelter Context 最多一筆 active draft。多筆 active draft view、跨裝置同步與跨 context 選擇只有在後續規格明確修改既有 domain rule 後才可加入。

## RequestLifecycle（請求生命週期）

### Management route

1. Boundary 取得 profile + Active Context。
2. 推導 `RouteAccessDecision`。
3. 只有 `allow-management` 才取得 organizations 並掛載 Management Shell。
4. Shell 通過後才掛載 Dashboard／Animals／Reports／Settings 等 page children。

### Volunteer route

1. Boundary 取得 profile + Active Context。
2. 只有 `allow-volunteer` 才掛載 page children。
3. `/animal-confirmation` 再取得今日動物與 current draft。
4. `/care-report` 再取得既有 current draft。

### 不變條件

- `VOLUNTEER` 開啟 management route 時，management page request count 必須是 0。
- Role/context 尚未完成時，管理與志工業務 children 都不掛載。
- 任何前端 request 的 organization／resource id 都不能取代後端 scope 驗證。
