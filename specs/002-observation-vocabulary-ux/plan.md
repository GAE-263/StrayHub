# 實作計畫：觀察詞彙管理介面資訊架構與可讀性優化

**分支**：`002-observation-vocabulary-ux` | **日期**：2026-08-11 | **規格**：[spec.md](spec.md)

**輸入**：來自 `specs/002-observation-vocabulary-ux/spec.md` 的功能規格，以及專案 constitution 的 CRM 唯一事實來源、志工低摩擦、歷史追溯、權限隱私稽核、正體中文與多收容所資料隔離要求。

## 摘要

本功能將既有 `/settings/observation-options` 從平鋪長清單改為以繁體中文、觀察類別分組與漸進式揭露為核心的管理介面。桌面版優先支援收容所管理者快速維護自訂選項；一般工作人員以唯讀方式快速理解啟用中的詞彙；小尺寸螢幕則以不擠壓文字與操作的卡片或簡化閱讀方式呈現。

實作會沿用現有觀察類別／選項、FastAPI 端點、PostgreSQL 租戶隔離與 AuditRecord，擴充回傳摘要、來源／狀態／最後修改資訊、封存生命週期與管理權限邊界；並沿用既有 `/v1/management/audit`，只讓設定管理者在本頁唯讀查看 `ObservationOption` 的單一自訂選項變更前後內容，其他稽核資源維持既有入口權限。歷史使用判斷以可重建的觀察選項使用索引輔助，正式照護回報與 `answer_snapshots` 仍是歷史資料來源；任何選項異動都不覆寫既有回報快照。

契約以既有觀察詞彙 HTTP 路徑與管理稽核查詢為相容基礎，新增明確的生命週期動作、管理回應資料與 `resource_id` 稽核篩選；前端使用單次載入後的組合篩選與類別分組，符合目前約 13 個類別、約 500 個選項的規模目標。完整決策與替代方案記錄於 [research.md](research.md)。

## 技術脈絡

**語言／版本**：Python `>=3.11`、FastAPI、Pydantic、SQLAlchemy 2.x、Alembic；前端使用 TypeScript 5.7、React 19、Next.js 15；Contract Types 使用 `openapi-typescript`。精確套件版本沿用現有 lockfile 與專案設定。

**主要依賴**：PostgreSQL／PostgreSQL RLS、`asyncpg`、既有 `RequestContext` 與 management access、`ObservationRepository`、`ObservationOptionService`、`AuditService`、Next.js 管理工作台、既有 `StateViews`、Vitest、Pytest、Ruff 與 generated OpenAPI types。

**儲存**：現有 `observation_categories`、`observation_options`、`care_reports.answer_snapshots` 與 `audit_records`；新增一個可由照護回報重建的觀察選項歷史使用索引，並以 Alembic migration 增加 `archived` 狀態、`audit_records.operation_id`、必要資料約束與索引。既有稽核資料的 `operation_id` 以該筆 AuditRecord 的 `id` 回填，新的單次 mutation 產生新的 UUID；同次多選項排序共用同一 UUID。正式 CRM 資料與歷史快照不移轉到獨立來源。

**測試**：Python 使用 Pytest、Ruff 與現有 unit／integration／contract／security／isolation／e2e 分層；前端使用 Vitest、TypeScript typecheck、Prettier 與現有 a11y／mobile quality scripts；Contract 使用 OpenAPI contract test 與 `npm --prefix packages/contracts run check`。

**目標平台**：多收容所 Web 管理工作台，包含桌面版管理、一般工作人員唯讀查看與小尺寸螢幕閱讀；API 仍由既有 FastAPI CRM 邊界提供。

**專案類型**：既有多租戶 Web application monorepo，包含 `apps/web` 前端、`services/api` CRM API、`packages/contracts` 生成契約型別與 PostgreSQL migration／seed／測試。

**效能目標**：在約 13 個類別與 500 個選項的代表性資料量下，初次載入至摘要可見、搜尋／組合篩選至結果可見，以及請求失敗至明確錯誤或重新載入狀態可見的 p95 時間均不超過 2 秒。前端搜尋不得因展開全部類別而造成長清單初始閱讀負擔。

**限制**：平台預設選項在收容所管理範圍唯讀；收容所自訂 stable code 在目前收容所可見的完整有效詞彙範圍內唯一；沒有硬刪除；已使用 code 鎖定；停用／封存不影響歷史回報；Staff 只能唯讀且不可查看本頁觀察選項管理稽核細節；成功 mutation 的 AuditRecord 結果固定為「成功」，失敗、取消或拒絕不得建立成功 mutation 紀錄；所有查詢與寫入受操作當下已驗證的單一 Shelter Context 與 PostgreSQL RLS 約束，平台管理員必須先切換有效情境；既有稽核入口對其他資源維持原有權限；不得要求 LINE、AI 或 GCP 服務才能完成本功能驗收。

**規模／範圍**：每個收容所約 13 個類別、最多約 500 個選項；平台預設與收容所自訂混合讀取；管理頁不新增類別、不提供批次匯入／匯出／跨收容所複製、不重做完整手機回報流程。

## Constitution Check

### Gate：Phase 0 前

- **I. CRM 為唯一事實來源：通過。** 觀察選項與照護回報仍由既有 CRM 模型保存；使用索引只是可由 `CareReport` 與快照重建的衍生查詢輔助，不取代正式回報。
- **II. 原始資料不得被衍生結果取代：通過。** 編輯、停用、封存不修改歷史回報的 `answers` 或 `answer_snapshots`；新的快照只在新回報保存當時的名稱、code 與必要說明。
- **III. AI 不負責計算、診斷或最終判定：不適用且通過。** 本功能不引入 AI，也不把詞彙狀態交給 AI 判定。
- **IV. AI 結果必須驗證、標示與追溯：不適用且通過。** 本功能不修改既有 AI 結果。
- **V. 志工回填必須低摩擦：通過。** 主要名稱改用台灣繁體中文；啟用、排序與補充說明設定仍由既有回報流程讀取，不要求志工理解 stable code。
- **VI. 歷史紀錄必須完整且可追溯：通過。** 停用／封存只影響新表單；歷史回報保留原始快照；使用索引可重建且失敗時採安全的唯讀／不可改 code 行為。
- **VII. LINE Bot 只是輸入通道：通過。** 只調整有效 Observation Vocabulary 讀取與快照補充，不把核心規則移到 LINE、LIFF 或前端。
- **VIII. 權限、隱私與稽核預設啟用：通過。** Staff 只讀取詞彙，SHELTER_ADMIN／具設定管理權限者可寫入並查看本頁自訂選項稽核；成功 mutation 的結果固定為「成功」，所有操作沿用 AuditService 並限制於操作當下已驗證的 Shelter Scope，不改變其他稽核資源的既有權限。
- **IX. P0 不得依賴 P1 或 P2：通過。** 管理頁、API、migration、歷史相容性與隔離測試可在本機獨立完成，不依賴 AI、LINE 正式服務或 GCP。
- **X. 正體中文與 Python 品質門檻：通過。** 規劃與驗收文件使用台灣正體中文；實作後必須通過 Ruff、Pytest、前端 quality、typecheck 與 generated contract check。
- **XI. 多收容所資料隔離：通過。** 使用索引帶 `organization_id` 並受 RLS；每次 mutation 與稽核均以操作當下已驗證的單一 Shelter Context 綁定，平台管理員需先切換情境；管理者不得以 option id、搜尋、網址或 context 外資料讀寫其他收容所。

**Gate 結論**：通過，沒有需要以例外方式降低 constitution 要求的設計。

### Gate：Phase 1 後

**重新檢查結果：通過。** `data-model.md` 將使用索引定義為可由 CareReport／snapshot 重建的衍生資料，migration 要求不覆寫既有快照；`ui-behavior.md` 與 HTTP contract 分離 Staff 唯讀及 SHELTER_ADMIN／PLATFORM_ADMIN 管理能力，並將本頁 `ObservationOption` 變更紀錄限制為設定管理者，同時保留其他稽核資源既有權限；HTTP contract 保留既有 `source` 與 `enabled` 欄位並新增 `archived`、明確狀態動作、固定成功結果、非空稽核範圍欄位、共同 `operation_id` 與既有 Audit API 的 `resource_id` 篩選；`audit_records.operation_id` 由 migration 回填既有紀錄、由 AuditService 產生新 mutation 識別，排序對每個受影響 option 各記一筆且共用同一 operation id；每個成功新增、更新、排序、停用、恢復與封存都要求對應 AuditRecord，且以目前已驗證 Shelter Context 綁定。Phase 1 沒有新增 constitution 例外。

## Phase 0：研究與決策摘要

研究結果集中於 [research.md](research.md)，已解決所有技術脈絡中的未知事項：

1. 沿用現有 observation HTTP 路徑與 OpenAPI source-of-truth，不另建第二套詞彙服務。
2. 管理畫面一次取得目前收容所的有效與歷史選項，再在前端做組合搜尋、篩選、分組與漸進式揭露；資料量超出約 500 筆時才另立分頁／伺服器查詢規格。
3. `archived` 是與 `active`、`disabled` 並列的選項狀態；`enabled` 維持為 `status == active` 的相容欄位，不提供 DELETE。
4. Staff 可以查看啟用中的詞彙，只有現有 admin-level settings 權限可以變更收容所自訂詞彙；不在本功能新增任意細粒度角色模型。
5. 既有 `organization_extension` wire value 保留，畫面與文件顯示為「收容所自訂」。
6. 變更紀錄重用既有 `/v1/management/audit` 與 `AuditRecord`；只有 `resource_type=ObservationOption` 的本頁查詢收斂為設定管理權限，其他稽核資源維持既有入口權限；成功 mutation 的結果固定為「成功」，查詢與 mutation 均以操作當下已驗證 Shelter Context 綁定。

## Project Structure

### 本功能文件

```text
specs/002-observation-vocabulary-ux/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── README.md
│   ├── observation-vocabulary.yaml
│   └── ui-behavior.md
└── checklists/requirements.md
```

### 實際程式碼與測試

```text
apps/web/app/(management)/settings/observation-options/page.tsx
apps/web/features/observation-vocabulary/
├── ObservationVocabularyPage.tsx
├── observationVocabulary.ts
├── ObservationSummary.tsx
├── ObservationFilters.tsx
├── ObservationCategoryGroup.tsx
├── ObservationOptionCard.tsx
├── ObservationOptionForm.tsx
└── *.test.tsx
apps/web/app/globals.css

services/api/app/api/observation_options.py
services/api/app/api/audit.py
services/api/app/application/observation_option_service.py
services/api/app/application/observation_option_usage_service.py
services/api/app/persistence/models/observation.py
services/api/app/persistence/models/observation_usage.py
services/api/app/persistence/repositories/observation_repository.py
services/api/app/persistence/repositories/observation_usage_repository.py
services/api/app/application/report_submission.py
services/api/app/application/report_correction.py
services/api/app/persistence/models/care_report.py
services/api/migrations/versions/00xx_observation_vocabulary_management.py

packages/contracts/src/openapi.ts  # 只由 OpenAPI source 重新產生，不直接編輯

tests/unit/test_observation_option_service.py
tests/integration/test_observation_options.py
tests/integration/test_observation_option_usage.py
tests/integration/test_observation_option_audit.py
tests/fixtures/observation_vocabulary.py
tests/isolation/test_observation_option_isolation.py
tests/contract/test_observation_options_contract.py
tests/contract/test_management_workbench_contract.py
tests/e2e/test_us4_observation_options.py
tests/performance/test_observation_vocabulary_performance.py
apps/web/features/observation-vocabulary/ObservationLifecycleDialog.tsx
apps/web/features/observation-vocabulary/ObservationAuditPanel.tsx
apps/web/features/observation-vocabulary/ObservationAccessibility.test.tsx
apps/web/features/observation-vocabulary/ObservationAuditPanel.test.tsx
```

**Structure Decision**：採現有 Web application monorepo 的前端 feature module、FastAPI API／Application／Repository／Model 分層與 Alembic migration。頁面路徑保留，將現有單一頁面拆成可測試的觀察詞彙 feature 元件；API 保留既有 observation 路徑與 Audit API，另外為狀態轉換提供明確的動作路徑及觀察選項 `resource_id` 稽核篩選；契約 source 仍由既有 project contract 流程統一生成 `packages/contracts/src/openapi.ts`。

## 實作順序與交付邊界

1. **Foundational data and safety**：補齊 `archived` 狀態、使用索引、歷史快照補充欄位、租戶隔離、stable code 格式／唯一性、admin-only mutation 與 Audit payload。
2. **API contract**：擴充摘要、類別計數、來源／狀態／最後修改資訊與 `has_historical_usage`；加入 disable／restore／archive 明確動作；擴充既有管理稽核查詢的 `resource_id` 與設定管理者授權；保留既有 response 欄位與無 DELETE 保證。
3. **Frontend information architecture**：建立摘要、來源說明、搜尋／篩選、收合類別、自訂優先、唯讀平台預設、表單、確認對話、狀態元件與自訂選項變更紀錄唯讀檢視。
4. **Responsive and accessibility**：套用既有管理工作台樣式基線，補齊小尺寸版式、焦點管理、語意標籤、非顏色狀態與載入／空／錯誤狀態。
5. **Regression and validation**：更新 Python／contract／isolation 測試，新增前端互動／a11y／mobile 測試，依 quickstart 驗證兩收容所、Staff 唯讀、歷史快照與回報流程。

## 複雜度追蹤

| 項目 | 必要原因 | 已評估的較簡單替代方案 |
| --- | --- | --- |
| 可重建的觀察選項使用索引 | 既有歷史回報以 JSON 保存，需可靠判斷 stable code 是否已被使用，才能安全允許未使用自訂 code 修改並顯示管理狀態 | 每次對每個選項掃描 `care_reports` JSON；在代表性 500 選項下會造成難以預測的查詢成本與遺漏舊快照風險 |
| 明確的 disable／restore／archive 動作 | 三種狀態轉換的提示、權限與稽核語意不同，不能以含糊的 `enabled` 布林值取代 | 只擴充 PATCH `enabled`；會無法區分恢復與封存，也容易遺漏停用前說明與專屬 Audit action |
