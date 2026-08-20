# Tasks: 志工角色導向入口與管理路由隔離

**Input**: Design documents from `/specs/004-volunteer-entry-route-isolation/`

**Prerequisites**: `plan.md`、`spec.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md`

**Implementation approach**: 先完成共用 auth／route foundation，再以 user story 為單位交付；每個 story 都有獨立測試與驗收矩陣。正式 LIFF 依賴已完成的 005 Membership／Grant／entry reference contract，但不在本功能重做其 lifecycle。

## Phase 1: Setup（共享基礎設定）

**目的**：準備 LIFF runtime dependency、canonical contract 與 P0 測試入口。

- [ ] T001 [P] 在 `apps/web/package.json` 與 `apps/web/package-lock.json` 加入與鎖定 `@line/liff` dependency，保留既有 Next.js／React 版本相容性
- [ ] T002 [P] 在 `apps/web/next.config.ts` 與 `infra/gcp-demo/terraform/cloud-run.tf` 對齊 server runtime `LIFF_ID` 注入，確保正式 LIFF ID 不需暴露為授權 secret
- [ ] T003 在 `specs/001-volunteer-care-report/contracts/openapi.yaml` 更新 `LiffExchangeRequest` 為必填 `id_token` + `shelter_entry_reference`，並依 canonical workflow 重新生成 `packages/contracts/src/openapi.ts`
- [ ] T004 [P] 在 `apps/web/package.json` 將 `e2e/liff-route-isolation.spec.ts` 納入 P0 browser、a11y 與必要的 visual test scripts

## Phase 2: Foundational（阻塞所有 user stories 的共用能力）

**目的**：建立 server-side entry/access primitive、前端 route decision 與不掛載 children 的 boundary；本階段完成前不得開始 user-story implementation。

- [ ] T005 在 `apps/web/lib/auth.ts` 與 `apps/web/lib/liff-session.ts` 建立 typed auth/context/recovery state、transient entry reference storage、session source 標記與 logout/terminal cleanup，明確禁止以 client cache 判定 role 或 Membership
- [ ] T006 [P] 在 `apps/web/lib/route-access.ts` 與 `apps/web/lib/route-access.test.ts` 實作 `EffectiveRole`、management/volunteer area、context-required、redirect、recovery 與 finite-state decision matrix
- [ ] T007 [P] 在 `services/api/app/infrastructure/line/entry_reference_adapter.py` 實作既有 `VolunteerEntryResolverPort` adapter，呼叫005 fixed-purpose digest resolver並只回安全organization公開context；不得在identity確認前開啟ambient organization scope
- [ ] T008 在 `services/api/app/persistence/repositories/authentication_repository.py` 增加 exact-organization effective Membership/Grant 查詢與 concurrency lock 支援，重用 005 的 active、valid_from、expires_at、Grant predicate，不建立新的授權規則
- [ ] T009 [P] 在 `apps/web/components/auth/ProtectedRouteState.tsx` 建立 checking、redirecting、context-required、temporary-error、re-entry 與 safe status/alert 的繁中可及狀態元件
- [ ] T010 在 `apps/web/components/auth/AuthenticatedRouteBoundary.tsx` 建立不掛載 children 的共用 profile/context loader，區分 local session、formal LIFF session、management allow 與 volunteer allow
- [ ] T011 在 `apps/web/app/(management)/layout.tsx`、`apps/web/app/(management)/page.tsx` 與 `apps/web/app/page.tsx` 調整 root route composition，讓 `/` 與所有 management children 由同一 boundary 控制且 Dashboard 不提前掛載
- [ ] T012 [P] 在 `tests/fixtures/volunteer_access.py` 擴充 ORG-A／ORG-B、matching/cross-tenant、pending/rejected/future/expired/revoked/active-unexpired access builders，供後續 server 與 e2e matrix 共用

**Checkpoint**：entry resolver、effective-access primitive、route decision、safe state 與 route boundary 可被獨立測試；尚未開放任何新的志工流程。

## Phase 3: User Story 1－志工登入後直接開始回報（Priority: P0）🎯 MVP

**Goal**：志工從共用 LIFF App 的收容所專屬入口完成無帳密 LINE 驗證、原子建立 Session/context，並直接進入 `/animal-confirmation`，只看到正確收容所資料。

**Independent Test**：使用受控 ORG-A／ORG-B LIFF entry 與對應 active-unexpired volunteer identity，再以 `local-volunteer-a/b` fixture 驗證無帳密、正確 shelter label、今日動物、cross-entry reject 與 management request count=0。

### Tests for User Story 1

- [x] T013 [P] [US1] 在 `tests/contract/test_authentication_contract.py`、`tests/contract/test_openapi_contract.py` 與 `tests/contract/test_generated_contract_types.py` 驗證LIFF exchange request欄位、security、state-discriminated canonical schema與generated type無drift（RED：contract assertions failed；GREEN：contract suite passed；`npm --prefix packages/contracts run check`通過；runtime Pydantic binding與Task 5 exact-org service同一安全切片完成）
- [x] T014 [P] [US1] 在 `tests/integration/test_authentication_session.py` 建立 valid binding、active user/org、matching entry 與 active-unexpired Membership/Grant 的 exchange success integration test
- [x] T015 [P] [US1] 在 `tests/security/test_liff_exchange_authorization.py`、`tests/security/test_liff_exchange_state_matrix.py`、`tests/integration/test_liff_runtime_state_matrix.py` 建立invalid token的401／403／503安全HTTP matrix，以及missing binding→NEW、pending→PENDING、future/expired/revoked/missing Grant→SUSPENDED、active exact access→ACTIVE matrix；每個非ACTIVE結果都assert Session/Refresh/context新增為0
- [ ] T016 [P] [US1] 在 `tests/isolation/test_liff_entry_isolation.py` 驗證 ORG-A entry 不會解析或建立 ORG-B context，且相同 shelter number、animal id、query 與轉傳 URL 不會擴大租戶範圍

### Implementation for User Story 1

- [ ] T017 [US1] 在 `services/api/app/api/authentication.py` 擴充 `LiffExchangeRequest` 為 `id_token` + `shelter_entry_reference`，注入 entry resolver，維持未授權 endpoint 與既有 ErrorResponse contract
- [ ] T018 [US1] 在 `services/api/app/application/authentication/session_service.py` 實作 raw LINE identity、entry organization、Binding、User、Organization、exact Membership/Grant lock 與 SessionRecord/RefreshTokenRecord 同 transaction exchange；任何失敗都 rollback 且不修改 005 access records
- [ ] T019 [US1] 在 `services/api/app/api/authentication.py` 與 `services/api/app/application/authentication/session_service.py` 完成 exchange transaction boundary、commit/rollback 與安全錯誤 mapping，禁止回傳其他 organization、Membership、動物或草稿資訊
- [ ] T020 [US1] 在 `apps/web/features/liff/LiffSessionProvider.tsx` 與 `apps/web/app/(volunteer-entry)/volunteer-entry/page.tsx` 實作 LIFF init/login/raw `getIDToken` bootstrap，只送 token + entry reference，成功後保存 Session/recovery hint 並 replace 到 `/animal-confirmation`
- [ ] T021 [US1] 在 `apps/web/app/login/page.tsx`、`apps/web/lib/auth.ts` 與 `apps/web/app/(volunteer)/layout.tsx` 實作 local fixture role-directed destination、formal LIFF/session source 分流、server-confirmed shelter label 與 volunteer children mount gate
- [ ] T022 [US1] 在 `apps/web/app/(volunteer)/animal-confirmation/page.tsx` 與 `apps/web/app/(volunteer)/care-report/page.tsx` 加入目前 Active Shelter Context 收容所名稱，確保 context gate 通過前不發 animals、draft 或 report request
- [ ] T023 [US1] 在 `apps/web/e2e/liff-route-isolation.spec.ts` 實作 US1 browser matrix：local volunteer destination、受控 LIFF bootstrap adapter、ORG-A/ORG-B label/data、no-password flow、cross-entry denial 與 management request count=0

**Checkpoint**：US1 可獨立 demo／驗收；志工可直接開始回報，且後端 transaction 與前端入口均已證明租戶隔離。

## Phase 4: User Story 2－志工安全恢復 active draft（Priority: P0）

**Goal**：context 驗證後提供單一可恢復草稿的「繼續回報／稍後處理」，不載入過期、跨收容所或不可回報草稿。

**Independent Test**：以 no draft、active-unexpired/same-context、expired/non-active、cross-context、animal unavailable 與 save failure fixtures 驗證 prompt、資料遮蔽、continue/later 與原始輸入保留。

### Tests for User Story 2

- [ ] T024 [P] [US2] 在 `apps/web/app/(volunteer)/animal-confirmation/page.test.tsx` 與 `apps/web/app/(volunteer)/care-report/page.test.tsx` 覆蓋 no draft、resumable draft、unavailable draft、continue/later、context mismatch 與 save failure 行為
- [ ] T025 [P] [US2] 在 `apps/web/e2e/liff-route-isolation.spec.ts` 增加 current draft network/UI assertions，確認 boundary 通過前不讀 draft、不可恢復內容不曝光且 later 不產生 Draft mutation

### Implementation for User Story 2

- [ ] T026 [US2] 在 `apps/web/features/line-bot/ActiveDraftPrompt.tsx` 建立 `ActiveDraftResumeView` 的繁中、keyboard、screen-reader 與 360px prompt，提供「繼續回報」「稍後處理」「無法恢復」狀態
- [ ] T027 [US2] 在 `apps/web/app/(volunteer)/animal-confirmation/page.tsx` 組合既有今日 animals 與 `/v1/line/care-report/drafts/current`，只在 active、未過期、same context 且 animal 可回報時顯示 prompt
- [ ] T028 [US2] 在 `apps/web/app/(volunteer)/care-report/page.tsx` 接入 continue 後的 server-side current draft re-read，保存失敗時保留原始輸入並禁止自動重播非冪等 mutation

**Checkpoint**：US1 與 US2 均可獨立驗收；志工可安全繼續或稍後處理草稿，且不跨 tenant。

## Phase 5: User Story 3－志工直接開啟管理網址時不會看到管理資料（Priority: P0）

**Goal**：志工對 `/`、所有既有 management route、deep link、query、reload、back 或未知 management child 都不會看到管理內容，也不會發出管理 page request。

**Independent Test**：以 `local-volunteer-a/b` 逐一開啟 route matrix，觀察 first visible state、navigation、network request、reload/back 與 management shell mount 結果。

### Tests for User Story 3

- [ ] T029 [P] [US3] 在 `apps/web/lib/route-access.test.ts` 與 `apps/web/components/auth/AuthenticatedRouteBoundary.test.tsx` 覆蓋全部 management area、dynamic/query/trailing-slash、role mismatch、checking 與 redirect decision
- [ ] T030 [P] [US3] 在 `apps/web/e2e/liff-route-isolation.spec.ts` 建立 management deep-link matrix，assert Dashboard/organizations/page-specific management request count=0、first visible state 不含管理資料且無 redirect loop

### Implementation for User Story 3

- [ ] T031 [US3] 在 `apps/web/components/management/ManagementLayout.tsx` 重排 request lifecycle：先 profile + Active Context、推導 role，再只對 management role 取得 organizations、掛載 Shell 與 page children
- [ ] T032 [US3] 在 `apps/web/app/(management)/layout.tsx`、`apps/web/app/(management)/page.tsx` 與 `apps/web/app/page.tsx` 完成 `/` route group migration，移除 root 與 Dashboard 的重複 layout/guard composition
- [ ] T033 [US3] 在 `apps/web/components/auth/ProtectedRouteState.tsx` 與 `apps/web/components/management/ManagementLayout.tsx` 確保 volunteer redirect 使用 replace、children 不掛載、管理 error view 不曝光 metrics/count/detail

**Checkpoint**：US3 的志工管理 route isolation 可獨立驗收，且不影響 management role 的既有 API 授權。

## Phase 6: User Story 4－工作人員登入後維持管理首頁（Priority: P0）

**Goal**：STAFF 角色登入、reload、management deep link 與既有未授權頁面行為維持不變，不被導向 volunteer entry。

**Independent Test**：以 `local-staff-a` 驗證 `/`、既有 Sidebar/management shell、reload、back、authorized route 與既有 403/denied behavior。

### Tests for User Story 4

- [ ] T034 [P] [US4] 在 `apps/web/e2e/login-home.spec.ts` 與 `apps/web/e2e/management-shell.spec.ts` 增加 STAFF destination、reload、deep-link、Sidebar 與 management child regression assertions

### Implementation for User Story 4

- [ ] T035 [US4] 在 `apps/web/components/management/ManagementLayout.tsx` 與 `apps/web/components/management/AppSidebar.tsx` 保留 STAFF 的既有 management shell、導航與 context label，僅套用新的 mount-before-check boundary
- [ ] T036 [US4] 在 `apps/web/components/management/route-state.ts` 與 `apps/web/app/login/page.tsx` 對 STAFF 缺少單一管理權限時維持既有安全提示，不把 denial 轉成 volunteer access 或跨 tenant data

**Checkpoint**：US4 可單獨證明 route isolation 是雙向的，STAFF management workflow 無回歸。

## Phase 7: User Story 5－管理者維持原本的管理流程與 context 選擇（Priority: P0）

**Goal**：SHELTER_ADMIN 與 PLATFORM_ADMIN 維持 `/`、既有 context selector、租戶範圍與切換失敗時的舊 context 保留行為。

**Independent Test**：使用 shelter admin/platform admin fixture 驗證 single/multiple context、成功切換、失敗重試、reload 與只顯示後端確認 context 的管理資料。

### Tests for User Story 5

- [ ] T037 [P] [US5] 在 `tests/integration/test_active_shelter_context.py` 與 `tests/security/test_request_context.py` 增加 context switch success/failure、old-context preservation、membership mismatch 與 cross-tenant denial assertions
- [ ] T038 [P] [US5] 在 `apps/web/e2e/management-core.spec.ts` 與 `apps/web/e2e/liff-route-isolation.spec.ts` 增加 SHELTER_ADMIN/PLATFORM_ADMIN destination、multi-context selector、switch failure、reload 與 stale data assertions

### Implementation for User Story 5

- [ ] T039 [US5] 在 `apps/web/components/management/ManagementLayout.tsx` 完成 context switch 的 success-only view replacement，失敗時保留 server-confirmed old context/data、顯示錯誤並允許 retry，不混合新 context response

**Checkpoint**：US4 與 US5 的 management regression 可獨立通過，且 platform context switch 不破壞 XI 多租戶原則。

## Phase 8: User Story 6－共用 LINE／LIFF 與 local fixture 遵循一致的志工權限邊界（Priority: P0）

**Goal**：同一 LINE OA/channel/Webhook/LIFF App 下的 ORG-A／ORG-B 專屬入口、local fixture 與 LINE Bot 具有一致的 context、Membership、route isolation 與 dog-first 邊界。

**Independent Test**：local deterministic matrix 先重跑所有 entry/access/route cases，再用同一受控 LIFF App 的兩個入口與至少兩個 LINE identity 驗證正確 context、cross-entry denial、dog selection 與 Bot fallback。

### Tests for User Story 6

- [ ] T040 [P] [US6] 在 `tests/fixtures/volunteer_access.py`、`tests/contract/test_volunteer_access_contract.py` 與 `tests/security/test_volunteer_access_entry_reference.py` 補齊 shared-channel entry reference、purpose、rotation/revocation 與 raw token/reference 不落庫／不進 log assertions
- [ ] T041 [P] [US6] 在 `tests/integration/test_line_webhook_session.py`、`tests/integration/test_line_postback_flow.py` 與 `tests/security/test_line_cross_tenant_postback.py` 驗證已確認 context 的 dog-first flow、未確認 context 的 LIFF fallback 與不以 dog name/shelter number 推測 tenant
- [ ] T042 [P] [US6] 在 `apps/web/e2e/liff-route-isolation.spec.ts` 與 `apps/web/e2e/volunteer-access-approval.spec.ts` 建立 local fixture 與 shared LIFF adapter 的相同 route/access matrix，確認 pending/rejected/revoked/expired 不會載入 animals/draft

### Implementation for User Story 6

- [ ] T043 [US6] 在 `apps/web/e2e/fixtures.ts`、`apps/web/e2e/volunteer-access-fixtures.ts` 與 `tests/fixtures/volunteer_access.py` 對齊 local-volunteer-a/b、ORG-A/B reference、membership state 與 formal-vs-local session source，讓兩種入口共用 observable policy
- [ ] T044 [US6] 在 `services/api/app/application/line_webhook_session.py` 與 `services/api/app/application/authentication/line_identity_service.py` 對齊既有 effective Membership/Active Context check，維持 LINE Bot state machine、Webhook signature/idempotency 與 CRM write path 不變
- [ ] T045 [US6] 在 `specs/004-volunteer-entry-route-isolation/validation/controlled-line-evidence.md` 記錄同一受控 LINE OA/channel/Webhook/LIFF App 的 ORG-A／ORG-B entry、cross-entry denial、360px dog selection 與回報入口驗收結果，遮罩所有 raw token/reference/PII

**Checkpoint**：US6 完成後，local fixture 可重跑同一矩陣，且受控共用 LINE／LIFF 已留下兩收容所獨立 context 的 P0 evidence。

## Phase 9: User Story 7－遇到 session、context 或權限問題時知道下一步（Priority: P0）

**Goal**：處理 local 401、formal LIFF 401、context 缺少、Membership 不一致、temporary error 與 entry failure，提供繁中安全終止與明確下一步，不形成 loop。

**Independent Test**：注入各類 failure，觀察 protected content 是否先卸載、exchange/navigation 次數、錯誤文案、keyboard/screen-reader 操作與 re-entry/back-to-LINE 結果。

### Tests for User Story 7

- [ ] T046 [P] [US7] 在 `apps/web/lib/liff-session.test.ts` 與 `apps/web/components/auth/AuthenticatedRouteBoundary.test.tsx` 覆蓋 single-flight 401、並行 401、exchange failure、second 401、missing token/reference、local 401 與 terminal epoch transitions
- [ ] T047 [P] [US7] 在 `apps/web/e2e/liff-route-isolation.spec.ts` 與 `apps/web/e2e/state-feedback.spec.ts` 驗證 redirect/navigation loop=0、formal recovery exchange<=1、mutation 不自動 replay、context-required、temporary error 與 re-entry/back-to-LINE actions
- [ ] T048 [P] [US7] 在 `apps/web/e2e/p0-keyboard.spec.ts`、`apps/web/e2e/p0-a11y.spec.ts` 與 `apps/web/e2e/p0-responsive.spec.ts` 驗證 loading/status/alert/primary action 的 keyboard、screen-reader 與 360px 長中文可用性

### Implementation for User Story 7

- [ ] T049 [US7] 在 `apps/web/lib/liff-session.ts` 與 `apps/web/features/liff/LiffSessionProvider.tsx` 實作 recovery epoch single-flight、原 entry reference exchange、成功後 profile/context recheck、mutation no-replay 與 terminal cleanup
- [ ] T050 [US7] 在 `apps/web/lib/auth.ts` 與受保護 request helper 中區分 local/session 401 與 formal LIFF 401：local 清除 auth 導向 `/login`，formal 只觸發一次 LIFF recovery，禁止無限 retry
- [ ] T051 [US7] 在 `apps/web/components/auth/ProtectedRouteState.tsx`、`apps/web/components/management/route-state.ts` 與 `apps/web/app/(volunteer-entry)/volunteer-entry/page.tsx` 完成 context-required、access-unavailable、temporary-error、re-entry、back-to-LINE 與 LIFF initialization failure 的台灣繁中 copy/accessibility

**Checkpoint**：US7 的所有 failure state 可獨立驗收；受保護內容不 stale、不洩漏、不 loop，且每個失效事件自動 exchange 不超過一次。

## Phase 10: Polish & Cross-Cutting Concerns

**目的**：完成跨 story 的品質、安全、文件與 release gate。

- [ ] T052 [P] 在 `apps/web/e2e/p0-visual.spec.ts`、`apps/web/e2e/p0-visual.spec.ts-snapshots/` 與 `apps/web/e2e/p0-a11y.spec.ts` 完成 360/768/1024/1440 viewport visual、axe 與 reviewer-approved baseline，禁止未審查 snapshot 更新
- [ ] T053 [P] 在 `tests/security/test_liff_exchange_authorization.py`、`tests/isolation/test_liff_entry_isolation.py` 與 `tests/security/test_unauthenticated_internal_data.py` 完成 server-side authorization、RLS、no partial state、no stale protected content 與 raw secret logging regression
- [ ] T054 在 `specs/004-volunteer-entry-route-isolation/quickstart.md`、`specs/004-volunteer-entry-route-isolation/contracts/README.md` 與 `specs/004-volunteer-entry-route-isolation/validation/controlled-line-evidence.md` 更新實際 command、controlled evidence location、known limitations 與 release checklist
- [ ] T055 在 `specs/004-volunteer-entry-route-isolation/` 執行 quickstart 全部 validation commands，並在 `specs/004-volunteer-entry-route-isolation/validation/` 保存不含 secret/PII 的結果摘要
- [ ] T056 在 repository root 執行 `ruff check .`、`ruff format --check .`、`pytest`、`npm --prefix apps/web run quality`、`npm --prefix apps/web run build`、P0 e2e/a11y/visual 與 `./scripts/verify_local.sh`，確認所有 constitution gate 通過後才標記 feature 完成

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**：無前置依賴；T001/T002/T004 可平行，T003 完成後才能進行 contract implementation。
- **Phase 2 Foundational**：依賴 Setup；T006、T007、T009、T012 可在不互相修改同一檔案時平行，T010/T011 依賴 T005/T006。
- **Phase 3 US1**：依賴 Phase 2；是 MVP 核心，T013–T016 應先於 T017–T023。
- **Phase 4 US2**：依賴 US1 的 volunteer boundary 與 context label（T020–T022），可在 US1 checkpoint 後開始。
- **Phase 5 US3**：依賴 Phase 2；與 US2 可平行，但 T031–T033 會修改 management route composition，整合時需先通過 US3 checkpoint。
- **Phase 6 US4**：依賴 US3 的 management boundary；只保留 regression-safe management role behavior。
- **Phase 7 US5**：依賴 US3/US4 的 management shell；T037 的 server regression 可與 T038 的 browser regression 平行。
- **Phase 8 US6**：依賴 US1 的 exchange 與 US3 的 route isolation；local fixture tasks 可平行，controlled LINE evidence 必須在程式與測試完成後執行。
- **Phase 9 US7**：依賴 US1 的 LIFF provider 與 protected fetch；T046–T048 可平行，T049–T051 依測試結果實作。
- **Phase 10 Polish**：依賴所有要交付的 user stories；T052/T053 可平行，T055/T056 必須最後執行。

### User Story Completion Order

1. **US1 P0 MVP**：formal/local volunteer entry → atomic exchange → `/animal-confirmation`。
2. **US2 P0**：active draft resume/later/unavailable。
3. **US3 P0**：全部 management route isolation。
4. **US4 P0**：STAFF management regression。
5. **US5 P0**：SHELTER_ADMIN/PLATFORM_ADMIN context regression。
6. **US6 P0**：shared LINE／LIFF + local fixture + Bot regression + controlled evidence。
7. **US7 P0**：session/context failure and recovery UX。

US2、US3、US6、US7 的部分工作可由不同開發者在 Foundation 完成後平行進行；涉及 `apps/web/e2e/liff-route-isolation.spec.ts` 的修改需集中整合避免 merge conflict。

## Parallel Execution Examples

### Foundation

```text
Task T006: route-access decision matrix in apps/web/lib/route-access.ts
Task T007: entry resolver adapter in services/api/app/infrastructure/line/entry_reference_adapter.py
Task T009: protected route states in apps/web/components/auth/ProtectedRouteState.tsx
Task T012: shared ORG-A/ORG-B fixtures in tests/fixtures/volunteer_access.py
```

### US1

```text
Task T013: authentication/OpenAPI contract tests
Task T014: exchange success integration test
Task T015: exchange authorization failure matrix
Task T016: cross-tenant isolation test
```

### US2 / US3

```text
Task T024: volunteer page unit tests
Task T029: pure route/boundary tests
Task T030: management deep-link network assertions
```

### US4 / US5

```text
Task T034: STAFF regression e2e
Task T037: backend context switch security tests
Task T038: management role/context browser tests
```

### US6 / US7

```text
Task T040: shared entry reference contract/security tests
Task T041: LINE Bot context regression tests
Task T046: LIFF recovery unit tests
Task T048: keyboard/a11y/responsive tests
```

## Implementation Strategy

### MVP First

1. 完成 Phase 1–2，先固定 atomic exchange、route decision 與 boundary。
2. 完成 Phase 3 US1，驗證 local fixture + controlled LIFF 的最短可用路徑。
3. 執行 US1 checkpoint；只有 contract、security、isolation 與 first-visible/network assertions 全通過，才進入 US2/US3。

### Incremental Delivery

1. US2 增加 draft resume，不改變 US1 的 entry/access boundary。
2. US3 增加 management isolation，US4/US5 立即做 management regression。
3. US6 補齊共用 LINE／LIFF 與 Bot evidence。
4. US7 補齊 failure/recovery/accessibility。
5. 最後執行 Phase 10 全部 quality/security/release gates。

### Completion Rules

- 每個 story 的 independent test criteria 必須獨立通過，不能以後續 story 的輸出代替。
- 任何前端 redirect 測試不得取代後端 authorization、RLS、Membership/Grant 或 transaction tests。
- 任何受控 LINE evidence 不得保存 raw token、entry reference、LINE user id、個資或 protected animal/report content。
- 只有 T056 所列 constitution gates 全部通過，才能將 004 標記完成。
