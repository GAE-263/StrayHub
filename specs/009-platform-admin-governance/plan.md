# Implementation Plan: 平台管理員人數與替換治理

**Branch**: `fix/member_management` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/009-platform-admin-governance/spec.md`

## Summary

本功能建立平台管理員的全域治理流程：啟用中的平台管理員至少一位、正常最多兩位；一般新增或提升在達到上限時被拒絕，並提供一次完成新舊交接的替換流程。設計沿用既有 `User.platform_role`、帳號 `status` 與 `AuditRecord`，新增單一平台治理政策資料列作為上下限來源與並發操作的鎖定點；平台管理員管理 route 不依賴收容所 Membership 或 Active Shelter Context。

## Technical Context

**Language/Version**: Python 3.12、TypeScript、React 19、Next.js 15

**Primary Dependencies**: FastAPI、SQLAlchemy、Pydantic、Alembic、Next.js、React、既有 AuditService 與 management shell

**Storage**: PostgreSQL，透過既有 SQLAlchemy models、Alembic migrations 與 platform-scoped AuditRecord

**Testing**: Pytest、Ruff、Vitest、TypeScript typecheck、Playwright E2E、既有 OpenAPI／contract tests

**Target Platform**: FastAPI web service 與桌面／手機瀏覽器管理介面

**Project Type**: 前後端分離的 web application

**Performance Goals**: 平台管理員候選清單在 Standard Local Fixture 下以單次主要查詢完成；治理操作沿用 policy row lock 與單一交易，不另訂本 Feature 之外的 latency SLA，SC-006 以管理者完成辨識與操作的時間作為使用者驗收指標。

**Constraints**: 平台 route 必須只允許啟用中的 PLATFORM_ADMIN；不得依賴 organization context；所有上下限檢查與權限異動必須在後端同一交易內完成；重要成功與拒絕操作必須可稽核；本 Feature 不提供平台管理員封存、硬刪除或移除 User；具有 VOLUNTEER Membership 或 VolunteerApplication 的帳號不得直接轉任平台管理員。

**Scale/Scope**: 平台管理員治理與一個全域管理頁；本 Feature 涵蓋平台管理員帳號建立／提升、啟用／停用、降權、替換、查詢與稽核，不改變 STAFF、SHELTER_ADMIN、VOLUNTEER 的人數政策。

## Constitution Check

_Gates evaluated before Phase 0 and re-evaluated after Phase 1 design._

- **CRM 唯一事實來源**: PASS — 平台管理員仍是既有 User 的平台角色，不建立第二份帳號資料；治理政策與稽核是平台治理資料，不能取代 User。
- **權限、隱私與稽核預設啟用**: PASS — 所有 route 由後端重新確認平台角色；新增、提升、啟用、停用、降權、替換與拒絕結果均寫入平台稽核紀錄。
- **多收容所資料隔離**: PASS — 平台管理員 route 使用平台 scope，不把任一收容所當成預設範圍；User 的 Membership 仍與平台角色分離，拒絕回應不洩漏非必要資料。
- **歷史紀錄完整且可追溯**: PASS — 不 hard delete User、Membership 或 AuditRecord；降權與停用保留目標帳號及前後狀態。
- **P0 獨立可驗收**: PASS — 可用 local fixture 與測試資料獨立驗收一位下限、兩位上限、替換與稽核，不依賴 LINE、AI 或其他 P1/P2 功能。
- **文件語言與 Python 品質門檻**: PASS — 規劃與驗收文件以台灣正體中文為主；Python 實作完成前執行 Ruff 與 Pytest。

## Project Structure

### Documentation (this feature)

```text
specs/009-platform-admin-governance/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── platform-admin-governance.md
└── tasks.md
```

### Source Code (repository root)

```text
services/api/app/api/platform_admin_management.py
services/api/app/application/platform_admin_management.py
services/api/app/persistence/models/platform_governance.py
services/api/app/persistence/repositories/platform_admin_repository.py
services/api/migrations/versions/0029_platform_admin_governance.py

tests/unit/test_platform_admin_management_service.py
tests/integration/test_platform_admin_governance.py
tests/contract/test_platform_admin_management_contract.py

apps/web/app/(management)/platform-admins/page.tsx
apps/web/app/(management)/platform-admins/page.test.tsx
apps/web/e2e/platform-admin-governance.spec.ts
apps/web/components/management/AppSidebar.tsx
apps/web/components/management/ManagementLayout.tsx
packages/contracts/src/openapi.ts
specs/001-volunteer-care-report/contracts/openapi.yaml
```

**Structure Decision**: 沿用既有 FastAPI／SQLAlchemy／Alembic 後端與 Next.js management route。平台管理員使用獨立 `/platform-admins` route 及 `/v1/platform/administrators` API，避免將全域平台角色混入 `/shelters` 的 organization-scoped Membership 清單；既有 AuditService 與 OpenAPI contracts 同步更新。

## Phase 0: Research Decisions

研究結果收錄於 [research.md](./research.md)，已解除技術上下文的未知項目：

1. 保留 `User.platform_role` 作為平台角色真實來源，`User.status` 作為帳號是否啟用的真實來源。
2. 新增單一 `PlatformAdminPolicy` 資料列保存 `min_active_admins = 1`、`max_active_admins = 2`，並作為並發治理操作的 row lock。
3. 使用獨立 platform-scoped API 與 route，不要求 Active Shelter Context。
4. 沿用 `AuditRecord` 的 `organization_id = null`、`resource_type = platform` 能力，成功與拒絕均可追溯。
5. 提升候選清單排除所有志工 Membership／申請歷史，並由後端在 promote／replacement 再次拒絕，避免 UI 篩選成為唯一安全邊界。
6. Promote／replacement 的歷史志工排除驗證使用真實 `PlatformAdminRepository` 與 PostgreSQL transaction；測試資料在測試結束 rollback，不以 fake repository 作為唯一證據。
7. Standard Local Fixture 必須同時覆蓋 active、expired、revoked Membership，以及 rejected、withdrawn、pending VolunteerApplication；revoked 的資料來源需與現有志工 access 狀態模型一致。
8. Remediation task 邊界固定為：T054 維持既有候選清單覆蓋、T055 負責真實 repository 的 promote／replacement 拒絕、T056 負責 revoked fixture 與 quickstart 同步，不重複宣稱同一項 replacement coverage。

## Phase 1: Design Summary

- [data-model.md](./data-model.md) 定義 User、PlatformAdminPolicy、PlatformAdminView 與平台 AuditRecord 的欄位、狀態與 invariant。
- [contracts/platform-admin-governance.md](./contracts/platform-admin-governance.md) 定義清單、建立／提升、狀態異動、替換、稽核與錯誤契約。
- [quickstart.md](./quickstart.md) 定義包含 2 位平台管理員、1 個可提升帳號、3 種 Membership 歷史與 3 種 VolunteerApplication 歷史的 local fixture，以及上下限、替換、拒絕、並發、志工歷史排除與稽核驗收。
- 後續 remediation 應由 `$speckit-tasks` 追加真實 repository 的 promote／replacement 驗證，以及 revoked fixture 的一致性測試；實作仍須維持 platform role 與 Membership 的角色分離。

### Constitution Check — Post-Design

- **PASS** — 單一政策資料列是治理政策與並發鎖定點，不是第二份 User 或 Membership 事實來源。
- **PASS** — 降權清除既有平台角色；目前平台管理員清單只呈現仍具平台角色的 User，撤銷歷史由既有平台 AuditRecord 追溯，避免狀態語意分裂。
- **PASS** — 平台 API 不依賴收容所 context，並以平台 scope 與後端上下限檢查保護跨租戶治理。
- **PASS** — 設計仍可由 local fixture、單元／整合／contract／E2E 測試獨立驗收，不依賴外部服務。
- **PASS** — 志工歷史排除的追加驗收使用真實 repository transaction 與 rollback，不建立第二份志工身分事實來源，也不讓 fake repository 成為唯一安全邊界。

## Complexity Tracking

本設計沒有違反 Constitution Gate，不需新增例外。
## Security and migration clarifications

- Account creation, promotion, and replacement reuse the existing account security rules: non-empty unique username, active User status, no existing `PLATFORM_ADMIN` role, and existing password-policy validation for newly created accounts. Temporary passwords are never stored in plaintext.
- Migration `0029_platform_admin_governance.py` creates the singleton policy and validates existing data. A non-empty database with zero or more than two active platform administrators fails closed with an actionable repair error. A clean empty database may migrate first, but bootstrap/seed must create one active platform administrator before the service accepts traffic.
