# 資料模型：志工報名與限時授權

## 設計原則

- PostgreSQL CRM 是申請、授權、期限、批次結果、通知與稽核的唯一事實來源。
- 每個 tenant business entity 都有 `organization_id`，repository query 同時帶 scope，資料表啟用 FORCE RLS。
- Application 決策與 Access Grant 效力分開：前者回答「是否曾核准」，後者回答「目前能否使用」。
- 每個 user／organization 維持一筆 Membership；重新授權新增 Grant Cycle，不新增第二筆 Membership。
- 所有 timestamp 使用 timezone-aware UTC；UI 再轉為台灣時區。
- 草稿、Care Report、Media 與歷史資料不因 Membership 到期或撤銷被刪除或改寫。

## 關聯概覽

```text
Organization 1 ── 1 OrganizationVolunteerAccessPolicy
Organization 1 ── * ShelterVolunteerEntryReference
Organization 1 ── * VolunteerApplication * ── 1 User 1 ── * LineUserBinding
VolunteerApplication 1 ── 0..1 VolunteerAccessGrant * ── 1 OrganizationMembership
Organization 1 ── * VolunteerDecisionBatch 1 ── * VolunteerDecisionBatchItem
VolunteerApplication 1 ── * VolunteerDecisionBatchItem
Organization 1 ── * VolunteerNotificationDelivery * ── 1 User
Organization 1 ── * VolunteerNotificationRetryBatch 1 ── * VolunteerNotificationRetryBatchItem
```

`AuditRecord` 以既有 `operation_id`、resource type/id、before/after/reason/result 關聯上述異動，不另複製 business payload。

## AuditRecord（既有 entity 擴充）

為了讓一次性遷移不冒充管理員，新增 nullable `actor_type`（`user`、`system`）與 `actor_reference`。既有 user action 使用 `actor_type=user` + `actor_user_id`；legacy backfill 使用 `actor_type=system`、`actor_user_id=null`、`actor_reference=SYSTEM_MIGRATION`。PLATFORM_ADMIN 支援 read/write 仍使用 user actor，`reason` 保存必填 support reason，`organization_id` 保存單一 target。

- user actor 必須有 `actor_user_id`；system actor 必須有 allowlist `actor_reference` 且 user id 為 null。
- `SYSTEM_MIGRATION` 只允許 migration 執行角色與 migration source channel 建立，runtime API 不接受 client 提交 actor 欄位。
- 新增索引 `(organization_id, actor_type, actor_reference, created_at DESC)`，既有 Audit 保存政策不變。

## OrganizationVolunteerAccessPolicy

每個收容所的志工申請入口設定。P0 至少需要能安全關閉入口，並保存可由收容所調整的預設授權期限；新 organization 初始為 168 小時。

| 欄位 | 型別 | 必填 | 規則 |
| --- | --- | --- | --- |
| `organization_id` | UUID PK/FK | 是 | 對應 `organizations.id`，一個 organization 一筆 |
| `applications_enabled` | boolean | 是 | 預設 `true`；false 時 apply 回安全停用狀態且不建立申請，既有 applicant 仍可查 own status |
| `default_grant_duration_hours` | integer | 是 | 新 organization 初始 `168`；大於 0，管理員可修改或於每次核准覆寫 |
| `version` | integer | 是 | 預設 1；policy mutation +1，供 optimistic concurrency |
| `created_at` / `updated_at` | timestamptz | 是 | AuditMixin |

### Constraints / Indexes

- PK 同時保證每個 organization 唯一。
- `CHECK (default_grant_duration_hours > 0)`。
- organization create service 必須在建立 organization 的同一 transaction 插入初始 policy（`applications_enabled=true`、`default_grant_duration_hours=168`）；任一步驟失敗皆回滾，不採首次 GET lazy-create。
- FORCE RLS：organization scope 或受控 platform scope。
- 本功能的新表對 PLATFORM_ADMIN 仍要求 `organization_id = app.current_org_id`；`app.platform_scope=true` 只表示略過 Membership，不表示可略過 target organization。API 新增 `set_platform_support_scope(target_organization_id)`，不得直接沿用可見所有 tenant 的一般 platform scope。
- policy mutation 使用 `expected_version`；成功後 version +1 並寫前後值 Audit。既有 Application、Batch、Grant 與 Membership 不追溯改寫。

## ShelterVolunteerEntryReference

收容所專屬 LIFF／QR 入口的 opaque reference。它只解析候選 organization，不是登入或授權憑證。

| 欄位 | 型別 | 必填 | 規則 |
| --- | --- | --- | --- |
| `id` | UUID PK | 是 | server 產生 |
| `organization_id` | UUID FK | 是 | 單一 tenant |
| `token_digest` | string(64) | 是 | 256-bit 以上 raw token 的 SHA-256；raw token 不落 DB／Audit |
| `purpose` | string | 是 | 固定 `volunteer_application_entry` |
| `status` | string | 是 | `active`、`revoked` |
| `issued_by_user_id` | UUID FK | 否 | PLATFORM_ADMIN 發行時填入 |
| `issued_by_actor_reference` | string | 否 | 受控部署發行時填入 allowlist system actor；與 user id 擇一 |
| `issued_at` | timestamptz | 是 | 發行時間 |
| `revoked_by_user_id` | UUID FK | 否 | PLATFORM_ADMIN 撤銷時填入 |
| `revoked_by_actor_reference` | string | 否 | 受控部署撤銷時可填；與 user id 擇一 |
| `revoked_at` | timestamptz | 否 | revoked 時必填 |
| `rotation_group_id` | UUID | 是 | 同一次輪替鏈的穩定 reference |
| `created_at` / `updated_at` | timestamptz | 是 | AuditMixin |

### Constraints / Indexes

- `UNIQUE (token_digest)`；lookup 只比對 digest。
- `(organization_id, status, issued_at DESC)`；允許部署切換期間同 organization 暫時存在新舊兩筆 active reference。
- issue actor 的 user id/system reference 必須恰有一個；revoked conditional fields 與 revoke actor 也必須完整。revoked reference 不得恢復 active，需另發新 reference。
- FORCE RLS；發行／撤銷需 platform support scope 與 Audit。pre-context LIFF resolve 不授予 runtime 跨租戶 SELECT，只能呼叫固定 `search_path`、owner 不可登入、輸出僅含 active reference id/organization id 的 `SECURITY DEFINER resolve_volunteer_entry_reference(digest, purpose)`；取得候選 organization 後立即切換一般 organization scope。

## VolunteerApplication

一個已驗證 LINE identity 對單一收容所提出的一次申請。舊週期不可覆寫。

| 欄位 | 型別 | 必填 | 規則 |
| --- | --- | --- | --- |
| `id` | UUID PK | 是 | server 產生 |
| `organization_id` | UUID FK | 是 | 單一 tenant scope |
| `user_id` | UUID FK | 是 | password-less 或既有 User |
| `status` | string | 是 | `pending`、`approved`、`rejected`、`withdrawn` |
| `source_channel` | string | 是 | `liff`、`management`、`legacy_migration` |
| `client_request_id` | UUID | 否 | LIFF submit 冪等 key |
| `previous_application_id` | UUID FK self | 否 | 同 user/org 的前次已結案申請 |
| `submitted_at` | timestamptz | 是 | 建立時間；不因決策改寫 |
| `decided_at` | timestamptz | 否 | approved/rejected 必填 |
| `decided_by_user_id` | UUID FK | 否 | 一般核准／拒絕必填；legacy migration 可空 |
| `decision_reason` | string(500) | 否 | rejected 必填；approved 可選 |
| `withdrawn_at` | timestamptz | 否 | withdrawn 必填 |
| `version` | integer | 是 | 預設 1，每次合法 mutation +1 |
| `created_at` / `updated_at` | timestamptz | 是 | AuditMixin |

### Constraints / Indexes

- Partial unique：`UNIQUE (organization_id, user_id) WHERE status = 'pending'`。
- Optional unique：`UNIQUE (organization_id, user_id, client_request_id) WHERE client_request_id IS NOT NULL`。
- List index：`(organization_id, status, submitted_at DESC, id)`。
- History index：`(organization_id, user_id, submitted_at DESC)`。
- `previous_application_id` 必須指向相同 organization/user；application service 強制並由 integration test 驗證。
- `rejected` 必須有 `decided_at`、`decided_by_user_id`、非空 reason；`approved` 必須有 decided fields；`withdrawn` 必須有 withdrawn_at。
- FORCE RLS：organization scope 或受控 platform scope。LIFF pre-context flow 先以 reference 解析 organization，再設定該 scope；own-status query 另必須加 user id。

### 狀態轉換

```text
pending ──approve──> approved
pending ──reject───> rejected
pending ──withdraw─> withdrawn
```

- terminal application 不再 mutation。
- rejected／withdrawn 可建立新 application。
- approved 只有其 Grant 已 expired/revoked 後才可重新報名；新 application 連回 previous application。
- duplicate pending submit 回傳既有 application，不產生 transition 或第二筆 row。

## OrganizationMembership（既有 entity 擴充）

Membership 仍代表 user 在 organization 的目前角色；本功能新增 `VOLUNTEER` 的目前有效期間投影。

### 新增欄位

| 欄位 | 型別 | 必填 | 規則 |
| --- | --- | --- | --- |
| `valid_from` | timestamptz | 條件式 | role=VOLUNTEER 時必填；管理角色維持 null |
| `expires_at` | timestamptz | 條件式 | role=VOLUNTEER 時必填，且嚴格晚於 valid_from |
| `access_version` | integer | 是 | 預設 0；志工授權／期限／撤銷 mutation +1 |

### 狀態

- 既有：`invited`、`active`、`disabled`。
- 志工生命週期新增：`expired`、`revoked`。
- `active` 不代表已到開始時間；effective predicate 仍需檢查 `valid_from <= now < expires_at`。
- 管理角色不套用限時 grant predicate，但仍需既有 active status。

### Constraints / Indexes

- 保留 `UNIQUE (organization_id, user_id)`。
- `CHECK (role <> 'VOLUNTEER' OR (valid_from IS NOT NULL AND expires_at IS NOT NULL AND expires_at > valid_from))`。
- Due sweep index：`(organization_id, status, expires_at) WHERE role = 'VOLUNTEER' AND status = 'active'`。
- existing RLS policy 保留；authorization query 必須在 role=VOLUNTEER 時套用 effective predicate。

### Effective predicate

```text
membership.role == VOLUNTEER
AND membership.status == active
AND membership.valid_from <= now
AND now < membership.expires_at
AND current grant status == active
```

STAFF／SHELTER_ADMIN 仍使用既有 active Membership；PLATFORM_ADMIN 使用既有受控 platform scope。

## VolunteerAccessGrant

一次完整的限時授權週期。新週期 append，不覆寫前次週期；目前週期可以調整期限或撤銷，但所有 mutation 另寫 Audit。

| 欄位 | 型別 | 必填 | 規則 |
| --- | --- | --- | --- |
| `id` | UUID PK | 是 | server 產生 |
| `organization_id` | UUID FK | 是 | 必須等於 application/membership organization |
| `user_id` | UUID FK | 是 | 必須等於 application/membership user |
| `membership_id` | UUID FK | 是 | 指向唯一 org/user Membership |
| `application_id` | UUID FK | 是 | 來源 approved application；legacy migration 使用 synthetic application |
| `status` | string | 是 | `active`、`expired`、`revoked` |
| `valid_from` | timestamptz | 是 | 可為未來；仍須 status active 但 effective access 為 false |
| `expires_at` | timestamptz | 是 | 嚴格晚於 valid_from |
| `approved_at` | timestamptz | 是 | decision commit time |
| `approved_by_user_id` | UUID FK | 否 | 一般 grant 必填；legacy migration 可空 |
| `policy_version_used` | integer | 否 | 未逐批／逐筆覆寫時，保存 decision 建立時 organization policy version；legacy migration 必填 |
| `duration_hours_used` | integer | 否 | 保存由 policy 套用的時數；明確提供 expires_at 時可空 |
| `source_type` | string | 是 | `manager_approval` 或 `legacy_migration` |
| `revoked_at` | timestamptz | 否 | revoked 必填 |
| `revoked_by_user_id` | UUID FK | 否 | revoked 必填 |
| `revocation_reason` | string(500) | 否 | revoked 必填、不可空白 |
| `version` | integer | 是 | 預設 1；期限或 revoke mutation +1 |
| `created_at` / `updated_at` | timestamptz | 是 | AuditMixin |

### Constraints / Indexes

- `UNIQUE (application_id)`：一筆 application 最多產生一個 grant。
- Partial unique：同一 Membership 最多一筆 `status = 'active'` grant。
- `CHECK (expires_at > valid_from)`。
- `source_type = 'legacy_migration'` 時 `policy_version_used`、`duration_hours_used` 必填且 `approved_by_user_id` 為 null；一般 manager approval 的 actor 必填。
- Due sweep：`(status, expires_at, organization_id) WHERE status = 'active'`。
- Member history：`(organization_id, membership_id, approved_at DESC)`。
- revoked fields 的 conditional check。
- FORCE RLS。

### 狀態轉換

```text
active ──expires_at reached──> expired
active ──admin revoke────────> revoked
active ──shorten <= now──────> expired  (需明確立即失效確認)
```

- 尚未開始的 active grant 可調整 valid_from/expires_at 或撤銷。
- active grant 可延長或縮短；每次同步更新 Membership current projection。
- expired/revoked grant 不再修改；重新授權建立新 application/grant cycle。

## VolunteerDecisionBatch

一次管理員提交的批次審核 orchestration 與摘要。

| 欄位 | 型別 | 必填 | 規則 |
| --- | --- | --- | --- |
| `id` | UUID PK | 是 | server 產生 |
| `organization_id` | UUID FK | 是 | 單一 tenant |
| `operation_id` | UUID | 是 | caller 產生的冪等 key |
| `actor_user_id` | UUID FK | 是 | SHELTER_ADMIN 或 PLATFORM_ADMIN |
| `platform_support_reason` | string(500) | 否 | actor 為 PLATFORM_ADMIN 時必填；SHELTER_ADMIN 為 null |
| `decision` | string | 是 | `approve` 或 `reject`；單批一致 |
| `reason` | string(500) | 否 | reject 必填；approve 可選 |
| `default_valid_from` | timestamptz | 否 | approve 可省略，server commit time 為 default |
| `default_expires_at` | timestamptz | 否 | approve 可省略，server 以快照 policy duration 計算 |
| `policy_version_used` | integer | 否 | approve 且未提供共同 expires_at 時必填 |
| `default_duration_hours_used` | integer | 否 | approve 且套用 policy 時必填 |
| `selection_mode` | string | 是 | `explicit_items` 或 `all_filtered` |
| `filter_snapshot` | JSON | 否 | `all_filtered` 的 normalized pending/time filter；不含 pagination |
| `snapshot_at` | timestamptz | 是 | server 建立不可變 target items 的時間 |
| `request_fingerprint` | string(64) | 是 | normalized payload hash；同 operation id 不同 payload 時 409 |
| `status` | string | 是 | `queued`、`processing`、`completed`、`completed_with_errors` |
| `requested_count` | integer | 是 | 大於 0；全選可超過 500 |
| `processed_count` | integer | 是 | 預設 0；等於三種 terminal count 合計 |
| `succeeded_count` | integer | 是 | 預設 0 |
| `conflict_count` | integer | 是 | 預設 0 |
| `failed_count` | integer | 是 | 預設 0 |
| `completed_at` | timestamptz | 否 | 完成時必填 |
| `created_at` / `updated_at` | timestamptz | 是 | AuditMixin |

### Constraints / Indexes

- `UNIQUE (organization_id, operation_id)`。
- `CHECK (requested_count > 0)`；500 是每次 claim chunk 上限，不是 logical batch 上限。
- `CHECK (processed_count = succeeded_count + conflict_count + failed_count)`。
- `selection_mode = 'all_filtered'` 時 `filter_snapshot` 必填；`explicit_items` 時為 null。
- PLATFORM_ADMIN actor 必須有非空 `platform_support_reason`。
- `(organization_id, actor_user_id, created_at DESC)`。
- Worker claim index：`(status, updated_at, organization_id) WHERE status IN ('queued', 'processing')`。
- FORCE RLS。

## VolunteerDecisionBatchItem

批次中的單一 target 與可重播結果。

| 欄位 | 型別 | 必填 | 規則 |
| --- | --- | --- | --- |
| `id` | UUID PK | 是 | server 產生 |
| `organization_id` | UUID FK | 是 | 等於 batch/application organization |
| `batch_id` | UUID FK | 是 | parent batch |
| `application_id` | UUID FK | 是 | target application |
| `expected_version` | integer | 是 | explicit mode 由 caller 提供；all-filtered mode 由 server snapshot query 擷取 |
| `override_valid_from` | timestamptz | 否 | approve per-item override |
| `override_expires_at` | timestamptz | 否 | approve per-item override |
| `result` | string | 是 | `pending`、`succeeded`、`conflict`、`failed` |
| `claim_token` / `claimed_at` / `claimed_by` | nullable | 否 | 分段 orchestrator ownership；stale claim 可回收 |
| `error_code` | string | 否 | 安全、穩定、不含其他 tenant 細節 |
| `resulting_application_version` | integer | 否 | succeeded 時回傳 |
| `membership_id` | UUID FK | 否 | approve succeeded 時填入 |
| `grant_id` | UUID FK | 否 | approve succeeded 時填入 |
| `processed_at` | timestamptz | 否 | terminal result 必填 |
| `created_at` / `updated_at` | timestamptz | 是 | AuditMixin |

### Constraints / Indexes

- `UNIQUE (batch_id, application_id)`。
- `(organization_id, batch_id, result, id)`；每次 `SKIP LOCKED` 最多 claim 500 筆 pending item。
- item 一旦 terminal 不再重做；retry failed targets 由新 batch／operation id 執行，或原 processing batch 只處理仍為 pending 的 item。
- Batch 建立 transaction 完成後 item target/application version 不再新增或替換；確認後的新 application 不會進入既有 Batch。
- FORCE RLS。

## VolunteerNotificationDelivery

LINE／local status delivery outbox。它反映傳送狀態，不是申請或授權事實。

| 欄位 | 型別 | 必填 | 規則 |
| --- | --- | --- | --- |
| `id` | UUID PK | 是 | server 產生 |
| `organization_id` | UUID FK | 是 | tenant scope |
| `user_id` | UUID FK | 是 | recipient |
| `line_binding_id` | UUID FK | 否 | 建立時可解析；binding 無效時 delivery failed |
| `event_type` | string | 是 | `application_submitted`、`application_withdrawn`、`approved`、`rejected`、`grant_changed`、`expired`、`revoked` |
| `resource_type` | string | 是 | application 或 grant |
| `resource_id` | UUID | 是 | domain resource |
| `idempotency_key` | string(160) | 是 | 每個 domain event 唯一 |
| `payload` | JSON | 是 | 最少必要顯示內容；不含動物／草稿／其他志工資料 |
| `status` | string | 是 | `pending`、`sending`、`retry_wait`、`sent`、`failed` |
| `attempt_count` | integer | 是 | 預設 0 |
| `available_at` | timestamptz | 是 | 下一次可 claim 時間 |
| `claim_token` / `claimed_at` / `claimed_by` | nullable | 否 | worker ownership |
| `last_error_code` | string | 否 | sanitize 後錯誤碼，不保存 access token 或 provider body |
| `last_failed_at` | timestamptz | 否 | retry_wait／failed 時填入；管理清單時間 filter |
| `sent_at` | timestamptz | 否 | sent 必填 |
| `created_at` / `updated_at` | timestamptz | 是 | AuditMixin |

### Constraints / Indexes

- `UNIQUE (organization_id, idempotency_key)`。
- Claim index：`(status, available_at, organization_id)`。
- 統一失敗清單：`(organization_id, status, last_failed_at DESC, id) WHERE status IN ('retry_wait', 'failed')`。
- `(organization_id, resource_type, resource_id, created_at DESC)`。
- `attempt_count >= 0`。
- FORCE RLS。

### 狀態轉換

```text
pending ──claim──> sending ──success──> sent
                         └──transient──> retry_wait ──claim──> sending
                         └──terminal/max attempts──> failed
failed ──admin retry──> retry_wait
```

## VolunteerNotificationRetryBatch／Item

管理員一次重試單筆或多筆通知的冪等 orchestration。Batch 保存 `organization_id`、`operation_id`、actor、PLATFORM_ADMIN support reason、request fingerprint、requested/requeued/skipped counts 與時間；Item 保存 `batch_id`、`notification_delivery_id`、`result`（`requeued`、`conflict`、`failed`）及安全錯誤碼。

- `UNIQUE (organization_id, operation_id)`；同 operation id 不同 payload 拒絕。
- `UNIQUE (batch_id, notification_delivery_id)`。
- explicit retry 一次 1..500 筆；只允許目前 organization 的 `failed` delivery 轉為 `retry_wait`，已送達／傳送中項目回 conflict，不改 domain resource。
- retry Batch/Item 與 delivery mutation 在同一 transaction；每個 delivery 只新增傳送嘗試機會，不重建 notification 或來源決策。
- 所有表 FORCE RLS，並可用 Batch operation id 對應 `volunteer_notification.retry_requested` Audit。

## User 與 LineUserBinding（既有 entity 使用方式）

- 首次 application 可建立 `User(username=null, password_hash=null, display_name=<LINE 最小可用顯示名>, status=active)`。
- `LineUserBinding.line_user_id` 既有 global unique constraint 保證一個 LINE identity 對應唯一 User。
- 已有 binding 時必須重用 User；不得因跨 organization 報名建立第二個 User。
- 未知 LINE identity 的 status lookup 不建立 User、LineUserBinding、SessionRecord、WebhookSession 或 OrganizationMembership；只有 submit 可原子建立／重用 User + Binding + pending Application。
- `applications_enabled=false` 只阻止 submit；既有 applicant 仍可讀取 own application/grant summary，且查詢仍同時受 organization/user scope 限制。
- pending Application 不建立 SessionRecord、WebhookSession 或 OrganizationMembership。
- 使用者停用／binding 無效時，不建立 application；回應不揭露內部停用原因。

## Session/context 失效規則

當 grant 被撤銷、縮短至現在以前、自然到期、organization 停用或 user 停用：

1. request-time predicate 先拒絕受保護 action。
2. `SessionRecord` 只在 `active_organization_id == target organization_id` 時清為 null；Session 本身可保持 active，讓 user 使用其他有效 organization。
3. target organization 的 `WebhookSession` 標為 `revoked` 或 `expired`。
4. 既有 access/refresh token 不含可被信任的 organization/role claims；下一個 request 仍由 server-side state 判斷。
5. Draft、Care Report、Media 與歷史不刪除；重新取得同 organization access 後仍依原本業務規則處理。
6. organization/user 停用 transaction 應同步執行 scoped cleanup；Worker 另掃描未收斂的 inactive organization/disabled user，保證即使沒有後續 request，持久化 context 也在 60 秒內清除。

## Batch consistency 與 Audit mapping

| Domain action | Transaction 內必須同時完成 | Audit action |
| --- | --- | --- |
| policy update | policy version/default + before/after | `volunteer_access.policy_changed` |
| application submit | application + notification outbox | `volunteer_application.submitted` |
| withdraw | application terminal state + outbox | `volunteer_application.withdrawn` |
| approve item | application + membership + grant + batch item + outbox | `volunteer_application.approved`、`volunteer_access.granted` |
| reject item | application + batch item + outbox | `volunteer_application.rejected` |
| grant time update | grant + membership projection + optional context cleanup + outbox | `volunteer_access.period_changed` |
| revoke | grant + membership + context cleanup + outbox | `volunteer_access.revoked` |
| natural expiry | grant + membership + context cleanup + outbox | `volunteer_access.expired` |
| decision batch snapshot | batch + immutable target items + policy snapshot | `volunteer_decision.snapshot_created` |
| notification retry | retry batch/items + delivery state only | `volunteer_notification.retry_requested` |
| platform support read | 無 business mutation；同 request 寫 target/reason/result Audit | `platform_support.accessed` |

- Batch 的所有 per-target Audit 使用相同 batch `operation_id`，便於對帳。
- failure/conflict item 可記錄 result audit，但不得保存其他 tenant resource 細節。
- rejection/revocation reason 進入 Audit；approved reason 可空。
- PLATFORM_ADMIN 的 read/mutation Audit 另保存 support reason；不得以 application decision reason 代替。

## Migration 與 rollback

### Upgrade

1. `0024_volunteer_access_expand` 建立 policy、entry reference、application、grant、decision batch/item、notification delivery/retry batch/item tables 與 indexes；每個 organization 建立初始 policy（168 小時）。
2. 0024 對新 tables 啟用 FORCE RLS、建立 pre-context entry resolver，並為 Membership／AuditRecord 加入 nullable projection/system actor 欄位；此時尚不切換 authorization read path。
3. 若收容所需要不同過渡窗口，部署者在 0024 與 0025 之間透過受控 `configure_volunteer_access_policy.py` 設定 organization policy；未設定者維持 168。
4. `0025_volunteer_access_enforce` 以單一 migration timestamp，只為 existing active、unbounded VOLUNTEER 建立 synthetic legacy application/grant；每筆 `expires_at` 依所屬 organization 當時 policy 計算，並快照 policy version/duration。Disabled、revoked、expired 或其他非有效 Membership 保持不變，且不得建立 synthetic Application／Grant。
5. 0025 驗證每筆 active VOLUNTEER 都有有限期與一筆 active grant，再加入 DB check constraint；應用程式只在 0025 完成後切換 effective Membership read path。
6. seed_local 對 local volunteer 使用 deterministic entry reference/application/grant，另新增 organization policy 變更、pending/rejected/expired/revoked、通知失敗、1,200 筆 ORG-A 全選與 ORG-B 對照 fixtures。

### Rollback / forward recovery

- Schema downgrade 只適用於尚未產生新正式 decisions 的非正式環境。
- production 一旦有 005 business data，不刪除 Application／Grant／Audit；以 forward migration 修正。
- application/grant schema rollout 與 application code 採 0024 expand → policy configuration window → 0025 backfill/enforce → switch-read 順序，避免部署窗口把 null validity 誤判為有效。
- 若 Worker rollout 失敗，request-time predicate 仍拒絕 expired access；可安全重跑 sweep 收斂狀態。

## 保存與個資最小化

- Application/Grant/Batch/Audit 是授權責任歷史，依 CRM 稽核保存政策保留，不因 user revoke 或 notification failure 刪除。
- Notification payload 只保存收容所顯示名、申請／授權狀態、期限與下一步；不保存動物、草稿、回報內容。
- LINE provider raw response、id token、channel secret、access token 不進資料庫或 Audit。
- 管理列表只回傳 display name、申請時間、狀態、期限與審核必要識別；不回傳 LINE user id。
