# Tasks：毛孩日記管理頁

**Input**：`specs/011-growth-diary-management/` 下的 spec、plan、research、data-model、contracts 與 quickstart。

**Scope guard**：本文件只規劃 implementation；執行 task 時不得新增 streaming storage abstraction、read audit、permission abstraction、平行 image service 或規格外 mutation。

**Task format**：每項 task 依 dependency order 排列；`[P]` 只代表依賴完成後可與其他不同檔案 task 平行；`[US1]`、`[US2]`、`[US3]` 對應 spec user story。

## Phase 1：Contract guardrails 與 schema foundation

**Purpose**：先鎖定 feature contract 與資料欄位，避免 repository、API 或前端建立在漂移契約上。

- [ ] T001 建立 Growth Diary feature contract 文件測試於 `tests/contract/test_growth_diary_management_contract.py`
  - **Area**：`specs/011-growth-diary-management/contracts/growth-diary-management.openapi.yaml`、`tests/contract/test_growth_diary_management_contract.py`
  - **Depends on**：無
  - **Goal**：鎖定 list/detail/photo paths、list 無 raw output、detail 有 provenance/raw output、photo 僅 `content.image/webp`，且 OpenAPI headers 不重複宣告 `Content-Type`。
  - **Acceptance**：測試驗證 `Cache-Control=private, no-store`、`nosniff`、query bounds、nullable 欄位及安全錯誤 schema；不得修改 production code。

- [ ] T002 [P] 建立 additive migration 驗收測試於 `tests/integration/test_growth_diary_management_migration.py`
  - **Area**：`tests/integration/test_growth_diary_management_migration.py`
  - **Depends on**：T001
  - **Goal**：先定義 revision 0042 的 upgrade/downgrade、nullable legacy 行為與不可信資料不回填。
  - **Acceptance**：測試列出且只列出 data-model 的九個新增欄位；既有 entry 保持原 note/photo/AI 欄位，`photo_content_type` 與 provenance 欄位維持 null。

- [ ] T003 實作 migration `services/api/migrations/versions/0042_growth_diary_management.py`
  - **Area**：`services/api/migrations/versions/0042_growth_diary_management.py`
  - **Depends on**：T002
  - **Goal**：新增 `photo_content_type`、`ai_analysis_status`、`ai_provider`、`ai_model_name`、`ai_model_version`、`ai_prompt_version`、`ai_output_schema_version`、`ai_raw_output`、`ai_analyzed_at`。
  - **Acceptance**：upgrade/downgrade 與 0041 revision chain 正確；無 MIME/provenance backfill；T002 通過。

- [ ] T004 更新 GrowthDiary ORM 欄位於 `services/api/app/persistence/models/growth_diary.py`
  - **Area**：`services/api/app/persistence/models/growth_diary.py`、`tests/integration/test_growth_diary_management_migration.py`
  - **Depends on**：T003
  - **Goal**：使 ORM 型別、nullable 與 JSON/datetime 欄位符合 data-model，不新增額外欄位或 table。
  - **Acceptance**：ORM 與 migration 欄位逐一一致；legacy row 可正常載入；migration test 通過。

## Phase 2：Media safety 與 persistence foundation

**Purpose**：完成所有 user story 共用的安全圖片、metadata、transaction 與 AI persistence 邊界。

**⚠️ CRITICAL**：Phase 2 未完成前不得開始 management read API 或 frontend。

- [ ] T005 [P] 建立 pre-full-decode pixel safety 測試於 `tests/unit/test_media_sanitization.py`
  - **Area**：`tests/unit/test_media_sanitization.py`
  - **Depends on**：T001
  - **Goal**：獨立鎖定 `Image.open → actual format validation → width×height gate → full decode` 順序。
  - **Acceptance**：測試證明超過 10 MB 拒絕、小 compressed file 但超過 25M pixels 在 `source.load()` 前拒絕、MIME mismatch 拒絕、Pillow `DecompressionBombWarning`／`DecompressionBombError` fail closed。

- [ ] T006 實作 Growth Diary pre-decode image policy 於 `services/api/app/application/media_sanitization.py`
  - **Area**：`services/api/app/application/media_sanitization.py`
  - **Depends on**：T005
  - **Goal**：在既有 pipeline 增加 Growth Diary 明確選用的 application-level 25M pixel boundary，不全域改寫 Pillow threshold。
  - **Acceptance**：任何 load、orientation 或 frame copy 前完成尺寸檢查；錯誤轉成安全 `DomainError`；T005 通過。

- [ ] T007 建立 WebP normalization 與 fallback 測試於 `tests/unit/test_media_sanitization.py`
  - **Area**：`tests/unit/test_media_sanitization.py`
  - **Depends on**：T006
  - **Goal**：用可控制 encoder/output size 的 fixture 鎖定三階段 deterministic fallback。
  - **Acceptance**：覆蓋 JPEG→WebP、PNG→WebP、WebP→normalized WebP、1600/82→1600/72→1280/68→reject、no-upscale、first-frame-only、EXIF orientation、metadata removal、alpha preservation、final size ≤2 MB。

- [ ] T008 實作 Growth Diary WebP normalization policy 於 `services/api/app/application/media_sanitization.py`
  - **Area**：`services/api/app/application/media_sanitization.py`
  - **Depends on**：T007
  - **Goal**：沿用同一 sanitization function/service boundary，只讓 Growth Diary caller選用 WebP policy，不保存 original/intermediate。
  - **Acceptance**：固定輸出 `image/webp`；只回傳 final bytes；checksum 依 final bytes；fallback 與圖片語意測試全部通過。

- [ ] T009 驗證其他既有 media caller regression boundary 於 `tests/integration/test_media_validation.py` 與 `tests/unit/test_media_sanitization.py`
  - **Area**：`tests/integration/test_media_validation.py`、`tests/unit/test_media_sanitization.py`、既有 media caller fixtures
  - **Depends on**：T008
  - **Goal**：證明未選用 Growth Diary policy 的 care report、staff animal input 等既有 caller 不會被無意改成新輸出契約。
  - **Acceptance**：既有 declared/actual MIME、EXIF removal 與 storage metadata assertions 維持；只允許 Growth Diary 新照片固定 WebP。

- [ ] T010 建立 final media metadata 測試於 `tests/integration/test_growth_diary_media_consistency.py`
  - **Area**：`tests/integration/test_growth_diary_media_consistency.py`
  - **Depends on**：T004、T008
  - **Goal**：先鎖定 `MediaProcessingService`、`StoredObject.metadata` 與 GrowthDiaryEntry photo metadata 的一致性。
  - **Acceptance**：checksum、size、content type 只來自 final WebP；storage 無 original/intermediate；`photo_key != null` 時新 entry 的 `photo_content_type=image/webp`。

- [ ] T011 更新既有 media service metadata 行為於 `services/api/app/application/media_service.py`
  - **Area**：`services/api/app/application/media_service.py`
  - **Depends on**：T010
  - **Goal**：讓 Growth Diary 明確傳入 WebP policy，並以 final sanitized bytes 建立 `ObjectMetadata`，不新增平行 service。
  - **Acceptance**：回傳 `StoredObject` 帶 final checksum/size/MIME；storage 只接受 final bytes；T009、T010 通過。

- [ ] T012 [P] 建立 Growth Diary persistence tenant/invariant 測試於 `tests/integration/test_growth_diary_media_consistency.py`
  - **Area**：`tests/integration/test_growth_diary_media_consistency.py`
  - **Depends on**：T004
  - **Goal**：先鎖定 entry、inquiry、animal organization 一致，以及 repository 接收 `photo_content_type` 的規則。
  - **Acceptance**：跨 organization inquiry/animal 建立失敗；client 無法提供 organization override；文字與照片皆空拒絕；legacy nullable row 仍可讀。

- [ ] T013 更新 Growth Diary repository persistence 於 `services/api/app/persistence/repositories/growth_diary_repository.py`
  - **Area**：`services/api/app/persistence/repositories/growth_diary_repository.py`
  - **Depends on**：T011、T012
  - **Goal**：保存 final `photo_content_type` 並在 server-side 驗證 inquiry/animal/entry tenant invariant。
  - **Acceptance**：repository 不接受 client organization id；新 photo entry 僅接受 `image/webp`；T010、T012 通過。

- [ ] T014 建立 transaction compensation 與 post-commit side-effect integration tests 於 `tests/integration/test_growth_diary_media_consistency.py`
  - **Area**：`tests/integration/test_growth_diary_media_consistency.py`、LINE/storage fakes
  - **Depends on**：T013
  - **Goal**：將 orphan cleanup 與 commit-before-side-effect 設為獨立高優先 failure matrix。
  - **Acceptance**：覆蓋 storage failure→無 entry、DB flush failure→delete、DB commit failure→rollback+delete、delete failure→`growth_diary_orphan_cleanup_failed` 且保留 DB root cause、commit 前不 reply/不註冊 AI task、commit 後 reply/task failure 不刪 durable entry/object。

- [ ] T015 實作 webhook per-event compensation boundary 於 `services/api/app/api/line_webhook.py`
  - **Area**：`services/api/app/api/line_webhook.py`
  - **Depends on**：T014
  - **Goal**：由既有 `session.begin()` owner 持有 organization-scoped compensation token，涵蓋 handler、flush 與 commit failure，不導入 saga/service abstraction。
  - **Acceptance**：commit 成功才清 token、LINE success reply 與 AI task registration；cleanup failure structured log 不取代 root cause且不對使用者暴露 object key；T014 通過。

- [ ] T016 建立 AI status/provenance persistence tests 於 `tests/integration/test_growth_diary_webhook_flow.py`
  - **Area**：`tests/integration/test_growth_diary_webhook_flow.py`、AI fake
  - **Depends on**：T004、T013
  - **Goal**：鎖定 pending/succeeded/failed/unconfigured/not_applicable 與完整 provenance/raw output 寫入。
  - **Acceptance**：configured note 為 pending→succeeded/failed；無 client 為 unconfigured；photo-only 為 not_applicable；legacy 不假造來源；AI failure 不修改 note/photo 或正式狀態。

- [ ] T017 實作 AI status/provenance persistence 於 `services/api/app/application/growth_diary_ai_analysis_service.py`、`services/api/app/infrastructure/ai/gemini_client.py` 與 `services/api/app/api/line_webhook.py`
  - **Area**：上述三個檔案
  - **Depends on**：T015、T016
  - **Goal**：保存 provider/model/model version/prompt/schema/raw output/analyzed time，並維持原始日記先 durable、AI 非同步。
  - **Acceptance**：raw output 經既有結構驗證路徑保存；失敗狀態可區分；不新增診斷、排序或 mutation；T016 通過。

**Checkpoint**：migration、media policy、storage/DB consistency、transaction compensation 與 AI persistence 已可獨立驗證。

## Phase 3：User Story 1 — 查看所屬收容所的毛孩日記（Priority P1）🎯 MVP

**Goal**：授權人員可查看 active shelter 的 newest-first 日記、原始文字、安全照片、AI summary 與 lazy detail provenance/raw output。

**Independent test**：以 STAFF 登入有 text/photo/pending/legacy fixture 的 shelter，list 不含 raw output；detail 才提供 provenance/raw output；photo 經 authenticated same-origin WebP endpoint 載入，其他 shelter 資料不可見。

### Tests for User Story 1

- [ ] T018 [P] [US1] 建立 runtime/feature API contract parity tests 於 `tests/contract/test_growth_diary_management_contract.py`
  - **Area**：`tests/contract/test_growth_diary_management_contract.py`
  - **Depends on**：T017
  - **Goal**：先鎖定 Pydantic runtime schema 與 feature list/detail/photo contract。
  - **Acceptance**：list required/nullable fields一致且無 `ai_raw_output`；detail 有 `ai_provenance`/`ai_raw_output`；photo OpenAPI 只有 `content.image/webp` 且無 Content-Type header declaration。

- [ ] T019 [P] [US1] 建立 organization-scoped read repository tests 於 `tests/integration/test_growth_diary_management.py`
  - **Area**：`tests/integration/test_growth_diary_management.py`
  - **Depends on**：T017
  - **Goal**：先驗證 count/list/detail/photo lookup、Animal join、Inquiry validation 全部 explicit active organization scope。
  - **Acceptance**：排序 `created_at DESC,id DESC`；相同 timestamp 不遺漏；entry/inquiry/animal 任一跨 tenant 不投影；client organization query 不存在。

- [ ] T020 [P] [US1] 建立角色與 tenant isolation security tests 於 `tests/security/test_growth_diary_management_isolation.py`
  - **Area**：`tests/security/test_growth_diary_management_isolation.py`
  - **Depends on**：T017
  - **Goal**：從 backend 證明角色、active context、RLS 與不存在行為，不依賴 navigation hidden。
  - **Acceptance**：STAFF、SHELTER_ADMIN、active-context PLATFORM_ADMIN 可讀；VOLUNTEER、無 active context、other organization 拒絕；A 無法以 B entry ID 探測 detail/photo；不新增任何 read audit event。

### Implementation for User Story 1

- [ ] T021 [US1] 實作 typed read models 與 organization-scoped service/repository 於 `services/api/app/application/growth_diary_service.py` 與 `services/api/app/persistence/repositories/growth_diary_repository.py`
  - **Area**：上述兩個檔案
  - **Depends on**：T019、T020
  - **Goal**：提供 list/detail/photo lookup、AI summary/detail projection 與 stable base pagination，不暴露 object key、adopter PII 或 list raw output。
  - **Acceptance**：所有 count/list/detail/photo/Animal/Inquiry query explicit organization scope；cross-tenant 與不存在使用相同 404；T019、T020 通過。

- [ ] T022 [US1] 實作 list/detail/photo router contracts 於 `services/api/app/api/growth_diary.py`
  - **Area**：`services/api/app/api/growth_diary.py`
  - **Depends on**：T018、T021
  - **Goal**：加入 Pydantic response models、detail route 與使用 `ObjectStoragePort.get()` 的 buffered photo response。
  - **Acceptance**：三種 role 經 `require_staff_or_admin`；photo legacy MIME/no-photo/storage/cross-tenant fail closed；runtime headers 為 `Content-Type:image/webp`、`private, no-store`、`nosniff`；不新增 read audit。

- [ ] T023 [US1] 合併 Growth Diary API 至 canonical OpenAPI 並生成 TypeScript contract
  - **Area**：`specs/001-volunteer-care-report/contracts/openapi.yaml`、`packages/contracts/src/openapi.ts`、`packages/contracts/scripts/check-generated.mjs`、`tests/contract/test_generated_contract_types.py`
  - **Depends on**：T022
  - **Goal**：把 011 feature paths/schemas 合併至唯一 canonical，更新 generator guard，再執行既有 generate command。
  - **Acceptance**：runtime/feature/canonical/generated parity tests 通過；generated list 無 raw output、detail 有 raw output；frontend 尚未開始前完成。

- [ ] T024 [US1] 建立 generated-type-based frontend data layer 於 `apps/web/features/growth-diary/api.ts` 與 `apps/web/features/growth-diary/types.ts`
  - **Area**：上述兩個檔案
  - **Depends on**：T023
  - **Goal**：使用 `authFetch` 與 generated OpenAPI types 實作 list/detail/photo request，不手寫第二份 response contract、不傳 organization id。
  - **Acceptance**：支援 AbortSignal、安全 error mapping、lazy detail；list type 在編譯期無 `ai_raw_output`。

- [ ] T025 [P] [US1] 建立 timeline card/page state component tests 於 `apps/web/features/growth-diary/GrowthDiaryPage.test.tsx` 與 `apps/web/features/growth-diary/GrowthDiaryEntryCard.test.tsx`
  - **Area**：上述兩個 test 檔案
  - **Depends on**：T024
  - **Goal**：先鎖定 loading、真正 empty、error/retry、文字／照片-only、AI disclosure 與 legacy 狀態。
  - **Acceptance**：原始文字與 AI 分區；concern 只顯示「AI 建議人工查看」；pending/failed/unconfigured/not_applicable/legacy 不隱藏原始內容。

- [ ] T026 [US1] 實作 Growth Diary timeline UI 於 `apps/web/features/growth-diary/GrowthDiaryPage.tsx`、`GrowthDiaryEntryCard.tsx` 與 `growth-diary.module.css`
  - **Area**：上述三個檔案
  - **Depends on**：T025
  - **Goal**：建立 newest-first 時間軸、動物識別、原始內容與 AI summary 區塊，沿用既有 UI primitives/StateViews。
  - **Acceptance**：所有 P1 state test 通過；長文字安全換行；AI 固定標示未確認及非醫療診斷。

- [ ] T027 [P] [US1] 建立 lazy provenance detail tests 於 `apps/web/features/growth-diary/GrowthDiaryEntryCard.test.tsx`
  - **Area**：`apps/web/features/growth-diary/GrowthDiaryEntryCard.test.tsx`
  - **Depends on**：T024
  - **Goal**：驗證只有使用者展開來源時取得 detail，且 raw output 不從 list props 進入 UI。
  - **Acceptance**：available 顯示 model/prompt/schema/time/raw；legacy_missing 顯示來源未留存；detail error 不破壞 entry card。

- [ ] T028 [US1] 實作 lazy AI provenance disclosure 於 `apps/web/features/growth-diary/GrowthDiaryEntryCard.tsx`
  - **Area**：`apps/web/features/growth-diary/GrowthDiaryEntryCard.tsx`
  - **Depends on**：T026、T027
  - **Goal**：按需呼叫 detail 並呈現完整 provenance/raw output，保持唯讀。
  - **Acceptance**：不新增覆核/mutation 控制；STAFF 等允許角色共享同一讀取 UI；T027 通過。

- [ ] T029 [P] [US1] 建立 authenticated photo Blob lifecycle tests 於 `apps/web/features/growth-diary/DiaryPhoto.test.tsx`
  - **Area**：`apps/web/features/growth-diary/DiaryPhoto.test.tsx`
  - **Depends on**：T024
  - **Goal**：獨立鎖定 `authFetch → Blob → object URL` 與 lifecycle safety。
  - **Acceptance**：new request/unmount/tenant abort 會 abort 舊請求並 revoke 舊 URL；stale response 不發布；image error 只替換圖片，不隱藏文字；不使用 query token。

- [ ] T030 [US1] 實作 authenticated photo component 於 `apps/web/features/growth-diary/DiaryPhoto.tsx`
  - **Area**：`apps/web/features/growth-diary/DiaryPhoto.tsx`
  - **Depends on**：T026、T029
  - **Goal**：以 active organization request scope 安全管理 photo Blob，不快取前一 shelter URL。
  - **Acceptance**：所有 Blob lifecycle tests 通過；alt/fallback 可理解；不直接使用 MinIO URL/object key。

- [ ] T031 [P] [US1] 建立 route/navigation integration tests 於 `apps/web/app/(management)/growth-diary/page.test.tsx` 與 `apps/web/components/management/management-shell.test.tsx`
  - **Area**：上述兩個 test 檔案
  - **Depends on**：T024
  - **Goal**：先鎖定 management shell route、三種 role navigation visibility 與既有 shell reuse。
  - **Acceptance**：VOLUNTEER 不顯示 link但 backend test仍是安全邊界；PLATFORM_ADMIN 必須有 active context；route 只組裝 feature page。

- [ ] T032 [US1] 建立 route 並整合管理導覽於 `apps/web/app/(management)/growth-diary/page.tsx` 與 `apps/web/components/management/AppSidebar.tsx`
  - **Area**：上述兩個檔案
  - **Depends on**：T028、T030、T031
  - **Goal**：把完成的 P1 feature 接入 management shell，不新增 permission abstraction。
  - **Acceptance**：桌面與 mobile navigation 可進入；route state、role、active context 行為符合既有模式；T025、T027、T029、T031 通過。

**Checkpoint**：US1 可單獨展示 list/detail/photo、AI provenance、role 與 A/B isolation，不依賴 US2 filter 或 US3 E2E polish。

## Phase 4：User Story 2 — 快速找出需要關注的日記（Priority P2）

**Goal**：使用者可搜尋動物名稱／收容編號，依 mood 篩選並穩定分頁，區分真正 empty 與 filtered empty。

**Independent test**：在至少 50 筆跨 mood/animal fixture 中搜尋、篩選及翻頁；count、items 與 stable ordering 一致，清除條件恢復完整清單。

- [ ] T033 [P] [US2] 建立 server-side filter/pagination tests 於 `tests/integration/test_growth_diary_management.py`
  - **Area**：`tests/integration/test_growth_diary_management.py`
  - **Depends on**：T022
  - **Goal**：先鎖定 query trim/case、mood enum、unanalyzed mapping、count-before-page 與 deterministic ordering。
  - **Acceptance**：搜尋只涵蓋同 organization Animal name/shelter_number；page≥1、page_size 1..100；client 無 organization filter；相同時間跨頁不重複/遺漏。

- [ ] T034 [US2] 實作 server-side search、mood filter 與 pagination 於 `services/api/app/persistence/repositories/growth_diary_repository.py`、`growth_diary_service.py` 與 `growth_diary.py`
  - **Area**：上述 repository/service/router 檔案
  - **Depends on**：T033
  - **Goal**：在 count/order/offset 前套用 tenant-scoped filter，保持 API contract bounds。
  - **Acceptance**：total 與 items 一致；unanalyzed 狀態投影誠實；T033、US1 isolation tests 全部通過。

- [ ] T035 [P] [US2] 建立 frontend query/filter/pagination tests 於 `apps/web/features/growth-diary/GrowthDiaryPage.test.tsx` 與 `apps/web/features/growth-diary/api.test.ts`
  - **Area**：上述兩個 test 檔案
  - **Depends on**：T024、T034
  - **Goal**：驗證 query builder、清除條件、換頁與 filtered empty，不在 client 端過濾當頁資料。
  - **Acceptance**：query trim、mood/page/page_size encoding 正確；新條件重設 page；abort stale request；空清單與無符合結果文案不同。

- [ ] T036 [US2] 實作搜尋、mood 篩選與分頁控制於 `apps/web/features/growth-diary/GrowthDiaryPage.tsx` 與 `growth-diary.module.css`
  - **Area**：上述兩個檔案
  - **Depends on**：T035
  - **Goal**：使用既有 Input/Select/Button/Badge 與 server-side API，提供可清除條件與結果總數。
  - **Acceptance**：鍵盤可操作；concern 不改變預設排序；P1 states 不退化；T035 通過。

**Checkpoint**：US2 可在 US1 基礎上獨立驗證完整 shelter 範圍搜尋、篩選與分頁。

## Phase 5：User Story 3 — 不同裝置與錯誤狀態安全閱讀（Priority P3）

**Goal**：桌面、平板、手機及鍵盤使用者皆可安全閱讀；權限、network、image 與 tenant switch state 不洩漏舊資料。

**Independent test**：在 360、768、1024、1440 viewport，以鍵盤操作 filter/detail，模擬 403/network/photo failure 與延遲 A→B switch，確認無 overflow、焦點可見、舊 JSON/Blob 不發布。

- [ ] T037 [US3] 建立 permission/error/responsive component tests 於 `apps/web/app/(management)/growth-diary/page.test.tsx` 與 `apps/web/features/growth-diary/GrowthDiaryPage.test.tsx`
  - **Area**：上述兩個 test 檔案
  - **Depends on**：T032、T036
  - **Goal**：鎖定 403、network retry、長文字、照片 fallback、focus 與 narrow layout state。
  - **Acceptance**：安全錯誤不顯示內部 detail；無 horizontal overflow；主要 control 有 label/focus；retry 不重用 stale shelter data。

- [ ] T038 [US3] 完成 responsive、keyboard 與 accessibility UI 調整於 `apps/web/features/growth-diary/GrowthDiaryPage.tsx`、`GrowthDiaryEntryCard.tsx`、`DiaryPhoto.tsx` 與 `growth-diary.module.css`
  - **Area**：上述四個 feature 檔案
  - **Depends on**：T037
  - **Goal**：完成 mobile stacking、文字 wrapping、圖片比例、focus-visible、ARIA disclosure 與 StateViews 整合。
  - **Acceptance**：component tests、typecheck 與 jsdom a11y tests 通過；不新增全域 CSS 或新 design system。

- [ ] T039 [US3] 建立 Growth Diary Playwright fixtures 於 `apps/web/e2e/fixtures.ts`
  - **Area**：`apps/web/e2e/fixtures.ts`
  - **Depends on**：T023、T038
  - **Goal**：提供 A/B shelter、三種 role、denied role、text/photo/AI/legacy、delayed JSON/detail/photo 與 failure fixtures。
  - **Acceptance**：fixtures 不依賴 Gemini online；所有 endpoint response 符合 canonical generated contract；可觀測 Blob request abort。

- [ ] T040 [P] [US3] 建立核心 Growth Diary E2E 於 `apps/web/e2e/growth-diary-management.spec.ts`
  - **Area**：`apps/web/e2e/growth-diary-management.spec.ts`
  - **Depends on**：T039
  - **Goal**：覆蓋 list/detail/photo、filter/pagination、empty/error/retry 與 allowed/denied roles。
  - **Acceptance**：list 不含 raw output；detail lazy；photo runtime headers正確；三種 allowed role 可讀，VOLUNTEER/no-context/other-org 不可讀。

- [ ] T041 [P] [US3] 擴充 responsive、keyboard 與 axe cases 於 `apps/web/e2e/p0-responsive.spec.ts`、`p0-keyboard.spec.ts`、`p0-a11y.spec.ts`
  - **Area**：上述三個 E2E 檔案
  - **Depends on**：T039
  - **Goal**：把 `/growth-diary` 納入既有 P0 viewport、keyboard 與 accessibility matrix。
  - **Acceptance**：360×800、768×1024、1024×768、1440×900 無 overflow/遮蔽；filter/detail 全鍵盤操作；axe 無新增重大違規。

- [ ] T042 [P] [US3] 建立 delayed A→B tenant switch Blob lifecycle E2E 於 `apps/web/e2e/management-context-switch.spec.ts`
  - **Area**：`apps/web/e2e/management-context-switch.spec.ts`
  - **Depends on**：T039
  - **Goal**：瀏覽器層證明舊 list/detail/photo request 與 object URL 在 context switch 後失效。
  - **Acceptance**：abort A requests、revoke A object URL、B 畫面從未短暫顯示 A 的文字/數量/名稱/圖片；重新登入亦同。

**Checkpoint**：所有 user story 皆能獨立驗收，且 tenant switch、responsive、keyboard、axe 有瀏覽器證據。

## Phase 6：Cross-cutting validation gate

**Purpose**：依 repository 真實 scripts 完成 targeted 與 full quality gate；不以刪測試、skip 或放寬 assertion 宣稱完成。

- [ ] T043 執行 Growth Diary targeted backend、media、contract 與 isolation validation
  - **Area**：`services/api/app/`、`tests/unit/test_media_sanitization.py`、`tests/contract/test_growth_diary_management_contract.py`、`tests/contract/test_generated_contract_types.py`、`tests/integration/test_growth_diary_management*.py`、`tests/security/test_growth_diary_management_isolation.py`
  - **Depends on**：T034、T040、T041、T042
  - **Goal**：先執行 quickstart 的 migration、Ruff、Pytest、contract generation/check 與 targeted web tests。
  - **Acceptance**：targeted Ruff/format/Pytest 通過；`npm --prefix packages/contracts run generate` 後 check 通過；Vitest/typecheck/format:check 與 Growth Diary Playwright/axe cases 通過；任何現有 architecture 若強制 read audit，停止並回報 blocker，不自行擴 scope。

- [ ] T044 執行完整 repository quality gate 並審查最終 diff
  - **Area**：`scripts/verify_local.sh`、整個 Git diff
  - **Depends on**：T043
  - **Goal**：以 repository 既有完整 gate 驗證 backend、frontend、contract、build、storage 與文件品質。
  - **Acceptance**：`VERIFY_LOCAL_SKIP_DOCKER=1 ./scripts/verify_local.sh`（或依環境執行完整版本）、必要 Playwright matrix、`git diff --check` 全通過；`git status` 僅含本 feature 預期檔案，無 read audit、streaming abstraction、原始圖片 storage 或 unrelated change。

## Dependencies & Execution Order

### Critical path

```text
T001 contract guard
  → T002–T004 migration/ORM
  → T005–T011 media policy/metadata
  → T012–T015 persistence/transaction compensation
  → T016–T017 AI provenance persistence
  → T018–T022 backend read contracts/APIs
  → T023 canonical/generated contract
  → T024–T032 P1 frontend
  → T033–T036 filters/pagination
  → T037–T042 responsive/E2E/tenant switch
  → T043–T044 validation gates
```

### User story dependencies

- **US1（P1）**：依賴 Phase 1–2；完成後可獨立展示 list/detail/photo/provenance。
- **US2（P2）**：依賴 US1 的 list API 與 frontend data/page，但不依賴 US3。
- **US3（P3）**：依賴 US1/US2 完整互動狀態，負責跨裝置與瀏覽器安全驗收。

### Parallel opportunities

- T002 與 T005 可在 T001 後平行，因分別修改 migration test 與 media unit test。
- T012 可在 T008/T009 進行期間平行準備，最後與 T011 匯合至 T013。
- T018、T019、T020 可在 T017 後平行建立 contract、repository 與 security tests。
- T025、T027、T029、T031 在 T024 後可分別於不同 test/component boundary 平行。
- T033 完成並由 T034 實作 backend filter 後，T035 可與其他不修改 Growth Diary page test 的 US1 polish 分工；正式依賴仍以 task metadata 為準。
- T040、T041、T042 在共同 fixtures T039 完成後可平行。

## Parallel execution examples

### US1 tests

```text
T018 runtime/feature contract parity
T019 organization-scoped repository reads
T020 role/RLS/tenant isolation
```

### US1 frontend boundaries

```text
T025 timeline/page states
T027 lazy provenance detail
T029 authenticated photo Blob lifecycle
T031 route/navigation integration
```

### US3 browser verification

```text
T040 core Growth Diary E2E
T041 responsive/keyboard/axe matrix
T042 delayed A→B tenant switch
```

## Implementation Strategy

### MVP first

1. 完成 T001–T017 foundational safety 與 persistence。
2. 完成 T018–T032 US1。
3. 停止並獨立驗收 list/detail/photo/provenance、角色與 A/B isolation。
4. 確認 MVP 後再加入 US2、US3。

### Incremental delivery

1. Foundation：migration、media、transaction、AI persistence。
2. US1：唯讀日記 timeline、detail/raw output、private photo。
3. US2：server-side search/mood/pagination。
4. US3：responsive、keyboard、error state、tenant switch 與 axe。
5. Targeted gate 後再執行 full repository gate。

## Notes

- Test tasks 必須先失敗，再執行相依 implementation task；不得刪除或任意放寬 assertion。
- `[P]` 僅在依賴已完成且檔案不衝突時成立。
- canonical/generated contract T023 是所有 frontend data/UI task 的硬 dependency。
- migration/ORM T002–T004 是 repository/API task 的硬 dependency。
- transaction compensation T014–T015 不得併入一般 webhook refactor。
- 若現有 architecture 強制新增 read audit，停止相關 task 並回報 blocker。
- 每完成一個 phase 先執行該 phase targeted tests，再進下一 phase。
