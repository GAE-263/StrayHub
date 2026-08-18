# Data Model: 平台管理員人數與替換治理

## User（既有資料）

`users` 仍是所有登入帳號的唯一來源；本 Feature 只明確定義平台管理員相關欄位的語意，不建立第二份帳號資料。

| Field | Type | Required | Description |
|---|---|---:|---|
| id | UUID | yes | 全平台 User 識別 |
| username | string/null | no | 登入帳號；建立平台管理員時必須唯一且非空 |
| display_name | string | yes | 管理頁顯示名稱 |
| password_hash | string/null | no | 本機／帳密登入憑證，沿用既有帳號安全規則 |
| status | enum | yes | `active` 才能登入並計入啟用中的平台管理員；`disabled` 不具有效平台權限 |
| platform_role | enum/null | no | `PLATFORM_ADMIN` 或 null；與 OrganizationMembership.role 分開判定 |

### User Validation Rules

- 啟用中的平台管理員必須同時滿足 `status = active` 與 `platform_role = PLATFORM_ADMIN`。
- 平台管理員不需要任何 OrganizationMembership；擁有 Membership 不會自動取得平台管理員權限。
- 降權清除 `platform_role`，但不得封存、刪除或移除 User、Membership、Session 或 AuditRecord。
- 停用帳號沿用既有 User status 規則；停用中的平台角色不計入啟用人數，也不可通過平台 scope 驗證。
- 具有任一 `OrganizationMembership.role = VOLUNTEER` 或任一 `VolunteerApplication` 紀錄的 User，不屬於平台管理員提升／替換候選；Membership 或申請歷史不限目前是否有效，至少涵蓋 active、expired、revoked、rejected、withdrawn、pending 等狀態。

## PlatformAdminPolicy（新增單例資料）

代表平台治理政策與並發治理異動的鎖定點。MVP 只保留一筆固定政策，不提供一般 UI 修改政策數值。

| Field | Type | Required | Description |
|---|---|---:|---|
| policy_key | string | yes | 固定為 `default`，唯一識別單例政策 |
| min_active_admins | integer | yes | 固定為 1；不得小於 1 |
| max_active_admins | integer | yes | 固定為 2；不得小於 min |
| version | integer | yes | 政策異動或 migration 版本 |
| updated_at | datetime | yes | 政策最後更新時間 |

### Policy Invariants

- 全平台只能存在一筆 `policy_key = default`。
- `1 <= min_active_admins <= max_active_admins = 2`。
- 每個平台管理員治理 mutation 必須在檢查與寫入前鎖定這筆政策資料。
- 政策資料列不是平台管理員帳號，不計入管理員人數，也不出現在管理員清單。

## PlatformAdminView（衍生回應）

由 User 與治理政策計算，不建立獨立帳號副本。

| Field | Type | Description |
|---|---|---|
| user_id | UUID | 目標 User |
| username | string | 帳號識別 |
| display_name | string | 主要顯示名稱 |
| user_status | enum | `active` 或 `disabled` 等既有帳號狀態 |
| platform_role | enum/null | 目前 `PLATFORM_ADMIN` 或 null |
| effective_status | enum | `active` 或 `disabled`，由 User status 與 platform_role 推導；降權帳號不屬於目前平台管理員清單 |
| can_enable | boolean | 依當前角色、帳號狀態與 max 計算 |
| can_disable | boolean | 依 min 下限與目標狀態計算 |
| can_demote | boolean | 依 min 下限與目標狀態計算 |

## AuditRecord（既有資料）

平台治理沿用 `audit_records`，`organization_id = null`、`resource_type = platform`；替換的成對事件共用 operation id。

### Actions

- `platform_admin.created`
- `platform_admin.promoted`
- `platform_admin.enabled`
- `platform_admin.disabled`
- `platform_admin.demoted`
- `platform_admin.replaced`
- `platform_admin.access_denied`

每筆事件保存 actor、時間、target user、before／after、source channel、result、reason（拒絕時）與 operation id。

## State Transitions

```text
non-admin active user ── promote ──> active platform admin
active platform admin ── disable ──> disabled platform admin
disabled platform admin ── enable ──> active platform admin
active platform admin ── demote ──> active non-admin user
active admin + eligible user ── replace ──> new active admin + old non-admin
```

### Transition Rules

- `promote`／`create` 只有在啟用人數小於 max 時允許。
- `enable` 只有在目標 User active 且啟用後不超過 max 時允許。
- `disable`／`demote` 只有在結果仍不低於 min 時允許。
- `replace` 必須先驗證 replacement user active、尚未具備平台管理員角色且不是 outgoing user，再在同一交易完成新舊轉換。

### Volunteer-history Verification Fixture

- 候選清單、promote 與 replacement 的整合測試必須使用真實 `PlatformAdminRepository`，不可只設定 fake repository 的布林欄位。
- Standard Local Fixture 固定至少包含 2 位平台管理員、1 個無志工歷史的可提升 User、3 位分別具有 active／expired／revoked Membership 歷史的 active Users，以及 3 位分別具有 rejected／withdrawn／pending VolunteerApplication 歷史的 active Users。
- T054 維持候選清單查詢覆蓋；T055 驗證真實 repository 的 promote／replacement 拒絕；T056 建立 revoked Membership 並同步 quickstart，不重複宣稱 replacement backend coverage。
- 測試資料使用 PostgreSQL transaction 建立並 rollback；不得污染 local seed 或其他測試案例。
- 任何驗證失敗或寫入失敗都不得留下部分替換結果。
- 既有 OrganizationMembership 的狀態與角色不因平台管理員異動而自動改變。
- 降權後的 User 透過平台 AuditRecord 查詢歷史，不以額外的「已降權平台角色」欄位製造第二套目前狀態。
## Account eligibility invariants

- `username` is required and unique according to the existing User-account rules.
- A User entering the platform-admin set must have `status = active`.
- A promotion or replacement target must have `platform_role IS NULL` (or any non-platform-admin value); an existing platform administrator cannot be selected again as a target.
- A newly created account's temporary password is validated by the existing password policy and stored only through the existing password-hashing path.

## Migration invariant

- After migration, a database with existing User records must have between one and two active platform administrators. Counts outside this range fail migration with an actionable repair error.
- An empty database may complete migration before bootstrap; bootstrap must establish one active platform administrator before service startup.
