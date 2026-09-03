# Implementation Plan: 收容所權限管理介面改善

**Branch**: `007-shelter-permission-ux` | **Date**: 2026-08-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-shelter-permission-ux/spec.md`

## Summary

本功能改善收容所管理員的 `/shelters` 權限管理體驗：由 Membership 清單回傳目前收容所範圍內使用者的顯示名稱與帳號，前端以「權限管理」作為頁面主標題，將身份、角色／狀態與操作分層呈現，並在桌面與手機寬度採可重排的 Membership 卡片。時區改為只顯示台灣統一使用 `Asia/Taipei` 的說明，不再提供頁面上的時區修改控制。既有 Membership mutation、授權與 Audit 行為維持不變。

## Technical Context

**Language/Version**: TypeScript／React／Next.js 15；Python 3.12／FastAPI

**Primary Dependencies**: React 19、現有 UI primitives、SQLAlchemy、Pydantic、OpenAPI Typescript contract

**Storage**: PostgreSQL 既有 `users`、`organization_memberships` 與 `organizations` 資料；不新增資料表或欄位

**Testing**: Vitest、TypeScript typecheck、Pytest contract tests、Ruff；Browser smoke 以本機管理頁面與 `local-shelter-admin-a` 驗證

**Target Platform**: 本機與正式瀏覽器的響應式 Web 管理工作台；FastAPI runtime

**Project Type**: 多租戶 Web application（Next.js frontend + FastAPI backend）

**Performance Goals**: 權限管理頁面的既有資料載入與操作延遲不因新增身份欄位而顯著增加；清單維持單次組合查詢，避免每筆 Membership 觸發額外查詢

**Constraints**: 使用者資料只能在已驗證的 organization scope 內回傳；不改變既有授權、Audit、Membership mutation 與醫療資料權限政策；時區固定為台灣 `Asia/Taipei`

**Scale/Scope**: 目前 `/shelters` 頁面與其 Membership list response；涵蓋至少數十筆 Membership、1440px／768px／360px 寬度，不改動其他管理頁

## Constitution Check

*Gate before Phase 0*: PASS

- CRM 為唯一事實來源：使用既有 User 與 Membership 資料，不建立前端或第二份使用者資料。
- 權限、隱私與稽核預設啟用：身份查詢沿用目前收容所 authorization gate，既有 mutation 與 Audit 不放寬。
- 多收容所資料隔離：Membership 與 User join 必須綁定目前 organization，禁止跨租戶補名。
- 文件語言與 Python 品質門檻：本 feature 文件以台灣正體中文撰寫；Python 變更需通過 Ruff／Pytest 驗證。
- 開發流程：本計畫由 spec、research、data model、contract、quickstart 與 tasks 依序產生，再進入實作。

## Project Structure

### Documentation (this feature)

```text
specs/007-shelter-permission-ux/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── membership-list.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
apps/web/app/(management)/shelters/
├── page.tsx
└── page.test.tsx
apps/web/components/management/AppSidebar.tsx
apps/web/app/globals.css
services/api/app/api/organization_management.py
services/api/app/persistence/repositories/organization_repository.py
packages/contracts/src/openapi.ts
specs/001-volunteer-care-report/contracts/openapi.yaml
tests/contract/test_organization_management_contract.py
```

**Structure Decision**: 沿用現有管理工作台與 organization management API；前端只在 shelters route 及共用 sidebar／global styles 增加呈現層，後端只在 organization membership read model 增加目前 scope 內的 User identity projection，契約同步更新並由既有測試驗證。

## Complexity Tracking

無 Constitution violation，不需要例外。
