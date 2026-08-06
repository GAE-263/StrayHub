# 資料模型：志工日常照護回報與動物近期歷程

**用途**：定義 Phase 1 的業務實體、關係、租戶邊界、驗證規則與狀態轉換。這不是 SQL 或完整資料庫 Schema；欄位名稱是供實作與測試對齊的業務語意。

## 共通資料治理規則

- 每一筆非公開業務資料都必須有 `shelter_id` 或等價的明確 Shelter 歸屬；平台治理資料與 `PLATFORM_ADMIN` 的授權上下文使用平台級 `PLATFORM` Scope。
- 所有讀取、新增、修改、搜尋、封存、Draft／Temporary Media 刪除與圖片存取都必須取得已驗證的 `ActorScope`，再由 CRM 邊界判定 `shelter_id`；本 Feature 不提供批次匯出。
- 使用者提交的 `shelter_id`、Animal 識別、Shelter Number、QR Token 或網址只能是候選輸入，不得直接成為授權依據。
- Shelter Number 只在同一 Shelter 內唯一；查詢、QR 解析與正式關聯都必須同時帶入 Shelter 範圍。
- 原始回報內容、原始照片、Volunteer Note、原始 AI 輸出與人工修正不可互相覆蓋。
- Signed URL、MinIO URL 與 Cloud Storage URL 是暫時存取位置，不是永久識別；永久關係只使用 Object Key 與 CRM 關聯。

## Database Access 與 Persistence 邊界

### Model 分層

- **Pydantic Model**：只負責 API Request／Response 的輸入輸出驗證與序列化，不直接代表資料庫持久化模型。
- **SQLAlchemy Model**：負責 PostgreSQL Database Mapping、關聯與持久化狀態，不直接作為公開 API Schema。
- **Domain／Application Layer**：負責角色能力、Organization／Shelter Scope、動物選擇、回報送出重新驗證、AI Job 交易流程與 Audit Record。
- **Controlled Repository**：負責所有租戶資料查詢與寫入；每個操作都必須接收已驗證的 `Organization Scope`，不得讓呼叫端自由省略或改寫範圍。

不使用 SQLModel。API Schema、Database Mapping 與多租戶關係必須保持可分別演進與測試。

### Organization Scope

本計畫以 `Organization` 作為資料存取層的租戶鍵，對應功能規格中的 Shelter／收容所。一般 Shelter 操作的每個 Repository 操作都必須同時具備：

1. 已驗證的 Actor Context。
2. 有效的 Organization／Shelter Membership。
3. 操作所需的角色能力。
4. 目標資源的 Organization／Shelter 歸屬。

前端、LIFF、QR Token、網址、Shelter Number 或任意 Request 欄位提供的 Organization 識別只能作為候選條件，不能取代已驗證 Scope。

`PLATFORM_ADMIN` 使用獨立的平台級 `PLATFORM` Scope，不建立 Shelter Membership；其內建最高權限角色可直接管理所有 Shelter 的非公開資料，不需逐次額外授權。資料存取層仍必須明確辨識 `PLATFORM` Scope，並對所有跨 Shelter 操作寫入 Audit Record。

### 租戶 Defense in Depth

- Application Layer 由受控 Repository 強制套用 Organization Scope。
- SQLAlchemy 關聯與資料庫約束確保跨 Organization 關聯不能成立。
- 同一 Organization 內的 Shelter Number 使用 Composite Unique Constraint；不同 Organization 可以重複。
- 需要跨租戶一致性的關聯使用包含 Organization 的 Composite Foreign Key 或等價的資料庫一致性防護。
- PostgreSQL 以 Row-Level Security（RLS）搭配交易內設定的 Organization Scope 防止繞過 Repository 的讀寫。Runtime Role 不擁有資料表、沒有 `BYPASSRLS`，租戶資料表使用 `FORCE ROW LEVEL SECURITY`。一般 Request／Worker Transaction 只能由後端設定單一 `app.current_org_id`；只有已重新驗證的 `PLATFORM_ADMIN` Transaction 可設定 `app.platform_scope` 並同步寫入 Audit Record。Request、Token、QR Code 或 Postback 不能直接設定 Database Scope；Worker 不取得平台級 Scope。
- Database Scope Setter 在 `AsyncSession` transaction 內以參數化 `set_config('app.current_org_id', :org_id, true)` 或受控的 `set_config('app.platform_scope', 'true', true)` 設定 RLS Context。`is_local=true` 是強制條件；transaction 結束後 scope 必須自動清除，不得殘留至 connection pool 的下一次使用。缺少 scope 時租戶資料預設不可存取。
- `tests/isolation`、Repository 測試、migration 測試與 GCP Demo 驗證共同確認 A／B Organization 不可互相讀寫或推測存在性。

### Migration 管理

- 所有資料表、Constraint、Index、Row-Level Security Policy、`FORCE ROW LEVEL SECURITY`、交易內 Scope 設定與 Schema 變更都由 `services/api/migrations/` 的 Alembic Migration 管理。
- 新環境必須能從空 PostgreSQL 執行完整 migration；不得依賴手動建立資料表或手動操作資料庫介面作為唯一建置方式。
- Migration 變更必須包含可驗證的 upgrade 路徑；需要回復的變更另提供明確 downgrade 或替代遷移策略。
- Cloud SQL Demo 必須重新執行 migration 驗證，不能以本機資料庫現況代替。

## 實體

### Shelter / Tenant

代表一個收容所、私人動物之家或中途機構。

主要資料：名稱、機構代碼、地址或服務區域、聯絡資訊、啟用狀態、初始管理員關聯、建立時間、更新時間與公開資料設定。

驗證規則：機構代碼在平台範圍內不可造成歧義；停用 Shelter 不刪除歷史資料；停用後一般使用者不能登入或建立新業務資料；跨 Shelter 管理只由明確授權的 Platform Administrator 執行。

### User、Platform Administrator、Shelter Administrator、Staff Member、Volunteer

代表平台與收容所使用者。User 保存身分狀態、角色與可用服務狀態；一般 Shelter 角色的每一次資料存取由 Shelter Membership／Authorization Scope 判定，`PLATFORM_ADMIN` 則由平台級 `PLATFORM` Scope 判定。

主要關係：Platform Administrator 可管理平台層 Shelter，且不建立任何 Shelter Membership；Shelter Administrator、Staff Member 與 Volunteer 必須有至少一個 Shelter Membership；Volunteer 可以有多個有效授權，但同一時間只能有一個綁定 Session 的 Active Shelter Context。

驗證規則：停用帳號不能登入、讀取或建立新資料；未綁定 Volunteer 不能建立匿名正式回報；一般角色不足不能依網址、識別碼、QR Token 或輸入條件擴大範圍；`PLATFORM_ADMIN` 的平台級角色本身即提供所有 Shelter 的管理與資料存取能力，但仍須留下 Audit Record。

### Session Record / Refresh Token / Active Shelter Context

Session Record 代表本系統的登入狀態；Refresh Token 只保存雜湊值並可輪替，Access Token 為短效憑證。Active Shelter Context 代表目前 Session 明確選擇的 Organization；Webhook Session 代表 LINE Webhook 依可信 LINE Binding 建立的受控事件處理上下文。

驗證規則：受保護 Request 必須重新驗證 Session、User、Organization、Membership、角色與 Active Shelter Context；`PLATFORM_ADMIN` 的平台級 Request 改驗證 `PLATFORM` Scope。Session 或 Refresh Token 撤銷、User／Membership／Organization 停用後立即拒絕存取。Active Shelter Context 必須來自有效 Membership、綁定 Session 且不得由 QR Code 或 Request 任意覆寫；切換時留下 Audit Record，Draft 不得跨 Organization 移動。Webhook Session 必須綁定 `system_user_id`、唯一有效 Shelter Context 與目前權限狀態。

### Shelter Membership / Authorization Scope

描述使用者與 Shelter 的所屬或明確授權關係，包含角色、狀態、授權來源、生效時間與失效時間（若適用）。

驗證規則：每次 CRM 操作都由已驗證身分取得有效 Scope；失效或停用的 Membership 不得授權新操作；`PLATFORM_ADMIN` 不需 Shelter Membership 或逐次額外授權，但所有跨機構操作都必須留下 Audit Record。

### Cage / Area

代表 Shelter 內的籠舍與區域。可供志工辨識位置，但不能取代 Animal 正式識別或 Shelter 範圍。

### Animal

代表 CRM 中一隻動物，具有不可變正式識別與 Shelter 歸屬。

主要資料：正式識別、Shelter、名稱、目前照片、Shelter Number（可選）、Cage／Area、目前狀態、公開狀態、建立與更新時間。

驗證規則：名稱與照片可重複；動物狀態若不允許回報，建立與送出都必須拒絕；名稱、照片、Shelter Number、籠位或區域變更不得改變既有回報的正式 Animal 關聯。

### Shelter Number

代表機構使用的收容編號。與 Shelter 組成唯一查詢範圍，可被人員搜尋與印在 QR 標示上。

驗證規則：同一 Shelter 內唯一；不同 Shelter 可以相同；重複、修正或缺少時不得自行猜測；歷史回報保存當時的顯示快照，但正式關聯仍使用 Animal 正式識別。

### Active Shelter Context

代表志工目前正在操作的 Shelter Context，以及 Draft、Animal、QR Token、Reportable Scope 與 Active Context 的 Organization 不一致事件。

主要資料：Volunteer、目前 Shelter、Session、開始時間、最後活動時間、來源通道、阻擋原因與處理結果。

驗證規則：Volunteer 可以有多個 Shelter Membership，但同一時間只能有一個 Active Shelter Context；系統不以 GPS、IP、裝置、時間重疊或地理距離推測地點。Organization 不一致時必須阻擋送出並保留 Draft；不得讓單筆 Report 同時歸屬多個 Shelter。

### Daily Reportable Scope / Animal Assignment

代表特定日期、Volunteer 或群組可回報的 Animal 集合。第一階段支援個別 Animal、Cage／Area 與指定 Volunteer，不包含完整班次排班。

驗證規則：範圍必須屬於同一 Shelter；送出時重新驗證是否仍有效；未在 Scope 內的 Animal 不得因 QR Code 或 Shelter Number 搜尋而自動取得回報資格。

### LINE User Binding

代表經 LINE 官方驗證的 `line_user_id` 與既有 User、Membership 的綁定關係。LINE 身分驗證成功不自動建立正式權限；未綁定或 Membership 無效時不得建立正式 Draft 或 Care Report。Webhook 必須先透過 Binding 取得 `system_user_id`，再解析唯一有效 Webhook Session 或唯一有效 Shelter Context；多個候選不得自動選擇。

### Webhook Session

代表 LINE Webhook 在完成 Signature 驗證後，依 `line_user_id`、LINE User Binding、`system_user_id` 與 Shelter Context 建立的受控處理上下文，不取代一般使用者 Session。

主要資料：`id`、`system_user_id`、LINE Binding、Organization／Shelter Context、建立時間、最後互動時間、撤銷時間、狀態與來源事件。

驗證規則：只有一個有效 Webhook Session 時才可直接進入 Membership 與權限檢查；沒有 Session 時只有一個有效 Shelter Context 才能建立新的 Webhook Session；多個 Session 或多個有效 Shelter Context 時不得自動選擇，應要求透過 LIFF 明確選擇。Webhook Session 不得由 Postback、QR Code、裝置、GPS、IP 或時間重疊自動改綁。

### Rich Menu、Quick Reply / Postback Action

代表 Bot 的環境化入口設定與逐題操作選項。Rich Menu Action 只提供流程入口；Quick Reply 顯示名稱與 Observation Option 的穩定 Code 分離，Postback payload 只能作候選輸入，不是 Organization、角色、Animal 或 Draft 授權資料。

### LINE Webhook Event

代表 LINE Messaging API 傳送的 Message、Image、Postback 或必要綁定事件。

主要資料：`webhook_event_id`、Event Type、Processing Status、Redelivery Flag、Received At、Processed At、Error Code、Failure Reason 與必要的 Message ID。不得長期保存不必要的完整敏感 Payload。

驗證規則：先以未修改的原始 Request Body 與 `X-Line-Signature` 驗證，再解析事件；事件依 `webhook_event_id` 冪等。非法簽章不查詢 CRM、不下載圖片、不建立或更新 Draft、Care Report 或 AI Job。

### QR Code / QR Token

代表貼於籠位或動物資料卡的候選查詢標示。QR Token 是非祕密候選參考值，不是登入憑證或授權證明。

主要資料：Token 參考值、Shelter、候選 Animal、啟用／撤銷狀態、建立人、建立時間與重新產生原因。

驗證規則：解析結果唯一且屬同一 Shelter；使用者 Scope、QR 所屬 Shelter 與 Animal 所屬 Shelter 必須一致；修改或複製 Token 不能繞過授權。

### Daily Care Report

代表一次已送出的人工照護回報。

主要資料：Animal、Shelter、Volunteer、回報來源、回報時間、照護／散步完成狀態、進食、飲水、活動、排泄、行為、外觀、原始建立時間、最後修改時間、動物名稱與 Shelter Number 快照、保存狀態，以及 AI dispatch 狀態 `not_requested`／`pending_enqueue`／`enqueued`／`enqueue_failed`。

驗證規則：必須有已驗證 Volunteer、有效 Shelter Scope、正式 Animal 關聯；同一 Animal 同日可有多筆；原始內容不可被 AI 或更正覆蓋；重複送出必須可辨識。Volunteer 可在建立後 24 小時內修改自己的內容、Photo 與 Note，但不能修改 Animal 綁定；Animal 綁定更正由 Shelter Administrator 或授權 Staff Member 處理。

### Report Draft / Draft Answer / Draft Media

代表尚未送出的回報草稿。

主要資料：`id`、`opaque_token`、Organization、已確認 Animal、Volunteer、Membership、`current_step`、已完成答案、Draft Media 關聯、心得、`last_interaction_at`、`expires_at`、狀態、建立時間與更新時間。

驗證規則：Draft 固定歸屬單一 Organization、Volunteer、Membership 與 Animal；重新開啟及每次 Postback／Image Event 都重新驗證 Animal、Shelter、Volunteer、Scope 與狀態。每名志工在單一 Organization 同時間只保留一筆 active Draft；建立新回報時提示繼續或放棄既有 Draft。取消或過期 Draft 不得建立正式 Care Report，且任何狀態不一致都不得改綁其他 Animal 或 Shelter。

Draft 狀態至少包含：`selecting_animal`、`confirming_animal`、`answering_feeding`、`answering_water`、`answering_activity`、`answering_elimination`、`answering_behavior`、`answering_special_status`、`awaiting_media`、`awaiting_note`、`reviewing`、`submitting`、`submitted`、`cancelled`、`expired`。後端依目前狀態驗證合法轉移，不信任 Postback 的 `step`。

若答案以 JSON 保存，必須由版本化的 Pydantic／Domain Validator 驗證類別、穩定 Code、Draft 狀態與可用選項；每次答案修改保存時間、來源 Event 與前後摘要，送出後由 Care Report 保存不可變的原始答案快照。

### Photo、Object Metadata、Volunteer Note

Photo 代表已清理並重新編碼的正式照片；Object Metadata 描述 Object Key、用途、內容類型、大小、Checksum、`exif_removed`、建立時間與來源；Temporary Media 代表尚未提交的暫存照片；Volunteer Note 代表志工原始心得文字。

驗證規則：正式 Photo 必須先完成大小、MIME、實際格式、解碼、EXIF 清理、重新編碼與 Checksum；含原始 EXIF 的檔案不得進入正式 Object Storage，AI 只能讀取清理後圖片。Temporary Media 不得簽發正式 Signed URL，成功或失敗後都必須清理。每個 Photo 與 Note 都有 Shelter、Report 與來源關聯；圖片取用要再次驗證 Scope；資料庫不保存永久 Signed URL；照片模糊、光線不足或 AI 無法判讀是觀察結果，不是人工回報失敗。

### Observation Category / Observation Option

代表可維護的標準化觀察語彙。Option 保存穩定識別、顯示名稱、說明、顯示順序、啟用狀態與適用 Shelter 或平台範圍。

驗證規則：停用 Option 不刪除歷史使用內容；志工能使用非診斷性描述；管理異動留下 Audit Record。

Foundational 邊界：US1／US2 開始前即建立 Category／Option 的持久化模型、Migration、平台預設 Seed、穩定 Code、歷史顯示快照，以及依 Organization 取得 Effective Options 的唯讀 Repository／Service。US4 只增加 Organization Extension、管理命令、排序、停用、Audit 與管理畫面，不重建另一套基礎語彙。

### AI Processing Job / AI Observation

AI Processing Job 代表待處理、處理中、成功、失敗或無效的非同步工作；AI Observation 代表從 Photo 或 Volunteer Note 衍生的描述性訊號。

主要關係：一筆 Report 可有多個 Job 與 AI Observation；同一 Report、Job Type 與版本組合具有唯一冪等關係。每個 Job 必須保存非空 Provider、Model Name、Model Version／Snapshot、Prompt Template ID、Prompt Version、Output Schema Version、Job Created／Started／Completed At、原始 AI 輸出、驗證結果、失敗原因與 Retry Count。每個 Observation 必須可追溯至清理後 Photo 或 Note，並將 `raw_ai_output`、`validated_ai_observation` 與 `human_review_result` 分開保存。

驗證規則：Report 先以獨立 transaction 保存，成功後才以另一個 transaction 冪等建立 Job；Job 建立或 AI 處理失敗都不影響 Report 保存。Report 處於 `pending_enqueue` 或 `enqueue_failed` 且沒有有效 Job 時，可由 reconciliation 安全補建，且不得產生重複 Job。AI 不得診斷、計分、排序、改變狀態、修改 Animal 或覆蓋原始資料；無效或禁用內容不能成為正式觀察結果。

Foundational 邊界：`AIProcessingJob` 的持久化模型、Migration、版本欄位、狀態、唯一冪等關係、Repository 與 reconciliation query 在 US2 前完成。US5 才建立 Worker claim／retry、AI Adapter、`AIObservation`、輸出驗證與人工覆核流程；MVP 不依賴 Worker 或 AI 成功。

### Animal Timeline

代表以 Shelter 與 Animal 為範圍的時間序列檢視，不是另一份可獨立修改的正式業務資料。

主要內容：近 14 個曆日每日是否有回報、回報筆數、每筆 Report、Photo、Note、AI Observation、人工修正、快照與 Audit Record；更早歷史可查詢。

驗證規則：沒有回報的日期顯示「當日無回報」；不得將空白、未觀察或 AI 失敗當成正常；工作人員只能查看已授權 Shelter。

### Audit Record

代表重要資料與權限異動的稽核紀錄。

主要資料：操作者、角色、來源通道、Shelter 範圍、操作類型、目標實體、時間、修改前後摘要、原因、結果與跨機構授權資訊（適用時）。

驗證規則：跨機構管理、動物綁定更正、權限／Scope 異動、AI 人工確認、公開狀態與重要刪除／停用都必須留下紀錄；一般使用者不能修改稽核紀錄。

## 主要關係

```text
Shelter
├── PLATFORM Scope ── Platform Administrator
├── Shelter Membership / Authorization Scope ── User / Role
├── Active Shelter Context ── Volunteer / Session
├── Webhook Session ── LINE User Binding / Active Shelter Context
├── LINE User Binding ── LINE User ID / User / Membership
├── Rich Menu ── Postback Action / Conversation State
├── LINE Webhook Event ── Draft / Message / Image / Postback
├── Animal ── Shelter Number / Cage / Area / QR Code
├── Daily Reportable Scope ── Volunteer / Animal
├── Report Draft ── Draft Answer / Draft Media
├── Daily Care Report ── Photo / Volunteer Note / AI Processing Job
│   └── AI Observation ── source Photo or Volunteer Note
├── Animal Timeline ── derived view of Reports and Audit Records
├── Observation Category ── Observation Option
└── Audit Record
```

## 關鍵狀態轉換

- **Shelter**：`pending_setup` → `active` → `suspended`；停用不刪除既有歷史。
- **User／Membership**：`invited` → `active` → `disabled`；非 active 不得建立或讀取業務資料。
- **Webhook Session**：`created` → `active` → `revoked`／`expired`；建立前必須完成 LINE Binding、唯一 Context 與權限驗證。
- **Report Draft**：`selecting_animal` → `confirming_animal` → `answering_feeding` → `answering_water` → `answering_activity` → `answering_elimination` → `answering_behavior` → `answering_special_status` → `awaiting_media` → `awaiting_note` → `reviewing` → `submitting` → `submitted`；任一步驟可依規則回到前一步、`cancelled` 或 `expired`。無效轉移必須拒絕；未提交 Draft 可由建立者放棄或由系統依設定過期清理。
- **LINE Webhook Event**：`received` → `signature_rejected`／`duplicate_ignored`／`processing` → `processed`／`failed`；同一 `webhook_event_id` 不得重複產生業務寫入。
- **Daily Care Report**：`saved` → `amended` → `archived`；Volunteer 可在 24 小時內修改內容、Photo 與 Note；Animal 綁定更正由授權人員執行；正式回報不 Hard Delete，原始內容永久保留，所有修改與封存另留 Audit Record。
- **Temporary Media / Photo**：`temporary` → `processed` → `attached` 或 `failed`；未提交 Temporary Media 可刪除或清理；正式 Photo 不 Hard Delete，只能標記不可使用或封存。
- **AI Dispatch / Processing Job**：Report `not_requested`／`pending_enqueue` → `enqueued` 或 `enqueue_failed`；成功建 Job 後，Job `pending` → `running` → `succeeded`／`failed`／`invalid`。Reconciliation 可由 `pending_enqueue`／`enqueue_failed` 冪等補建 Job；重試不改變原始 Report。
- **QR Code**：`active` → `revoked`；撤銷後不能帶入回報流程。

## 跨實體驗證規則

1. Report、Draft、Photo、Note、AI Job、AI Observation、QR Code、Scope、Session、Webhook Session、Active Shelter Context 與 Audit Record 的 Shelter 必須與其關聯 Animal／User／來源事件一致；`PLATFORM_ADMIN` 的平台治理資料使用 `PLATFORM` Scope。
2. 同一收容編號在不同 Shelter 可並存；任何查詢只在 ActorScope 允許的 Shelter 中執行。
3. 任何建立、修改、Draft／Temporary Media 刪除或 Care Report Archive 動作都要檢查 ActorScope、資源 Shelter、資源狀態與角色能力；正式 Care Report、正式 Photo 與 AI 原始輸出不得 Hard Delete；本 Feature 不提供批次 Export。
4. 任何物件檔案操作都要檢查 Object Key 的 Shelter 關聯，不接受前端任意 Object Key 作為授權。
5. Timeline 由 CRM 正式資料重建，不作為第二份事實來源。
6. Repository 以 `AsyncSession` 執行資料存取；Transaction 邊界必須涵蓋 Scope 驗證與正式資料寫入，避免驗證後範圍被替換。
7. Pydantic Request／Response Model 不得直接被當作 SQLAlchemy 持久化 Model；兩者轉換由 Application／Domain 邊界負責。
8. 每個租戶 transaction 必須在第一次租戶資料查詢前由 Database Scope Setter 設定 transaction-local scope；未設定、跨 scope、transaction 結束後重用 connection 或 Worker 嘗試平台 scope 都必須拒絕。
