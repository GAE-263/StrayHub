# Shelter Admin Governance Confirmation Contract

本功能沿用既有 Membership API，不新增 route；後端的上下限驗證是唯一安全邊界，前端確認 Modal 只負責降低誤操作。

## Authorization

- `PLATFORM_ADMIN` 可依既有平台 scope 管理被允許的收容所。
- `SHELTER_ADMIN` 只能管理目前 organization context 相同的收容所。
- `STAFF`、`VOLUNTEER`、停用帳號及未授權請求維持既有拒絕格式。
- 所有 route 以 path organization id 與已驗證 context 重新判定範圍，不信任前端選擇或請求內額外的 organization id。

## Existing endpoints

### Membership list

`GET /v1/organizations/{organizationId}/memberships`

- 維持目前 response projection 與封存排除規則。
- 前端依 response 計算目前啟用中的 `SHELTER_ADMIN` 數量，僅作為確認 Modal 預覽；後端提交時重新計算。

### Create membership / account

`POST /v1/organizations/{organizationId}/memberships`

`POST /v1/organizations/{organizationId}/accounts`

- 若結果會建立啟用中的 `SHELTER_ADMIN`，交易內必須確認新增後不超過兩位。
- `VOLUNTEER` 仍拒絕一般 Membership 建立，沿用志工報名與授權流程。
- `accounts` 若名額檢查失敗，不得先建立孤立 User；回傳錯誤且保留既有資料不變。

### Update membership

`PATCH /v1/organizations/{organizationId}/memberships/{membershipId}`

Request shape 維持既有欄位，並新增確認時讀到的 `expected_access_version`：

```json
{
  "role": "SHELTER_ADMIN",
  "status": "active",
  "medical_care_access": false,
  "expected_access_version": 3
}
```

- Service 以完整 before／after projection 一次驗證。
- 變更後成為第三位啟用中 `SHELTER_ADMIN` 時回傳 `409 shelter_admin_limit_reached`。
- 變更後少於一位啟用中 `SHELTER_ADMIN` 時回傳 `409 last_shelter_admin`。
- 目標在 Modal 開啟後已被修改時回傳 `409 membership_state_changed` 或等價的既有衝突錯誤；不得部分保存。
- `expected_access_version` 不符合鎖定後的最新 `access_version` 時回傳 `409 membership_state_changed`；成功保存後 `access_version` 遞增。
- 成功事件為 `membership.updated`；拒絕事件以 `result = denied` 寫入同 organization scope Audit。

### Archive and restore

`POST /v1/organizations/{organizationId}/memberships/{membershipId}/archive`

`POST /v1/organizations/{organizationId}/memberships/{membershipId}/restore`

兩個 endpoint 都要求 body：

```json
{ "expected_access_version": 3 }
```

- 封存啟用中的最後一位 `SHELTER_ADMIN` 回傳 `409 last_shelter_admin`。
- 恢復後若會形成第三位啟用中的 `SHELTER_ADMIN`，回傳 `409 shelter_admin_limit_reached`。
- 志工恢復仍依有效期間與授權狀態決定結果，不得繞過 `expired`／`revoked`。
- 成功事件分別為 `membership.archived` 與 `membership.restored`。

## Error contract

| HTTP | Code | Meaning |
|---:|---|---|
| 403 | `membership_management_denied` | 操作者無此收容所 Membership 管理權限 |
| 404 | `membership_not_found` | Membership 不存在或不在可揭露範圍 |
| 409 | `shelter_admin_limit_reached` | 新結果會超過兩位啟用中的收容所管理員 |
| 409 | `last_shelter_admin` | 新結果會少於一位啟用中的收容所管理員 |
| 409 | `membership_state_changed` | 確認後目標狀態已被其他操作改變 |
| 409 | `volunteer_authorization_not_active` | 志工授權已過期或撤銷，不能直接重新啟用 |

錯誤 response 維持既有 `{ code, message, request_id }` 形狀；拒絕原因不得包含其他租戶資訊。

## UI interaction contract

- `/shelters` 的角色、啟用／停用、醫療資料權限、封存與建立／提升為管理員的高風險權限操作，在最終提交前顯示 `AlertDialog`／確認 Modal；若建立帳號的結果是啟用中的 `SHELTER_ADMIN`，在帳號 Modal 送出前再顯示同一套最後確認。
- `/shelters/archived` 的恢復操作也必須顯示相同確認語意，尤其要列出恢復後的管理員人數影響。
- `/volunteers/access` 的志工授權期間調整與撤銷，以及 `/volunteers/applications` 的有效授權決策，也必須使用相同確認語意；志工授權的 `expected_version` 與既有授權流程仍維持不變。
- Modal 顯示收容所名稱、姓名／帳號、目前與變更後角色／狀態、管理員人數 `before → after`，並提供確認與取消；取消、關閉、Escape 不發送 mutation。
- 成功回應後清單重新載入，左下角顯示 `Toast`，文字包含「已將／已停用／已啟用／已封存／已恢復」等完成動作與目標身份。
- API 拒絕、網路錯誤或結果不明時不顯示成功 Toast；錯誤在可理解的 Alert 或 Modal 內呈現，並提示重新載入狀態。
- Toast 使用 `role=status`／`aria-live=polite`，確認 Modal 使用 `role=alertdialog`，且手機寬度不得裁切或遮蔽主要操作。
