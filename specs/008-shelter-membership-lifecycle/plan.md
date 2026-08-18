# Implementation Plan: 收容所成員封存與權限管理版型改善

**Branch**: `fix/member_management` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-shelter-membership-lifecycle/spec.md`

## Summary

本功能將現有 Membership 停用流程擴充為可稽核的「停用／重新啟用／封存／恢復」生命週期：預設權限管理頁面排除已封存成員，另提供 `/shelters/archived` 查詢與恢復；同時將志工置於上方、工作人員置於下方，並依角色與狀態排序，以偏灰色卡片降低停用、過期與撤銷項目的視覺強度。後端保留 User、Membership、照護回報與 Audit 歷史，不執行破壞性的 User 刪除。

## Technical Context

**Language/Version**: Python 3.11+、TypeScript、React 19、Next.js 15

**Primary Dependencies**: FastAPI、SQLAlchemy、Pydantic、Next.js、React、既有 UI Dialog/Card/Badge 元件

**Storage**: PostgreSQL，透過既有 SQLAlchemy models 與 Alembic migrations

**Testing**: Pytest、Ruff、Vitest、TypeScript typecheck、Playwright E2E、響應式與可及性測試

**Target Platform**: 本機與部署環境的桌面／手機瀏覽器；FastAPI web service

**Project Type**: 前後端分離的 web application

**Performance Goals**: 管理員開啟正常或封存成員清單時，在現有資料量下維持一次清單請求與可接受的後台互動速度；不新增逐筆查詢造成的明顯延遲。

**Constraints**: 所有成員查詢與異動必須受目前收容所範圍與既有管理員授權限制；重要異動必須寫入 Audit；志工授權的 `revoked` 狀態不得藉由重新啟用 Membership 繞過。

**Scale/Scope**: 目前每個收容所的成員數量為小至中型管理清單；本功能涵蓋 `/shelters`、`/shelters/archived` 及其 Membership API，不改寫其他管理頁的整體版型。

## Constitution Check

_Gates evaluated before Phase 0 and re-evaluated after Phase 1 design._

- **CRM 唯一事實來源**: PASS — 不建立第二份 User 或 Membership 資料，封存狀態仍由既有 CRM identity model 保存。
- **權限、隱私與稽核預設啟用**: PASS — 封存、恢復與查詢均沿用目前收容所授權，並新增對應 Audit 事件。
- **多收容所資料隔離**: PASS — API 以已驗證的 organization context 篩選，封存某一收容所的 Membership 不影響其他收容所。
- **原始資料與歷史紀錄完整**: PASS — 不刪除 User、照護回報、醫療資料或 Audit；封存只改變成員可管理狀態。
- **P0 獨立可驗收**: PASS — 封存／恢復與預設清單收起可獨立以 local-shelter-admin-a 測試。
- **文件語言與 Python 品質門檻**: PASS — 規格與驗收文件使用台灣正體中文；Python 變更完成前執行 Ruff 與 Pytest。

## Project Structure

### Documentation (this feature)

```text
specs/008-shelter-membership-lifecycle/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── membership-lifecycle.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
services/api/app/api/organization_management.py
services/api/app/application/organization_management.py
services/api/app/persistence/models/identity.py
services/api/app/persistence/repositories/organization_repository.py
services/api/app/persistence/repositories/volunteer_access_repository.py
services/api/migrations/versions/<new-membership-archive-migration>.py
tests/contract/test_organization_management_contract.py
tests/<organization-management-tests>.py

apps/web/app/(management)/shelters/page.tsx
apps/web/app/(management)/shelters/page.test.tsx
apps/web/app/(management)/shelters/archived/page.tsx
apps/web/app/(management)/shelters/archived/page.test.tsx
apps/web/components/management/<membership-components>.tsx
apps/web/components/ui/dialog.tsx
apps/web/app/globals.css
apps/web/e2e/organization-management.spec.ts
apps/web/e2e/p1-management.spec.ts
packages/contracts/src/openapi.ts
specs/001-volunteer-care-report/contracts/openapi.yaml
```

**Structure Decision**: 沿用既有 FastAPI／SQLAlchemy 後端、Next.js management route、共用 UI 元件與 contracts 生成／同步方式。將已封存頁面作為 `/shelters/archived` 的獨立 route，但讓 Membership 查詢與卡片分區邏輯可由正常頁與封存頁共用，避免兩頁出現不同的權限語意。

## Complexity Tracking

本設計沒有違反 Constitution Gate，不需新增例外。
