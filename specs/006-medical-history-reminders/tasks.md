# Tasks：動物就醫歷史與照護提醒行事曆

**Input**：`specs/006-medical-history-reminders/` 內的 `spec.md`、`plan.md`、`research.md`、`data-model.md`、`contracts/` 與 `quickstart.md`

**Tests**：本功能涉及正式醫療資料、週期規則、人工處理結果、多租戶隔離與明確成功標準，因此每個 User Story 都包含先失敗再實作的測試任務。

**Organization**：任務按 User Story 分階段，使每個故事都能獨立實作、驗收與交付。

**Implementation status (2026-08-17)**：核心功能與自動化 release gate 已完成；Ruff、pytest、mypy、Vitest、production Playwright、axe、visual、OpenAPI、build 與三輪 Agenda production DB 效能均通過。驗收期間發現並修正 Agenda 每區只顯示前 50 筆的漏列問題，真實 UI／API 對 500 筆 manifest 的遺漏／誤列為 0、分類正確率 100%。T097 仍只因正式 10 名管理員＋10 名授權工作人員人工驗收尚未執行而維持未完成；本次新增 T098～T104 對應平台／收容所管理權限邊界。

## Format：`[ID] [P?] [Story] Description`

- **[P]**：在同一階段的必要前置完成後，可在不同檔案平行進行。
- **[US1]～[US6]**：對應 `spec.md` 的使用者故事；US6 為本次新增的 P0 權限邊界。
- 每個任務均包含明確檔案路徑；若列出多個路徑，代表該任務必須保持這些邊界同步。

---

## Phase 1：Setup（共用契約）

**Purpose**：先建立唯一可產生型別的 HTTP 契約，避免後端、前端與測試各自定義不同資料形狀。

- [X] T001 將 `specs/006-medical-history-reminders/contracts/medical-care.openapi.yaml` 的 additive paths、schemas 與錯誤回應合併至 canonical `specs/001-volunteer-care-report/contracts/openapi.yaml`，同步擴充 Organization timezone／effective capabilities／Membership medical access 欄位，保留既有 Timeline 相容性且不接受 client `organization_id`
- [X] T002 由 canonical OpenAPI 重新產生並檢查 `packages/contracts/src/openapi.ts`，執行 `npm --prefix packages/contracts run generate` 與 `npm --prefix packages/contracts run check`，不得手改 generated file

**Checkpoint**：canonical contract 與 TypeScript generated contract 已同步。

---

## Phase 2：Foundational（阻塞所有故事的基礎）

**Purpose**：建立收容所時區、醫療 capability、共用資料表、RLS、稽核與前端 contract boundary。

**⚠️ CRITICAL**：本階段完成前，不開始任何 User Story 實作。

### 先建立失敗測試

- [X] T003 [P] 建立 feature paths／schemas、snake_case payload、camelCase path parameters 與 generated type drift 的失敗 contract tests 於 `tests/contract/test_medical_care_contract.py`
- [X] T004 [P] 建立空資料庫 bootstrap、前一 Alembic head upgrade、Organization timezone／Membership capability backfill 與新 tenant tables FORCE RLS 的失敗測試於 `tests/integration/test_medical_care_migration.py`
- [X] T005 [P] 建立 IANA timezone、local-day half-open range、DST gap／fold 與 timezone version cursor 的失敗單元測試於 `tests/unit/test_organization_timezone.py`
- [X] T006 [P] 建立 SHELTER_ADMIN implicit access、STAFF capability、VOLUNTEER deny、PLATFORM_ADMIN support scope，以及醫療 resource Audit query 重新檢查 capability 的失敗安全測試於 `tests/security/test_medical_care_authorization.py`

### 共用實作

- [X] T007 [P] 在 `services/api/app/persistence/models/identity.py` 為 Organization 新增 `timezone`／`timezone_version`，並為 OrganizationMembership 新增 `medical_care_access`
- [X] T008 [P] 在 `services/api/app/persistence/models/medical_care.py` 建立 MedicalRecord、MedicalRecordMedia、CareReminderSeries、CareReminderOccurrence 與 CareReminderAction models、enum、version、`actual_completed_at`／server `recorded_at` 及 tenant composite constraints，不建立提前提醒欄位
- [X] T009 更新 `services/api/app/persistence/models/__init__.py` 與 SQLAlchemy metadata exports，使新 models 可由 Alembic、repositories 與 tests 載入
- [X] T010 建立 `services/api/migrations/versions/0027_medical_history_reminders.py`，完成 identity 欄位 backfill、business tables、indexes、composite FKs、idempotency／lineage unique constraints 及 ENABLE／FORCE RLS policies
- [X] T011 [P] 在 `services/api/app/domain/organization_timezone.py` 實作 IANA 驗證、local datetime→UTC、half-open day range、DST deterministic policy 與 timezone-version cursor guard，使 T005 通過
- [X] T012 [P] 在 `services/api/app/domain/medical_care_access.py` 實作 role／active membership／capability／assigned-volunteer 的 effective permission policy，使 T006 通過
- [X] T013 在 `services/api/app/application/organization_management.py` 與 `services/api/app/api/organization_management.py` 加入 timezone 與 `medical_care_access` 的管理、驗證、version conflict 與 Audit mutation，禁止 STAFF／VOLUNTEER 自行授權
- [X] T014 在 `apps/web/app/(management)/shelters/page.tsx` 加入收容所時區與 STAFF 醫療權限的管理 UI、正體中文狀態與 capability 撤銷確認
- [X] T015 在 `services/api/app/application/medical_care_audit.py` 封裝同 transaction mutation Audit，以及跨收容所識別、缺少 capability、未指派／已撤權與 terminal conflict 在 rollback 後重新套用單一 tenant scope 的拒絕 Audit，不在 log／error 洩漏不可見 payload
- [X] T016 [P] 在 `apps/web/features/medical-care/types.ts`、`apps/web/features/medical-care/api.ts` 與 `apps/web/features/medical-care/mapping.ts` 建立由 generated contract 推導的 DTO、`apiFetch` client、query serialization、snake_case mapping、AbortController 及 403／409／載入失敗映射
- [X] T017 在 `tests/fixtures/medical_care.py` 建立兩收容所、五種權限身分、active／inactive 動物、醫療紀錄與提醒系列的可重用 fixture factory，提供固定 seed 的 100 隻動物／500 mixed occurrences builder；同時在 `scripts/seed_medical_care.py` 提供可重複執行的 `base`／`agenda-e2e` CLI profile 及帶輸出檔路徑值的 `--expected-output` option，manifest 為 `today_pending`／`overdue`／`today_resolved`／`next_seven_days` 每筆保存 `occurrence_id`、bucket、動物名稱、完整收容編號、提醒類型、標題、organization-local 預定時間、狀態及各 bucket 精確 total；`agenda-e2e` 必須要求 `STRAYHUB_MEDICAL_E2E_SEED_ALLOWED=1` 並拒絕 `STRAYHUB_TEST_DATABASE_URL` host 非 `127.0.0.1`／`localhost`，讓 Python、Playwright 與 SC-003 使用同一安全資料真值，並讓 T003～T006 與 migration 測試通過

**Checkpoint**：schema、時區、能力判定、稽核與 contract boundary 可供所有故事共用，且基礎測試全數通過。

---

## Phase 3：User Story 1－記錄並查詢動物醫療歷史（Priority：P1）🎯 MVP

**Goal**：管理員與獲授權 STAFF 能在單一動物名下快速建立、搜尋、更正及封存自由文字醫療歷史，保留同日多筆、體重、圖片附件與完整 Audit。

**Independent Test**：只啟用 medical-record endpoints 與動物醫療歷史 UI，建立同日多筆紀錄、依日期／類型／文字查詢、修改與封存；確認原文、公斤體重、圖片、建立者、before／after 及跨租戶拒絕皆正確，不需要提醒功能。

### Tests for User Story 1（先寫並確認失敗）

- [X] T018 [P] [US1] 為 medical-record list／create／get／patch／archive 的 request、response、錯誤與不接受 `organization_id` 建立 contract tests 於 `tests/contract/test_medical_records_contract.py`
- [X] T019 [P] [US1] 為同日多筆、日期／類型／文字搜尋、選填公斤體重、修改 version、封存與 Audit before／after 建立 integration tests 於 `tests/integration/test_medical_records.py`
- [X] T020 [P] [US1] 為跨 tenant animal／record／media id、未授權 STAFF、VOLUNTEER deep link、formal media、JPEG／PNG／WebP allowlist、EXIF 清理、signed URL，以及醫療 Audit query capability 建立測試於 `tests/security/test_medical_record_media_scope.py`
- [X] T021 [P] [US1] 為一分鐘最短表單、選填欄位、同日列表、組合篩選、成功空狀態、載入／附件／409 錯誤與未送出文字保留建立 Vitest 於 `apps/web/features/medical-care/MedicalHistory.test.tsx`

### Implementation for User Story 1

- [X] T022 [US1] 在 `services/api/app/persistence/repositories/medical_record_repository.py` 實作帶 organization predicate 的 create／get／search／update／archive、穩定 cursor、row lock 與 MedicalRecordMedia association 查詢
- [X] T023 [US1] 在 `services/api/app/application/medical_record_service.py` 實作 animal／capability revalidation、欄位與正數公斤驗證、optimistic version、封存 reason、Audit before／after 及無 hard delete 的 transaction
- [X] T024 [US1] 在 `services/api/app/application/medical_record_media_service.py` 整合既有 Media formalization／sanitization／purpose／短效 URL，只接受 JPEG／PNG／WebP，確保圖片附件失敗不把文字儲存呈現為空白成功
- [X] T025 [US1] 在 `services/api/app/api/medical_records.py` 實作 contract 定義的 list／create／get／patch／archive endpoints、具名 Pydantic models 與不洩漏存在性的錯誤
- [X] T026 [US1] 在 `services/api/app/main.py` 註冊 medical-record router，並確認 runtime OpenAPI 與 canonical `specs/001-volunteer-care-report/contracts/openapi.yaml` 一致
- [X] T027 [US1] 在 `apps/web/features/medical-care/api.ts` 與 `apps/web/features/medical-care/mapping.ts` 加入 medical-record CRUD、filters、signed image、`/v1/management/audit?resource_type=MedicalRecord&resource_id=...` 只讀查詢與 stale conflict mapping
- [X] T028 [P] [US1] 在 `apps/web/features/medical-care/MedicalHistoryFormDialog.tsx` 實作發生時間、類型、標題、自由文字、選填診所／獸醫／公斤體重／安全圖片與修改 reason 表單，明示內容為人工輸入且不計算藥量
- [X] T029 [P] [US1] 在 `apps/web/features/medical-care/MedicalHistoryList.tsx`、`apps/web/features/medical-care/MedicalHistoryEntry.tsx` 與 `apps/web/features/medical-care/MedicalHistoryAuditPanel.tsx` 實作同日多筆排序、日期／類型／文字 filters、安全圖片、受 medical capability 保護的只讀 before／after Audit、空／錯誤／封存狀態
- [X] T030 [US1] 在 `apps/web/app/(management)/animals/[animalId]/timeline/page.tsx` 掛載 medical history list 與新增／修改／封存 dialogs，同時保留既有 care-report Timeline 行為
- [X] T031 [US1] 在 `apps/web/e2e/medical-history.spec.ts` 建立一分鐘新增、同日多筆、搜尋、更正／封存、附件失敗、權限與跨 tenant deep-link 的 Playwright 驗收

**Checkpoint**：US1 可獨立作為最小 MVP 展示與驗收；沒有 reminder tables 的業務操作也能完成醫療歷史流程。

---

## Phase 4：User Story 2－建立單次與週期照護提醒（Priority：P1）

**Goal**：管理員能在一分鐘內建立單次、每天、每週、每月、每 N 月與每年提醒，正確處理短月、DST、停止、單次修改與本次及未來分段。

**Independent Test**：使用預先存在的動物，透過 series API／表單建立各種 recurrence，直接驗證純 recurrence output、series segment 與 occurrence identity；不需要 Agenda 頁或人工完成流程。

### Tests for User Story 2（先寫並確認失敗）

- [X] T032 [P] [US2] 為 `nth(index)`、單次／日／週／月／N 月／年、29～31 日 clipping、2/29、DST、無結束日、UUIDv5 lineage identity 與 ordinal jump 建立單元測試於 `tests/unit/test_care_recurrence.py`
- [X] T033 [P] [US2] 為 series create／get／stop、不接受提前提醒欄位或跨 tenant assignee、只改本次、本次及未來 split、已結案歷史不變與 inactive animal guard 建立 integration tests 於 `tests/integration/test_care_reminder_series.py`
- [X] T034 [P] [US2] 為 series 與 occurrence edit endpoints、recurrence schema、edit scope、version conflict 及停止語意建立 contract tests 於 `tests/contract/test_care_reminder_series_contract.py`
- [X] T035 [P] [US2] 為條件式 recurrence 欄位、每三個月顯示、29～31 日規則提示與 anchor 保存、管理員輸入標示、scope 選擇及一分鐘流程建立 Vitest 於 `apps/web/features/medical-care/ReminderFormDialog.test.tsx`

### Implementation for User Story 2

- [X] T036 [P] [US2] 在 `services/api/app/domain/care_recurrence.py` 實作可直接計算 `nth`／first／last ordinal 的純函式、短月份／閏年／DST policy、deterministic occurrence UUID 與最多 366 日 range guard
- [X] T037 [P] [US2] 在 `services/api/app/persistence/repositories/care_reminder_repository.py` 實作同 tenant series segment、lineage ordinal、virtual overlay、single override、stop 與 optimistic row-lock queries
- [X] T038 [US2] 在 `services/api/app/application/care_reminder_service.py` 實作管理員 create／get／stop、recurrence 驗證、active animal／assignee revalidation、拒絕提前提醒欄位、Audit 與無結束日 series 邏輯
- [X] T039 [US2] 在 `services/api/app/application/care_reminder_service.py` 實作「只修改這一次」occurrence override 與「本次及未來」同 lineage split-series transaction，保證已結案 ordinal 與 snapshots 不變
- [X] T040 [US2] 在 `services/api/app/api/care_reminders.py` 實作 series create／get／stop 與 occurrence patch endpoints、具名 Pydantic models、version conflict 與實際 local／UTC 日期回應
- [X] T041 [US2] 在 `services/api/app/main.py` 註冊 care-reminders router，並以 runtime OpenAPI test 對齊 canonical contract
- [X] T042 [US2] 在 `services/api/app/application/management_animal_service.py` 將 animal 轉為非 `active` 的既有異動流程接到 series suspension／Audit，並在提醒查詢保留 status guard 以涵蓋舊寫入路徑
- [X] T043 [US2] 在 `apps/web/features/medical-care/api.ts` 與 `apps/web/features/medical-care/mapping.ts` 加入 series CRUD、原始 anchor／recurrence 顯示、scope mutation 與 409 latest-state mapping，日期 occurrence 不在 client 重算
- [X] T044 [P] [US2] 在 `apps/web/features/medical-care/ReminderFormDialog.tsx` 實作類型、標題、指示、第一次日期時間、負責人、不重複／日／週／月／每 N 月／年與結束日表單，不呈現提前提醒設定
- [X] T045 [P] [US2] 在 `apps/web/features/medical-care/SeriesScopeDialog.tsx` 實作「只修改這一次」／「本次及未來」的明確選擇、影響說明、reason 與 focus restore
- [X] T046 [US2] 在 `apps/web/app/(management)/animals/[animalId]/page.tsx` 加入「建立提醒」、查看／停止 active series 與 suspended review 入口，STAFF 不顯示 series 管理操作
- [X] T047 [US2] 在 `apps/web/e2e/care-reminder-series.spec.ts` 建立單次／每月／每三月一分鐘流程、31 日 anchor 規則、單次／未來修改、停止及 inactive animal 的 Playwright 驗收，短月實際日期由 T032／T033 驗證

**Checkpoint**：US2 的 recurrence 與 series 管理可由 API、純 domain tests 與動物頁獨立驗收，尚不依賴今日 Agenda 或 action flow。

---

## Phase 5：User Story 3－從今日待辦與行事曆掌握工作（Priority：P1）

**Goal**：授權使用者能在 agenda-first `/care-calendar` 迅速辨識今天待處理、逾期、今天已處理與未來七日，並依指定日期與條件篩選。

**Independent Test**：載入 100 隻動物／500 筆預建提醒，在不同 browser timezone 下驗證後端收容所日期、四區互斥、精確筆數、組合篩選、指定日期、空／錯誤狀態與 p95 目標，不需要實際提交 action。

### Tests for User Story 3（先寫並確認失敗）

- [X] T048 [P] [US3] 為 care-agenda／care-calendar 的 organization timezone、四 bucket、filters、cursor、366 日限制與 conflict response 建立 contract tests 於 `tests/contract/test_care_agenda_contract.py`
- [X] T049 [P] [US3] 使用 T017 的 100／500 builder，為今天待處理／逾期／今天已處理／未來七日互斥、completed／skipped／cancelled 狀態保留、不提供 upcoming、effective scheduled date 分組、組合篩選、短月 actual date、UTC 前一日與 timezone-version cursor 建立 integration tests 於 `tests/integration/test_care_agenda.py`
- [X] T050 [P] [US3] 使用 T017 的固定 100 隻動物／500 mixed occurrences builder，在 `tests/performance/test_care_agenda_performance.py` 建立包含 Agenda service、資料庫查詢、recurrence projection 與 response serialization 的基準測試；每輪先暖機 5 次、連續量測 100 次並完整執行 3 輪，要求每輪 p95 ≤ 1 秒且分類正確率 100%，輸出 p50／p95／max、查詢數、資料筆數與環境資訊，另驗證長期 daily series 精確 overdue count 及 cursor 無重複／遺漏
- [X] T051 [P] [US3] 為四區互斥、今天已處理的實際 terminal 狀態、卡片識別資訊、組合 filters、server local date、短效 animal photo／expiry、空／loading／error／403／409、缺照片／負責人建立 Vitest 於 `apps/web/features/medical-care/CareAgenda.test.tsx`

### Implementation for User Story 3

- [X] T052 [US3] 在 `services/api/app/persistence/repositories/care_reminder_repository.py` 實作 range 候選、terminal／rescheduled overlay、effective scheduled date、assignee／animal／type／status filters、tenant-scoped animal photo reference 與穩定 cursor 的批次查詢
- [X] T053 [US3] 在 `services/api/app/application/care_agenda_service.py` 實作 organization-local `today_pending`／`overdue`／`today_resolved`／`next_seven_days`、每 series ordinal arithmetic、反向 iterator／heap overdue merge、精確 total count、effective scheduled calendar grouping，以及透過既有 MediaAccessService 取得 scoped animal photo 短效 URL／expiry，不提供 upcoming 或全量 materialization
- [X] T054 [US3] 在 `services/api/app/api/care_reminders.py` 實作 `GET /v1/management/care-agenda` 與 `GET /v1/management/care-calendar`，每次重驗 capability，回 timezone／version／目前 filters／animal photo expiry，並使改期 action 只按 acted date 出現在 Timeline
- [X] T055 [US3] 在 `apps/web/features/medical-care/api.ts` 與 `apps/web/features/medical-care/mapping.ts` 加入 Agenda／Calendar query、各 bucket cursor、latest-request guard 與 context-switch 清除
- [X] T056 [P] [US3] 在 `apps/web/features/medical-care/CareAgendaFilters.tsx` 實作指定日期、動物、類型、負責人、狀態、目前條件與符合筆數，提供上一日／下一日／回今天
- [X] T057 [P] [US3] 在 `apps/web/features/medical-care/ReminderCard.tsx` 與 `apps/web/features/medical-care/ReminderSection.tsx` 實作 mobile-first 卡片、短效照片與可辨識 alt／fallback、完整收容編號、完成／略過／取消的實際文字／icon／badge 狀態及每區空狀態
- [X] T058 [US3] 在 `apps/web/features/medical-care/CareAgenda.tsx` 組合「今天待處理／已逾期／今天已處理／未來七天」四個互斥區段、指定日期 Agenda、載入／錯誤／重試與 status live region，不使用第三方 calendar library
- [X] T059 [US3] 建立 `apps/web/app/(management)/care-calendar/page.tsx`，並更新 `apps/web/components/management/AppSidebar.tsx`、`apps/web/components/management/MobileNavigation.tsx` 與 `apps/web/components/management/icon-map.ts` 加入具 capability 的「照護行事曆」入口
- [X] T060 [US3] 在 `apps/web/e2e/fixtures/medical-care.ts` 從檔案位置解析 repository root，以 `mkdtemp` 建立隔離暫存目錄，先驗證 `STRAYHUB_TEST_DATABASE_URL`／`DATABASE_URL`／`STRAYHUB_MEDICAL_E2E_SEED_ALLOWED`，再依 `API_INTERNAL_URL`（預設 `http://127.0.0.1:8000`）輪詢 `/healthz`；health／環境失敗須回報 setup error。以不經 shell 的 `execFile`、repo-root `cwd` 執行 T017 `uv run python -m scripts.seed_medical_care --profile agenda-e2e --expected-output` 並傳入 manifest 路徑、解析 JSON、等待資料可查及提供清理函式；在 `apps/web/e2e/care-agenda.spec.ts` 將 suite 設為 serial、於 `beforeAll` seed 一次且 `afterAll` 清理，逐一比對四區完整 occurrence ID 集合、唯一性與 total 以證明分類 100% 正確，並驗收可見卡片欄位、100／500 資料的今天已處理狀態、照片、filters、指定日期、browser timezone、空／失敗狀態及未授權 deep link

**Checkpoint**：US3 可只讀地回答全收容所「今天要做什麼」，所有日期分類由後端權威時區決定。

---

## Phase 6：User Story 4－回報提醒的實際執行結果（Priority：P1）

**Goal**：授權 STAFF／管理員及被指派志工能對單次 occurrence 明確完成、略過、改期或取消，保存人工結果且防止重複結案。

**Independent Test**：直接對預建 virtual／persisted occurrence 執行各 action，驗證人員確認的 `actual_completed_at`、server `recorded_at`、reason、狀態互斥、改期 snapshots、冪等、雙人競爭、stale 409 與志工最小 projection；提醒逾期本身不得寫 action。

### Tests for User Story 4（先寫並確認失敗）

- [X] T061 [P] [US4] 為 virtual／pending 到 completed／skipped／cancelled、reschedule 仍 pending、terminal 不可重結案、實際完成時間預設與不得晚於 `recorded_at + 5 分鐘`、逾期不寫結果建立單元測試於 `tests/unit/test_care_reminder_state.py`
- [X] T062 [P] [US4] 為 complete 的 `actual_completed_at`／server `recorded_at`／actor，以及 skip／reschedule／cancel 的 reason／result、before／after action、Audit 與原／新時間建立 integration tests 於 `tests/integration/test_care_reminder_actions.py`
- [X] T063 [P] [US4] 為相同／不同 Idempotency-Key payload、virtual insert race、expected_version、兩人同時結案與 latest safe 409 建立並行測試於 `tests/integration/test_care_reminder_concurrency.py`
- [X] T064 [P] [US4] 為被指派志工最小 projection、complete／skip、未指派／撤權／跨 tenant／完整 Timeline deny 建立安全測試於 `tests/security/test_assigned_care_authorization.py`
- [X] T065 [P] [US4] 為三步完成、選填實際完成時間與預設、reason 條件、busy 防重送、409 保留輸入、focus trap／Escape／restore 與 assigned minimal UI 建立 Vitest 於 `apps/web/features/medical-care/ReminderActionDialog.test.tsx`

### Implementation for User Story 4

- [X] T066 [P] [US4] 在 `services/api/app/domain/care_reminder_state.py` 實作合法狀態轉移、required reason／result 規則與 terminal conflict，不將 overdue 轉成醫療結果
- [X] T067 [US4] 在 `services/api/app/persistence/repositories/care_reminder_repository.py` 實作 occurrence projection race recovery、unique lineage ordinal、`FOR UPDATE`、append-only action 與 actor-scoped idempotency fingerprint 查詢
- [X] T068 [US4] 在 `services/api/app/application/care_reminder_service.py` 實作 complete／skip／reschedule／cancel transaction、virtual materialization、選填且不得晚於 `recorded_at + 5 分鐘` 的 `actual_completed_at`、server `recorded_at` 預設／snapshot、version、Idempotency-Key 與 Audit
- [X] T069 [US4] 在 `services/api/app/application/assigned_care_service.py` 實作每次重新驗證 active membership／assignee／tenant 的最小 read model，只允許被指派志工 complete／skip
- [X] T070 [US4] 在 `services/api/app/api/care_reminders.py` 實作 management occurrence actions endpoint，complete 接受選填 `actual_completed_at`，回 action id、latest occurrence、actor、actual／recorded time 與不洩漏的 409／404
- [X] T071 [US4] 在 `services/api/app/api/assigned_care.py` 實作 assigned list／detail／actions endpoints，complete 接受選填 `actual_completed_at` 並回 server `recorded_at`，response 嚴格排除醫療歷史、體重、診所、附件、series 與其他 occurrence
- [X] T072 [US4] 在 `services/api/app/main.py` 註冊 assigned-care router，並擴充 runtime OpenAPI 與 response-schema tests 防止最小 projection 漂移
- [X] T073 [P] [US4] 在 `apps/web/features/medical-care/ReminderActionDialog.tsx` 實作完成／略過／改期／取消的單一 lifted dialog、三步完成、選填實際完成時間、原因／結果欄位、busy、409 latest state 與 focus 管理
- [X] T074 [P] [US4] 建立 `apps/web/app/(volunteer)/assigned-care/[occurrenceId]/page.tsx` 與 `apps/web/features/medical-care/AssignedCareTask.tsx`，只渲染 assigned contract 的最少資料與含選填實際完成時間的 complete／skip 操作
- [X] T075 [US4] 在 `apps/web/features/medical-care/ReminderCard.tsx` 與 `apps/web/features/medical-care/CareAgenda.tsx` 接入 lifted action dialog，結案後只更新對應 bucket 並重新驗證 server counts
- [X] T076 [US4] 在 `apps/web/e2e/care-reminder-actions.spec.ts` 建立三步完成、晚完成的 actual／recorded time、略過、取消、改期、重送、雙人 stale conflict、逾期非漏藥及志工指派邊界的 Playwright 驗收

**Checkpoint**：US4 的每筆結果皆由人工明確提交、最多一個目前有效 terminal state，並具有可追溯 action／Audit。

---

## Phase 7：User Story 5－查看單一動物今天發生什麼（Priority：P2）

**Goal**：在既有動物 Timeline 與動物頁同時呈現 care reports、medical records、reminder actions 與 pending／overdue occurrences，清楚區分 actual 與 scheduled。

**Independent Test**：建立同日多來源事件與未結案提醒，查閱至少近 14 個 organization-local days，驗證所有來源可找到、排序／標示正確，並逐一驗證五種今日摘要狀態。

### Tests for User Story 5（先寫並確認失敗）

- [X] T077 [P] [US5] 為既有 reports 相容欄位、additive events／scheduled／open_reminders discriminated union 與 organization timezone 建立 contract tests 於 `tests/contract/test_medical_timeline_contract.py`
- [X] T078 [P] [US5] 為 care report、medical record、complete／skip／reschedule／cancel、pending／overdue 合併、同日排序、14 日 local range 與 query count 建立 integration tests 於 `tests/integration/test_medical_timeline.py`
- [X] T079 [P] [US5] 為 actual／scheduled 文字標示、舊 `has_report` 語意、五種今日摘要、空／error 與 browser timezone 不改日建立 Vitest 於 `apps/web/features/animal-timeline/AnimalTimelineMedicalCare.test.tsx`

### Implementation for User Story 5

- [X] T080 [P] [US5] 在 `services/api/app/persistence/repositories/timeline_repository.py` 加入 tenant-scoped medical records、reminder actions 與 virtual open occurrences 的批次查詢，使用 organization-local half-open UTC range
- [X] T081 [US5] 在 `services/api/app/application/timeline_service.py` 合併四種來源、按 local day／actual instant 排序、去重 stable source id，保留舊 reports 欄位並新增 has_activity／events／scheduled／open_reminders
- [X] T082 [US5] 在 `services/api/app/api/animal_timeline.py` 以具名 discriminated Pydantic models 回傳 additive Timeline contract，授權失敗時不回任何 child medical payload
- [X] T083 [P] [US5] 在 `apps/web/features/animal-timeline/timelineMapping.ts` 加入 generated DTO 到 actual／scheduled UI union 的集中 mapping，不以 `has_report=false` 推導整日無事件
- [X] T084 [P] [US5] 在 `apps/web/features/animal-timeline/TimelineDaySection.tsx` 與 `apps/web/features/animal-timeline/TimelineEventCard.tsx` 實作先顯示 pending／overdue、再顯示 actual events 的文字／icon 區分與同日多筆列表
- [X] T085 [US5] 在 `apps/web/features/animal-timeline/AnimalTimeline.tsx` 整合 medical events、reminder actions、scheduled items、14 日 filters、長期 medical search 入口及各種空／error 狀態
- [X] T086 [US5] 在 `apps/web/features/medical-care/AnimalTodaySummary.tsx` 實作 no activity、events/no todos、pending、overdue、error 五態，完全使用 API `local_today`／day state
- [X] T087 [US5] 在 `apps/web/app/(management)/animals/[animalId]/page.tsx` 掛載 AnimalTodaySummary、今日未結案入口與醫療／提醒快速動作，不在 browser 端自行判定今天
- [X] T088 [US5] 在 `apps/web/e2e/animal-medical-timeline.spec.ts` 建立同日多來源、actual／scheduled、五種摘要、14 日、時區邊界、空／失敗與未授權 deep link 的 Playwright 驗收

**Checkpoint**：單一動物頁可在 30 秒內回答「今天發生什麼」及「還有什麼沒完成」，且來源與計畫不混淆。

---

## Phase 8：User Story 6－區分平台與收容所管理權限（Priority：P0）

**Goal**：只有 `PLATFORM_ADMIN` 能建立、啟用、停用及跨收容所管理；`SHELTER_ADMIN` 只看到並操作目前收容所的帳號、時區與區域，且任何直接 request 都由後端 403 防線拒絕。

**Independent Test**：以 `local-shelter-admin-a` 登入管理頁，確認不顯示建立收容所表單，直接送出建立 request 回 403 且沒有收容所、初始管理員或部分設定副作用；再以 `local-platform-admin` 建立待啟用收容所與初始管理員，確認成功、Audit 可追溯，並確認其他收容所範圍不可操作。

### Tests for User Story 6（先寫並確認失敗）

- [X] T098 [P] [US6] 擴充 `tests/contract/test_organization_management_contract.py`，驗證組織建立、初始管理員、狀態與目前收容所帳號／時區／區域路由的 request 不接受 client `organization_id`，固定 403／安全錯誤契約，並驗證 `/v1/auth/me` 以 `User.roles`／platform scope 表示 `PLATFORM_ADMIN`，`LoginOrganization.role` 僅表示收容所 Membership role。
- [X] T099 [P] [US6] 建立 `tests/integration/test_organization_creation_authorization.py`，驗證 SHELTER_ADMIN 建立收容所必須回 403 且不建立租戶、初始管理員、政策或部分設定；驗證 PLATFORM_ADMIN 可成功建立收容所與初始管理員並寫入建立／membership Audit；另驗證 SHELTER_ADMIN 可修改目前收容所時區、帳號與區域，STAFF 修改上述設定回 403，且拒絕後由獨立 Audit transaction 保存操作者、時間、目前收容所 scope、結果與原因。
- [X] T100 [P] [US6] 建立 `tests/security/test_organization_lifecycle_authorization.py`，驗證直接網址、手動 body、過期角色／context 與其他收容所識別不能擴張管理範圍；驗證 SHELTER_ADMIN 對其他 organization 的帳號／時區／區域操作回 403／404，拒絕回應不洩漏平台或其他租戶資料，且所有拒絕事件均有不含不可見 payload 的 durable Audit。
- [X] T101 [P] [US6] 擴充 `apps/web/app/(management)/shelters/page.test.tsx`，先驗證 PLATFORM_ADMIN 看得到「建立收容所」表單，SHELTER_ADMIN 只看到目前收容所管理，且角色切換／403 狀態不殘留舊表單或資料。

### Implementation for User Story 6

- [X] T102 [US6] 在 `services/api/app/api/organization_management.py` 與 `services/api/app/application/organization_management.py` 拆分 organization mutation policy：建立／初始管理員／啟用／停用／跨收容所操作套用 `_require_platform`；目前 organization 的帳號／時區／區域操作只允許 SHELTER_ADMIN；STAFF／VOLUNTEER 拒絕。所有判定必須先於寫入，成功與拒絕均依既有 Audit lifecycle 記錄，並保持 atomic rollback。
- [X] T103 [US6] 在 `apps/web/app/(management)/shelters/page.tsx` 沿用既有 `/v1/auth/me` 與 active shelter context 的角色資料；只有 `role === "PLATFORM_ADMIN"` 渲染建立收容所與平台層級選擇，SHELTER_ADMIN 只渲染目前收容所帳號、時區與區域管理，並以安全狀態處理 403／載入失敗，不以 UI 隱藏取代 API 授權。
- [X] T104 [US6] 建立 `apps/web/e2e/organization-management.spec.ts`，以 local-shelter-admin-a 驗證表單隱藏、直接建立請求 403／無副作用及目前收容所範圍，以 local-platform-admin 驗證建立收容所與初始管理員成功及 Audit 可追溯。

**Checkpoint**：平台／收容所管理權限可由 API、管理頁與真人操作獨立驗收；SHELTER_ADMIN 無法建立租戶，PLATFORM_ADMIN 可完成完整建立流程。

**執行優先序備註**：US6 是本次新增的 P0 待辦。US1～US5 的既有任務已完成，因此 T098～T104 應優先於 T097 執行；T097 必須等 US6 權限驗收完成後，才能作為最終 release gate。

---

## Phase 9：Polish & Cross-Cutting Concerns

**Purpose**：補齊跨故事的種子資料、隔離、效能、內容安全、responsive／a11y 與完整品質證據。

- [X] T089 [P] 擴充 Foundational 階段既有的 `scripts/seed_medical_care.py`，新增可重複執行且無參數時採用的 `full` quickstart profile，補齊兩收容所權限矩陣、短月／長期 daily、各 action 狀態與多來源 Timeline；保留 T017 的 `agenda-e2e` 固定 seed、loopback／opt-in guard，以及含內部 ID、畫面可見欄位與 bucket totals 的 `--expected-output` manifest 契約，不改變 US3／SC-003 已使用的測試前置
- [X] T090 [P] 擴充 `tests/isolation/test_cross_tenant_resource_matrix.py`，涵蓋 medical record、media association、series、occurrence、action、agenda、calendar、timeline、assigned endpoints 及 runtime DB role 的零洩漏矩陣
- [X] T091 [P] 在 `tests/integration/test_medical_care_audit.py` 驗證建立／修改／封存／series split／停止／指派／完成／略過／改期／取消／capability／timezone，以及跨 tenant、缺 capability、未指派、已撤權、terminal conflict 均有 durable Audit；並驗證醫療 resource Audit query 重新檢查 capability
- [X] T092 [P] 在 `tests/performance/test_care_agenda_performance.py` 增加數萬 ordinal long-running daily series、terminal／rescheduled exceptions、全 cursor walk、精確 total count、無全量 materialization 與 query-count 上限
- [X] T093 [P] 在 `apps/web/features/medical-care/medicalCareBoundary.test.tsx` 驗證 context switch 清除舊 tenant 資料、舊 request 不覆蓋新 filters、401 refresh、403、409 保留草稿與所有 loading／empty／failure 狀態
- [X] T094 [P] 在 `tests/security/test_medical_content_boundaries.py` 驗證體重不改提醒或藥量、管理員文字不呈現為系統建議、逾期不自動宣稱給藥／漏藥，且沒有診斷、處方、庫存、外部通知或 AI side effect
- [X] T095 將 `/care-calendar`、動物頁／Timeline、medical／reminder dialogs 與 assigned-care 納入 `apps/web/e2e/p0-responsive.spec.ts`、`apps/web/e2e/p0-keyboard.spec.ts`、`apps/web/e2e/p0-a11y.spec.ts` 與 `apps/web/e2e/p0-visual.spec.ts` 的 360／768／1024／1440、focus、axe、文字非只靠顏色及 visual baselines
- [X] T096 在 `tests/integration/test_empty_database_bootstrap.py` 與 `tests/contract/test_generated_contract_types.py` 補齊 0027 空庫／upgrade、canonical/runtime/generated drift 與完整 feature quality regression
- [ ] T097 依 `specs/006-medical-history-reminders/quickstart.md` 先以 repo-root、loopback test DB、seed opt-in、`API_INTERNAL_URL` 及 `/healthz` 前置執行 `uv run ruff check .`、`uv run ruff format --check .`、`uv run pytest`，再執行 mypy、Vitest、Playwright、axe、visual 與 OpenAPI check；依第 10 節執行三輪 Agenda 效能量測；至少邀請 10 名管理員驗收 SC-001／SC-002／SC-009，另以 T017 manifest 讓至少 10 名授權工作人員分別計時驗收 SC-003／SC-004，SC-003 以畫面可見欄位、重複筆數及 bucket totals 核對且每人均須在 120 秒內，不要求辨識內部 ID；Playwright 另以 occurrence IDs 證明無遺漏／重複及分類 100%，SC-004 至少 9 人於三步內完成；依第 12 節記錄 SC-010 的平台管理員／收容所管理員角色可見性、403／無副作用與成功建立結果；將指令、版本、匿名樣本、時間、步驟、expected／actual、遺漏／誤列、求助、通過率與證據連結取代「待執行」內容
  - 2026-08-16 狀態：自動化與三輪效能已通過；1 名管理員及 1 名工作人員的 agent 探索操作已留存，但不計正式樣本。正式樣本仍為管理員 0／10、工作人員 0／10，故不得勾選。證據：[`evidence/t097-validation-2026-08-16.md`](evidence/t097-validation-2026-08-16.md)。

**Checkpoint**：所有成功標準、憲章門檻與跨故事風險都有可重複的自動或人工證據。

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 Setup
    ↓
Phase 2 Foundational（阻塞全部故事）
    ├──→ Phase 3 US1 醫療歷史 ───────────────┐
    └──→ Phase 4 US2 週期提醒 ──┬──→ Phase 5 US3 Agenda ──┐
                               └──→ Phase 6 US4 結果回報 ─┤
US1 + US2 + US4 ───────────────────────────→ Phase 7 US5 Timeline
US1～US5 完成範圍 ─────────────────────────→ Phase 9 Polish
Foundational ─────────────────────────────→ Phase 8 US6（可與 US1～US5 平行）
```

### User Story Dependencies

- **US1（P1）**：只依賴 Foundational；可最先完成並形成 MVP。
- **US2（P1）**：只依賴 Foundational；可與 US1 平行，提供 recurrence／series 基礎。
- **US3（P1）**：依賴 US2 的 series、recurrence 與 virtual occurrence；只讀 Agenda 不依賴 US4 action。
- **US4（P1）**：核心 action API 依賴 US2；管理端卡片整合 T075 另依賴 US3，志工 assigned flow 不依賴 US3。
- **US5（P2）**：依賴 US1 的 medical records、US2 的 scheduled occurrence 及 US4 的 actual action events；可在 US3 之前開始 repository／mapping，但完整驗收需上述來源完成。
- **US6（P0）**：只依賴既有 organization management、authentication 與 active context；可與 US1～US5 平行，且不應等待醫療功能完成。

### Within Each User Story

1. 先完成該故事所有測試任務並確認針對尚未實作行為失敗。
2. domain／repository 或純 UI primitives 可依 `[P]` 平行。
3. models／repository 先於 application service，service 先於 API。
4. generated contract／API mapping 先於 page integration。
5. story 最後執行 Playwright independent test，再進入 Checkpoint。

---

## Parallel Execution Examples

### User Story 1

```text
平行：T018 contract、T019 integration、T020 security、T021 frontend tests
平行：T028 MedicalHistoryFormDialog、T029 MedicalHistoryList／Entry
收斂：T022 → T023／T024 → T025 → T026／T027 → T030 → T031
```

### User Story 2

```text
平行：T032 recurrence、T033 integration、T034 contract、T035 frontend tests
平行：T036 pure recurrence domain、T037 repository
平行：T044 ReminderFormDialog、T045 SeriesScopeDialog
收斂：T038 → T039 → T040 → T041／T043 → T046 → T047
```

### User Story 3

```text
平行：T048 contract、T049 integration、T050 performance、T051 frontend tests
平行：T056 filters、T057 card／section
收斂：T052 → T053 → T054／T055 → T058 → T059 → T060
```

### User Story 4

```text
平行：T061 state、T062 action、T063 concurrency、T064 security、T065 frontend tests
平行：T066 domain、T073 management dialog、T074 volunteer page
收斂：T067 → T068／T069 → T070／T071 → T072／T075 → T076
```

### User Story 5

```text
平行：T077 contract、T078 integration、T079 frontend tests
平行：T080 repository、T083 mapping、T084 day／event components
收斂：T080 → T081 → T082；T083／T084 → T085 → T086／T087 → T088
```

### User Story 6

```text
平行：T098 contract、T099 integration、T100 security、T101 frontend tests
平行：T102 backend authorization、T103 shelter management UI（均依賴對應測試先建立）
收斂：T102／T103 → T104 organization-management Playwright
```

---

## Implementation Strategy

### MVP First：User Story 1

1. 完成 Phase 1 Setup。
2. 完成 Phase 2 Foundational。
3. 完成 Phase 3 US1。
4. 停止擴張，依 US1 Independent Test 驗證同日多筆、查詢、更正／封存、體重、圖片與跨租戶隔離。
5. 若驗收通過，即可先交付可追溯的簡單醫療歷史 MVP。

### Incremental Delivery

1. **Foundation + US1**：先取代散落醫療記事。
2. **US2**：加入可靠的單次／週期規則，但尚不改變既有歷史。
3. **US3**：提供跨動物的只讀今日 Agenda／Calendar。
4. **US4**：加入人工結果、並行防重與志工最小指派流程。
5. **US5**：把所有來源整合到單一動物 Timeline／今日摘要。
6. **US6**：收斂平台／收容所管理權限，先完成 403、無副作用與前端表單可見性驗收。
7. **Polish**：完成 100／500、長期 daily、隔離、a11y、visual 與全品質 gate。

### Scope Discipline

- 不新增藥量計算、診斷、結構化處方、庫存、外部通知、完整排班、帳務、任意文件或 AI。
- 第一階段附件只沿用 JPEG／PNG／WebP 安全圖片管線；PDF／Office 文件另立 specification。
- 不新增 Worker materialization；所有未結案 occurrence 可由 series + exception／action 重建。
- 每個 Checkpoint 都可停止並驗收，不必等到 US5 才能取得前一故事的價值。

## Notes

- `[P]` 只代表檔案與前置依賴允許平行，不代表可略過「測試先失敗」門檻。
- 每完成一個任務或緊密邏輯群組即執行對應最小測試並提交，避免跨故事大批變更。
- 現有 dirty worktree 內容屬於使用者；實作時只修改本任務列出的範圍並保留無關變更。
- 若實作發現需求會改變醫療資料可見性、任意文件安全或外部通知範圍，先回到 specification／plan，不在任務內自行擴張。
