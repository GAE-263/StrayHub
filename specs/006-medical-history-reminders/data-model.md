# Data Model：動物就醫歷史與照護提醒行事曆

## 1. 設計原則

- 所有正式資料由 PostgreSQL CRM 保存；API write payload 不接受 `organization_id`。
- 所有 tenant business table（包含 association／action）都顯式保存 `organization_id`，同時使用 application predicate、複合 foreign key 與 FORCE RLS。
- 正式時間點使用 UTC `timestamptz`；行事曆 anchor 使用收容所本地日期／時間，並保存 IANA timezone snapshot。
- 醫療紀錄與提醒系列是 current projection；修改前後內容與所有人工操作寫入既有 append-only `AuditRecord`。正式資料只封存／停止，不 hard delete。
- 週期 occurrence 預設為查詢時計算的 virtual item；只有單次覆寫或人工 action 才建立 persisted projection。
- 體重只保存管理員輸入的正數公斤值，不觸發藥量或任何醫療判斷。

## 2. 既有 Entity 擴充

### 2.1 Organization

| 欄位 | 型別 | 規則 |
|---|---|---|
| `timezone` | varchar(64) | 非空；IANA timezone；既有與新資料預設 `Asia/Taipei`。 |
| `timezone_version` | integer | 非空、預設 1；每次 timezone 變更遞增並寫 Audit。 |

驗證由 application layer 使用 `zoneinfo.ZoneInfo` 執行。未知 timezone 回可理解的 422；資料庫只保存驗證後名稱。

### 2.2 OrganizationMembership

| 欄位 | 型別 | 規則 |
|---|---|---|
| `medical_care_access` | boolean | 非空、預設 false；僅管理員可變更；SHELTER_ADMIN 實際權限永遠為 true。 |

`STAFF` 需為 active membership 且此欄為 true 才可讀／維護完整醫療資料。`VOLUNTEER` 即使誤設 true 也不得取得完整醫療權限；其存取只由單次有效指派決定。

## 3. 新增 Entity

### 3.1 MedicalRecord

保存單一動物的一筆自由文字醫療歷史 current projection。

| 欄位 | 型別 | 必填／規則 |
|---|---|---|
| `id` | UUID | PK。 |
| `organization_id` | UUID | FK Organization，tenant scope。 |
| `animal_id` | UUID | 與 organization 組成複合 FK。 |
| `occurred_at` | timestamptz | 必填，UTC instant。 |
| `occurred_timezone` | varchar(64) | 建立時 organization timezone snapshot。 |
| `record_type` | enum | `visit`、`medication`、`vaccination`、`examination`、`weight`、`surgery`、`other`。 |
| `title` | varchar(200) | trim 後 1–200 字元。 |
| `content` | text | trim 後 1–10,000 字元；保留人工原文。 |
| `clinic` | varchar(300) | nullable。 |
| `veterinarian` | varchar(200) | nullable。 |
| `weight_kg` | numeric(8,3) | nullable；`> 0`；不衍生藥量。 |
| `status` | enum | `active`、`archived`。 |
| `version` | integer | 非空、從 1 開始；每次修改／封存遞增。 |
| `created_by_user_id` | UUID | 建立者。 |
| `created_at` | timestamptz | server time。 |
| `updated_by_user_id` | UUID | 最後修改者。 |
| `updated_at` | timestamptz | server time。 |
| `archived_by_user_id` | UUID | nullable。 |
| `archived_at` | timestamptz | nullable。 |
| `archive_reason` | text | 封存時必填。 |

規則：同一天可有任意多筆，沒有覆寫型 unique constraint；排序為 `occurred_at DESC, id DESC`。修改要求 `expected_version` 與 reason，Audit 保存完整 before／after snapshot。封存後預設不出現在一般清單，但授權查詢可包含；封存資料不可再一般修改或刪除。

### 3.2 MedicalRecordMedia

| 欄位 | 型別 | 規則 |
|---|---|---|
| `id` | UUID | PK。 |
| `organization_id` | UUID | tenant scope。 |
| `medical_record_id` | UUID | 與 organization 組成複合 FK。 |
| `media_asset_id` | UUID | 與 organization 組成複合 FK。 |
| `attached_by_user_id` | UUID | 操作者。 |
| `attached_at` | timestamptz | server time。 |

唯一 `(organization_id, medical_record_id, media_asset_id)`。關聯前必須重新驗證 MediaAsset 為同 tenant、formal、sanitized、purpose 合法；只回傳短效 signed URL，不持久化 URL。第一階段接受 JPEG／PNG／WebP。

### 3.3 CareReminderSeries

保存單次或週期提醒的規則 segment。series 不預展開所有 occurrence。

| 欄位 | 型別 | 必填／規則 |
|---|---|---|
| `id` | UUID | PK，單一規則 segment。 |
| `lineage_id` | UUID | 不可變；跨「本次及未來」分段保持相同。 |
| `organization_id` | UUID | tenant scope。 |
| `animal_id` | UUID | 與 organization 複合 FK。 |
| `reminder_type` | enum | `medication`、`follow_up`、`weight`、`vaccination`、`examination`、`other`。 |
| `title` | varchar(200) | trim 後 1–200。 |
| `instructions` | text | 0–5,000；UI 標示為管理員輸入。 |
| `assignee_membership_id` | UUID | nullable；必須是同 organization active membership。 |
| `anchor_local_date` | date | 第一次執行本地日期。 |
| `anchor_local_time` | time | 第一次執行本地時間。 |
| `start_ordinal` | bigint | 此 segment 第一個全域 occurrence index，從 0 開始。 |
| `end_ordinal` | bigint | nullable；split 後舊 segment 的最後 index。 |
| `frequency` | enum | `none`、`daily`、`weekly`、`monthly`、`yearly`。 |
| `interval` | integer | `>=1`；`none` 固定為 1；每 N 月為 `monthly + N`。 |
| `end_local_date` | date | nullable；不得早於 anchor；只限制未來 occurrence。 |
| `status` | enum | `active`、`suspended`、`stopped`。 |
| `supersedes_series_id` | UUID | nullable；指向被 split 的前一 segment。 |
| `version` | integer | 非空、從 1 開始。 |
| `created_by_user_id` | UUID | 管理員。 |
| `created_at`／`updated_at` | timestamptz | server time。 |
| `updated_by_user_id` | UUID | 最後修改者。 |
| `stopped_at`／`stopped_by_user_id`／`stop_reason` | nullable | stopped 時完整填寫。 |
| `suspended_at`／`suspend_reason` | nullable | 動物非 active 時使用。 |

約束：同一 lineage 的 segment ordinal 範圍不得重疊；`frequency=none` 只允許 index 0；monthly 永久使用 anchor 的原始 day-of-month，yearly永久使用 anchor month/day。`status != active` 不再產生未來可操作 occurrence，但歷史 action 仍可讀。

### 3.4 CareReminderOccurrence

只在 occurrence 有單次修改或人工處理時建立的 current projection。

| 欄位 | 型別 | 必填／規則 |
|---|---|---|
| `id` | UUID | deterministic UUIDv5(`lineage_id`, `occurrence_index`)。 |
| `organization_id` | UUID | tenant scope。 |
| `lineage_id` | UUID | 穩定 identity scope。 |
| `series_id` | UUID | 此 occurrence 所屬 segment。 |
| `occurrence_index` | bigint | 非負、在 lineage 內不可變。 |
| `nominal_local_date`／`nominal_local_time` | date／time | 原規則算出的本地值 snapshot。 |
| `original_scheduled_at` | timestamptz | 第一次投影的 UTC instant snapshot。 |
| `scheduled_at` | timestamptz | 套用改期後的目前 UTC instant。 |
| `effective_timezone` | varchar(64) | `scheduled_at` 使用的 IANA timezone snapshot。 |
| `timezone_version` | integer | 當時 Organization timezone version。 |
| `status` | enum | `pending`、`completed`、`skipped`、`cancelled`。 |
| `version` | integer | 建立為 1；每次合法 action 遞增。virtual item response 為 0。 |
| `assignee_membership_id` | UUID | nullable；本次覆寫後的負責人 snapshot。 |
| `title_snapshot`／`instructions_snapshot`／`type_snapshot` | text／enum | 結案時保存，避免 series 後改寫歷史。 |
| `actual_completed_at` | timestamptz | nullable；completed 時保存人員確認的實際完成時間，不得晚於 `recorded_at + 5 分鐘`，未填則等於 `recorded_at`。 |
| `recorded_at` | timestamptz | nullable；completed 時由 server 保存收到回報的時間。 |
| `completed_by_user_id`／`result_note` | nullable | completed 時保存執行人與選填結果。 |
| `last_action_at`／`last_action_by_user_id` | timestamptz／UUID | current summary。 |
| `created_at`／`updated_at` | timestamptz | server time。 |

唯一 `(organization_id, lineage_id, occurrence_index)` 及 `(organization_id, id)`。`scheduled_at` 不是 identity：短月 clipping、timezone 變更與改期都不會改 id。

### 3.5 CareReminderAction

每次人工 mutation 的 append-only business event；不得 UPDATE／DELETE。

| 欄位 | 型別 | 規則 |
|---|---|---|
| `id` | UUID | PK。 |
| `organization_id` | UUID | tenant scope。 |
| `occurrence_id` | UUID | 與 organization 複合 FK。 |
| `lineage_id`／`series_id`／`occurrence_index` | UUID／UUID／bigint | 穩定查詢與歷史 snapshot。 |
| `action_type` | enum | `created_override`、`rescheduled`、`completed`、`skipped`、`cancelled`。 |
| `actor_user_id` | UUID | 實際操作者。 |
| `acted_at` | timestamptz | server time。 |
| `before_state`／`after_state` | jsonb | 安全且完整的 business snapshot。 |
| `reason` | text | skip／reschedule／cancel 必填。 |
| `result_note` | text | completed 選填。 |
| `idempotency_key` | varchar(255) | write request header。 |
| `request_fingerprint` | varchar(64) | normalized payload hash。 |

唯一 `(organization_id, actor_user_id, idempotency_key)`。相同 key + fingerprint 回原結果；相同 key + 不同 fingerprint 回 409。所有 action 與 occurrence projection、Audit 在同一 transaction commit。

## 4. 衍生 Read Models（不另作正式資料表）

### CareAgendaItem

由 active series、virtual occurrence、persisted occurrence、Animal 與 Membership projection 組成：`occurrence_id`、`version`、`animal`、`reminder_type`、`title`、`instructions`、`nominal_local_at`、`scheduled_at`、`display_local_at`、`assignee`、`status`、`bucket`、`is_virtual`、`can_act`。四個 bucket 互斥：

1. `today_pending`：收容所今天內且 status pending。
2. `overdue`：今天 local midnight 前且 status pending。
3. `today_resolved`：action 在收容所今天發生且 terminal（completed／skipped／cancelled），item 保留實際狀態；改期事件另顯示在 Timeline。
4. `next_seven_days`：明天 local midnight 起至第七日結束的 pending。

第一階段不保存提前提醒天數，也不提供 `upcoming` 視圖；所有 pending item 只依原定或改期後的 effective scheduled time 分類。

### TimelineEvent / ScheduledItem

- `TimelineEvent` 是已發生事實：care report、medical record、reminder completed／skipped／rescheduled／cancelled。
- `ScheduledItem` 是 pending／overdue occurrence。
- 同一來源使用 stable `source_id` 去重；每個 day 依 organization local date 分組。
- 舊 `reports`、`has_report`、`report_count` 保留原語意；新增 `has_activity`、`event_count` 不以 `has_report` 代替。

## 5. Recurrence 與時區規則

### 穩定 identity

- lineage 的第 n 次 occurrence 使用全域 `occurrence_index=n`，public id 為 UUIDv5。
- `nth(index)` 必須是純函式，可由 anchor、frequency、interval 直接計算，不依賴前一 occurrence。
- 「本次及未來」在目標 ordinal 前結束舊 segment，建立相同 lineage、`start_ordinal=目標` 的新 segment；既有 id 不變。

### 日期規則

- daily：anchor + `index * interval` 日。
- weekly：anchor + `index * interval * 7` 日。
- monthly：anchor 月份 + `index * interval` 月；若不存在原始 day，使用該月最後一日，後續月份恢復原始 day。
- yearly：anchor 年份 + `index * interval` 年；2/29 遇非閏年使用 2 月最後一日。
- DST gap：移至當日本地時間 gap 後第一個有效 instant。
- DST fold：採第一次 instant（`fold=0`），response 帶實際 offset。

### 長期 overdue

`last_index_before(local_now)` 以算術求最大到期 ordinal，不從 anchor 逐筆生成。每個 series 建立反向 iterator，跨 series 用 heap 依 `scheduled_at DESC, occurrence_id` 合併；terminal occurrence 由 DB 批次 overlay 並繼續取候選直到填滿 page。`total_count` 使用 ordinal 數量減 terminal、調整改期項目精確計算。cursor 至少綁定 organization、filter hash、timezone_version、sort key；scope 或 timezone 變動要求刷新。

## 6. 狀態轉移

| 目前狀態 | 動作 | 新狀態 | 必填資料 |
|---|---|---|---|
| virtual／pending | complete | completed | expected_version、Idempotency-Key；`actual_completed_at` 選填且不得晚於 `recorded_at + 5 分鐘`，未填時使用 server `recorded_at`，結果選填。 |
| virtual／pending | skip | skipped | reason。 |
| virtual／pending | cancel | cancelled | reason。 |
| virtual／pending | reschedule | pending | 新本地日期時間、reason；保存原／新時間。 |
| virtual／pending | edit this | pending | 本次 title／instructions／assignee／time override。 |
| virtual／pending | edit this and future | 舊 segment 截止 + 新 segment | scope、目標 ordinal、new rule、reason。 |
| active／suspended series | stop future | stopped | reason。 |
| completed／skipped／cancelled | 任一正常 action | 不變 | 409，回最新安全狀態。 |

到期時間經過只改變 read-model bucket，不寫入 terminal 狀態。吃藥逾期仍是 `pending/overdue`，不能推導「漏藥」。

## 7. Authorization 與動物狀態

- SHELTER_ADMIN：完整讀寫、series 管理、capability 管理。
- active STAFF + `medical_care_access=true`：完整讀取、建立／更正／封存 medical record、處理 occurrence；不修改 series future rule。
- VOLUNTEER：只對同 tenant、目前指派給自己的 occurrence 使用 assigned API；不得取得 clinic、veterinarian、weight、附件、其他紀錄、其他 occurrence 或完整 Timeline。
- PLATFORM_ADMIN：只在既有 support scope lifecycle 中操作單一 organization 並要求理由。
- Animal `status != active`：禁止新 medical reminder series；尚未到期 series 衍生為 suspended/review-required，保留歷史並讓管理員明確停止。動物狀態變更 application service 應在同 transaction 寫 suspension／Audit；為兼容既有未集中寫入路徑，Agenda 查詢仍以 animal status 作第二道 guard。

跨租戶或不可見 id 統一使用不洩漏存在性的 404／403 策略。重要拒絕明確包含跨收容所識別、缺少醫療 capability、志工未被指派、membership／capability 已撤銷，以及對已結案 occurrence 的衝突提交；主 transaction rollback 後，以重新套用單一 organization scope 的獨立 terminal Audit transaction 寫入。既有 `GET /v1/management/audit` 查詢 `MedicalRecord`、`CareReminderSeries`、`CareReminderOccurrence` 或 `CareReminderAction` 時，也必須重新檢查 medical capability，不能只依一般 STAFF role。

## 8. 索引與約束

- `medical_record (organization_id, animal_id, occurred_at DESC, id DESC)`；另建符合既有 PostgreSQL 能力的 title/content search index。
- `care_reminder_series (organization_id, status, animal_id, anchor_local_date)`。
- `care_reminder_series (organization_id, assignee_membership_id, status)`。
- exclusion／application validation 確保同 lineage segment ordinal 範圍不重疊。
- `care_reminder_occurrence (organization_id, scheduled_at, status, id)`。
- `care_reminder_occurrence (organization_id, assignee_membership_id, status, scheduled_at)`。
- `care_reminder_action (organization_id, occurrence_id, acted_at DESC)`。
- idempotency unique、lineage ordinal unique、所有 tenant association 複合 FK。

所有新表 `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY`，policy 使用 transaction-local `app.current_org_id`，runtime role 不得 bypass。

## 9. Migration 與 Backfill

1. 新增 Organization timezone／timezone_version，既有資料 backfill `Asia/Taipei` 後設 NOT NULL。
2. 新增 Membership capability，全部 backfill false；SHELTER_ADMIN 的權限由 policy／service implicit true，不需批次改欄位。
3. 建立 medical／series／occurrence／action／media association table、enum／check／index／複合 FK。
4. 建立並 FORCE RLS，擴充 runtime-role A/B isolation matrix。
5. canonical seed 新增兩收容所、管理員、授權／未授權員工、志工、active／archived animal、短月份／長期 daily／各狀態 occurrence。
6. Timeline 日界線改為 organization local half-open interval，再轉 UTC 查詢；不得使用 UTC midnight 或 `time.max`。

Migration 不回填虛擬 occurrence，也不啟動 Worker materialization。
