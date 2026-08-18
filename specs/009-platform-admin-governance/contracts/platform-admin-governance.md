# Platform Admin Governance Contract

## Authorization Boundary

所有 `/v1/platform/administrators` route 都必須重新驗證目前 User 為啟用中的 `PLATFORM_ADMIN`。不要求 Active Shelter Context；`SHELTER_ADMIN`、`STAFF`、`VOLUNTEER` 與停用帳號收到既有安全拒絕格式，不得藉由提供 organization id 或 user id 繞過授權。

平台管理員 route 的資料範圍為平台，不回傳收容所 Membership 作為平台角色判定依據。若回應需要顯示 Membership 摘要，必須明確標示為獨立資料，不得暗示 Membership 等同平台角色。

## GET Platform Administrators

`GET /v1/platform/administrators`

Response:

```json
{
  "policy": {
    "min_active_admins": 1,
    "max_active_admins": 2,
    "active_count": 1,
    "available_slots": 1
  },
  "items": [
    {
      "user_id": "user-id",
      "username": "local-platform-admin",
      "display_name": "本機平台管理員",
      "user_status": "active",
      "platform_role": "PLATFORM_ADMIN",
      "effective_status": "active",
      "can_enable": false,
      "can_disable": false,
      "can_demote": false
    }
  ]
}
```

清單必須包含目前具有 `PLATFORM_ADMIN` 角色的啟用與停用帳號，且不以 UUID 作為唯一可理解的顯示資訊。排序先啟用中，再停用；已降權或撤銷平台權限的帳號不得出現在目前管理員清單，應透過平台稽核查詢歷史。

## Create Platform Administrator

`POST /v1/platform/administrators`

Request:

```json
{
  "username": "new-platform-admin",
  "display_name": "新平台管理員",
  "temporary_password": "local-only-password"
}
```

- 建立啟用中的全域 User，不能建立任何必要 Membership。
- 若 username 已存在，回傳 `409 username_exists`。
- 若 active count 已達 2，回傳 `409 platform_admin_limit_reached`，提示使用替換流程。
- 成功回傳 `201`、User projection 與更新後 policy summary，並寫入 `platform_admin.created`。

## Promote Existing User

`POST /v1/platform/administrators/{userId}/promote`

- 目標 User 必須存在、active、尚未具備平台角色，且符合既有帳號安全條件。
- 具有 `VOLUNTEER` Membership 或志工申請紀錄的帳號不會出現在候選清單，也不可透過此 API 直接取得平台管理員角色；包含 expired、rejected、revoked 與 pending 的志工資料。
- 已達兩位時回傳 `409 platform_admin_limit_reached`。
- 成功設定平台角色並回傳更新後 projection；Membership 不改變。
- 事件為 `platform_admin.promoted`。

## Enable / Disable / Demote

`POST /v1/platform/administrators/{userId}/enable`

- 只允許啟用符合既有帳號安全條件的 User，且結果不得超過 max。
- 啟用後事件為 `platform_admin.enabled`。

`POST /v1/platform/administrators/{userId}/disable`

- 停用 User 的登入與平台 scope；若結果低於 min 回傳 `409 last_platform_admin`。
- 事件為 `platform_admin.disabled`。

`POST /v1/platform/administrators/{userId}/demote`

- 清除平台角色但保留 User 與既有 Membership；若結果低於 min 回傳 `409 last_platform_admin`。
- 事件為 `platform_admin.demoted`。

## Replace Platform Administrator

`POST /v1/platform/administrators/replacements`

Request:

```json
{
  "outgoing_user_id": "current-admin-id",
  "replacement_user_id": "replacement-user-id",
  "reason": "管理員交接"
}
```

- replacement User 必須 active、尚未具備平台管理員角色且符合既有帳號安全條件；outgoing User 必須是 active platform admin。
- replacement User 若具有任何 `VOLUNTEER` Membership 或 VolunteerApplication 歷史，即使狀態為 expired、revoked、rejected、withdrawn 或 pending，也必須回傳 `409 platform_admin_replacement_invalid`，不得取得平台管理員角色。
- 新舊 User 不得相同。
- 必須在同一個治理操作中完成 replacement role 建立與 outgoing role 清除；結果必須仍有一至兩位 active platform admins。
- 任何條件失敗回傳 `409 platform_admin_replacement_invalid`，既有角色不變。
- 成功回傳新舊 User projection、更新後 policy summary，並以同一 operation id 寫入 `platform_admin.replaced`。

## GET Platform Audit

`GET /v1/platform/administrators/audit?user_id=&action=&limit=`

- 只允許啟用中的 PLATFORM_ADMIN。
- 回傳 `resource_type = platform` 且 `organization_id = null` 的平台管理員事件。
- 每筆包含 actor、target、action、before、after、reason、result、operation id 與時間。
- 拒絕事件可查詢，且 `result` 必須為 `denied`，不得回傳非必要的其他租戶資料。

## Error Contract

| HTTP | Code | Meaning |
|---:|---|---|
| 403 | `platform_admin_required` | 操作者不是啟用中的平台管理員 |
| 404 | `user_not_found` | 目標 User 不存在或不可揭露 |
| 409 | `platform_admin_limit_reached` | 新增／提升／啟用後會超過兩位 |
| 409 | `last_platform_admin` | 停用／降權後會少於一位 |
| 409 | `platform_admin_replacement_invalid` | 替代者或交接狀態不符合條件 |
| 409 | `platform_admin_state_changed` | 目標在確認後已被其他操作改變 |
| 409 | `username_exists` | 建立帳號時 username 已存在 |

## UI Route Contract

- `/platform-admins` 是只供 PLATFORM_ADMIN 使用的全域管理頁，不要求選擇收容所。
- 頁首顯示平台管理員目前人數、`1–2` 政策、剩餘名額與主要操作。
- `新增平台管理員`、`提升既有帳號`、`啟用`、`停用`、`降權` 與 `替換` 都需明確確認；最後一位管理員的危險操作要顯示拒絕原因。
- 停用帳號使用偏灰色視覺，並保留姓名與帳號，不用 UUID 取代身份資訊；降權歷史在稽核檢視中以相同身份欄位呈現。
- 替換對話框要同時顯示 outgoing／replacement、結果人數與不可部分完成的提示。
- 平台管理員頁不提供封存、硬刪除或移除 User 的操作。
## Account eligibility

Create, promote, and replacement operations must reject a target unless all of the following are true:

- The username is non-empty and unique under the existing account rules.
- The User is active.
- The User is not already a `PLATFORM_ADMIN`.
- For a newly created account, the temporary password passes the existing password policy and is stored only through the existing password-hashing path.

## Migration and bootstrap

Migration creates the singleton platform-admin policy. If the database already contains User records and the active platform-admin count is `0` or greater than `2`, migration fails closed with an actionable repair error. A clean empty database may migrate first, but bootstrap/seed must create one active platform administrator before the service is exposed.
