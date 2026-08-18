# Data Model: 收容所管理員人數與權限調整確認

本功能不新增資料表或欄位；使用既有 `Organization`、`User`、`OrganizationMembership` 與 `AuditRecord`。管理員人數是依租戶與 Membership 狀態即時計算的 invariant。

## OrganizationMembership

### Relevant fields

| Field | Type | Required | Feature meaning |
|---|---|---:|---|
| `id` | UUID | yes | API 與稽核關聯識別，僅供操作關聯，不作為主要 UI 名稱 |
| `organization_id` | UUID | yes | 收容所租戶範圍；所有計數、查詢與異動都必須以此限制 |
| `user_id` | UUID | yes | 全平台 User 關聯；不因單一收容所異動而刪除 |
| `role` | string | yes | `SHELTER_ADMIN`、`STAFF`、`VOLUNTEER` |
| `status` | string | yes | `active`、`disabled`、`invited`、`expired`、`archived` 等既有狀態語意 |
| `medical_care_access` | boolean | yes | 只對 `STAFF` 有效；不改變管理員計數 |
| `archived_from_status` | string/null | no | 恢復封存 Membership 時使用既有狀態 |
| `access_version` | integer | yes | Modal 確認後的樂觀並發版本；每次成功 Membership mutation 遞增 |
| `volunteer_authorization_status` | derived | no | 由既有志工授權資料推導，不取代 Membership status |

## Active shelter-admin invariant

對每個 `organization_id`：

```text
active_shelter_admin_count
  = count(OrganizationMembership
          where organization_id = target
            and role = 'SHELTER_ADMIN'
            and status = 'active')

1 <= active_shelter_admin_count <= 2（每次成功 mutation 完成後）
```

- 計數只針對單一收容所；平台管理員的 `User.platform_role` 不納入。
- `disabled`、`expired` 與 `archived` Membership 不計入，但不能被當成沒有歷史的 User。
- 任何 mutation 必須計算最終 projection 的 count，而非只檢查目前 count。
- 同一收容所的 mutation 先鎖定 `Organization` row，鎖定期間重新讀取資料並驗證；不同收容所可並行處理。
- 這是「成功 mutation 完成後」的 invariant，不把既有歷史異常資料假裝成有效狀態。既有資料若已低於一位，僅允許增加管理員的受控修復操作；會再降低有效管理能力的操作仍拒絕。既有資料若已高於兩位，禁止再增加，後續修復由受控資料修正處理。

## Permission change projection

Service 在寫入前建立單次候選結果：

| Value | Description |
|---|---|
| `membership_id` | 目標 Membership |
| `before` | role、status、medical care access、volunteer authorization status |
| `after` | 本次請求驗證後的完整結果 |
| `admin_count_before` | 交易內鎖定後的最新啟用中管理員數量 |
| `admin_count_after` | 套用 after projection 後的數量 |
| `operation` | `created`、`updated`、`archived`、`restored` |
| `validation_result` | `success` 或 `denied`；拒絕時包含安全 domain code |

驗證順序：操作者與 organization scope → 目標 Membership 最新狀態 → role／status／志工授權規則 → admin count bounds → 套用欄位與 Audit。任何失敗都不得套用部分 after。

更新、封存與恢復的請求必須包含目標目前的 `access_version`。鎖定 Organization 後重新讀取版本；版本不符時回傳 `membership_state_changed`，不得套用 after，也不得遞增版本。成功套用後以原子方式遞增 `access_version`，讓 Modal 開啟後的舊資料不能覆寫較新的權限異動。

## State transitions

```text
active SHELTER_ADMIN ── disable / demote / archive ──> non-active or non-admin
       │                                                  │
       │ if count_after < 1: reject                       │
       │                                                  │
active STAFF ── promote ──> active SHELTER_ADMIN          │
disabled SHELTER_ADMIN ── re-enable ──> active admin      │
archived SHELTER_ADMIN ── restore ──> archived_from_status│
       │ if count_after > 2: reject                       │
```

角色轉換至 `VOLUNTEER` 仍須走既有志工授權流程；志工 `expired`／`revoked` 不得由一般重新啟用繞過授權。

## AuditRecord

沿用既有 `audit_records`，`organization_id` 為目前收容所，`resource_type = organization_membership`。

成功事件至少保存 actor、organization、target、operation、before／after、source channel 與 `result = success`。拒絕事件至少保存相同範圍識別、action、`result = denied`、`reason` domain code 與可安全保存的 before 狀態；不得在 reason 或 response 洩漏其他收容所資料。

## UI-only entities

`PermissionChangeConfirmation` 與 `PermissionChangeToast` 是暫存的 UI state，不寫入資料庫：

- Confirmation：target identity、operation label、before／after labels、admin count before／after、confirm／cancel state。
- Toast：成功動作、target display name／username、`role=status`、左下角位置；不得攜帶密碼、醫療內容或 UUID 作為唯一身份。
