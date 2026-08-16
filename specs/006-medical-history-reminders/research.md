# Phase 0 Research：動物就醫歷史與照護提醒行事曆

本研究以既有 FastAPI／PostgreSQL CRM、Next.js 管理工作台、動物 Timeline、Media、Audit、Active Shelter Context、RLS 與 OpenAPI 產生流程為基線。所有設計未知事項均已收斂，沒有未決問題。

## 1. 功能邊界與既有架構整合

**Decision**：維持 `services/api`、`services/worker`、`apps/web`、`packages/contracts` 四個既有 workspace；正式醫療紀錄、提醒系列、單次結果與權限都寫入 PostgreSQL CRM。Next.js 只提供管理與指派任務介面，本功能不建立第二套資料來源，也不引入新的服務或外部行事曆供應商。

**Rationale**：專案已具備 Organization scope、Animal、User／Membership、Audit、Media、Timeline、管理 shell 與完整本機驗證流程。新增平行服務會增加租戶隔離、資料對帳與部署成本，也不符合使用者要求的簡單可維護 MVP。

**Alternatives considered**：

- 使用第三方行事曆或排程 SaaS：第一階段不需要外部通知或雙向同步，會增加憑證、失敗與隱私邊界。
- 將提醒存在瀏覽器或 Next.js：無法跨人員交班、稽核或由 CRM 重建，違反 Constitution。

## 2. 收容所時區與「今天」的權威來源

**Decision**：在 `Organization` 新增 IANA `timezone`，既有與新收容所預設 `Asia/Taipei`，由後端使用 Python `zoneinfo` 驗證。所有正式 instant 仍以 UTC 保存與傳輸；提醒系列保存本地 anchor date／time，未來 occurrence 每次依目前 Organization timezone 投影。已結案事件另外保存當時 timezone、local date／time 與 UTC instant snapshot。今日、逾期、未來七天及 Timeline 日界線全部由後端依 Organization timezone 計算，前端不得用瀏覽器時區重新分類。

**Rationale**：現有 `Organization` 沒有 timezone，Timeline repository 以 UTC midnight 切日，會讓台灣凌晨事件落在前一日。IANA zone 可支援未來非台灣收容所與日光節約時間；本地 anchor 可在 timezone 設定改變後自然重算未來事項，過去 snapshot 則不被改寫。

**Alternatives considered**：

- 全平台固定 `Asia/Taipei`：目前可運作，但與規格中的收容所時區假設不一致，且未來難以遷移。
- 只存 UTC recurrence：每月某日本地時間在 timezone／DST 改變後會漂移，不符合行事曆直覺。
- 由瀏覽器決定今天：不同裝置可能把同一事件分到不同日期，不能作正式交班依據。

日光節約時間規則固定為：不存在的本地時間移到該日第一個有效 instant；重複的本地時間採第一次出現並在 response 顯示實際 offset。閏年 2 月 29 日在非閏年使用 2 月最後一日，後續閏年恢復 2 月 29 日。

## 3. 週期提醒的 occurrence 策略

**Decision**：保存一筆 `CareReminderSeries` 作正式規則，使用純 domain recurrence 函式在查詢時產生 virtual occurrences；只有完成、略過、改期、取消或單次覆寫時才持久化 `CareReminderOccurrence` 與 append-only `CareReminderAction`。不預先無限展開 occurrence，也不依賴 Worker 才能看到待辦。

每個 virtual occurrence 使用不可變 `series_lineage_id + occurrence_index` 產生 deterministic UUIDv5；未異動版本為 0。第一次 mutation 以該 id 建立 occurrence current projection，並寫入 action、Audit 與 idempotency record。原日期、短月 clipping、改期或 timezone 變更不改變 identity；「本次及未來」分段後仍沿用 lineage 與全域 ordinal。行事曆查詢單次最多 366 日、結果 cursor 分頁；agenda 對逾期 occurrence 以 ordinal 算術直接求候選範圍，再以 heap 合併各 series 並 overlay 已結案 occurrence，不從 series anchor 逐日盲目掃描。逾期總數以每個 series 的到期 ordinal 數減去 terminal exceptions，再納入仍逾期的改期項目精確計算。驗收規模為 500 筆 occurrence，另以長期 daily series 驗證逐頁無重複、無遺漏且不會無限展開。

**Rationale**：不設結束日的每日提醒無法安全地預先建立全部 occurrence。純查詢投影可由 series 與 action 重建、沒有 Worker 落後造成漏提醒的問題；只持久化例外與結果也能保留完整人工歷史。

**Alternatives considered**：

- 建立提醒時預展開一年：一年後仍需補資料，修改 series 需要大量重寫，且無期限 series 沒有自然上限。
- Worker 每分鐘 materialize：可提供實體 occurrence id，但 Worker 中斷會直接影響核心待辦可見性，對沒有外部通知的 MVP 不值得。
- 只保存 `next_due_at`：無法同時呈現每日提醒的今天、逾期與未來七天，也無法保留每次獨立結果。

## 4. 短月份、週期編輯與 series lineage

**Decision**：recurrence 採 `frequency = none | daily | weekly | monthly | yearly` 加正整數 `interval`；每三個月表示 `monthly + interval=3`。series 永久保存原始 anchor day／time，短月份只調整該次 occurrence，不修改 anchor。

- 「只修改這一次」建立或更新 occurrence override。
- 「修改這一次及未來」在目標 nominal occurrence 前結束舊 series，建立帶 `supersedes_series_id` 的新 series；已結案 occurrence 與 action 不變。
- 「停止後續所有提醒」將 series 設為 stopped，不刪除歷史。
- 動物進入不可建立日常待辦的狀態時，series 進入 suspended review；管理員可結束或在動物重新啟用後恢復。

**Rationale**：split-series 可讓未來規則改變而不重寫過去；單次 override 與 series edit scope 對應使用者在行事曆產品中熟悉的心智模型。

**Alternatives considered**：

- 直接更新同一 series：會讓過去 occurrence 依新規則重算，破壞稽核與 Timeline。
- 為每次修改複製所有未來 occurrence：產生大量資料且增加並行衝突。

## 5. 醫療照護權限

**Decision**：在既有 `OrganizationMembership` 增加單一 `medical_care_access` capability，避免建立通用 ACL 系統。

- `SHELTER_ADMIN` 永遠具有完整醫療歷史、提醒 series 管理與 occurrence action 權限。
- `STAFF` 必須為 active Membership 且 `medical_care_access=true`，才能查看／維護醫療歷史與處理提醒；series 建立、未來規則修改與停止仍只限管理員。
- `VOLUNTEER` 不取得完整 capability；只有仍具有效 Membership 且被同 organization occurrence 指派時，才能透過獨立最小 projection 查看與回報該次任務。
- `PLATFORM_ADMIN` 沿用既有單一 target organization、支援原因、受限 RLS scope 與 read/write Audit lifecycle。

Capability 由收容所管理員在既有 Membership 管理介面授予或撤銷，變更本身需要 Audit。API 每次 request 重新判定；前端 capability 只用於導覽與操作提示，不能作安全邊界。

**Rationale**：現有角色沒有醫療資料細分；直接讓所有 STAFF 看到私人醫療內容不符合最小權限。單一 capability 足以達成本功能，不必同時導入複雜 permission catalog。

**Alternatives considered**：

- 將 active STAFF 直接視為已授權：維護最少，但無法讓收容所限制敏感醫療內容。
- 建立 read/write/manage/execute 多個 capability：控制更細，但超出簡單 MVP，管理負擔高。

## 6. 醫療歷史、更正與封存

**Decision**：`MedicalRecord` 保存目前有效 projection，所有建立、修改與封存使用既有 `AuditRecord` 保存 before／after／reason／actor／source，不另建重複 revision table。正式 record 不提供 hard delete；封存需要原因。醫療歷史查詢只回 current projection，單筆異動歷史沿用受醫療 capability 保護的 management audit query。

**Rationale**：現有 AuditService 已能保存完整前後內容與 operation id，ObservationOption 亦採相同查詢模式。重複建立 revision table 會產生兩個需對帳的歷史來源。

**Alternatives considered**：

- 每次修改新增完整 MedicalRecord row：讀取 current 版本與附件關聯更複雜。
- 只覆寫 current row：不能還原原始內容或證明誰在何時修改。

## 7. 醫療附件

**Decision**：沿用 `MediaAsset` 的清理、private object storage 與短效下載 URL，新增帶 `organization_id` 的 `MedicalRecordMedia` association。建立／修改醫療紀錄時只接受目前收容所、已正式化、已清理且未被其他正式資源不當移用的 media id；文字紀錄與附件 promotion 在同一 transaction 決定關聯，附件失敗不覆蓋已保存文字。

第一階段附件格式沿用現行安全 allowlist（JPEG、PNG、WebP），UI 清楚說明支援格式；一般 PDF／Office 文件的惡意內容掃描、預覽與下載政策另立功能，不在本次默默加入不完整驗證。

**Rationale**：現有 sanitizer 只對影像解碼、重新編碼與清除 EXIF。僅以副檔名或 PDF magic bytes 接受文件不足以構成安全驗證；使用者要求的主要價值可先以自由文字與安全圖片完成。

**Alternatives considered**：

- 只在 MedicalRecord 保存 object key：會繞過 Media scope、清理與正式化規則。
- 本次新增任意文件：需要額外 parser、惡意內容政策及呈現驗證，會把簡單記事擴張成文件管理。

## 8. Timeline 與今日摘要整合

**Decision**：擴充既有 `GET /v1/animals/{animalId}/timeline`，保留 `reports`、`has_report`、`report_count` 相容欄位，additive 新增：

- `organization_timezone`；
- 每日 `has_activity`、`event_count` 與 discriminated `events[]`；
- 每日 `scheduled[]`；
- top-level `open_reminders`，集中今天仍待處理與較早逾期項目。

`events.kind` 至少區分 `care_report`、`medical_record`、`reminder_completed`、`reminder_skipped`、`reminder_rescheduled`、`reminder_cancelled`；planned occurrence 必須在 `scheduled` 或 `open_reminders`，不得偽裝成 actual event。沒有 care report 的舊欄位仍只表示「當日無日常照護回報」，不能再被解讀為整天沒有任何事件。

**Rationale**：沿用單一 Timeline 符合 CRM 歷史一致性並避免第二套動物歷史頁；additive contract 降低既有 P0 前端與測試的破壞。

**Alternatives considered**：

- 新增獨立 Medical Timeline：管理員必須在兩套歷史之間切換，容易漏看交班事件。
- 把 planned reminder 混進 `reports`：會把尚未執行的事情誤作已發生紀錄。

## 9. 並行、冪等與狀態衝突

**Decision**：MedicalRecord、ReminderSeries 與已持久化 Occurrence 都使用整數 `version` 作 optimistic concurrency；高風險 occurrence action 另要求 `Idempotency-Key` header 與 `expected_version`。相同 key／相同 normalized payload 回傳原結果，相同 key／不同 payload 回 409，stale version 亦回 409 並提供最新安全狀態。完成 action 分開保存人員確認的 `actual_completed_at` 與 server `recorded_at`；前者選填、未填時使用後者，且不得晚於 `recorded_at + 5 分鐘`。mutation 以 transaction、row lock、唯一 `(organization_id, occurrence_id)` 及 action idempotency constraint 保證只有一個有效 current result。

**Rationale**：提醒卡容易被兩位交班人員同時開啟；單靠前端 disabled 或最後寫入者覆蓋會造成重複給藥風險。

**Alternatives considered**：

- 只依 `updated_at`：時間精度與序列化差異較難作穩定 token。
- 悲觀鎖住整個編輯期間：Web request 無法安全持有長時間鎖，使用體驗也較差。

## 10. Agenda／Calendar API 與前端資訊架構

**Decision**：後端提供 timezone-aware `care-agenda` 四個互斥 bucket（今天待處理、已逾期、今天已處理、未來七天）與可分頁 `care-calendar`；「今天已處理」包含完成、略過與取消，但 item 保留實際狀態。Next.js 新增唯一頂層 `/care-calendar`，預設採 agenda-first 卡片清單，而非引入大型月曆元件。支援今天／指定日期、上一日／下一日／回今天及日期、動物、類型、負責人、狀態篩選。動物檔案加入今日摘要與「新增醫療紀錄／建立提醒」動作，完整歷史仍在既有 Timeline。第一階段不提供提前提醒設定或 `upcoming` 視圖。

前端 feature 使用 `apiFetch`、集中 query serialization、snake_case mapping 與 discriminated UI types。狀態用文字、icon 與 badge 呈現，不只靠顏色；動作 dialog 支援鍵盤、Escape、focus restore 與 busy 防重送。第一階段不安裝第三方 calendar library。

**Rationale**：agenda 最直接回答今天要做什麼，在 360px 手機也比月格容易操作；純原生日期控制與現有 UI primitives 維護面最小。

**Alternatives considered**：

- 完整月／週拖拉行事曆：增加套件、responsive、鍵盤與時區互動成本，規格未要求拖拉。
- 桌面表格：多動作欄位在 360px 需水平捲動，不符合低摩擦與無障礙目標。

## 11. HTTP contract 與 generated types

**Decision**：在本 feature 建立 `contracts/medical-care.openapi.yaml` 作 additive 可審查契約，另以 `authorization.md` 與 `timeline-and-calendar.md` 固定資料可見性、occurrence identity、bucket 與 Timeline union。實作時必須合併到 canonical `specs/001-volunteer-care-report/contracts/openapi.yaml`，再執行 `packages/contracts` generate/check；不可手改 `packages/contracts/src/openapi.ts`。

新 endpoint 使用具名 Pydantic request／response model、snake_case JSON、camelCase path placeholder 與既有 unified error。write request 不接受 `organization_id`；scope 只能來自已驗證 context。新前端 feature 直接從 generated contract 取 DTO 型別或建立由其推導的窄型別，不再複製未連結的 API shape。

**Rationale**：目前 canonical OpenAPI 與 generated type 流程已固定，但 FastAPI 部分舊 route 仍回傳裸 `dict`。新功能可從一開始保持 contract／runtime／frontend 一致，而不把全專案 runtime OpenAPI 重寫納入本 feature。

**Alternatives considered**：

- 只保留 feature YAML：generated types 不會讀取，最終必然漂移。
- 手動撰寫前端 DTO：短期較快，但 contract 變更無法被 drift check 發現。

## 12. 測試、效能與資料隔離

**Decision**：所有新 tenant business table 顯式帶 `organization_id`、建立複合 foreign key／unique constraint 防止跨 tenant 關聯、啟用並 FORCE RLS；repository query 仍同時帶 organization predicate。測試涵蓋 pure recurrence／bucket unit、migration bootstrap、API integration、Audit／Media、RLS isolation、authorization、concurrency、500 occurrence performance、Timeline、Vitest、Playwright、360／768／1024／1440 responsive、keyboard、axe 與 visual regression。

Agenda 效能使用固定 seed 的 100 隻動物／500 筆 mixed-state occurrence，涵蓋四個 bucket、單次與週期提醒、terminal／rescheduled exceptions 及長期 daily series。基準測試以單一服務程序連接已完成 migration、seed 且暖機的本機 PostgreSQL；計時範圍包含 Agenda application service、資料庫查詢、recurrence projection 與 response serialization，不包含 migration、seed、程序啟動、網路傳輸或瀏覽器 render。每輪先執行 5 次不計分暖機，再連續量測 100 次，完整執行 3 輪；每輪 p95 均須 ≤ 1 秒，並記錄 p50、p95、max、查詢數、資料筆數、commit、作業系統、CPU／RAM 與 PostgreSQL 版本。參考環境至少具備 4 個 logical CPU 與 8 GiB RAM；未達參考環境的結果可作診斷，但不得單獨作為門檻失敗判定。

SC-003 與 Playwright 共用 `agenda-e2e` 固定 seed 的 expected manifest。Manifest 為每筆事項保存內部 `occurrence_id`，以及畫面可見的 bucket、動物名稱、完整收容編號、提醒類型、標題、organization-local 預定時間與狀態；Playwright 以 ID 驗證集合唯一性與完整分類，真人驗收以可見欄位、重複筆數與 bucket total 比對，不要求受測者辨識內部 ID。

需要真實 API 的 Playwright suite 以 repository root 作為 seed subprocess `cwd`，明確使用既有 `STRAYHUB_TEST_DATABASE_URL`／`DATABASE_URL`，並要求額外的本機 seed opt-in；seed 僅允許 loopback PostgreSQL。Next.js 使用既有 `API_INTERNAL_URL` 指向 API，suite 在 seed／瀏覽頁面前確認 `${API_INTERNAL_URL}/healthz` 成功。API 未啟動、環境缺少或資料庫非 loopback 必須回報為測試前置失敗，不得誤判成 UI 功能錯誤。

API cursor page 預設 50、上限 100，calendar 日期範圍上限 366 日。資料庫 index 以 `(organization_id, animal_id, occurred_at)`、series active/anchor、occurrence status/scheduled instant、assignee 及 action idempotency 為主。

**Rationale**：Playwright mock 只能證明 UI，不能證明 RLS、transaction 或 Audit；分層測試才能對應 Constitution 與 SC-003／SC-007。

**Alternatives considered**：

- 只測 happy path：無法涵蓋醫療資料隔離與雙人同時完成的高風險情境。
- 只依 RLS、不帶 application predicate：降低 defense in depth，且測試 fake repository 時無法驗證 scope。
- 以單次人工碼表或瀏覽器載入時間作 p95：樣本不足，且會混入網路與前端 render，無法穩定判斷 Agenda server-side projection 是否退化。
- 完全依賴任意開發者電腦的未記錄結果：環境差異無法重現，因此要求固定資料、暖機／樣本流程及環境資訊。
- 讓 Playwright 從 `apps/web` 的隱含 cwd 執行 root seed、或自動接受任意資料庫 URL：前者會使 module resolution 依啟動方式漂移，後者可能污染非正式驗收範圍以外的資料，因此拒絕。

## 13. 明確不採用的功能

**Decision**：本 plan 不加入藥量計算、處方結構、藥品庫存、交互作用檢查、AI 醫療判斷、外部通知、完整排班、任意文件管理、費用／帳務或公開醫療資料。任何後續需求均建立獨立 specification。

**Rationale**：這些能力具有不同安全與治理風險，會破壞本次「自由文字歷史＋行事曆提醒＋人工結果」的可維護邊界。

**Alternatives considered**：一次建立完整醫療系統；因範圍、醫療安全與維護成本過高而拒絕。
