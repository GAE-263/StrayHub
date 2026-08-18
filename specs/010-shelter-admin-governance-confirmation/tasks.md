# Tasks: 收容所管理員人數與權限調整確認

**Input**: Design documents from `/specs/010-shelter-admin-governance-confirmation/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md

**Tests**: 本 feature 的規格與 quickstart 明確要求 unit、integration、contract、Vitest、Playwright 與品質驗證，因此包含測試任務；測試任務應先建立並確認在實作前失敗。

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 建立本 feature 所需的測試情境與合約驗證入口。

- [X] T001 [P] 擴充 `tests/unit/test_organization_management_service.py` 與 `tests/integration/test_organization_management.py` 的收容所、User、Membership fixture，涵蓋一位、兩位、停用、封存與跨收容所資料。
- [X] T002 [P] 擴充 `apps/web/app/(management)/shelters/page.test.tsx` 與 `apps/web/app/(management)/shelters/archived/page.test.tsx` 的 mock response helper，支援角色異動、狀態衝突、成功與拒絕回應。
- [X] T003 [P] 在 `specs/001-volunteer-care-report/contracts/openapi.yaml` 補齊本 feature 使用的 Membership mutation request version、錯誤碼、結果欄位，以及志工授權有效異動沿用 `expected_version` 的 endpoint 行為描述；此為唯一 OpenAPI 編輯任務。

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 建立所有 user stories 共用的交易、稽核與權限變更基礎；本階段完成前不得開始 user story 實作。

- [X] T004 [P] 在 `services/api/app/persistence/repositories/organization_repository.py` 新增鎖定目標 `Organization` 的查詢方法，並讓啟用中 `SHELTER_ADMIN` 計數查詢可在鎖定交易內重用。
- [X] T005 [P] 在 `services/api/app/application/audit_service.py` 統一拒絕事件的 `result = denied`、reason 與 organization scope 行為，保留既有成功 Audit 相容性。
- [X] T006 建立 `services/api/app/application/organization_management.py` 的權限變更 before／after projection 與共用驗證入口，先驗證完整結果再套用欄位，避免角色、狀態與醫療權限部分更新。
- [X] T007 在 `services/api/app/api/organization_management.py` 建立共用的 organization lock、錯誤 rollback 與拒絕 Audit 邊界，讓所有 Membership mutation 使用一致交易語意。

**Checkpoint**: Foundation ready — 後端已具備租戶鎖定、完整 projection 與可追溯拒絕結果；US1 與 US2 可在此後平行開發。

## Phase 3: User Story 1 - 維持每個收容所的管理員人數邊界 (Priority: P1) 🎯 MVP

**Goal**: 任何收容所 Membership 建立、提升、重新啟用、停用、降權、封存與恢復後，啟用中的 `SHELTER_ADMIN` 都維持一至兩位，且不產生部分成功結果。

**Independent Test**: 使用一位啟用中管理員的 fixture，驗證最後一位不能被移除；使用兩位管理員的 fixture，驗證第三位不能被建立／提升／恢復；再驗證合法的 `1 → 2` 與 `2 → 1` 變更，以及不同收容所互不影響。

### Tests for User Story 1

- [X] T008 [P] [US1] 在 `tests/unit/test_organization_management_service.py` 先新增一位下限、兩位上限、角色／狀態合併變更、既有低於一位資料的受控修復、建立帳號無孤立 User 與志工狀態邊界測試，確認目前實作會失敗。
- [X] T009 [P] [US1] 在 `tests/integration/test_organization_management.py` 先新增 create account、create membership、PATCH、archive、restore 的 HTTP／交易測試，驗證 409 錯誤、資料不變、成功 Audit、`access_version` 遞增與過期版本拒絕。
- [X] T010 [P] [US1] 在 `tests/integration/test_organization_management.py` 新增同一收容所兩個並發提升／停用操作測試，確認 row lock 後最終數量不會變成 0 或超過 2。
- [X] T011 [P] [US1] 在 `tests/contract/test_organization_management_contract.py` 先新增 Membership 人數限制、`membership_state_changed` 錯誤碼、`expected_access_version` request 與錯誤 response shape 測試，確認 OpenAPI 與 router 尚未符合新契約。

### Implementation for User Story 1

- [X] T012 [US1] 在 `services/api/app/application/organization_management.py` 將 `create_membership`、`create_account` 與 `create_initial_admin` 接到共用管理員人數驗證，超過兩位時在建立 User 前拒絕。
- [X] T013 [US1] 在 `services/api/app/application/organization_management.py` 重構 `update_membership`，依完整 after projection 判斷角色／狀態是否使管理員數量低於 1 或高於 2，驗證 `expected_access_version` 並在成功時遞增 `access_version`，同時維持志工授權與 STAFF 醫療權限規則。
- [X] T014 [US1] 在 `services/api/app/application/organization_management.py` 更新 `archive_membership` 與 `restore_membership` 的管理員計數及 `expected_access_version` 驗證，讓最後一位封存被拒絕、恢復第三位被拒絕且志工過期／撤銷狀態不被繞過；成功時遞增版本。
- [X] T015 [US1] 在 `services/api/app/api/organization_management.py` 將所有 Membership mutation 接到 organization row lock、版本檢查、完整交易與拒絕 Audit；成功與拒絕均回傳既有 response shape，不留下部分寫入。
- [X] T016 [US1] 在 `tests/contract/test_organization_management_contract.py` 補上 `shelter_admin_limit_reached`、`last_shelter_admin`、`membership_state_changed` 的 409 response、request version 與 `access_version` response assertions；不再修改 OpenAPI 檔案。

**Checkpoint**: US1 complete — API 直接呼叫與整合測試已能保證每個收容所一至兩位管理員，並能獨立通過 quickstart 的人數邊界驗收。

## Phase 4: User Story 2 - 以確認 Modal 防止誤改權限 (Priority: P1)

**Goal**: 所有有效權限調整在提交前顯示可辨識前後差異的確認 Modal；取消、關閉或 Escape 不會送出 mutation。

**Independent Test**: 以 `local-shelter-admin-a` 開啟 `/shelters`，對角色、狀態、醫療權限與封存操作各測一次；確認 Modal 內容、取消／Escape 無變更、確認後才送出。再於 `/shelters/archived` 驗證恢復同樣行為。

### Tests for User Story 2

- [X] T017 [P] [US2] 在 `apps/web/components/ui/dialog.test.tsx` 與新增的 `apps/web/components/management/MembershipPermissionDialog.test.tsx` 先測試 alertdialog semantics、目標身份、before／after、管理員人數影響、取消、Escape 與 focus return。
- [X] T018 [P] [US2] 在 `apps/web/app/(management)/shelters/page.test.tsx` 先新增角色、醫療資料權限、停用、重新啟用與封存操作的「先開 Modal、不直接 fetch」測試。
- [X] T019 [P] [US2] 在 `apps/web/app/(management)/shelters/archived/page.test.tsx`、`apps/web/features/volunteer-access/AccessGrantTable.test.tsx` 與 `apps/web/features/volunteer-access/ApplicationBatchWorkbench.test.tsx` 先新增恢復、志工授權期間調整及撤銷的確認 Modal、取消與確認後 fetch 測試，涵蓋管理員數量及授權狀態風險文字。

### Implementation for User Story 2

- [X] T020 [US2] 新增 `apps/web/components/management/MembershipPermissionDialog.tsx`，以 `AlertDialog` 呈現收容所、姓名／帳號、目前與變更後權限／狀態、管理員數量或志工授權 before／after 與確認／取消操作，供 Membership 與志工授權頁共用。
- [X] T021 [US2] 重構 `apps/web/app/(management)/shelters/page.tsx` 的角色 Select、醫療資料 checkbox、停用／重新啟用／封存按鈕為 controlled pending change state，統一透過確認 Modal 提交；建立帳號若選擇啟用中的 `SHELTER_ADMIN`，在帳號 Modal 送出前再開最後確認，並在關閉時清除待提交資料。
- [X] T022 [US2] 重構 `apps/web/app/(management)/shelters/archived/page.tsx`、`apps/web/app/(management)/volunteers/access/page.tsx` 與 `apps/web/app/(management)/volunteers/applications/page.tsx`，重用 `MembershipPermissionDialog` 處理恢復、志工授權期間調整／撤銷及有效授權決策；Membership mutation 明確帶入 `expected_access_version`，志工授權維持既有 `expected_version`，目標狀態衝突時重新載入清單。
- [X] T023 [US2] 在 `apps/web/app/globals.css` 補足確認 Modal 的內容間距、窄螢幕堆疊與鍵盤操作樣式，確保 1440px、768px、360px 不裁切主要操作。

**Checkpoint**: US2 complete — 每種有效權限異動都可獨立驗證「先確認、再提交」，取消與 Escape 不會改變後端資料。

## Phase 5: User Story 3 - 透過 Toast 確認完成的權限動作 (Priority: P2)

**Goal**: 權限異動成功後在左下角顯示包含動作與目標身份的 Toast；拒絕、失敗或結果不明不顯示成功 Toast。

**Independent Test**: 以正常與封存頁各完成一項成功異動與一項被後端拒絕的異動，確認成功 Toast 的位置、內容、可及性與敏感資料遮蔽，以及失敗沒有成功通知。

### Tests for User Story 3

- [X] T024 [P] [US3] 在 `apps/web/components/ui/toast.test.tsx` 與 `apps/web/app/(management)/shelters/page.test.tsx` 新增 Toast 的 `role=status`、左下角 class、動作／目標文字、成功後顯示與失敗不顯示測試；以 `performance.now()` 或等價方式驗證成功回應後 2 秒內可見。
- [X] T025 [P] [US3] 在 `apps/web/e2e/organization-management.spec.ts` 與 `apps/web/e2e/volunteer-access-approval.spec.ts` 新增 Playwright 案例，驗證 Modal 確認後 2 秒內 Toast、取消無 Toast、最後管理員／第三位管理員拒絕無成功 Toast、archived restore Toast 與志工授權異動 Toast。

### Implementation for User Story 3

- [X] T026 [US3] 在 `apps/web/components/ui/toast.tsx` 擴充可辨識的成功 Toast props，維持 `role=status`／`aria-live=polite` 並避免渲染密碼、醫療資料或 UUID-only identity。
- [X] T027 [US3] 在 `apps/web/app/(management)/shelters/page.tsx`、`apps/web/app/(management)/shelters/archived/page.tsx`、`apps/web/app/(management)/volunteers/access/page.tsx` 與 `apps/web/app/(management)/volunteers/applications/page.tsx` 接上成功 mutation 的 Toast state；只有 API 成功且清單重新載入後才顯示，錯誤／拒絕／結果不明時維持 Alert。
- [X] T028 [US3] 在 `apps/web/app/globals.css` 完成 `.ui-toast` 左下角固定位置、z-index、窄螢幕寬度與不遮蔽主要操作的 responsive style。

**Checkpoint**: US3 complete — 正常與封存 route 都能以 Toast 回報每項成功權限動作，失敗與取消沒有誤導性成功提示。

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 完成跨端整合、文件驗收與品質門檻。

- [X] T029 [P] 更新 `specs/010-shelter-admin-governance-confirmation/quickstart.md` 與 `scripts/demo.sh` 的本機帳號／API 8001／Web 3001 說明，使手動驗收步驟與實際 fixture 一致。
- [X] T030 [P] 在 `tests/integration/test_organization_management.py` 與 `tests/contract/test_organization_management_contract.py` 補足成功／拒絕 Audit 的必要欄位、organization scope 與平台角色／Membership 角色分離驗證。
- [X] T031 執行 `uv run pytest tests/unit/test_organization_management_service.py tests/integration/test_organization_management.py tests/contract/test_organization_management_contract.py`，修正本 feature 後端測試失敗並確認完整交易未留下資料。
- [X] T032 執行 `npm --prefix apps/web run test -- 'app/(management)/shelters/page.test.tsx' 'app/(management)/shelters/archived/page.test.tsx' 'features/volunteer-access/AccessGrantTable.test.tsx' 'features/volunteer-access/ApplicationBatchWorkbench.test.tsx' 'components/management/MembershipPermissionDialog.test.tsx' 'components/ui/toast.test.tsx'` 與 `npm --prefix apps/web run typecheck`，修正 Membership 與志工授權頁面的 Modal／Toast 測試與型別問題。
- [ ] T033 執行 quickstart 的 Playwright、響應式與鍵盤驗收，並在 `apps/web/e2e/organization-management.spec.ts` 記錄必要的 route、帳號與錯誤回饋證據；依 quickstart 的五位管理者 30 秒任務 protocol，將 4/5 通過結果記錄到 `specs/010-shelter-admin-governance-confirmation/validation/usability-test-plan.md`。
- [ ] T034 執行 `ruff check .`、`ruff format --check .`、完整 `pytest`、前端 `npm --prefix apps/web run quality`，並將驗證結果整理到 `specs/010-shelter-admin-governance-confirmation/quickstart.md` 的驗收紀錄。

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001–T003 可平行執行，無 user story 依賴。
- **Foundational (Phase 2)**: T004–T007 依賴 Setup 完成，並阻塞所有 user story。
- **User Story 1 (Phase 3)**: T008–T011 測試先行；T012–T016 實作依賴 Foundation 與對應失敗測試。
- **User Story 2 (Phase 4)**: T017–T019 測試先行；T020–T023 可在 Foundation 完成後開始，API contract 可與 US1 實作平行，但完整 E2E 依賴 US1 API。
- **User Story 3 (Phase 5)**: T024–T025 可在 T020–T023 的 UI state 接口確定後開始；T026–T028 依賴確認 Modal mutation flow。
- **Polish (Phase 6)**: T029–T034 依賴要交付的 user stories 完成；T031、T032、T033、T034 應按順序執行以縮小除錯範圍。

### User Story Dependencies

- **US1 (P1)**: 依賴 Phase 2；不依賴其他 user story，是 MVP。
- **US2 (P1)**: 依賴 Phase 2；可與 US1 平行開發，但完整驗收需使用 US1 的實際 mutation contract。
- **US3 (P2)**: 依賴 US2 的確認提交流程；Toast state 可與 US1 的 API 實作平行，但最終 E2E 依賴 US1 與 US2。

### Parallel Opportunities

- T001–T003 可平行。
- T004、T005 可平行；T006、T007 依序接上共用驗證設計。
- US1 的 T008–T011 可平行；US2 的 T017–T019 可平行。
- T012–T014 需共享 service 檔案，應由同一實作者順序完成；T015、T016 可在 service 介面穩定後平行。
- US2 的 component、正常頁、封存頁測試與 CSS 可由不同實作者平行，但 T021／T022 共用待確認 state 命名時需先對齊。
- T024、T025 可平行；T026、T028 可平行，T027 依賴 Toast props。

## Parallel Example: User Story 1

```text
Task: "T008 unit 邊界測試 in tests/unit/test_organization_management_service.py"
Task: "T009 API transaction tests in tests/integration/test_organization_management.py"
Task: "T010 concurrent mutation tests in tests/integration/test_organization_management.py"
Task: "T011 contract tests in tests/contract/test_organization_management_contract.py"
```

## Parallel Example: User Story 2

```text
Task: "T017 confirmation dialog tests in apps/web/components/management/MembershipPermissionDialog.test.tsx"
Task: "T018 normal shelter page confirmation tests in apps/web/app/(management)/shelters/page.test.tsx"
Task: "T019 archived restore confirmation tests in apps/web/app/(management)/shelters/archived/page.test.tsx"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1 Setup 與 Phase 2 Foundation。
2. 先完成 T008–T011 失敗測試，再完成 T012–T016 後端與合約實作。
3. 執行 US1 checkpoint，確認一位下限、兩位上限、並發與 Audit。
4. US1 可獨立展示；再進入 Modal 與 Toast UI。

### Incremental Delivery

1. Phase 1–2 完成後，US1 與 US2 可平行開發。
2. US1 完成後可先交付後端治理；US2 完成後交付誤操作防護。
3. US3 接上成功結果回饋，再執行跨端 Polish 與 quickstart。
4. 每個 checkpoint 都要先通過該 user story 的獨立測試，再合併下一階段。

## Notes

- `[P]` 只表示不同檔案且沒有未完成依賴；同一檔案的 tasks 不應同時修改。
- 所有 user story 任務都包含 `[US1]`、`[US2]` 或 `[US3]` 標籤，Setup、Foundation、Polish 任務不使用 story label。
- 後端 row lock 與 audit 是安全邊界；前端的 count 預覽、Modal 與 Toast 不能取代後端重新驗證。
