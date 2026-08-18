# Data Model: 收容所權限管理介面改善

本功能只擴充既有 read projection，不新增資料表、欄位或獨立資料副本。

## User

代表可登入管理工作台的使用者。

| 欄位 | 來源 | 用途 | 規則 |
| --- | --- | --- | --- |
| `id` | 既有 User | 與 Membership 關聯 | 只作內部關聯與操作識別，不作主要畫面名稱 |
| `username` | 既有 User | 顯示帳號名稱 | 可為空；有值時作為姓名下方的輔助辨識 |
| `display_name` | 既有 User | 顯示使用者姓名 | 優先作為主要畫面名稱；缺少時由 UI 顯示未命名提示 |

## OrganizationMembership

代表 User 在單一收容所內的角色與有效狀態。

| 欄位 | 來源 | 用途 | 規則 |
| --- | --- | --- | --- |
| `id` | 既有 Membership | 角色／狀態／權限 mutation target | 必須與目前 organization scope 一致 |
| `organization_id` | 既有 Membership | 租戶隔離 | 查詢與操作均受目前已驗證收容所限制 |
| `user_id` | 既有 Membership | 關聯 User | API 可保留，但 UI 不以 UUID 作主要名稱 |
| `role` | 既有 Membership | 顯示與角色選擇 | `SHELTER_ADMIN`、`STAFF`、`VOLUNTEER` |
| `status` | 既有 Membership | 顯示目前狀態 | 至少支援 `invited`、`active`、`disabled`、`expired`、`revoked` |
| `medical_care_access` | 既有 Membership | STAFF 醫療資料權限 | 只對 STAFF 顯示／操作；原有授權規則不變 |
| `username` | User read projection | 顯示帳號 | nullable，不是 Membership 的第二份事實資料 |
| `display_name` | User read projection | 顯示姓名 | nullable，不是 Membership 的第二份事實資料 |

## Organization timezone policy

目前各台灣收容所沿用 `Asia/Taipei`。本 feature 只在頁面顯示固定政策，不提供 timezone mutation；既有 Organization timezone 欄位仍由原有服務與資料模型管理，避免改動其他功能。

## 關聯與資料流

```text
已驗證的 current organization
        │
        ▼
OrganizationMembership ── organization-scoped association ── User
        │                                                   │
        └── role/status/medical_care_access                 └── username/display_name
```

## 安全與狀態規則

- 清單必須先通過既有 Membership management authorization，再執行 User identity projection。
- API 不接受 client 提供 organization scope 來擴張查詢範圍。
- 查不到 User identity 時回傳 nullable identity 欄位；UI 不向其他 organization 查詢補值。
- 既有角色調整、醫療資料權限切換、停用與 Audit 使用原本的 Membership mutation contract。
