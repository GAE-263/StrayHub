# Tasks: 平台管理員人數與替換治理

**Input**: Design documents from `/specs/009-platform-admin-governance/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/platform-admin-governance.md](./contracts/platform-admin-governance.md), [quickstart.md](./quickstart.md)

**Organization**: Tasks are grouped by the three P1 user stories so each story can be implemented and tested as an independently valuable increment after the shared foundation is complete.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 建立本 Feature 的測試、契約與 local fixture 骨架。

- [X] T001 [P] 建立平台管理員治理測試 fixture builders 與可重置的 User／Policy／AuditRecord 建立方式於 `tests/fixtures/platform_admin_governance.py`
- [X] T002 [P] 將平台管理員治理的 request／response schema、錯誤碼與路由契約加入 `specs/001-volunteer-care-report/contracts/openapi.yaml`
- [X] T003 [P] 建立前端平台管理員頁面的測試資料型別與 mock response fixtures 於 `apps/web/app/(management)/platform-admins/page.test.tsx`
- [X] T004 [P] 整理平台治理 quickstart 所需的 local fixture username、角色與清理入口於 `scripts/seed_local.py`

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 建立所有 user story 共用的政策資料、鎖定、平台 scope 與 contract plumbing；本階段完成前不得開始 user story 實作。

- [X] T005 建立 `PlatformAdminPolicy` SQLAlchemy model、模型匯出與 singleton 欄位驗證於 `services/api/app/persistence/models/platform_governance.py` 與 `services/api/app/persistence/models/__init__.py`
- [X] T006 建立 `0029_platform_admin_governance` migration，建立 default policy row（min=1、max=2）並對既有 active `PLATFORM_ADMIN` 資料做一致性檢查於 `services/api/migrations/versions/0029_platform_admin_governance.py`
- [X] T007 [P] 實作平台管理員 repository 的 policy row lock、active count、User lookup、current admin listing 與 platform audit query 於 `services/api/app/persistence/repositories/platform_admin_repository.py`
- [X] T008 [P] 建立只接受啟用中 `PLATFORM_ADMIN` 且不要求 organization context 的共用授權 helper 於 `services/api/app/api/management_access.py`，並補上拒絕測試於 `tests/unit/test_platform_authorization.py`
- [X] T009 建立 `PlatformAdminManagementService` 的交易邊界、policy validation、before／after projection 與 domain error mapping 於 `services/api/app/application/platform_admin_management.py`
- [X] T010 [P] 建立平台管理員 router 的 response schemas、錯誤回應與 audit resource naming 於 `services/api/app/api/platform_admin_management.py`
- [X] T011 將平台管理員 router 註冊到 FastAPI app，並同步 route tags 與 OpenAPI generated types 於 `services/api/app/main.py`、`specs/001-volunteer-care-report/contracts/openapi.yaml`、`packages/contracts/src/openapi.ts`
- [X] T012 [P] 建立管理工作台的 `/platform-admins` route 存取邊界與 sidebar 項目，保持不要求 Active Shelter Context 於 `apps/web/app/(management)/platform-admins/page.tsx`、`apps/web/components/management/AppSidebar.tsx`、`apps/web/components/management/ManagementLayout.tsx`

**Checkpoint**: Platform policy singleton、並發鎖定、全域授權、API router 與前端 route 骨架完成；user stories 可開始依序或分工實作。

## Phase 3: User Story 1 - 維持平台管理員安全下限 (Priority: P1) 🎯 MVP

**Goal**: 平台永遠保留至少一位啟用中的平台管理員；最後一位的停用、降權與移除會被安全拒絕並留下稽核結果。

**Independent Test**: 以一位 active platform admin 開始，對同一帳號執行 disable／demote，確認回傳 `409 last_platform_admin`、資料未改變；以兩位開始則可停用或降權其中一位，且剩餘一位仍可管理平台。

### Tests for User Story 1

- [X] T013 [P] [US1] 撰寫最後一位停用、降權、非平台角色拒絕與 policy boundary 的 unit tests 於 `tests/unit/test_platform_admin_management_service.py`
- [X] T014 [P] [US1] 撰寫清單、最後一位保護、成功稽核與 `result=denied` 拒絕稽核的 contract tests 於 `tests/contract/test_platform_admin_management_contract.py`
- [X] T015 [P] [US1] 撰寫單一交易與並發停用／降權驗收，確認最終數量不低於一位且無部分異動於 `tests/integration/test_platform_admin_governance.py`

### Implementation for User Story 1

- [X] T016 [US1] 實作 current admin listing、active count、policy summary 與最後一位保護的 service methods 於 `services/api/app/application/platform_admin_management.py`
- [X] T017 [US1] 實作 GET `/v1/platform/administrators`、POST `/{userId}/disable`、POST `/{userId}/demote`，並在成功路徑寫入 `result=success`、拒絕路徑寫入 `result=denied` 的 platform AuditRecord 於 `services/api/app/api/platform_admin_management.py`
- [X] T018 [US1] 實作平台管理員清單頁的政策摘要、啟用／停用卡片、最後一位危險操作提示與偏灰狀態樣式於 `apps/web/app/(management)/platform-admins/page.tsx` 與 `apps/web/app/globals.css`
- [X] T019 [US1] 補上平台管理員頁的角色拒絕、最後一位保護、摘要與狀態視覺 unit tests 於 `apps/web/app/(management)/platform-admins/page.test.tsx`
- [X] T020 [US1] 建立 local platform admin 登入、清單與最後一位拒絕的瀏覽器驗收於 `apps/web/e2e/platform-admin-governance.spec.ts`
- [X] T021 [US1] 同步 US1 endpoint schema、error response 與 generated contract types 於 `specs/001-volunteer-care-report/contracts/openapi.yaml` 與 `packages/contracts/src/openapi.ts`

**Checkpoint**: User Story 1 可獨立證明至少一位平台管理員的安全下限與拒絕稽核。

## Phase 4: User Story 2 - 控制平台管理員正常上限 (Priority: P1)

**Goal**: 平台最多保留兩位啟用中的平台管理員；支援建立、提升與重新啟用，但第三位一般操作必須被拒絕並引導替換。

**Independent Test**: 以一位 active platform admin 開始建立或提升第二位；再嘗試建立／提升／啟用第三位，確認 `409 platform_admin_limit_reached`、既有角色不變且可見剩餘名額為零。

### Tests for User Story 2

- [X] T022 [P] [US2] 撰寫建立全域帳號、username 重複、提升既有 User、重新啟用與 max=2 boundary 的 unit tests 於 `tests/unit/test_platform_admin_management_service.py`
- [X] T023 [P] [US2] 撰寫 create／promote／enable 的 request、response、錯誤碼與 Membership 不被修改的 contract tests 於 `tests/contract/test_platform_admin_management_contract.py`
- [X] T024 [P] [US2] 撰寫兩位上限與並發提升驗收，確認最多一個競爭請求成功且最終數量不超過兩位於 `tests/integration/test_platform_admin_governance.py`

### Implementation for User Story 2

- [X] T025 [US2] 實作 create global User、promote existing User、enable disabled admin、username／帳號狀態驗證與 max boundary 於 `services/api/app/application/platform_admin_management.py`
- [X] T026 [US2] 實作 POST `/v1/platform/administrators`、POST `/{userId}/promote`、POST `/{userId}/enable`，並建立對應成功／拒絕 audit actions 於 `services/api/app/api/platform_admin_management.py`
- [X] T027 [US2] 為 local seed 增加可提升的 active non-admin fixture、disabled platform admin fixture 與兩位上限驗收資料於 `scripts/seed_local.py`
- [X] T028 [US2] 在平台管理員頁加入新增帳號 modal、提升既有帳號選擇、重新啟用操作、名額滿載狀態與錯誤回饋於 `apps/web/app/(management)/platform-admins/page.tsx`
- [X] T029 [US2] 補上建立、提升、重新啟用、重複帳號、名額滿載與 modal reset 的 frontend unit tests 於 `apps/web/app/(management)/platform-admins/page.test.tsx`
- [X] T030 [US2] 建立第二位管理員、驗證兩位摘要、嘗試第三位、重新啟用，並記錄 5 次操作中至少 4 次於 30 秒內辨識摘要與可用操作的瀏覽器驗收於 `apps/web/e2e/platform-admin-governance.spec.ts`
- [X] T031 [US2] 同步 US2 endpoint schema、request validation、error response 與 generated contract types 於 `specs/001-volunteer-care-report/contracts/openapi.yaml` 與 `packages/contracts/src/openapi.ts`

**Checkpoint**: User Stories 1 and 2 可共同證明平台管理員數量始終介於一至兩位，且新增／提升／啟用符合上限。

## Phase 5: User Story 3 - 以替換流程完成管理員交接 (Priority: P1)

**Goal**: 已達兩位平台管理員時，透過一次確認完成新舊帳號交接，避免短暫零位或超過兩位，並讓替換與失敗原因可稽核。

**Independent Test**: 以兩位 active platform admins 和一位 eligible active non-admin 開始，完成 replacement 後確認新帳號成為平台管理員、原帳號被降權、總數仍為兩位；替代者停用或兩個 id 相同時確認新舊狀態完全不變。

### Tests for User Story 3

- [X] T032 [P] [US3] 撰寫 replacement service 的成功、替代者不合格、outgoing／replacement 相同、state changed 與 rollback unit tests 於 `tests/unit/test_platform_admin_management_service.py`
- [X] T033 [P] [US3] 撰寫 replacement request／response、operation id、雙事件 audit、`result=success`／`result=denied` 與失敗錯誤 contract tests 於 `tests/contract/test_platform_admin_management_contract.py`
- [X] T034 [P] [US3] 撰寫 replacement transaction、並發 replacement、失敗無部分狀態與最終一至兩位 invariant 的 integration tests 於 `tests/integration/test_platform_admin_governance.py`

### Implementation for User Story 3

- [X] T035 [US3] 實作 replacement service，鎖定 policy row、重新驗證兩個 User、以同一 transaction 交換 platform role 並產生共同 operation id 於 `services/api/app/application/platform_admin_management.py`
- [X] T036 [US3] 實作 POST `/v1/platform/administrators/replacements`，回傳新舊 projection 與 policy summary，並記錄 `platform_admin.replaced` 於 `services/api/app/api/platform_admin_management.py`
- [X] T037 [US3] 實作 GET `/v1/platform/administrators/audit`，支援 user／action／limit 篩選與 platform-scoped audit projection 於 `services/api/app/api/platform_admin_management.py`
- [X] T038 [US3] 在平台管理員頁加入 outgoing／replacement 選擇、原因輸入、一次確認、失敗復原與稽核檢視於 `apps/web/app/(management)/platform-admins/page.tsx`
- [X] T039 [US3] 補上 replacement modal、成功／失敗狀態、operation id 稽核呈現與不可部分完成提示的 frontend unit tests 於 `apps/web/app/(management)/platform-admins/page.test.tsx`
- [X] T040 [US3] 建立兩位管理員交接、替代者失效、並發交接、稽核查詢與所有成功案例一次確認完成的瀏覽器驗收於 `apps/web/e2e/platform-admin-governance.spec.ts`
- [X] T041 [US3] 同步 replacement、platform audit 與 operation id schema 到 `specs/001-volunteer-care-report/contracts/openapi.yaml` 與 `packages/contracts/src/openapi.ts`

**Checkpoint**: 三個 P1 user stories 全部可獨立驗收；替換不會造成平台治理能力短暫中斷。

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 完成跨故事安全、文件、品質與回歸驗證。

- [X] T042 [P] 補齊平台管理員 API、policy migration、`success`／`denied` audit actions 與 role／Membership 分離的 contract regression tests 於 `tests/contract/test_platform_admin_management_contract.py` 與 `tests/contract/test_openapi_contract.py`
- [X] T043 [P] 補齊平台管理員 concurrency、RLS／platform scope、Session invalidation 與拒絕不洩漏資料的安全測試於 `tests/security/test_platform_admin_governance.py`
- [X] T044 [P] 更新 platform admin local fixture 登入說明、migration／seed 前置條件與一至兩位驗收步驟於 `specs/009-platform-admin-governance/quickstart.md` 與 `scripts/demo.sh`
- [X] T045 [P] 更新管理導覽、平台管理員 route 權限說明與無 Active Shelter Context 行為於 `apps/web/components/management/AppSidebar.tsx`、`apps/web/components/management/ManagementLayout.tsx` 與 `specs/009-platform-admin-governance/contracts/platform-admin-governance.md`
- [X] T046 執行 quickstart 全部情境、確認三個 user story 的 acceptance scenario、並記錄驗證結果於 `specs/009-platform-admin-governance/quickstart.md`
- [X] T047 執行完整 Ruff、Pytest、Vitest、TypeScript、Prettier、OpenAPI check 與 platform admin E2E，修正所有回歸問題於 `specs/009-platform-admin-governance/quickstart.md`

### Remediation clarifications

- [X] T048 [P] 在 `services/api/app/application/platform_admin_management.py` 與 `services/api/app/persistence/repositories/platform_admin_repository.py` 增加帳號名稱非空且唯一、User 啟用中及目標尚未具備 `PLATFORM_ADMIN` 的共用驗證
- [X] T049 [P] 在 `services/api/app/application/platform_admin_management.py` 確認新建平台管理員的暫時密碼沿用既有密碼政策與雜湊流程，不保存明文
- [X] T050 [P] 在 `tests/unit/test_platform_admin_management_service.py` 與 `tests/contract/test_platform_admin_management_contract.py` 補上重複／空白帳號、停用目標、已是平台管理員目標與無效暫時密碼測試
- [X] T051 在 `services/api/migrations/versions/0029_platform_admin_governance.py` 實作既有 User 資料在啟用平台管理員為 0 或超過 2 位時 fail closed，並允許全新空資料庫完成 Migration
- [X] T052 在 `tests/integration/test_platform_admin_governance.py` 與 `scripts/seed_local.py` 補上全新資料庫 bootstrap 後建立一位初始平台管理員的驗證
- [X] T053 在候選清單與 promote／replacement 後端驗證中排除所有具有 `VOLUNTEER` Membership 或志工申請紀錄的帳號，並補上志工帳號不會出現在提升候選清單的測試
- [X] T054 [P] 在 `tests/integration/test_platform_admin_governance.py` 以 active、expired Membership 與 rejected、withdrawn、pending VolunteerApplication 歷史資料驗證 repository 候選清單不回傳志工帳號，且保留可提升帳號
- [X] T055 在 `tests/integration/test_platform_admin_governance.py` 使用真實 `PlatformAdminRepository` 與 `PlatformAdminManagementService`，自行建立 persisted expired、revoked、rejected、withdrawn、pending 志工歷史，驗證 promote／replacement 都被拒絕，並以 transaction rollback 保持測試隔離
- [X] T056 在 `tests/integration/test_platform_admin_governance.py` 與 `specs/009-platform-admin-governance/quickstart.md` 補齊 revoked Membership 的 Standard Local Fixture 與候選清單驗收，確認不新增第二套角色來源；不重複 T055 的 replacement backend coverage

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: 無依賴；可先建立測試 fixture、OpenAPI contract 與 local seed 骨架。
- **Phase 2 Foundational**: 依賴 Setup；建立 policy singleton、migration、鎖定 repository、platform auth、router 與前端 route，完成後才可開始 user stories。
- **Phase 3 User Story 1**: 依賴 Foundational；MVP，先交付最後一位保護與目前清單。
- **Phase 4 User Story 2**: 依賴 Foundational；可與 US1 平行開發，但共用 service、router、page，實際合併時需先整合 US1。
- **Phase 5 User Story 3**: 依賴 Foundational、US1 的 admin projection 與 US2 的 eligible account／enable 行為；替換是完整治理流程的最後一個 P1 slice。
- **Phase 6 Polish**: 依賴所有要交付的 user stories；完成後才可宣稱整體 Feature 通過。

### User Story Dependencies

- **US1 (P1)**: Foundational 完成後即可開始；不依賴其他 user story。
- **US2 (P1)**: Foundational 完成後即可開始；與 US1 共享 policy／repository／service，但可用獨立測試驗收上限。
- **US3 (P1)**: 依賴 Foundational、US1 的 listing／audit projection 與 US2 的 eligible account／enable；不可在替換前跳過上下限基礎。

### Requirement Traceability

| User Story | Main requirements | Contract sections | Main validation |
|---|---|---|---|
| US1 | FR-002、FR-003、FR-006、FR-010、FR-011、FR-013 | GET list、disable、demote、Authorization、Error Contract | T013–T021 |
| US2 | FR-004、FR-005、FR-008、FR-010、FR-012、FR-014、FR-015 | create、promote、enable、Error Contract、UI summary | T022–T031、T055–T056 |
| US3 | FR-007、FR-009、FR-011、FR-013、FR-014、FR-015 | replacement、platform audit、operation id | T032–T041、T055 |

## Parallel Execution Examples

### User Story 1

```text
T013 unit tests
T014 contract tests
T015 integration/concurrency tests
T018 frontend page implementation
```

以上任務可在不同檔案平行處理；T016–T017 service／API 完成後，T019–T020 才能執行完整 UI／E2E 驗收。

### User Story 2

```text
T022 unit tests
T023 contract tests
T024 integration tests
T027 local seed fixtures
T028 frontend modal implementation
```

T025–T026 完成後整合測試；T029–T031 依序完成 frontend、E2E 與 generated contract 同步。

### User Story 3

```text
T032 replacement unit tests
T033 replacement contract tests
T034 replacement integration tests
T038 replacement UI
```

T035–T037 完成後才能執行 T039–T041 的整合驗收；T034 應以真實資料庫交易確認並發與 rollback。

### Remediation Follow-up

```text
T055 real-repository promote／replacement history rejection tests
T056 revoked fixture and quickstart synchronization
```

T055 依賴既有 US2／US3 service 與 repository 完成；T056 與 T055 共用 integration fixture 檔案，依序執行。

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1 Setup。
2. 完成 Phase 2 Foundational，確保 policy singleton 與 platform authorization 可用。
3. 完成 Phase 3 US1，交付目前管理員清單、政策摘要與最後一位保護。
4. 停下來依 `quickstart.md` Scenario 1–2 驗證，再決定是否繼續新增與替換。

### Incremental Delivery

1. Setup + Foundational → policy、鎖定與授權基礎完成。
2. US1 → 能安全維持至少一位平台管理員。
3. US2 → 支援第二位、拒絕第三位與帳號建立／提升／啟用。
4. US3 → 支援完整替換交接與平台稽核查詢。
5. Polish → 完成安全、OpenAPI、responsive／a11y、quickstart 與完整品質門檻。
6. Remediation Follow-up → 完成 persisted volunteer-history rejection 與 revoked fixture coverage，再重新執行完整品質門檻。

## Notes

- 每個 task 都使用 `- [ ] Txxx` checklist 格式；user story phase task 都標示 `[US1]`、`[US2]` 或 `[US3]`。
- `[P]` 只用於不同檔案且不依賴未完成前置 task 的工作；共用 `page.tsx`、service 或 contract 檔案的 task 不標示 `[P]`。
- 所有替換、上下限與 audit 驗證都必須以後端最新資料為準，不能以 UI 隱藏按鈕取代授權。
