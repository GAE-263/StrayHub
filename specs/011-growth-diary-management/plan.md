# Implementation Plan: 毛孩日記管理頁

**Branch**: `011-growth-diary-management` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-growth-diary-management/spec.md`

## Summary

在既有管理工作台新增 `/growth-diary`，讓 STAFF、SHELTER_ADMIN 與具 active shelter context 的 PLATFORM_ADMIN 以時間軸卡片查看目前收容所的領養後日記。後端把既有無型別、無分頁清單補成明確 response model，加入 server-side 動物搜尋、AI mood 篩選、穩定分頁、單筆 provenance detail 與 authenticated buffered photo response。前端沿用 management shell、`authFetch`、StateViews 與 generated OpenAPI type，tenant switch 時中止舊請求並清除 photo Blob。

AI 摘要固定標示為未經人工確認、非醫療診斷；additive migration 保存分析狀態、模型／prompt／schema 版本、raw output 與時間，既有缺少來源的資料不回填假 provenance。新圖片透過既有 Pillow sanitization pipeline 在完整 decode 前做 25M pixel gate，套用 orientation、移除 metadata、取 animated 第一幀、保留 alpha，並以 1600px/quality 82 → quality 72 → 1280px/quality 68 的固定 fallback 產生最多 2 MB 的 WebP。第一版唯讀，不新增 read audit、streaming abstraction、編輯、刪除、正式處理狀態或聯絡領養人的 mutation。

## Technical Context

**Language/Version**: Python 3.12、TypeScript 5.7、React 19、Next.js 15

**Primary Dependencies**: FastAPI、Pydantic、SQLAlchemy、Alembic、PostgreSQL、MinIO/S3 adapter、Next.js App Router、既有 UI primitives、lucide-react；不新增 runtime dependency

**Storage**: PostgreSQL `growth_diary_entries`、`animals`、`adoption_inquiries`；private MinIO object storage；只保存 final sanitized WebP

**Testing**: Ruff、Pytest、runtime/canonical OpenAPI contract tests、Vitest、TypeScript typecheck、Prettier、Playwright、axe

**Target Platform**: Linux/GCP FastAPI service，以及桌面／平板／手機瀏覽器管理介面

**Project Type**: 前後端分離、多租戶 web application

**Performance Goals**: 預設 50 筆、上限 100 筆；3 秒內看到首批結果或明確 state；50 筆標準資料可在 15 秒內找到指定動物或 concern 項目

**Constraints**: 每條 entry/detail/photo/count/join query 顯式限制 active `organization_id`；不接受 client organization id；RLS 繼續 FORCE；private photo 不暴露 MinIO host/object key/Bearer query token；輸入最多 10 MB 且完整 decode 前限制 25M pixels；final WebP 最多 2 MB；storage success + DB transaction failure 必須補償刪除；原始 note 不被 AI 覆蓋；AI 不診斷、不自動排序、不改正式狀態；list 不含 raw output；切換 shelter 不得發布舊 request/blob；第一版唯讀且不新增 read audit

**Scale/Scope**: 一個 management route、三個 GET API contract（list/detail/photo）、一個 additive migration、既有 growth diary AI 寫入補強、canonical/generated contract、backend/frontend/E2E 測試

## Constitution Check

_Gates evaluated before Phase 0 and re-evaluated after Phase 1 design._

- **CRM 唯一事實來源：PASS** — 只讀既有 GrowthDiaryEntry 與 Animal，不建立前端副本或第二套正式狀態。
- **原始資料不得被衍生結果取代：PASS** — note 與提交事實持續保存；照片依既有 CRM media safety policy 只保存正規化 WebP，AI 與 provenance 只做衍生區塊，migration 不改既有原始日記。
- **AI 不負責診斷或最終判定：PASS** — concern 顯示為「AI 建議人工查看」，只供主動篩選，不自動排序、不寫醫療／動物狀態。
- **AI 結果驗證、標示與追溯：PASS** — 新分析保存 provider/model/model version/prompt/schema/raw output/time；UI 標示未確認與非診斷，legacy 誠實標示來源未留存。
- **回填低摩擦：PASS** — LINE 維持非同步且先保存原始日記；只補 photo metadata 與 provenance，不增加領養人步驟。
- **歷史完整可追溯：PASS** — 不刪除或覆蓋日記；stable newest-first pagination 保留同日多筆。
- **LINE 只是輸入通道：PASS** — 圖片驗證、正規化、storage ownership、DB 建立與 compensation 均由既有後端流程負責；管理授權、filter、photo 與 provenance 也由後端處理。
- **權限、隱私與稽核：PASS** — list/detail/photo 均驗證 role、active organization 與 RLS；photo fail closed，raw AI 只由授權 detail 提供。本 feature 不新增高頻 read audit，因 Constitution VIII 要求的是重要資料異動稽核；authentication、authorization、mutation audit 與錯誤可觀測性維持不變。
- **P0 獨立可驗收：PASS** — local fixture 可獨立驗證清單、空狀態、隔離與圖片，不依賴 Gemini 在線成功。
- **文件與品質門檻：PASS** — 文件以台灣正體中文為主；實作完成前執行 Ruff/Pytest 與 web test/typecheck/format/E2E。
- **多收容所隔離：PASS** — client 不送 organization id；platform scope 仍有 explicit organization filters，A/B isolation 與 context switch 有專門測試。

## Project Structure

### Documentation (this feature)

```text
specs/011-growth-diary-management/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── growth-diary-management.openapi.yaml
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
services/api/app/api/growth_diary.py
services/api/app/application/growth_diary_service.py
services/api/app/application/growth_diary_ai_analysis_service.py
services/api/app/application/media_sanitization.py
services/api/app/application/media_service.py
services/api/app/api/line_webhook.py
services/api/app/infrastructure/ai/gemini_client.py
services/api/app/persistence/models/growth_diary.py
services/api/app/persistence/repositories/growth_diary_repository.py
services/api/migrations/versions/0042_growth_diary_management.py

apps/web/app/(management)/growth-diary/page.tsx
apps/web/app/(management)/growth-diary/page.test.tsx
apps/web/features/growth-diary/GrowthDiaryPage.tsx
apps/web/features/growth-diary/GrowthDiaryEntryCard.tsx
apps/web/features/growth-diary/DiaryPhoto.tsx
apps/web/features/growth-diary/api.ts
apps/web/features/growth-diary/types.ts
apps/web/features/growth-diary/growth-diary.module.css
apps/web/components/management/AppSidebar.tsx
apps/web/e2e/fixtures.ts
apps/web/e2e/growth-diary-management.spec.ts
apps/web/e2e/p0-responsive.spec.ts
apps/web/e2e/p0-keyboard.spec.ts
apps/web/e2e/p0-a11y.spec.ts

specs/001-volunteer-care-report/contracts/openapi.yaml
packages/contracts/src/openapi.ts
tests/contract/test_growth_diary_management_contract.py
tests/integration/test_growth_diary_management.py
tests/integration/test_growth_diary_media_consistency.py
tests/security/test_growth_diary_management_isolation.py
tests/unit/test_media_sanitization.py
```

**Structure Decision**：沿用 FastAPI router → application service → SQLAlchemy model/repository 與 Next.js management route → feature components 的既有分層。route 只組裝 `GrowthDiaryPage`；API、generated types、card/photo lifecycle 與 page-scoped CSS 放在 `features/growth-diary`。不新增 domain abstraction；擴充既有 GrowthDiary service/repository。

## Phase 0: Research Decisions

完整決策見 [research.md](./research.md)：

1. 重用 management shell 與 organization-scoped `authFetch`，不信任 client organization id。
2. 使用能承載照片、長文字及 AI 分區的時間軸卡片，不使用 table。
3. list 加 server-side query/mood/page/page_size 與 deterministic ordering。
4. `specs/001-volunteer-care-report/contracts/openapi.yaml` 維持唯一 canonical source；feature contract 是設計輸入，實作時同步合併到 canonical，再生成 TypeScript。
5. private photo 走同源 authenticated buffered response；2 MB ceiling 下沿用 `ObjectStoragePort.get()`，React 管理 scoped Blob lifecycle。
6. 既有 media sanitization pipeline 擴充為 WebP normalization；不建立平行 image service，並在完整 decode 前執行 application-level 25M pixel gate。
7. per-event webhook orchestration 擁有新 object 的 compensation token；只有 DB transaction 成功離開 commit boundary 後才視為 durable。
8. AI mood 是未確認描述性建議；新增 status/provenance/raw output，legacy 不假造歷史，raw output 只在 detail。
9. 重用 StateViews/UI primitives，區分真正 empty、filtered empty、403、network 與 image error。
10. 以 sanitization unit、storage/DB failure integration、contract、API/RLS、component 與 browser tenant switch 分層驗證。

## Phase 1: Design Summary

- [data-model.md](./data-model.md) 定義原始資料 invariant、final WebP metadata、媒體處理暫態狀態、AI state/provenance、list/detail read models、filter/page 與 additive migration。
- [contracts/growth-diary-management.openapi.yaml](./contracts/growth-diary-management.openapi.yaml) 定義 active-shelter list/detail/photo、auth、query bounds、nullable、安全錯誤；photo media type 由 `content.image/webp` 表達，額外 headers 只宣告 cache 與 nosniff。
- [quickstart.md](./quickstart.md) 定義 migration、Ruff/Pytest、contract generation、Vitest/typecheck/Prettier、Playwright、responsive/a11y 與 A→B switch 驗收。

### Implementation sequence

1. 擴充既有 `media_sanitization.py`，由 Growth Diary 呼叫明確選用 WebP normalization policy，既有其他 media caller 的輸出契約不在本 feature 內變更：10 MB input gate、在 `source.load()` 前檢查 25M pixels、將 Pillow `DecompressionBombWarning` 視為拒絕訊號並同時保留 application-level lower limit、套用 EXIF orientation、取第一 frame、保留 alpha、不 upscale，最後依 1600/82 → 1600/72 → 1280/68 產生最多 2 MB 的 WebP；checksum/MIME/size 只從 final bytes 計算。
2. 在既有 `MediaProcessingService` 與 LINE growth-diary handler 串接 final `StoredObject.metadata`，不保存 original/intermediate；新增 per-event compensation ownership，使 sanitization failure 無 object、storage failure 無 entry、DB flush/commit failure 刪除已建立 object，cleanup failure structured log 且保留原始錯誤。
3. 新增 additive migration 與 ORM 欄位；新資料 `photo_key != null` 時 `photo_content_type=image/webp`，legacy 維持 nullable/fail closed；AI 背景任務保存 explicit status/provenance/raw output。
4. 擴充 GrowthDiary service：entry/inquiry/animal 與所有 count/list/detail/photo join 明確 organization scope；stable pagination/filter/order、AI projection、detail 與使用 `ObjectStoragePort.get()` 的 buffered private photo read。
5. Router 加 Pydantic response models、Query validation、detail/photo routes 與安全 error contract；photo 只回 `image/webp`、`private, no-store`、`nosniff`。
6. 將 feature contract 合併進唯一 canonical OpenAPI，更新 generated TypeScript 與 contract tests，先鎖定 API 再接前端；list 僅含 provenance summary，detail 才含完整 provenance/raw output。
7. 建立 growth-diary feature：query builder、state、timeline cards、AI disclosure、authenticated Blob photo lifecycle。
8. 建立 route 與 shared navigation；完成 empty/filter/error/permission/retry/pagination/mobile layout。
9. 補 sanitization unit tests、storage/DB/cleanup failure integration tests、角色與 A/B isolation tests、Vitest、Playwright fixtures、feature E2E、responsive/keyboard/axe 與 delayed A→B tenant switch。

### Transaction and orphan cleanup boundary

- **Ownership**：`_handle_growth_diary_message` 仍使用既有 `MediaProcessingService` 寫入 object；webhook 的單一 event orchestration 持有該次新建 object 的 organization-scoped compensation token。不得建立新的 saga/service layer。
- **Failure boundary**：目前 DB transaction 由 `webhook()` 的 `async with session.begin()` 擁有，真正 commit 發生在 handler 返回後；因此 handler-local `try/delete` 只能涵蓋 insert/flush error，不能單獨涵蓋 commit error。
- **Success**：只有 event transaction 成功離開 `session.begin()` 後才清除 compensation token，object 與 GrowthDiaryEntry 才同時視為 durable；Growth Diary 成功回覆與 AI background task 參數由 handler 準備、在 commit 後才送出／註冊，避免 commit failure 後仍告知「已記錄」或分析不存在的 entry。
- **Compensation**：任何 sanitization 後、object put 後且 transaction 尚未 durable 的錯誤（含 insert、flush、commit failure）都以相同 `organization_id + object_key` 呼叫現有 `ObjectStoragePort.delete()`；deterministic event object key 也避免 retry 產生多個不同 orphan。
- **Cleanup failure**：以 `logger.exception` 產生 `growth_diary_orphan_cleanup_failed` structured log，包含 organization/entry event correlation 但不回傳 object key 或內部例外給使用者；保留並重新拋出／回報原始 DB failure，cleanup failure 不覆蓋 root cause。第一版不導入 distributed transaction、saga 或 background cleanup framework。
- **Post-commit external failure**：DB 已 durable 後若 LINE 成功回覆或 AI task registration 失敗，不刪除 object/entry；沿用外部通知失敗的可觀測 logging／安全回覆策略，原始日記仍保留。

### Constitution Check — Post-Design

- **PASS** — migration 只補圖片 metadata 與 AI provenance，不建立另一份日記或正式健康狀態。
- **PASS** — list/detail/photo explicit organization filter、Animal join scope 與 FORCE RLS 形成雙層隔離，platform admin 亦然。
- **PASS** — AI 可追溯且 UI 標示限制；無憑證、photo-only 或分析失敗時原始日記仍可查看。
- **PASS** — authenticated buffered Blob 不把 credential 放 URL，不暴露 MinIO hostname/object key，unmount/context switch 會撤銷；final 2 MB ceiling 不需要 streaming abstraction。
- **PASS** — P0 不依賴外部 Gemini、P1 mutation 或完整人工覆核流程。
- **PASS** — 驗收涵蓋 Ruff、Pytest、contract generation、Vitest、typecheck、format、Playwright 與 axe。

## Complexity Tracking

本設計沒有 Constitution gate 例外。migration、detail、authenticated photo endpoint 與 transaction compensation 用於滿足 AI 追溯、private media、多租戶安全及 object/DB 一致性；沿用既有 Pillow、media service、storage port 與 webhook transaction ownership，未新增 domain abstraction、read audit 或外部 dependency。
