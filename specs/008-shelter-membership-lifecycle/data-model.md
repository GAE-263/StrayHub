# Data Model: 收容所成員封存與權限管理版型改善

## OrganizationMembership

既有 `organization_memberships` 關聯使用者與收容所；本功能擴充其生命週期，不建立第二份成員資料。

### Fields

| Field | Type | Required | Description |
|---|---|---:|---|
| id | UUID | yes | Membership 技術識別，僅供 API／操作關聯使用 |
| organization_id | UUID | yes | 所屬收容所，所有查詢必須以此租戶範圍限制 |
| user_id | UUID | yes | 關聯的全平台 User |
| role | enum | yes | `SHELTER_ADMIN`、`STAFF`、`VOLUNTEER` |
| status | enum | yes | 既有狀態加上 `archived` |
| archived_from_status | enum/null | no | 封存前狀態，供安全恢復；非封存時為 null |
| archived_at | datetime/null | no | 封存時間，使用既有台灣收容所時間語意 |
| archived_by_user_id | UUID/null | no | 執行封存的操作者 |
| valid_from | datetime/null | no | 志工有效期間起點 |
| expires_at | datetime/null | no | 志工有效期間終點 |
| medical_care_access | boolean | yes | STAFF 醫療資料權限，非 STAFF 不提供控制 |

### Derived Membership View Fields

| Field | Type | Required | Description |
|---|---|---:|---|
| volunteer_authorization_status | enum/null | no | 由目前收容所 Membership 對應的最新 VolunteerAccessGrant 推導；`active`、`expired`、`revoked` 或 null，不另建資料副本 |

### Validation Rules

- `archived_from_status` 只有在 `status = archived` 時應有值。
- 封存不得刪除 `user_id`、照護回報關聯、稽核關聯或其他歷史欄位。
- 封存某一 Membership 不得改變同一 `user_id` 在其他 `organization_id` 的 Membership。
- 恢復 STAFF／SHELTER_ADMIN 時使用 `archived_from_status`；恢復 VOLUNTEER 時另檢查 `valid_from` 與 `expires_at`。
- 權限管理 API 的所有查詢與更新都必須同時限制 `organization_id` 與管理員授權。
- 一般 Membership 重新啟用前，若 `role = VOLUNTEER` 且最新授權為 `expired` 或 `revoked`，必須拒絕直接設為 `active`。
- 志工授權撤銷時 Membership 可維持 `disabled`；`volunteer_authorization_status = revoked` 只作為清單顯示與重新啟用判斷，不取代 Membership status。

### State Transitions

```text
invited / active / disabled / expired / revoked
                    │
                    ├── archive ──> archived
                    │                 │
                    └─────────────────┘
                              restore
                    └──> archived_from_status
```

實際恢復志工時，若有效期間已結束，結果為 `expired`；不得因恢復而繞過志工授權流程。

清單排序規則為志工區塊在前、工作人員區塊在後；工作人員內先 SHELTER_ADMIN 再 STAFF；各區內依 `active`、`disabled`、`expired`、`revoked` 排序。撤銷狀態若來自 VolunteerAccessGrant，顯示為「授權已撤銷」。

## Archived Membership View

非獨立資料表，而是以 `status = archived` 的 OrganizationMembership 加上受同一 organization scope 限制的 User projection 組成。

### Display Fields

- display_name：主要身份名稱，缺少時使用安全未命名提示。
- username：次要帳號識別。
- role：中文角色名稱與必要的原始狀態。
- status：已封存。
- archived_at：封存時間。
- archived_by：操作者顯示名稱，若可安全取得。
- restore_action：僅在授權與狀態條件允許時提供。

## Audit Events

沿用既有 AuditLog 資料模型，新增或標準化以下 action：

- `membership.archived`
- `membership.restored`

每筆事件至少保存 organization、actor user、target membership、時間、來源通道與狀態前後差異。
