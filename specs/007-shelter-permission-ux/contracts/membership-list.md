# Membership List Contract

## 範圍

此 contract 描述目前收容所管理員在權限管理頁面讀取 Membership 清單時需要的 additive identity projection。既有授權與 mutation contract 不變。

## Response

`GET /v1/organizations/{organizationId}/memberships` 回傳：

```json
{
  "items": [
    {
      "id": "membership-uuid",
      "organization_id": "organization-uuid",
      "user_id": "user-uuid",
      "role": "STAFF",
      "status": "active",
      "medical_care_access": false,
      "username": "local-staff-a",
      "display_name": "本機工作人員 A"
    }
  ]
}
```

## 欄位規則

- `username` 與 `display_name` 是 nullable 的既有 User identity projection。
- `user_id` 可保留供內部關聯與 accessibility fallback，但不得作為主要可見身份名稱。
- `role`、`status`、`medical_care_access` 的既有語意與 mutation 行為不變。
- 清單只包含目前已驗證 organization 的 Membership；不得回傳其他 organization 使用者的身份資料。
- 未找到 User identity 時，`username` 與 `display_name` 回傳 `null`，不以另一收容所資料補值。

## UI contract

- 頁面主要標題：`權限管理`。
- 每筆 Membership 必須分開呈現身份、角色／狀態摘要與操作區域。
- STAFF 顯示醫療資料權限；其他角色不顯示不適用的 checkbox。
- 頁面顯示 `Asia/Taipei（台灣時間）` 統一使用說明，不顯示 timezone select 或儲存按鈕。
- 1440px、768px、360px 下不得有文字或控制項重疊；手機下操作區可直向排列。
