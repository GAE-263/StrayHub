# Data Model：志工角色導向入口與管理路由隔離

本功能不新增 CRM 資料表。下列模型分為「既有持久化 entity」與「前端 runtime view/state」。正式授權只來自既有 CRM entity；runtime state 不得成為角色、Membership、期限或 organization scope 的事實來源。

## 1. 既有持久化 entities

### ShelterEntryReference（由 005 提供）

收容所專屬 LIFF URL／QR Code 的 opaque reference。

| 欄位 | 用途 | 004 規則 |
| --- | --- | --- |
| `id` | reference identity | resolver 的最小輸出之一；不回 client |
| `organization_id` | 候選收容所 | 只作 exchange 的候選 scope |
| `token_digest` | raw reference digest | raw reference 不落庫、不寫 log |
| `purpose` | 使用目的 | 必須符合 volunteer entry purpose |
| `status` | active/revoked | 只有 active 可解析 |
| rotation metadata | 發行／撤銷／輪替 | 004 只消費，不管理 lifecycle |

**驗證規則**：

- 只透過 005 的 fixed-purpose resolver 解析。
- resolver 只回 `reference_id + organization_id`，不得回 Membership、user 或內部設定。
- reference 無效、撤銷、purpose 不符或 organization 停用時不得建立 Session/context。
- reference 被轉傳不授權；同一 reference 對不同 LINE identity 必須分別驗證。

### LineUserBinding

已驗證 LINE user id 與 StrayHub User 的綁定。

| 欄位 | 用途 | 004 規則 |
| --- | --- | --- |
| `line_user_id` | LINE verifier 解析結果 | 不信任 client profile/sub claim |
| `user_id` | CRM User | 必須指向 active User |
| `status` | binding 狀態 | 只有 active binding 可 exchange |

004 不建立或修復 Binding；缺少/停用時回安全錯誤，由既有報名/綁定流程處理。

### User

| 欄位 | 用途 | 驗證 |
| --- | --- | --- |
| `id` | Membership/Session owner | 必須與 Binding 一致 |
| `status` | active/disabled | 只有 active 可建立 Session |
| `platform_role` | 平台角色 | route boundary 用於 local 管理流程；正式 volunteer entry 不用它繞過 Membership |

### Organization

| 欄位 | 用途 | 驗證 |
| --- | --- | --- |
| `id` | exact tenant scope | 必須等於 resolver organization |
| `name` | volunteer route 顯示名稱 | context 通過後才可顯示 |
| `code` | local/diagnostic label | 不授權 |
| `status` | active/suspended 等 | 只有 active 可 exchange/讀取資料 |

### OrganizationMembership（由 005 擴充）

| 欄位 | 用途 | 004 驗證 |
| --- | --- | --- |
| `id` | Membership identity | 與 active Grant 關聯 |
| `organization_id` | tenant | 必須等於 resolver organization |
| `user_id` | member | 必須等於 Binding User |
| `role` | organization role | 正式 volunteer entry 必須為 `VOLUNTEER` |
| `status` | active/revoked/expired/disabled | 必須為 active |
| `valid_from` | 授權開始 | `valid_from <= database_now` |
| `expires_at` | 授權到期 | `database_now < expires_at` |
| `access_version` | lifecycle version | 由 005 mutation/cleanup 管理；004 只讀 |

**Effective predicate**：

```text
user.status == active
AND organization.status == active
AND membership.user_id == bound_user.id
AND membership.organization_id == resolved_organization.id
AND membership.role == VOLUNTEER
AND membership.status == active
AND membership.valid_from <= database_now
AND database_now < membership.expires_at
AND matching active VolunteerAccessGrant exists for the same interval
```

pending/rejected Application 不會形成有效 Membership；future、expired、revoked、disabled 或缺少 Grant 全部拒絕。

### VolunteerAccessGrant（由 005 提供）

| 欄位 | 用途 | 004 驗證 |
| --- | --- | --- |
| `membership_id` | 對應 Membership | 必須等於 exact Membership |
| `organization_id` | tenant | 必須等於 resolver organization |
| `status` | active/expired/revoked | 必須為 active |
| `valid_from` | grant start | `valid_from <= database_now` |
| `expires_at` | grant end | `database_now < expires_at` |
| `version` | concurrency | 由 005 管理；exchange lock 只穩定 commit ordering |

### SessionRecord

既有 server-side Session，也是 Active Shelter Context 的持久化載體。

| 欄位 | 用途 | 004 寫入規則 |
| --- | --- | --- |
| `id` | Session identity | exchange transaction 內產生 |
| `user_id` | authenticated user | Binding User |
| `active_organization_id` | Active Shelter Context | 必須直接寫入 resolver organization，不可先為 null 再切換 |
| `status` | active/revoked/expired | 新 exchange 為 active |
| `expires_at` | Session lifetime | 沿用既有 refresh TTL |

### RefreshTokenRecord

| 欄位 | 用途 | 004 寫入規則 |
| --- | --- | --- |
| `session_id` | 所屬 Session | 與新 Session 同 transaction |
| `token_digest` | refresh token digest | raw token 只回 client |
| `family_id` | rotation family | 沿用既有 SessionService |
| `status` | active/rotated/revoked | 新 exchange 為 active |
| `expires_at` | refresh expiry | 沿用既有 TTL |

### 原子關係與 lock ordering

```text
ShelterEntryReference --resolve--> Organization
LINE raw ID token --verify--> LineUserBinding --> User
User + Organization --> OrganizationMembership --> VolunteerAccessGrant
有效且鎖定的 Membership/Grant --> SessionRecord(active_organization_id)
SessionRecord --> RefreshTokenRecord
```

固定順序：

1. resolve reference，取得單一 organization 並設定 organization RLS scope；
2. verify LINE identity，讀 Binding/User；
3. 驗證 Organization active；
4. `FOR UPDATE`（或等價穩定 lock）取得 exact Membership 與 active Grant；
5. 以 database time 重做 effective predicate；
6. insert SessionRecord（含 context）；
7. insert RefreshTokenRecord；
8. commit 後才回 AuthResponse。

任一步驟失敗：transaction rollback，新增 SessionRecord=0、RefreshTokenRecord=0、Active Shelter Context=0；不得更新 Membership/Grant/Application。

## 2. Runtime view/state

### LiffEntryBootstrap

正式 `/volunteer-entry` 單次 bootstrap input/state。

| 欄位 | 型別 | 來源／規則 |
| --- | --- | --- |
| `liffId` | string | server runtime `LIFF_ID`；public app identifier，不是 secret |
| `entryReference` | string | URL `entry`；非空；只送 exchange，不解碼 |
| `idToken` | string/null | `liff.getIDToken()` raw result；不得從 query 取得 |
| `phase` | enum | `initializing`、`logging-in`、`exchanging`、`redirecting`、`error` |
| `errorKind` | enum/null | entry、identity、access、dependency、configuration |

**不變條件**：`idToken` 與 `entryReference` 不出現在 UI、analytics、console、error description 或 permanent URL；exchange 成功前不掛載 protected volunteer children。

### AuthenticatedRouteContext

| 欄位 | 型別 | 來源 |
| --- | --- | --- |
| `profile` | CurrentUser | `GET /v1/auth/me` |
| `organizationId` | UUID | `GET /v1/auth/active-shelter-context` |
| `organizationName` | string/null | role/context 通過後由 scoped organization list 對應 |
| `effectiveRole` | EffectiveRole/null | profile + active context 純函式推導 |
| `sessionSource` | `local`/`liff` | client workflow hint；不授權 |

### EffectiveRole

```text
PLATFORM_ADMIN | SHELTER_ADMIN | STAFF | VOLUNTEER
```

推導規則：

1. active profile 的 `platform_role == PLATFORM_ADMIN` → `PLATFORM_ADMIN`；
2. 否則找 `membership.organization_id == activeContext.organization_id`；
3. matching Membership 必須是 server response 中 active；
4. 找不到 matching Membership → 不產生 fallback role，進入安全 context/access state。

前端 role 只決定可見 route；後端 endpoint 仍可施加更窄權限。

### ProtectedRoutePolicy

| `area` | 允許角色 | 通過前可發出的業務 request |
| --- | --- | --- |
| `management` | STAFF、SHELTER_ADMIN、PLATFORM_ADMIN | 0；只允許 profile/context |
| `volunteer` | VOLUNTEER；既有管理角色不新增反向限制 | 0；只允許 profile/context |

`(management)` route group 自動涵蓋所有 child route，不使用易漏的 pathname allowlist。

### RouteAccessDecision

```text
checking
allow-management
allow-volunteer
redirect-volunteer
redirect-login
context-required
access-unavailable
temporary-error
liff-recovery
liff-reentry-required
```

| Decision | Children | Navigation／操作 |
| --- | --- | --- |
| `checking` | 不掛載 | 顯示 polite status |
| `allow-management` | 掛載 management shell + child | 之後才讀 organizations/page data |
| `allow-volunteer` | 掛載 volunteer child | 之後才讀 shelter/animals/draft |
| `redirect-volunteer` | 不掛載 | `replace('/animal-confirmation')` |
| `redirect-login` | 不掛載 | clear auth，`replace('/login')` |
| `context-required` | 不掛載 | 重試／返回／聯絡管理者 |
| `access-unavailable` | 不掛載 | 等待核准／重新報名／聯絡管理者 |
| `temporary-error` | 不掛載 | 重試／返回，不顯示 stale data |
| `liff-recovery` | 不掛載 | 同一 epoch exchange 一次 |
| `liff-reentry-required` | 不掛載 | 重新進入／回到 LINE；不再自動 exchange |

### LiffRecoveryEpoch

| 欄位 | 型別 | 規則 |
| --- | --- | --- |
| `epochId` | monotonically increasing integer | 第一個 protected 401 建立 |
| `exchangeAttempts` | 0/1 | 同一 epoch 最大 1 |
| `inFlight` | Promise/null | 並行 401 共用 |
| `entryReference` | string/null | 來自同 session 的 transient hint |
| `originalPath` | safe volunteer pathname | 只允許 volunteer route；不保存 management deep link |
| `state` | idle/recovering/recovered/terminal | terminal 不再自動重試 |

**狀態轉移**：

```text
idle --first protected 401--> recovering(attempt=1)
recovering --exchange success--> recovered --profile/context recheck--> idle
recovering --token/ref/exchange failure--> terminal
recovered --same recovery cycle receives 401--> terminal
terminal --user taps re-enter--> full /volunteer-entry bootstrap
terminal --user taps back to LINE--> close/back action
```

Mutation request 在 401 後不自動 replay；保留可恢復 client input，要求使用者在新 Session 下明確重試。

### ActiveDraftResumeView

| 欄位 | 來源 | 規則 |
| --- | --- | --- |
| `draftId` | current draft response | 不放 URL、不用 client id 改 scope |
| `organizationId` | draft/context | 必須與 Active Context 一致 |
| `animalId` | draft | animal 必須仍在今日可回報清單 |
| `animalName` | scoped animals response | context 通過後顯示 |
| `shelterNumber` | scoped animals response | 可為 null |
| `progressLabel` | draft step 的繁中映射 | 不改 Draft state |
| `canResume` | derived boolean | active、未過期、同 context、animal 可回報 |

**操作**：

- `continue`：前往 `/care-report`，由該頁重新讀取 current draft。
- `later`：只關閉本次 prompt，留在 `/animal-confirmation`。
- unavailable：不顯示答案或其他 tenant 資料，提供重試／聯絡管理者。

## 3. Context 與 stale data 規則

- organization label、animals、draft、report form data 必須由同一已驗證 context cycle 產生。
- pathname、entry reference、QR、animal id、shelter number、sessionStorage organization id 不得改變後端 scope。
- context switch/recovery 開始時先卸載或遮蔽前一 context 的 protected children；新 context 全部驗證成功後才顯示新資料。
- management context switch 失敗時保留後端仍確認有效的舊 context/view；不得把部分新 context response 合併進舊 view。
- Membership 到期/撤銷後，Draft/Report/Media 保留；request-time access 成功率為 0。

## 4. 資料模型完成條件

- 新資料表與 migration 數量為 0。
- `LiffExchangeRequest` 只新增 `shelter_entry_reference`。
- 所有 exchange 失敗案例新增 Session/Refresh/context 數量為 0。
- 成功 exchange 的 Session 與 Active Context 在同一 commit 可見。
- transient client state 不含可替代 server authorization 的 role/status/expiry。
- ORG-A entry + ORG-B-only Membership 不得建立任一 organization context。
