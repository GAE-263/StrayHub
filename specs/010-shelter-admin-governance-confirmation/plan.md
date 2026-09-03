# Implementation Plan: 收容所管理員人數與權限調整確認

**Branch**: `fix/member_management` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-shelter-admin-governance-confirmation/spec.md`

## Summary

本功能在每個收容所的 Membership 權限管理中維持一至兩位啟用中的 `SHELTER_ADMIN`。既有的角色與狀態欄位已能表達需求，因此由後端在所有會改變管理員有效權限的寫入路徑統一驗證，並以收容所資料列作為同一租戶內並發異動的鎖定點。前端將角色、啟用狀態、醫療資料權限、封存／恢復等權限異動改為先開啟確認 Modal，成功後才在左下角顯示 Toast；取消、拒絕、失敗或結果不明均不顯示成功 Toast。

## Technical Context

**Language/Version**: Python 3.12、TypeScript、React 19、Next.js 15

**Primary Dependencies**: FastAPI、SQLAlchemy、Pydantic、Alembic（本功能不新增 migration）、Next.js、React、既有 `AlertDialog`／`Dialog`／`Toast` 元件

**Storage**: PostgreSQL，沿用 `organizations`、`organization_memberships`、`users` 與既有 `audit_records`

**Testing**: Pytest、Ruff、TypeScript typecheck、Vitest、Playwright E2E、既有 OpenAPI／contract tests

**Target Platform**: FastAPI web service 與桌面／平板／手機瀏覽器管理介面

**Project Type**: 前後端分離的 web application

**Performance Goals**: 權限調整維持單次主要 Membership 讀取與寫入交易；成功操作後頁面在一次重新載入內反映新狀態，Toast 於成功回應後 2 秒內可見。

**Constraints**: 人數上下限必須在後端交易內重新驗證；所有 Membership 查詢與異動受 organization scope 及既有授權限制；更新、封存與恢復必須帶入讀取時的 `access_version`，成功寫入後遞增版本，過期版本不得覆寫最新狀態；重要成功與拒絕結果寫入 Audit；不新增第二套 User／Membership 狀態來源；不修改時區語意。

**Scale/Scope**: 目前 `/shelters` 與 `/shelters/archived` 兩個管理 route、Membership 相關 API、共用權限管理 UI 與測試；每個收容所為小至中型成員清單。

## Constitution Check

_Gates evaluated before Phase 0 and re-evaluated after Phase 1 design._

- **CRM 唯一事實來源**: PASS — 使用既有 `OrganizationMembership` 的角色／狀態與既有 `User`，不建立管理員數量副本。
- **權限、隱私與稽核預設啟用**: PASS — 後端重新驗證操作者及 organization scope；成功與拒絕的權限異動都保留 Audit，Toast 不顯示敏感資料。
- **多收容所資料隔離**: PASS — 以 organization id 鎖定、查詢及寫入 Membership；收容所 A 的管理員不能影響或得知收容所 B 的成員。
- **歷史紀錄完整且可追溯**: PASS — 停用／封存／降權不刪除 User、Membership 歷史或 Audit；志工授權狀態仍與 Membership 狀態分開。
- **P0 獨立可驗收**: PASS — 一至兩位管理員的上下限、Modal 確認與 Toast 可使用 local fixture 獨立測試，不依賴 LINE、AI 或外部服務。
- **文件語言與 Python 品質門檻**: PASS — 規劃、合約與驗收文件以台灣正體中文為主；實作完成前執行 Ruff、Pytest 及前端品質檢查。

## Project Structure

### Documentation (this feature)

```text
specs/010-shelter-admin-governance-confirmation/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── shelter-admin-governance-confirmation.md
├── validation/
│   └── usability-test-plan.md  # 由實作驗收建立
├── checklists/
│   └── requirements.md
└── tasks.md              # 由 $speckit-tasks 建立
```

### Source Code (repository root)

```text
services/api/app/application/organization_management.py
services/api/app/api/organization_management.py
services/api/app/persistence/repositories/organization_repository.py
services/api/app/application/audit_service.py

apps/web/app/(management)/shelters/page.tsx
apps/web/app/(management)/shelters/archived/page.tsx
apps/web/app/(management)/volunteers/access/page.tsx
apps/web/app/(management)/volunteers/applications/page.tsx
apps/web/components/management/MembershipPermissionDialog.tsx
apps/web/components/ui/alert-dialog.tsx
apps/web/components/ui/toast.tsx
apps/web/app/globals.css

tests/unit/test_organization_management_service.py
tests/integration/test_organization_management.py
tests/contract/test_organization_management_contract.py
tests/contract/test_volunteer_access_contract.py
tests/unit/test_volunteer_grant_mutation.py
tests/integration/test_volunteer_access_approval.py
apps/web/app/(management)/shelters/page.test.tsx
apps/web/app/(management)/shelters/archived/page.test.tsx
apps/web/e2e/organization-management.spec.ts
apps/web/e2e/volunteer-access-approval.spec.ts
specs/001-volunteer-care-report/contracts/openapi.yaml
```

**Structure Decision**: 沿用既有 FastAPI／SQLAlchemy／PostgreSQL 後端與 Next.js management route。把人數邊界放在 `OrganizationManagementService` 的集中轉換規則，讓所有 API 寫入路徑共用；把確認 Modal 抽成可重用的管理 UI 元件，正常與封存頁共用同一套確認與結果回饋語意。因既有 schema 已有必要欄位，本功能不建立新的資料表或 migration。

## Phase 0: Research Decisions

研究結果收錄於 [research.md](./research.md)，已解除技術上下文的未知項目：

1. 沿用既有 `OrganizationMembership.role` 與 `status`，不新增管理員政策資料表或 migration；人數是跨 Membership 的衍生 invariant，不是另一份身分來源。
2. 以 `organizations` 的資料列鎖定同一收容所的權限 mutation；鎖定後重新讀取目標 Membership 與啟用中管理員數量，再檢查最終狀態，避免兩個請求同時突破一至兩位。
3. 由 Service 先計算完整的 before／after projection，並要求 mutation 帶入目前 `access_version`；所有驗證通過後才套用欄位，成功時遞增版本，避免角色與狀態同一請求中途修改後發生部分結果或舊 Modal 覆寫新資料。
4. API 沿用既有 Membership endpoints 與錯誤回應格式；成功與拒絕都寫入現有 `AuditService`，拒絕事件使用 `result = denied` 並保留安全的 domain code。
5. 前端重用既有 `AlertDialog`、`Dialog` 與 `Toast`，不引入外部通知套件；收容所 Membership 與志工授權的有效異動、以及建立啟用中 `SHELTER_ADMIN` 的最終提交，改為統一的待確認狀態。

## Phase 1: Design Summary

- [data-model.md](./data-model.md) 定義既有 Membership 的管理員計數 invariant、權限變更 projection、狀態轉換與 Audit 欄位；明確記錄不新增 migration。
- [contracts/shelter-admin-governance-confirmation.md](./contracts/shelter-admin-governance-confirmation.md) 定義既有 list／create／update／archive／restore endpoints 的人數驗證、錯誤與稽核契約，以及 `/shelters` 與 `/shelters/archived` 的確認／Toast 行為。
- [quickstart.md](./quickstart.md) 定義以 `local-shelter-admin-a` 在 API 8001／Web 3001 驗證一位下限、兩位上限、取消 Modal、成功 Toast、失敗無 Toast、封存／恢復與租戶隔離的手動及自動測試。
- 實作優先順序為：後端鎖定與完整轉換驗證 → API 稽核／錯誤契約 → 共用確認 Modal／Toast → 正常與封存 route 接線 → unit／integration／contract／Vitest／Playwright 驗收。

### Constitution Check — Post-Design

- **PASS** — 不新增 User、Membership 或管理員政策副本；管理員數量由既有 Membership 交易狀態衍生。
- **PASS** — organization row lock 只負責並發序列化，不取代 CRM 資料；實際角色與狀態仍寫回既有 Membership。
- **PASS** — 所有 API 仍以已驗證的 organization scope 與 Membership 授權執行，前端 Modal／Toast 不是安全邊界。
- **PASS** — 成功及拒絕異動保留 Audit；封存、停用、降權不刪除 User 或歷史資料，志工授權狀態不被重新啟用繞過。
- **PASS** — 設計可由 local fixture 與現有測試工具獨立驗收，不依賴外部服務。
- **PASS** — 文件與測試規劃符合正體中文及 Python Ruff／Pytest 品質門檻。

## Complexity Tracking

本設計沒有違反 Constitution Gate，不需新增例外。
