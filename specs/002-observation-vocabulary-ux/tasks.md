---
description: "觀察詞彙管理介面資訊架構與可讀性優化的可執行任務"
---

# Tasks: 觀察詞彙管理介面資訊架構與可讀性優化

**Input**: `/Users/js/gae_cowork_project/StrayHub/specs/002-observation-vocabulary-ux/` 的 `spec.md`、`plan.md`、`research.md`、`data-model.md`、`contracts/` 與 `quickstart.md`

**原則**：所有畫面文字、測試描述、錯誤訊息與驗收記錄使用台灣正體中文；程式識別字、API 路徑、資料表與 stable code 維持英文中性命名。任務不改變既有平台預設 code、歷史回報快照或跨收容所資料邊界。

## Phase 1: Setup（共用準備）

**目的**：建立本功能的前後端修改邊界、契約對照與可測試的功能骨架。

- [X] T001 [P] 建立觀察詞彙前端 feature module、測試檔案位置與 `/settings/observation-options` 頁面組合入口，範圍限定於 `apps/web/features/observation-vocabulary/` 與 `apps/web/app/(management)/settings/observation-options/page.tsx`
- [X] T002 [P] 將本功能的既有觀察詞彙路徑、相容欄位與新增生命週期操作對照到正式契約來源 `specs/001-volunteer-care-report/contracts/openapi.yaml`
- [X] T003 [P] 在功能驗證指南中補上實作後的 targeted test、generated contract check 與本機驗收順序，維護 `specs/002-observation-vocabulary-ux/quickstart.md`

## Phase 2: Foundational（阻塞性基礎）

**目的**：完成所有使用者故事都依賴的資料狀態、歷史保護、租戶範圍、驗證、稽核與契約基礎；本階段完成前不得開始 UI 故事整合。

**⚠️ 重要**：usage index 是可重建的衍生資料，正式 CRM 回報與 `answer_snapshots` 仍是唯一事實來源；任何回填或索引失敗不得覆寫、刪除或阻止保存原始回報。

- [X] T004 擴充觀察選項模型與查詢投影，正式支援 `active`、`disabled`、`archived` 三種狀態，保留既有 `enabled` 相容語意與平台預設來源，修改 `services/api/app/persistence/models/observation.py` 與 `services/api/app/persistence/repositories/observation_repository.py`
- [X] T005 建立 `ObservationOptionUsage` 模型、Repository 與依收容所隔離的查詢／重建介面，新增 `services/api/app/persistence/models/observation_usage.py` 與 `services/api/app/persistence/repositories/observation_usage_repository.py`
- [X] T006 建立向前相容的 Alembic migration，加入 archived 狀態約束、`audit_records.operation_id` 欄位、usage index、必要索引與 RLS policy；既有 AuditRecord 以自身 `id` 回填 operation id，不改寫既有回報，新增 `services/api/migrations/versions/0023_observation_vocabulary_management.py` 並同步 `services/api/app/persistence/models/audit.py`
- [X] T007 實作既有 `answer_snapshots` 優先、`answers` 補足、無法對應 option 仍保留 orphan usage 的可重複回填／校正流程，並在 `services/api/app/application/observation_option_usage_service.py` 明確採 fail-closed 鎖定 stable code
- [X] T008 在回報建立與觀察修正交易中追加 usage index，並讓新快照保存 category code、stable code、當時中文名稱、說明與來源；不得移除原始 snapshot，修改 `services/api/app/application/report_submission.py`、`services/api/app/application/report_correction.py` 與 `services/api/app/persistence/models/care_report.py`
- [X] T009 在 `services/api/app/application/observation_option_service.py` 統一實作中文名稱、排序、stable code 格式、目前收容所 effective vocabulary 全域唯一性、已使用 code 鎖定、來源唯讀與操作當下已驗證 Shelter Context 綁定
- [X] T010 在 `services/api/app/application/observation_option_service.py` 與 `services/api/app/application/audit_service.py` 建立觀察選項新增、修改、排序、停用、恢復、封存的 before／after payload 與 action 對照，為每次 mutation 產生唯一 operation id、讓同次多選項排序共用 operation id，成功 mutation 的結果固定為 `success`，確保取消、失敗與拒絕不會產生成功 mutation audit
- [X] T011 同步正式契約與生成型別，將 `specs/002-observation-vocabulary-ux/contracts/observation-vocabulary.yaml` 的 response、status、history usage、固定成功 result 與 lifecycle 語意整合至 `specs/001-volunteer-care-report/contracts/openapi.yaml`，再由生成流程更新 `packages/contracts/src/openapi.ts`
- [X] T012 [P] 建立涵蓋 13 類別、平台預設、自訂、停用、封存、歷史使用、A／B 收容所與 Staff／管理者角色的測試 fixture，新增 `tests/fixtures/observation_vocabulary.py`
- [X] T013 驗證 migration、AuditRecord operation id 回填／新舊資料相容、usage 回填／重建、舊 snapshot 不變、新回報／修正追加 usage、空資料庫與既有資料升級的整合測試，更新 `tests/integration/test_observation_option_usage.py` 與 `tests/integration/test_audit_service.py`

**Checkpoint**：資料狀態、歷史追溯、穩定識別、權限所需的基礎查詢與正式契約已可供所有使用者故事使用。

## Phase 3: User Story 1 - 先看懂收容所目前的觀察詞彙全貌（Priority: P1）🎯 MVP

**目標**：管理者首次進入頁面即可看到不受篩選影響的四項摘要、平台預設／收容所自訂差異與初始收合的類別摘要。

**獨立測試**：使用含 13 個類別、平台預設、自訂、停用與封存資料的管理者帳號；不展開任何類別即可核對四項摘要、來源說明與初始收合狀態，且回應只包含目前收容所與平台預設資料。

### User Story 1 的測試

- [X] T014 [P] [US1] 新增管理者完整摘要／類別計數、Staff active-only 摘要／類別計數、摘要 scope 與未篩選總量的 API 契約／整合案例，更新 `tests/contract/test_observation_options_contract.py` 與 `tests/integration/test_observation_options.py`
- [X] T015 [P] [US1] 新增摘要 selector 的測試資料轉換與四項摘要計算測試，建立 `apps/web/features/observation-vocabulary/observationVocabulary.test.ts`

### User Story 1 的實作

- [X] T016 [P] [US1] 擴充觀察詞彙型別、13 個中文類別名稱對照、摘要與類別計數 selector，實作於 `apps/web/features/observation-vocabulary/observationVocabulary.ts`
- [X] T017 [US1] 在 `services/api/app/api/observation_options.py` 與 `services/api/app/application/observation_option_service.py` 依角色回傳 `admin_full` 或 `staff_active` 摘要／類別計數、來源、狀態與最後修改資訊；符合筆數由前端完整 response 計算，不放入 API 未篩選摘要
- [X] T018 [US1] 實作頁面標題、用途副標題、四項摘要卡、平台預設／收容所自訂差異說明與類別初始收合骨架，修改 `apps/web/features/observation-vocabulary/ObservationVocabularyPage.tsx`、`apps/web/features/observation-vocabulary/ObservationSummary.tsx` 與 `apps/web/app/(management)/settings/observation-options/page.tsx`
- [X] T019 [US1] 補上頁面首次載入、可靠資料載入失敗、無資料與權限不足的繁體中文狀態，確保載入中不顯示誤導性零摘要，測試 `apps/web/features/observation-vocabulary/ObservationVocabularyPage.test.tsx`

**Checkpoint**：管理者不展開清單即可理解全貌、資料來源與本收容所管理範圍。

## Phase 4: User Story 2 - 依類別逐步找到需要維護的選項（Priority: P1）

**目標**：以 13 個中文觀察類別分組，顯示可辨識的狀態／來源／計數，展開後先看收容所自訂，再獨立展開平台預設。

**獨立測試**：展開任一混合來源類別，只透過中文類別名稱、類別計數與自訂優先順序找到指定自訂項目；確認中文名稱是第一層資訊、stable code 為次要資訊，收合不會改變資料。

### User Story 2 的測試

- [X] T020 [P] [US2] 覆蓋 13 類別名稱／code、啟用／自訂／停用計數、初始收合、自訂優先與平台預設次級區段的 selector 測試，更新 `apps/web/features/observation-vocabulary/observationVocabulary.test.ts`
- [X] T021 [P] [US2] 覆蓋類別展開／收合、中文名稱優先、來源與狀態文字、平台預設無管理操作的前端互動測試，新增 `apps/web/features/observation-vocabulary/ObservationCategoryGroup.test.tsx` 與 `apps/web/features/observation-vocabulary/ObservationOptionCard.test.tsx`

### User Story 2 的實作

- [X] T022 [P] [US2] 實作依類別、來源、狀態與 display order 排序的分組 selector，確保自訂選項優先且平台順序不被收容所排序改寫，修改 `apps/web/features/observation-vocabulary/observationVocabulary.ts`
- [X] T023 [P] [US2] 建立語意化類別展開／收合與選項呈現元件，顯示類別中文名稱、次要 code、三組計數、中文選項名稱、來源、狀態、說明、補充說明與最後修改資訊，新增 `apps/web/features/observation-vocabulary/ObservationCategoryGroup.tsx` 與 `apps/web/features/observation-vocabulary/ObservationOptionCard.tsx`
- [X] T024 [US2] 將分組、收合狀態、自訂區段與可獨立展開的平台預設區段整合至頁面，並明確隱藏平台預設的編輯／狀態操作，修改 `apps/web/features/observation-vocabulary/ObservationVocabularyPage.tsx`
- [X] T025 [US2] 更新管理頁回歸驗收，驗證既有平台預設選項、中文類別、歷史選項顯示與新回報可用詞彙未因分組改版而漂移，修改 `tests/e2e/test_us4_observation_options.py`

**Checkpoint**：管理者可在不閱讀長平鋪清單的情況下，按類別逐步找到自訂詞彙並辨識來源／狀態。

## Phase 5: User Story 3 - 以搜尋與組合篩選快速定位選項（Priority: P1）

**目標**：支援中文名稱、stable code、說明搜尋，以及類別、狀態、來源的 AND 組合篩選，無結果時提供可復原的繁體中文操作。

**獨立測試**：建立同類別、不同來源／狀態且文字相似的資料；驗證三種搜尋欄位、stable code 大小寫、任意組合條件、符合筆數、空結果與清除後的完整列表。

### User Story 3 的測試

- [X] T026 [P] [US3] 新增搜尋欄位不分大小寫、類別／狀態／來源 AND 篩選、摘要不變、空結果與清除條件的 selector 測試，更新 `apps/web/features/observation-vocabulary/observationVocabulary.test.ts`
- [X] T027 [P] [US3] 新增搜尋輸入、三組篩選控制、目前符合筆數與「清除搜尋與篩選」操作的前端互動測試，建立 `apps/web/features/observation-vocabulary/ObservationFilters.test.tsx`

### User Story 3 的實作

- [X] T028 [P] [US3] 實作帶有可讀標籤、提示與繁體中文選項的搜尋／篩選控制，新增 `apps/web/features/observation-vocabulary/ObservationFilters.tsx`
- [X] T029 [US3] 將搜尋與類別、狀態、來源篩選整合到分組頁面，僅顯示符合結果的類別，保留未篩選摘要並在清除後恢復初始收合狀態，修改 `apps/web/features/observation-vocabulary/ObservationVocabularyPage.tsx` 與 `apps/web/features/observation-vocabulary/observationVocabulary.ts`
- [X] T030 [US3] 補上無結果、篩選條件摘要、重新載入與篩選後錯誤的繁體中文狀態，確保 Staff 預設不因找不到啟用詞彙而推測資料不存在，測試 `apps/web/features/observation-vocabulary/ObservationVocabularyPage.test.tsx`

**Checkpoint**：管理者與一般工作人員可用自然語言或技術 code 快速定位詞彙，且組合篩選不會誤算總量或呈現空類別。

## Phase 6: User Story 4 - 新增與修改收容所自訂觀察選項（Priority: P1）

**目標**：具備設定管理權限者可安全新增／編輯本收容所自訂選項，修改名稱、說明、排序與補充說明需求；平台預設唯讀，stable code 依格式、唯一性與歷史使用鎖定。

**獨立測試**：管理者新增合法自訂選項，觸發空白、非法、重複 code 與無效排序錯誤，再成功修改可編輯欄位；另驗證已使用 code 唯讀、平台預設無編輯入口，且只有本收容所資料改變。

### User Story 4 的測試

- [X] T031 [P] [US4] 新增／編輯 request schema、`expected_updated_at` 版本條件、stable code 格式與目前收容所 effective vocabulary 唯一性的 API 契約案例，更新 `tests/contract/test_observation_options_contract.py`
- [X] T032 [P] [US4] 覆蓋空白名稱、非法 code、重複 code、負數排序、平台預設唯讀、未使用 code 可改與歷史使用 code 鎖定的服務單元測試，更新 `tests/unit/test_observation_option_service.py`
- [X] T033 [P] [US4] 覆蓋新增、編輯、輸入保留、欄位錯誤、`expected_updated_at` 過期寫入、成功回饋與資料更新衝突的前端表單測試，新增 `apps/web/features/observation-vocabulary/ObservationOptionForm.test.tsx`

### User Story 4 的實作

- [X] T034 [US4] 擴充 `services/api/app/api/observation_options.py` 的新增／修改 request 與 response 驗證，要求 `expected_updated_at` 並回傳可理解的格式、重複、鎖定與 `data_changed` conflict 錯誤，禁止修改平台預設來源
- [X] T035 [US4] 完成 `services/api/app/application/observation_option_service.py` 的新增、編輯、排序欄位更新、歷史使用判斷、操作當下 Shelter Context 綁定與 `updated_at` 條件更新，並在成功時建立結果為 `success` 的正確 audit payload
- [X] T036 [US4] 建立具備可讀 label、用途提示、即時驗證、stable code 唯讀提示、儲存／取消動詞與錯誤區域的表單，新增 `apps/web/features/observation-vocabulary/ObservationOptionForm.tsx`
- [X] T037 [US4] 將新增／編輯表單接入頁面與原有搜尋／展開脈絡，送出 `expected_updated_at`，處理儲存成功更新列表／摘要、過期寫入保留草稿並要求重新確認、其他失敗重試與平台預設唯讀，修改 `apps/web/features/observation-vocabulary/ObservationVocabularyPage.tsx`
- [X] T038 [US4] 驗證新增／編輯／排序 API 的跨層行為、相近用途自訂選項與平台預設並存且平台預設仍可使用、後續新回報使用更新內容、audit before／after 與 A／B 不互相影響，更新 `tests/integration/test_observation_options.py` 與 `tests/e2e/test_us4_observation_options.py`

**Checkpoint**：管理者可在兩分鐘內完成安全的自訂詞彙維護，錯誤可修正且不會建立半成品或改寫平台預設。

## Phase 7: User Story 5 - 安全地排序、停用、恢復或封存選項（Priority: P1）

**目標**：管理者可調整自訂排序並以有明確影響說明的確認流程執行停用、恢復與封存；新回報只用 active，歷史回報與快照永遠保留，沒有永久刪除。

**獨立測試**：以有／無歷史使用的自訂選項各一個，完成排序、停用取消與確認、恢復、封存、狀態篩選、新回報可見性與歷史原始快照驗證；確認沒有 DELETE 或永久刪除操作。

### User Story 5 的測試

- [X] T039 [P] [US5] 覆蓋 disable／restore／archive／reorder 的狀態轉換、平台預設拒絕、原子性、無 DELETE 與歷史使用保護，更新 `tests/unit/test_observation_option_service.py`、`tests/integration/test_observation_options.py` 與 `tests/contract/test_observation_options_contract.py`
- [X] T040 [P] [US5] 覆蓋停用／封存／恢復確認文字、取消不變更、成功回饋、狀態篩選與焦點回復的前端互動測試，新增 `apps/web/features/observation-vocabulary/ObservationLifecycleDialog.test.tsx`

### User Story 5 的實作

- [X] T041 [US5] 在 `services/api/app/application/observation_option_service.py` 與 `services/api/app/api/observation_options.py` 實作自訂選項的 disable、restore、archive 與同類別 reorder，明確排除平台預設、跨類別與跨收容所 mutation，並以目前已驗證 Shelter Context 綁定寫入範圍
- [X] T042 [US5] 建立生命週期確認元件，顯示選項中文名稱、目前／新狀態、新回報表單影響、歷史回報保留與取消／確認動詞，新增 `apps/web/features/observation-vocabulary/ObservationLifecycleDialog.tsx`
- [X] T043 [US5] 將生命週期 action、排序操作與確認流程整合頁面，成功後同步狀態／摘要／類別計數／新回報有效詞彙，失敗時保留原狀態並提供重試，修改 `apps/web/features/observation-vocabulary/ObservationVocabularyPage.tsx`
- [X] T044 [US5] 完成歷史快照與新回報有效選項的回歸驗證，確認停用／封存不出現在新表單、恢復後重新出現、舊名稱與 stable code 不變，更新 `tests/e2e/test_us4_observation_options.py` 與 `tests/integration/test_observation_options.py`

**Checkpoint**：所有生命週期操作都是可追蹤、可取消、非破壞性的；歷史資料與新回報可見性符合規格。

## Phase 8: User Story 7 - 只在正確收容所範圍內管理並查看稽核紀錄（Priority: P1）

**目標**：只有操作當下已驗證 Shelter Context 的設定管理者能 mutation 與查看本頁變更紀錄；平台管理員必須先切換有效收容所情境；Staff 讀取不越權；A／B 收容所即使 stable code 相同也完全隔離；每次成功 mutation 都保留結果為 `success` 的可查 audit，其他稽核資源維持既有入口權限。

**獨立測試**：建立 A／B 兩所及同 code 自訂項目，從 id、網址、搜尋與 context 變更嘗試跨所讀寫；驗證拒絕回應不洩漏存在性、A 變更不改 B，平台管理員未切換情境時不能寫入，且新增／修改／排序／停用／恢復／封存均有正確 actor、時間、scope、前後內容與 `success` 結果；管理者可在本頁查看 A 的變更紀錄，Staff 與 B 不可查看或推測，其他稽核資源的既有入口權限不受影響。

### User Story 7 的測試

- [X] T045 [P] [US7] 新增 A／B 相同 stable code、path id、搜尋條件、Staff、Volunteer、無 context 與平台管理者 scope 的隔離測試，更新 `tests/isolation/test_observation_option_isolation.py`
- [X] T046 [P] [US7] 覆蓋所有成功 mutation audit 欄位、非空 organization／actor／resource／operation id、固定 `result=success`、只記錄真正變更、取消／失敗不記成功 action、每個排序受影響 option 各一筆且共用 operation id、audit scope 隔離，以及依 `resource_id` 查詢單一觀察選項變更紀錄的整合測試，更新 `tests/integration/test_observation_options.py`、`tests/integration/test_observation_option_usage.py` 與新增 `tests/integration/test_observation_option_audit.py`
- [X] T047 [P] [US7] 更新觀察詞彙與既有管理稽核契約測試，確認 `resource_type=ObservationOption`、`resource_id`、`operation_id`、`result=success`、非空稽核範圍欄位、前後內容回應、目前 Shelter Context 管理者授權、Staff 禁止語意，以及其他 resource type 維持原有稽核權限，修改 `tests/contract/test_observation_options_contract.py` 與 `tests/contract/test_management_workbench_contract.py`

### User Story 7 的實作

- [X] T048 [US7] 修正 `services/api/app/api/observation_options.py` 的 mutation role gate，沿用 `require_admin_context` 只允許 `SHELTER_ADMIN` 與操作當下有效 Shelter Context 的 `PLATFORM_ADMIN`，平台管理員未切換情境時拒絕寫入，Staff 僅保留安全唯讀回應
- [X] T049 [US7] 擴充 `services/api/app/api/audit.py` 的 `resource_id` 篩選與條件式設定管理權限 gate，僅對 `resource_type=ObservationOption` 限制目前 Shelter Context 的設定管理者，Staff 不取得本頁管理稽核細節，其他 resource type 維持既有稽核入口權限
- [X] T050 [US7] 將每個 observation option mutation 的 audit scope、actor、source channel、before／after、固定 `result=success` 與 latest modifier 回應整合；排序對每個受影響 option 建立獨立紀錄並共用 `operation_id`，修改 `services/api/app/application/observation_option_service.py` 與 `services/api/app/application/audit_service.py`
- [X] T051 [US7] 建立「查看變更紀錄」唯讀面板，透過 `resource_type=ObservationOption` 與 option id 載入操作者、時間、操作類型、變更前後內容、固定結果「成功」、空狀態與重新載入錯誤，新增 `apps/web/features/observation-vocabulary/ObservationAuditPanel.tsx`
- [X] T052 [US7] 將變更紀錄入口整合至自訂選項卡片與頁面，平台預設、Staff、未授權者與其他收容所不顯示或可取得該入口，並更新 `apps/web/features/observation-vocabulary/ObservationVocabularyPage.tsx`
- [X] T053 [US7] 完成端到端 A／B、角色、變更紀錄與 audit 回歸，確認前端隱藏只是體驗改善且 API／Repository／RLS 仍強制邊界，更新 `tests/e2e/test_us4_observation_options.py`、`tests/isolation/test_observation_option_isolation.py` 與 `apps/web/features/observation-vocabulary/ObservationAuditPanel.test.tsx`

**Checkpoint**：在任何已支援入口中，租戶隔離與最小權限均由後端強制，且所有成功管理變更可稽核追溯。

## Phase 9: User Story 6 - 在管理細節與快速閱讀之間切換（Priority: P2）

**目標**：Staff 只快速閱讀啟用中的中文詞彙與用途；管理者桌面版保留管理效率；320px 左右小尺寸螢幕、鍵盤與螢幕閱讀器均可完成主要流程。

**獨立測試**：以 Staff 與管理者在桌面／320px 寬度及純鍵盤情境操作，同一資料集下驗證可見內容、唯讀能力、文字／狀態可讀性、Tab 順序、Escape 關閉與錯誤／成功訊息可被輔助技術取得。

### User Story 6 的測試

- [X] T054 [P] [US6] 覆蓋 Staff 只顯示 `staff_active` 摘要與 active 詞彙、沒有新增／編輯／排序／狀態按鈕，以及管理者顯示 `admin_full` 摘要與完整操作的角色呈現測試，更新 `apps/web/features/observation-vocabulary/ObservationVocabularyPage.test.tsx`
- [X] T055 [P] [US6] 覆蓋 320px 與桌面版的卡片／可水平閱讀版式、鍵盤 Tab／Escape、expanded 語意、焦點移入／回復、欄位錯誤與 live status 的前端 a11y／mobile 測試，新增 `apps/web/features/observation-vocabulary/ObservationAccessibility.test.tsx`

### User Story 6 的實作

- [X] T056 [P] [US6] 實作桌面與小尺寸螢幕的摘要、類別、選項與操作版式，確保中文名稱、狀態、來源與按鈕不重疊／截斷，修改 `apps/web/app/globals.css`
- [X] T057 [P] [US6] 補齊標題階層、`aria-expanded`／控制關聯、欄位 label／error、live region、dialog focus trap、Escape 關閉與觸發按鈕焦點回復，涵蓋 `ObservationAuditPanel.tsx`，修改 `apps/web/features/observation-vocabulary/ObservationCategoryGroup.tsx`、`ObservationOptionForm.tsx`、`ObservationLifecycleDialog.tsx`、`ObservationAuditPanel.tsx` 與 `ObservationVocabularyPage.tsx`
- [X] T058 [US6] 整合既有管理工作台的載入／錯誤／空狀態視圖與清楚動詞按鈕，完成「重新載入」、「清除搜尋與篩選」、「新增選項」、「編輯」、「停用」、「恢復」、「封存」、「查看變更紀錄」、「儲存」、「取消」文字驗證，修改 `apps/web/components/management/StateViews.tsx` 與 `apps/web/features/observation-vocabulary/ObservationVocabularyPage.tsx`

**Checkpoint**：Staff 可以低摩擦理解可用詞彙，管理者可以用桌面／鍵盤完成管理，手機寬度不犧牲文字與操作可讀性。

## Phase 10: Polish & Cross-Cutting Concerns

**目的**：跨故事完成相容性、文件、品質門檻與本機驗收，不擴大至本次不包含的類別治理、批次操作、匯入匯出或完整手機回報流程。

- [X] T059 [P] 重新產生並檢查 OpenAPI generated types，確認正式來源、觀察詞彙契約與管理稽核契約在 `packages/contracts/src/openapi.ts` 無漂移，執行 `packages/contracts/package.json` 所定義的 generate／check 流程
- [X] T060 [P] 更新 `specs/002-observation-vocabulary-ux/quickstart.md` 的檔案路徑、測試命令、變更紀錄人工驗收證據與完成判定，確保文件仍只使用本機虛構資料
- [X] T061 [P] 執行本功能 targeted backend、audit query、contract、isolation、usage、history 與 e2e 測試，依 `specs/002-observation-vocabulary-ux/quickstart.md` 驗證相關 `tests/` 路徑
- [X] T062 [P] 執行前端 Vitest、typecheck、mobile／a11y test 與生成契約檢查，涵蓋 `ObservationAuditPanel`，依 `apps/web/package.json`、`packages/contracts/package.json` 與 `apps/web/features/observation-vocabulary/` 驗證
- [X] T063 執行完整 Python 與前端品質 Gate：`uv run pytest -q`、`uv run ruff check .`、`uv run ruff format --check .`、`npm --prefix apps/web run quality`、`npm --prefix apps/web run build` 與 `npm --prefix packages/contracts run check`，記錄於 `specs/002-observation-vocabulary-ux/quickstart.md`
- [X] T064 執行本機 quickstart 的 13 類別／約 500 選項、A／B 隔離、目前 Shelter Context、Staff 唯讀與不可查詢本頁稽核、管理者變更紀錄、固定成功結果、歷史快照、320px 與純鍵盤人工驗收，將結果與未解決缺口記錄於 `specs/002-observation-vocabulary-ux/quickstart.md`
- [X] T065 進行 constitution 與 MVP 邊界複核，確認未建立第二份 CRM 事實來源、未覆寫歷史 snapshot、未放寬多收容所隔離、未加入永久刪除或本次不包含功能，複核記錄於 `specs/002-observation-vocabulary-ux/plan.md`
- [X] T066 [P] 建立 13 類別／約 500 選項的初次摘要載入、前端搜尋／篩選與模擬請求失敗狀態效能測試，固定本機驗收環境並驗證 10 次執行的摘要、結果與錯誤／重新載入狀態 p95 各不超過 2 秒，新增 `tests/performance/test_observation_vocabulary_performance.py`

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**：無前置依賴；T001–T003 可平行執行。
- **Phase 2 Foundational**：依賴 Phase 1 的邊界與契約對照；T004–T011 建立模型／資料／服務／契約基礎，T012 可與不修改同一檔案的基礎工作平行，T013 需在 migration、usage 與回報接線完成後執行；本階段阻塞所有使用者故事。
- **Phase 3 US1**：依賴 Phase 2；先完成 T014–T015 的可觀察契約／selector 測試，再由 T016–T019 提供摘要與頁面骨架。
- **Phase 4 US2**：依賴 US1 的頁面骨架與 response；T020–T021 可平行，T022–T025 完成分組與漸進式揭露。
- **Phase 5 US3**：依賴 US2 的分組資料流；T026–T027 可平行，T028–T030 完成組合搜尋／篩選與空結果。
- **Phase 6 US4**：依賴 Phase 2 的驗證／audit 與 US1 的頁面資料流；T031–T033 可平行，T034–T038 完成表單與 mutation。
- **Phase 7 US5**：依賴 US4 的 mutation 邊界與 Phase 2 的歷史索引；T039–T040 可平行，T041–T044 完成生命週期與新回報／歷史驗證。
- **Phase 8 US7**：依賴 Phase 2 的租戶／audit 基礎與 US4／US5 的全部 mutation；T045–T047 可平行，T048–T050 完成後端授權與 audit query，T051–T053 完成頁內變更紀錄與端到端隔離。
- **Phase 9 US6**：依賴 US2／US3 的可讀呈現與 Phase 2 的角色回應；T054–T055 可平行，T056–T058 完成 responsive、a11y 與狀態視圖。
- **Phase 10 Polish**：依賴所有要交付的故事；T059–T062 與 T066 可在實作完成後平行，T063–T065 需在 targeted validation 後完成。

### User Story Completion Order

```text
Setup
  ↓
Foundational
  ↓
US1 摘要與來源說明
  ↓
US2 類別分組與漸進式揭露
  ↓
US3 搜尋與組合篩選
  ├──────────────→ US4 新增／編輯／排序
  │                              ↓
  └────────────────────────────→ US5 停用／恢復／封存
                                 ↓
                               US7 權限／隔離／稽核
  US2 + US3 ─────────────────────→ US6 Staff 唯讀／響應式／可及性
  所有目標故事 ───────────────────→ Polish
```

US1–US3 的搜尋與閱讀能力可先交付價值；US4／US5 是管理 mutation；US7 是發布前的安全門檻，不能因 UI 故事完成而省略；US6 可在核心管理流程穩定後補齊小尺寸螢幕與可及性。

## Parallel Execution Examples

### Setup 與 Foundational

```text
T001 前端 feature 骨架
T002 正式 OpenAPI 對照
T003 quickstart 驗證矩陣
T012 測試 fixture（在資料契約已固定後）
```

### User Story 1

```text
T014 API 契約／整合測試
T015 前端摘要 selector 測試
T016 前端型別與 selector
```

### User Story 2

```text
T020 分組 selector 測試
T021 類別／選項互動測試
T022 分組 selector
T023 類別與選項元件
```

### User Story 3

```text
T026 組合篩選 selector 測試
T027 篩選控制互動測試
T028 篩選控制元件
```

### User Story 4–7

```text
T031–T033 US4 API、服務與表單測試
T039–T040 US5 lifecycle API／UI 測試
T045–T047 US7 isolation、audit query、contract 測試
T049、T051 US7 audit query API 與變更紀錄面板
T054–T055 US6 role、mobile、a11y 測試
```

同一個檔案的任務（尤其 `ObservationVocabularyPage.tsx`、`observationVocabulary.ts`、`test_observation_options.py`）不可同時平行修改；上述平行僅適用於前置依賴已完成且不會產生檔案衝突的工作。

## Implementation Strategy

### MVP First（US1）

1. 完成 Phase 1 Setup。
2. 完成 Phase 2 Foundational，先建立歷史／租戶／稽核安全底座。
3. 完成 Phase 3 US1，交付四項摘要、來源說明與初始收合類別。
4. 以 US1 的獨立測試、13 類別資料與本收容所 scope 驗收後再繼續。

### Incremental Delivery

1. US1：先看懂全貌。
2. US2：按類別逐步閱讀並優先找到自訂選項。
3. US3：以搜尋／篩選快速定位。
4. US4：新增、編輯與排序自訂詞彙。
5. US5：停用、恢復、封存與歷史相容。
6. US7：完成發布前必要的權限、隔離與稽核門檻。
7. US6：補齊 Staff 快速閱讀、響應式與可及性。
8. Polish：執行完整品質 Gate 與本機人工驗收。

### Non-Scope Guardrails

- 不建立、刪除、合併或重新命名觀察類別。
- 不在收容所管理頁修改平台預設 option。
- 不提供永久刪除、批次操作、匯入／匯出、跨收容所複製或完整手機回報流程重做。
- 不修改既有 CareReport 原始答案、照片、心得、人工修正或歷史顯示快照。
- 不把前端隱藏當成授權；所有 organization scope、RLS、stable code 鎖定與 audit 都必須由後端驗證。

## Notes

- `[P]` 僅表示可在其前置依賴完成後，針對不同檔案或互不衝突的工作平行執行。
- `[US#]` 對應 `spec.md` 的使用者故事編號；Setup、Foundational 與 Polish 任務不加故事標籤。
- 每個使用者故事都包含獨立測試標準與 checkpoint；若任一故事的測試無法在不依賴後續故事的情況下執行，應先補齊測試 fixture 或拆分任務，而不是略過驗收。
