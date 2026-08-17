# Authorization Contract：志工報名與限時授權

## 1. 信任邊界

| 輸入 | 可用用途 | 不得用作 |
| --- | --- | --- |
| LINE id token | 經 LINE verifier 取得唯一 LINE user identity | 直接決定 organization、role 或 Membership |
| `shelter_entry_reference` | 以 digest lookup 驗證 active purpose 並解析本次候選 organization | 核准、建立 Membership、建立受保護 context |
| path `organizationId` | 指定管理操作的候選 tenant | 取代 actor Membership／Active Context／RLS |
| application／grant id | 指定 tenant query 內的候選 resource | 證明 resource 可存取或存在 |
| browser token／sessionStorage | 傳送既有 access token | 保存正式 role、期限或授權結果 |
| notification delivery | 告知外部訊息是否送達 | 決定 application／grant 正式狀態 |

後端 CRM、已驗證 actor、organization scope、Membership status／time 與 Grant state 才能共同產生正式存取結果。

## 2. Effective Membership predicate

### VOLUNTEER

只有下列條件全部成立，才是 organization 的有效志工授權：

```text
organization.status == active
user.status == active
membership.organization_id == organization.id
membership.user_id == user.id
membership.role == VOLUNTEER
membership.status == active
membership.valid_from <= database_now
database_now < membership.expires_at
current_grant.status == active
current_grant.organization_id/user_id/membership_id 與 membership 一致
```

- 邊界採半開區間 `[valid_from, expires_at)`；在 `expires_at` 精確時刻已無權限。
- 判斷時間使用 server/database UTC，不接受 client clock。
- access token 不攜帶可被信任的 organization、role、status 或 expiry claims。
- 每次受保護 request、Active Context 建立／切換、LIFF exchange 與 Webhook Session resolution 都必須重新套用 predicate。

### SHELTER_ADMIN／STAFF

沿用既有 active Membership 規則，不套用 Volunteer Grant 時間欄位。只有 SHELTER_ADMIN 可使用本功能管理 endpoint；STAFF 無權查看申請名單、人數或通知狀態。

### PLATFORM_ADMIN

PLATFORM_ADMIN 角色本身代表平台已明確授權，但每個本功能的 management request 還必須：

- path 明確指定單一 target organization；
- 提供 trim 後 1..500 字的 `X-Platform-Support-Reason`；
- 在執行 business query 前呼叫 `set_platform_support_scope(target_organization_id)`，同時設定 platform actor 與 `app.current_org_id`；本功能 RLS 即使 platform mode 也必須匹配 target organization，不得直接使用可見全部 tenant 的一般 scope；
- 每次 read 與 mutation 都寫入 target organization、platform actor、support reason、resource/operation（如適用）與 result 的 platform-support Audit。

缺少 target 或 support reason 時直接拒絕，不執行 query，也不回傳任何 organization 名單、count 或資源存在性。SHELTER_ADMIN 不需 support reason。

## 3. LIFF onboarding authorization

### Status / apply / withdraw

1. 驗證 LINE id token，取得 line user id。
2. 對 raw reference 計算 digest，以固定 purpose 呼叫最小輸出的 DB `SECURITY DEFINER` resolver；runtime 不取得 entry table 的跨租戶 SELECT。resolver 只回 active reference id／候選 organization id。
3. 確認 organization active；apply 另須確認 application policy enabled，status 對既有 applicant 不受 `applications_enabled=false` 阻擋。
4. 立即設定該 organization RLS scope；只有 apply 可在同一 transaction create/reuse User + LineUserBinding，未知 identity 的 status 不得持久化 User／Binding。
5. query 必須同時帶 `organization_id` 與 `user_id`；只能回傳自己的 application/grant summary。

status endpoint 不得建立 User、LineUserBinding、Membership、SessionRecord、WebhookSession 或 Active Shelter Context；若 Binding 已存在則只讀 own status。apply 只建立／重用 identity 並建立 pending Application；withdraw 只允許同一 identity 的 pending Application 且需 `expected_version`。

### 可見資料

| 狀態 | 可回傳 | 禁止回傳 |
| --- | --- | --- |
| 無申請 | 收容所 public name、入口可用、可申請下一步 | 動物、其他申請者、內部 counts |
| pending | 自己的 application id/status/submitted/version、等待／撤回 | Membership、動物、草稿、回報 |
| approved + upcoming/active | 自己的 application、grant start/end、剩餘期限、進入下一步 | 其他使用者或其他 organization 資料 |
| rejected | 自己的結果、可公開給申請人的 reason、重新申請／聯絡下一步 | 管理員內部備註、其他申請 |
| expired/revoked | 自己的 grant result、到期／撤銷下一步 | 受保護資料；revocation 內部敏感細節可只顯示通用說明 |

跨 organization、停用 user/binding 或無權資源使用相同安全錯誤族群，不回傳名單或 count。停用申請入口時，未知 identity/status 與新 apply 回安全停用狀態；既有 applicant 仍只取得自己的 application/grant summary。

## 4. 管理 authorization

所有 management paths 都是 organization-scoped：

```text
/v1/organizations/{organizationId}/volunteer-...
```

SHELTER_ADMIN 必須同時符合：

- server-side Session active 且未到期；
- Active Shelter Context 等於 path organization；
- 該 organization active；
- actor 的 SHELTER_ADMIN Membership active。

PLATFORM_ADMIN 可跳過 tenant Membership，但必須通過上一節的 target + support reason gate，設定只限 target 的受控 platform scope，且讀寫都寫入 platform-support Audit。VOLUNTEER、STAFF 與其他 organization SHELTER_ADMIN 收到拒絕，且回應不能揭露 resource 是否存在。

前端 Sidebar 只對 SHELTER_ADMIN／PLATFORM_ADMIN 顯示功能入口；這只是 UX，不能替代上述 API gate 與 RLS。

## 5. 批次 decision contract

### 建立與冪等

- request 必須有 UUID `operation_id`，並選擇 `explicit_items` 或 `all_filtered` target mode。
- `explicit_items` 需要 1..500 個 application/version；`all_filtered` 提交 pending/time filter，不接受 pagination cursor/limit。
- `(organization_id, operation_id)` 唯一；normalized request fingerprint 必須相同才可重播。
- 同 operation id + 相同 payload：回傳既有 batch 並繼續 pending items。
- 同 operation id + 不同 payload：409 `operation_payload_conflict`，不處理任何新 item。

### 全部 filter snapshot

`all_filtered` 在 Batch 建立的 repeatable-read transaction 內：

1. 重新驗證 actor 與 organization scope。
2. 讀取並快照 organization policy version/default duration。
3. 以 normalized filter 執行不含 pagination 的 pending application query。
4. 將每個 application id 與當時 version 寫成不可變 BatchItem；個別期限覆寫只可套用 snapshot 內 target。
5. 寫 Batch requested count、snapshot time、filter snapshot 與 Audit 後 commit。

transaction snapshot 後才建立／才符合 filter 的 application 不納入。logical batch 可超過 500；orchestrator 每次以 `SKIP LOCKED` claim 最多 500 個 pending items。Batch status/summary 可輪詢，逐筆結果以 cursor 分頁取得。

### 每項 transaction

每個 item 使用獨立 DB transaction 與 organization scope：

1. application `FOR UPDATE`。
2. 比對 `status == pending` 與 `version == expected_version`。
3. 驗證 dates/reason/actor。
4. approve：application → approved，建立／啟用 VOLUNTEER Membership，新增 active Grant；reject：application → rejected，不建立 Membership。
5. 寫 per-target Audit、notification outbox 與 terminal item result。
6. commit 後才算該 item succeeded。

conflict／failed item 不修改 Application、Membership 或 Grant。其他 item 的 success 不回滾。程序中斷時只重跑 `result == pending`；已 terminal items 不重做。chunk claim 失效可回收，但不得遺失 snapshot item 或把確認後的新申請加入 Batch。

### Optimistic concurrency

- Application decision 使用 `expected_version`。
- Grant update/revoke 使用 `expected_version`。
- stale version 回 409/per-item `conflict`；管理 UI 必須重新載入後再讓使用者決定。
- `updated_at` 可顯示但不是 concurrency token。

## 6. Grant mutation contract

### 更新期限

- 只允許目前 active Grant。
- `expires_at > valid_from`。
- 未提供的欄位沿用目前值。
- resulting `expires_at <= server_now` 時必須帶 `confirm_immediate_expiry=true`；成功後狀態改為 expired，並立即執行 context cleanup。
- 期限變更同步更新 Membership projection、Grant version、Membership access version、Audit 與 outbox。

### 撤銷

- 只允許目前 active Grant。
- `reason` 必填且 trim 後不可空。
- Grant → revoked，Membership → revoked，立即清除 target organization context，寫 Audit 與 outbox。
- retry 同一 expected version 會 conflict；不會再次撤銷或建立重複通知。

### 重新授權

expired/revoked Grant 不直接改回 active。必須由新的 pending Application 經核准，建立新的 Grant Cycle；舊 Application/Grant/Audit 保留。

## 7. Session、context 與 request failure

### Request-time

若 VOLUNTEER effective predicate 失敗：

- 不執行 endpoint business query/mutation；
- 不回傳 stale protected body；
- organization access 回安全 403/404 或 context-required 狀態；
- 若目前 Session context 指向失效 organization，可在受控 cleanup transaction 清為 null。

### Cleanup

- `SessionRecord.active_organization_id == target organization` → null。
- target organization 的 active `WebhookSession` → revoked/expired。
- 不撤銷 user 在其他 organization 的 Membership 或 context 建立能力。
- 不刪 access/refresh token family，除非 user/session 本身失效。
- 不刪 Draft、Report、Media、Audit 或 LINE Binding。
- organization/user 停用 transaction 應同步清理受影響 context；背景收斂器另掃描未完成項目，確保沒有後續 request 時仍在 60 秒內完成。

### Invalidation convergence Worker

- loop interval 不超過 60 秒。
- request-time predicate 在 Worker 前已生效。
- Worker 以 due index 取得 active grant，並掃描 inactive organization／disabled user 所屬的未收斂 context；逐 organization transaction + row lock，重複執行冪等。
- 同 transaction 更新 Grant/Membership、cleanup、Audit 與 outbox。
- Worker crash 後可從仍 active 且 expires_at <= now 的 rows 繼續。

## 8. Notification outbox contract

- domain mutation 與 outbox insert 同 transaction；LINE push 在 commit 後由 Worker 執行。
- claim 使用 `FOR UPDATE SKIP LOCKED`、claim token/owner/time；stale claim 可回到 retry_wait。
- domain event idempotency key 唯一，provider retry 不得建立第二個 Membership／Grant／Application。
- transient failure 使用 bounded backoff；terminal failure 進入 failed 並顯示給管理員。
- management failure list 只查目前 organization，涵蓋 application submitted/withdrawn、approved/rejected、grant changed、expired/revoked；可依 event type、status、failed time cursor 分頁。
- manual retry 接受 1..500 個 notification ids + UUID `operation_id`，持久化 retry Batch/Item；同 operation/payload 重播既有結果，不同 payload 回 409。
- manual retry 只把仍為 failed 的 delivery 改為 retry_wait 並新增 Audit／attempt opportunity，不重放 domain mutation；sent/sending/其他 organization target 回逐項 conflict 且不洩漏存在性。
- payload 不含 id token、LINE user id、provider credential、動物、草稿或回報內容。

## 9. 與 004 的 contract 邊界

005 提供：

- entry reference verifier contract；
- LINE Binding + User；
- approved Membership 的 role/status/valid_from/expires_at；
- current active Grant 與 request-time effective predicate；
- pending/rejected/expired/revoked own-status 與安全下一步。

004 負責：

- 在 `POST /v1/auth/liff/exchange` 同時提交 id token + entry reference；
- 在單一 transaction 驗證 005 effective predicate，成功後才建立 Session + Active Shelter Context；
- role-directed route、管理內容 mount-before-check 防護、session recovery、動物／草稿入口。

004 不得建立、核准、延長、撤銷或繞過 Membership；005 不在 pending onboarding 階段載入動物、草稿或管理資料。

## 10. 可驗證不變條件

- 同 user/org pending Application 最大數：1。
- pending/rejected/withdrawn application 對應 Membership 新增數：0。
- active VOLUNTEER 且 null/invalid expiry 數：0。
- 同 Membership active Grant 最大數：1。
- expired/revoked/future Grant 的 protected request 成功率：0%。
- ORG-A actor 對 ORG-B application/grant/list/count 可見數：0。
- batch succeeded item 的 transaction、Audit、outbox 完整率：100%。
- batch conflict/failed item 的 domain mutation 數：0。
- 1,200 筆 all-filtered Batch 的 target/result 完整率：100%，確認後新增誤納入與 chunk retry 重做成功項目數：0。
- notification failure 導致 domain rollback 數：0。
- organization failure list 的跨 tenant delivery 數：0；manual retry 導致 domain mutation 數：0。
- PLATFORM_ADMIN 缺少 target/reason 的 read/write 成功數：0；合法支援 request 的 read/write Audit 覆蓋率：100%。
- 自然到期、撤銷或 organization/user 停用後 request-time 越權窗口：0；即使沒有後續 request，target Session/context 與適用 Audit 收斂：60 秒內；其他 organization 誤清除數：0。
