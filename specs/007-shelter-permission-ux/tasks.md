---
description: "收容所權限管理介面改善的可執行任務"
---

# Tasks: 收容所權限管理介面改善

**Input**: Design documents from `/specs/007-shelter-permission-ux/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/membership-list.md、quickstart.md

**Tests**: 依規格與 quickstart 明確要求，包含 page tests、contract tests、typecheck 與本機 Browser 驗證。

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 確認既有管理頁、契約與測試入口，不引入新的依賴或資料表。

- [X] T001 [P] 確認 `apps/web/app/(management)/shelters/page.tsx`、`apps/web/app/(management)/shelters/page.test.tsx`、`services/api/app/api/organization_management.py` 與 `services/api/app/persistence/repositories/organization_repository.py` 的現況，記錄本 feature 只需 additive read projection 與呈現調整
- [X] T002 [P] 確認 `packages/contracts/src/openapi.ts` 由 `specs/001-volunteer-care-report/contracts/openapi.yaml` 產生，並在 `specs/007-shelter-permission-ux/quickstart.md` 保留可重複執行的前端、後端與 Browser 驗證命令

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 先固定身份 read contract 與租戶隔離測試，所有 UI 工作都依賴此邊界。

- [X] T003 [P] 在 `specs/001-volunteer-care-report/contracts/openapi.yaml` 與 `packages/contracts/src/openapi.ts` 新增 nullable `username`、`display_name` Membership response 欄位，維持既有 role、status、medical_care_access 與 mutation contract
- [X] T004 [P] 在 `tests/contract/test_organization_management_contract.py` 增加 Membership identity projection 欄位與 organization-scoped response contract assertion

**Checkpoint**：API contract 清楚定義使用者辨識欄位，且沒有新增 migration、client organization scope 或跨租戶資料來源。

## Phase 3: User Story 1 - 辨識收容所帳號與權限 (Priority: P1) 🎯 MVP

**Goal**：管理員能以姓名／帳號辨識 Membership，並清楚看見角色、狀態與 STAFF 醫療資料權限。

**Independent Test**：以 page test 與 `local-shelter-admin-a` Browser 流程確認清單不以 UUID 作主要名稱，至少五筆既有 Membership 的身份、角色、狀態與醫療權限呈現正確。

### Tests for User Story 1

- [X] T005 [P] [US1] 在 `apps/web/app/(management)/shelters/page.test.tsx` 先補充姓名／帳號、角色／狀態中文標籤、STAFF 醫療權限與固定 Asia/Taipei 說明的驗收測試

### Implementation for User Story 1

- [X] T006 [US1] 在 `services/api/app/persistence/repositories/organization_repository.py` 實作目前 organization 範圍內的 Membership + User identity projection 查詢，避免逐筆 N+1 查詢並保持既有 authorization gate
- [X] T007 [US1] 在 `services/api/app/api/organization_management.py` 將 `username`、`display_name` 加入 Membership response，並讓 list memberships 回傳 organization-scoped identity projection；缺少 User 時回傳 nullable 欄位
- [X] T008 [US1] 在 `apps/web/app/(management)/shelters/page.tsx` 以 display name／username 呈現 Membership 身份，加入角色與狀態可讀標籤，保留既有角色切換、醫療權限與停用操作及其 accessibility label

**Checkpoint**：US1 可獨立驗證，且既有 Membership mutation 與授權結果不變。

## Phase 4: User Story 2 - 以不擁擠的版面管理權限 (Priority: P1)

**Goal**：桌面與手機寬度下，身份、狀態與操作均有清楚層次且可操作。

**Independent Test**：在 1440px、768px、360px 驗證 Membership 卡片沒有文字／控制項重疊、水平溢出或不可操作的控制。

### Tests for User Story 2

- [X] T009 [P] [US2] 在 `apps/web/e2e/organization-management.spec.ts` 更新 SHELTER_ADMIN 驗收為「權限管理」、姓名／帳號、Asia/Taipei 說明與無時區選單，並加入 Membership card controls 的可見性斷言

### Implementation for User Story 2

- [X] T010 [US2] 在 `apps/web/app/globals.css` 建立 Membership identity／meta／actions 的卡片排版、間距、focus／操作尺寸與 1080px／600px responsive 重排規則，避免清單擁擠與水平溢出
- [X] T011 [US2] 在 `apps/web/app/(management)/shelters/page.tsx` 將頁面主標題改為「權限管理」，以 page-level spacing 組織收容所、權限清單與建立帳號區塊，並維持錯誤／成功訊息不遮擋清單
- [X] T012 [US2] 在 `apps/web/components/management/AppSidebar.tsx` 將 `/shelters` 導覽名稱同步為「權限管理」，確保導覽、頁面標題與使用者心智模型一致

**Checkpoint**：US1 與 US2 可在桌面及手機寬度獨立展示，既有操作仍可用。

## Phase 5: User Story 3 - 使用固定的台灣收容所時區 (Priority: P2)

**Goal**：頁面清楚說明台灣統一時區，且不再提供時區修改控制。

**Independent Test**：以收容所管理員開啟頁面，看到 Asia/Taipei 說明但找不到 timezone select／儲存按鈕，且帳號權限管理照常可用。

### Tests for User Story 3

- [X] T013 [P] [US3] 擴充 `apps/web/app/(management)/shelters/page.test.tsx` 與 `apps/web/e2e/organization-management.spec.ts`，驗證時區 select／其他時區選項／儲存按鈕不存在，並驗證 STAFF 不取得管理頁的權限控制

### Implementation for User Story 3

- [X] T014 [US3] 在 `apps/web/app/(management)/shelters/page.tsx` 移除時區 local state、更新 handler、時區選單與儲存按鈕，改顯示固定 Asia/Taipei（台灣時間）說明，不改動既有 organization timezone API

**Checkpoint**：US3 完成後不會因 UI 移除時區控制而影響既有帳號、Membership、提醒或日期資料。

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：依 quickstart 完成 contract、型別、Python 品質與本機真人驗證。

- [X] T015 [P] 重新產生並格式化 `packages/contracts/src/openapi.ts`，確認 canonical OpenAPI 與 runtime Membership response 欄位一致
- [X] T016 [P] 執行 `apps/web/app/(management)/shelters/page.test.tsx`、`apps/web` TypeScript typecheck、`tests/contract/test_organization_management_contract.py` 與 `git diff --check`，修正所有因本 feature 造成的失敗
- [X] T017 使用 `local-shelter-admin-a` 在 `http://127.0.0.1:3000/shelters` 以 1440px、768px、360px 完成 `specs/007-shelter-permission-ux/quickstart.md` 的真人驗收，記錄身份辨識、既有操作、固定時區與 layout 結果

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：可立即開始；只確認既有結構。
- **Foundational (Phase 2)**：依賴 Setup，阻塞 US1～US3 的 contract 與資料範圍。
- **US1 (Phase 3)**：依賴 Foundational；是 MVP，先完成 API identity projection 與清單辨識。
- **US2 (Phase 4)**：依賴 Foundational；可與 US1 的不同檔案工作平行，但整合驗證依賴 US1 的 identity 欄位。
- **US3 (Phase 5)**：依賴 Foundational；可與 US2 平行，最後與 US1／US2 一起驗證。
- **Polish (Phase 6)**：依賴所有目標 user story 完成。

### User Story Dependencies

- **US1 (P1)**：只依賴 Foundational，可獨立交付 MVP。
- **US2 (P1)**：只依賴 Foundational；視覺工作可與 US1 平行，但 E2E 需要 US1 的 identity projection fixture。
- **US3 (P2)**：只依賴 Foundational；不依賴 backend schema，需與 US1／US2 共用頁面驗證。

### Parallel Opportunities

- T003 與 T004 可平行：契約 schema 與 contract test 不修改同一檔案。
- T005 可先於 T006～T008 執行，符合 tests-first；T006 與 T008 可在不同檔案平行，T007 依賴 T006。
- T009、T010、T013 可在各自檔案平行準備；T011／T014 同一 page file 必須依序整合。
- T015、T016 可平行執行；T017 需在前述驗證通過後進行。

## Parallel Example: User Story 1

```text
先行：T005 page test
平行：T006 repository projection、T008 page identity rendering
收斂：T007 API response → T005／T008 通過 → T017 Browser 驗證
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Setup 與 Foundational，固定 Membership identity contract。
2. 先寫 T005 page test，再完成 T006～T008。
3. 執行 US1 checkpoint，確認姓名／帳號、角色／狀態、醫療權限與既有 mutation。

### Incremental Delivery

1. US1：完成可辨識的 Membership 清單。
2. US2：加入桌面／手機卡片排版與導覽命名。
3. US3：移除時區 mutation 控制並顯示固定台灣政策。
4. Polish：通過 quickstart 的自動化與本機真人驗收。

## Notes

- 所有任務均使用 `- [ ] Txxx` checklist format；user story 任務均含 `[USn]` label 與精確檔案路徑。
- 不新增資料表、migration、外部服務或新的登入／授權流程。
