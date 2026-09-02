# Implementation Plan: 毛孩日記管理頁

**Branch**: `011-growth-diary-management` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-growth-diary-management/spec.md`

## Summary

在既有管理工作台新增 `/growth-diary`，讓 STAFF、SHELTER_ADMIN 與具 active shelter context 的 PLATFORM_ADMIN 以時間軸卡片查看目前收容所的領養後日記。後端把既有無型別、無分頁清單補成明確 response model，加入 server-side 動物搜尋、AI mood 篩選、穩定分頁、單筆 provenance detail 與 authenticated photo streaming。前端沿用 management shell、`authFetch`、StateViews 與 generated OpenAPI type，tenant switch 時中止舊請求並清除 photo Blob。

AI 摘要固定標示為未經人工確認、非醫療診斷；additive migration 保存分析狀態、模型／prompt／schema 版本、raw output 與時間，既有缺少來源的資料不回填假 provenance。第一版唯讀，不新增編輯、刪除、正式處理狀態或聯絡領養人的 mutation。

## Technical Context

**Language/Version**: Python 3.12、TypeScript 5.7、React 19、Next.js 15

**Primary Dependencies**: FastAPI、Pydantic、SQLAlchemy、Alembic、PostgreSQL、MinIO/S3 adapter、Next.js App Router、既有 UI primitives、lucide-react；不新增 runtime dependency

**Storage**: PostgreSQL `growth_diary_entries`、`animals`、`adoption_inquiries`；private MinIO object storage

**Testing**: Ruff、Pytest、runtime/canonical OpenAPI contract tests、Vitest、TypeScript typecheck、Prettier、Playwright、axe

**Target Platform**: Linux/GCP FastAPI service，以及桌面／平板／手機瀏覽器管理介面

**Project Type**: 前後端分離、多租戶 web application

**Performance Goals**: 預設 50 筆、上限 100 筆；3 秒內看到首批結果或明確 state；50 筆標準資料可在 15 秒內找到指定動物或 concern 項目

**Constraints**: 每條 entry/detail/photo/count/join query 顯式限制 active `organization_id`；不接受 client organization id；RLS 繼續 FORCE；private photo 不暴露 MinIO host/object key/Bearer query token；原始 note/photo 不被 AI 覆蓋；AI 不診斷、不自動排序、不改正式狀態；切換 shelter 不得發布舊 request/blob；第一版唯讀

**Scale/Scope**: 一個 management route、三個 GET API contract（list/detail/photo）、一個 additive migration、既有 growth diary AI 寫入補強、canonical/generated contract、backend/frontend/E2E 測試

## Constitution Check

_Gates evaluated before Phase 0 and re-evaluated after Phase 1 design._

- **CRM 唯一事實來源：PASS** — 只讀既有 GrowthDiaryEntry 與 Animal，不建立前端副本或第二套正式狀態。
- **原始資料不得被衍生結果取代：PASS** — note/photo 獨立顯示；AI 與 provenance 只做衍生區塊，migration 不改原始資料。
- **AI 不負責診斷或最終判定：PASS** — concern 顯示為「AI 建議人工查看」，只供主動篩選，不自動排序、不寫醫療／動物狀態。
- **AI 結果驗證、標示與追溯：PASS** — 新分析保存 provider/model/model version/prompt/schema/raw output/time；UI 標示未確認與非診斷，legacy 誠實標示來源未留存。
- **回填低摩擦：PASS** — LINE 維持非同步且先保存原始日記；只補 photo metadata 與 provenance，不增加領養人步驟。
- **歷史完整可追溯：PASS** — 不刪除或覆蓋日記；stable newest-first pagination 保留同日多筆。
- **LINE 只是輸入通道：PASS** — 管理授權、filter、photo 與 provenance 由後端處理。
- **權限、隱私與稽核：PASS** — list/detail/photo 均驗證 role、active organization 與 RLS；photo fail closed，raw AI 只由授權 detail 提供。
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
tests/security/test_growth_diary_management_isolation.py
```

**Structure Decision**：沿用 FastAPI router → application service → SQLAlchemy model/repository 與 Next.js management route → feature components 的既有分層。route 只組裝 `GrowthDiaryPage`；API、generated types、card/photo lifecycle 與 page-scoped CSS 放在 `features/growth-diary`。不新增 domain abstraction；擴充既有 GrowthDiary service/repository。

## Phase 0: Research Decisions

完整決策見 [research.md](./research.md)：

1. 重用 management shell 與 organization-scoped `authFetch`，不信任 client organization id。
2. 使用能承載照片、長文字及 AI 分區的時間軸卡片，不使用 table。
3. list 加 server-side query/mood/page/page_size 與 deterministic ordering。
4. Pydantic runtime model、canonical OpenAPI 與 generated TypeScript 共用契約。
5. private photo 走同源 authenticated streaming；React 管理 scoped Blob lifecycle。
6. AI mood 是未確認描述性建議；新增 status/provenance/raw output，legacy 不假造歷史。
7. 重用 StateViews/UI primitives，區分真正 empty、filtered empty、403、network 與 image error。
8. 以 contract、API/RLS、component 與 browser tenant switch 四層驗證。

## Phase 1: Design Summary

- [data-model.md](./data-model.md) 定義原始資料 invariant、photo content type、AI state/provenance、list/detail read models、filter/page 與 additive migration。
- [contracts/growth-diary-management.openapi.yaml](./contracts/growth-diary-management.openapi.yaml) 定義 active-shelter list/detail/photo、auth、query bounds、nullable、安全錯誤與 private image headers。
- [quickstart.md](./quickstart.md) 定義 migration、Ruff/Pytest、contract generation、Vitest/typecheck/Prettier、Playwright、responsive/a11y 與 A→B switch 驗收。

### Implementation sequence

1. 新增 additive migration 與 ORM 欄位；LINE 建立 entry 時保存 sanitized photo content type，AI 背景任務保存 explicit status/provenance/raw output，保持先保存原始日記。
2. 擴充 GrowthDiary service：所有 query 明確 organization scope、stable count/page/filter/order、AI projection、detail 與 private photo read；storage failure fail closed。
3. Router 加 Pydantic response models、Query validation、detail/photo routes 與安全 error contract。
4. 更新 canonical OpenAPI、generated TypeScript 與 contract tests，先鎖定 API 再接前端。
5. 建立 growth-diary feature：query builder、state、timeline cards、AI disclosure、authenticated Blob photo lifecycle。
6. 建立 route 與 shared navigation；完成 empty/filter/error/permission/retry/pagination/mobile layout。
7. 補 Vitest、Playwright fixtures、feature E2E、responsive/keyboard/axe 與 delayed A→B tenant switch。

### Constitution Check — Post-Design

- **PASS** — migration 只補圖片 metadata 與 AI provenance，不建立另一份日記或正式健康狀態。
- **PASS** — list/detail/photo explicit organization filter、Animal join scope 與 FORCE RLS 形成雙層隔離，platform admin 亦然。
- **PASS** — AI 可追溯且 UI 標示限制；無憑證、photo-only 或分析失敗時原始日記仍可查看。
- **PASS** — authenticated Blob 不把 credential 放 URL，不暴露 MinIO hostname/object key，unmount/context switch 會撤銷。
- **PASS** — P0 不依賴外部 Gemini、P1 mutation 或完整人工覆核流程。
- **PASS** — 驗收涵蓋 Ruff、Pytest、contract generation、Vitest、typecheck、format、Playwright 與 axe。

## Complexity Tracking

本設計沒有 Constitution gate 例外。migration、detail 與 authenticated photo endpoint 用於滿足 AI 追溯、private media 與多租戶安全，未新增 domain abstraction 或外部 dependency。
