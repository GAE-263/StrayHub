# Tasks：志工報名與限時授權

**Input**：`/specs/005-volunteer-access-approval/` 中的 `plan.md`、`spec.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md`

**Tests**：規格明訂 27 項 Functional Requirements、15 項 Success Criteria、1,200 筆完整全選、60 秒到期收斂、跨租戶零洩漏、PLATFORM_ADMIN 逐 request 稽核、人工計時與 accessibility 驗收，因此本清單採測試先行；每個故事先建立會失敗的 contract／unit／integration／browser tests，再完成實作。

**Organization**：任務依五個 P0 使用者故事分 phase；所有 story task 都標記 `[US1]`～`[US5]`。共用資料模型、兩階段 migration、entry resolver、effective Membership、RLS 與測試 fixtures 放在 Setup／Foundational，避免故事間建立互相矛盾的正式狀態。

## Format：`[ID] [P?] [Story] Description`

- **[P]**：可與同 phase 其他標記任務平行執行，因為修改不同檔案且不依賴尚未完成的同檔任務。
- **[USn]**：對應 [spec.md](spec.md) 的使用者故事。
- 每項任務都包含實際或預定建立的精確檔案路徑。

---

## Phase 1：Setup（contract 與共用測試資料基線）

**Purpose**：先固定 canonical API surface、generated types 與跨故事 fixture vocabulary。

- [X] T001 將 `specs/005-volunteer-access-approval/contracts/volunteer-access.openapi.yaml` 的 12 個 paths、13 個 operations、錯誤語意與 schemas 合併至 canonical `specs/001-volunteer-care-report/contracts/openapi.yaml`
- [X] T002 由 canonical OpenAPI 重新生成 `packages/contracts/src/openapi.ts`，並在 `packages/contracts/scripts/check-generated.mjs` 加入 005 operation/schema drift assertions
- [X] T003 [P] 建立 ORG-A／ORG-B、未知 LINE identity、停用申請入口、policy、entry reference、Application／Grant 狀態矩陣、停用 user/org 未清理 context、通知失敗、100 筆與 1,200 筆 batch 的共用 fixture builders 於 `tests/fixtures/volunteer_access.py`

**Checkpoint**：後續 API、Web 與測試皆使用同一份 canonical contract 與 fixture 命名。

---

## Phase 2：Foundational（阻擋所有使用者故事）

**Purpose**：建立時間／狀態規則、完整 CRM schema、兩階段 migration、entry resolver、RLS、effective Membership 與 scoped repository 基礎。

**⚠️ CRITICAL**：本 phase 未完成前，不得開始任何 user story endpoint 或 UI。

### Foundation tests（先寫並確認失敗）

- [X] T004 [P] 在 `tests/unit/test_volunteer_access_time.py` 建立 `[valid_from, expires_at)`、UTC、168 小時初始 policy、future／active／expired／revoked 與 immediate-expiry confirmation 的 domain tests
- [X] T005 [P] 在 `tests/unit/test_volunteer_access_models.py` 建立 Application transition、finite VOLUNTEER Membership、單一 active Grant、policy snapshot、Batch／Item terminality、Notification／Retry idempotency 與 Audit system actor constraints tests
- [X] T006 [P] 在 `tests/integration/test_volunteer_access_migration.py` 建立 empty DB upgrade、0024→staged policy→0025、active unbounded legacy policy-aware backfill、disabled／revoked／expired 不啟用且不建立 synthetic Application／Grant、`SYSTEM_MIGRATION` Audit、forward recovery 與單一 Alembic head tests
- [X] T007 [P] 在 `tests/security/test_volunteer_access_entry_reference.py` 建立 raw token 不落庫、tampered／revoked／cross-purpose 拒絕、resolver 最小輸出及 runtime role 無法直接 SELECT entry table 的 tests
- [X] T008 [P] 在 `tests/security/test_volunteer_access_effective_membership.py` 建立 null／invalid expiry、future、expired、revoked、停用 user/org 與跨 organization context 全部拒絕的 request-time security tests
- [X] T009 [P] 在 `tests/contract/test_organization_management_contract.py` 增加既有 membership endpoint 不得建立無期限 VOLUNTEER，以及 additive validity/access-version response tests
- [X] T010 [P] 在 `tests/integration/test_organization_management.py` 驗證新 organization 與 168 小時初始 Volunteer Access Policy 原子建立、預設 `applications_enabled=true`，且 policy insert failure 時兩者皆回滾
- [X] T011 [P] 在 `tests/unit/test_platform_scope_audit.py` 驗證 PLATFORM_ADMIN support success、denied、not-found、validation failure 與 exception 都記錄單一 target、reason 與 result，缺少 target/reason 時不執行 business query

### Foundation implementation

- [X] T012 在 `services/api/app/domain/volunteer_access.py` 實作 Application／Grant transition、effective predicate、UTC period validation、reason normalization、policy snapshot、request fingerprint 與 stable error codes
- [X] T013 在 `services/api/app/persistence/models/identity.py` 為 `OrganizationMembership` 新增 `valid_from`、`expires_at`、`access_version` 與 `expired`／`revoked` volunteer status semantics
- [X] T014 [P] 在 `services/api/app/persistence/models/audit.py` 為 `AuditRecord` 新增 `actor_type`、`actor_reference`、user/system conditional validation 與 `SYSTEM_MIGRATION` 表示法
- [X] T015 在 `services/api/app/persistence/models/volunteer_access.py` 建立 `OrganizationVolunteerAccessPolicy`、`ShelterVolunteerEntryReference`、`VolunteerApplication`、`VolunteerAccessGrant`、Decision Batch／Item、Notification Delivery／Retry Batch／Item models 與 constraints
- [X] T016 在 `services/api/app/persistence/models/__init__.py` 與 `services/api/app/persistence/__init__.py` 匯出 005 models，確保 API、Worker 與 Alembic metadata 使用同一定義
- [X] T017 在 `services/api/migrations/versions/0024_volunteer_access_expand.py` 建立 nullable Membership/Audit 擴充、新 tables/indexes/FORCE RLS、168 小時 organization policy backfill、固定 search path 的 `resolve_volunteer_entry_reference` SECURITY DEFINER function 與最小 runtime grants
- [X] T018 [P] 建立可在 0024 與 0025 間依 organization 調整遷移期限且寫入受控 Audit 的 `scripts/configure_volunteer_access_policy.py`
- [X] T019 在 `services/api/migrations/versions/0025_volunteer_access_enforce.py` 以單一 migration timestamp 與各 organization policy，僅為 active、unbounded VOLUNTEER 建立 legacy Application／Grant snapshot；disabled／revoked／expired Membership 保持原狀且 synthetic Application／Grant 數量為 0；寫 `SYSTEM_MIGRATION` Audit、驗證 active VOLUNTEER 有限期後加入 enforce constraints
- [X] T020 [P] 建立至少 256-bit raw token、只持久化 SHA-256 digest、支援發行／輪替／撤銷且 raw 僅顯示一次的 `scripts/issue_volunteer_entry_reference.py`
- [X] T021 在 `services/api/app/persistence/repositories/volunteer_access_repository.py` 建立強制 organization scope 的 policy、entry resolve、application、grant、batch/item、outbox/retry CRUD、row lock 與 cursor primitives
- [X] T022 [P] 在 `services/api/app/persistence/database/scope.py` 實作 `set_platform_support_scope(target_organization_id)`，讓 platform mode 仍設定單一 `app.current_org_id` 而非取得全租戶 scope
- [X] T023 在 `services/api/app/persistence/repositories/authentication_repository.py` 實作使用 database time 的 effective Membership query，讓 active-only memberships 排除 future／expired／revoked volunteer
- [X] T024 在 `services/api/app/api/dependencies.py` 套用 effective Membership request gate，並實作 PLATFORM_ADMIN 單一 target／`X-Platform-Support-Reason` 1..500 與 request-scoped Audit lifecycle，讓 success／denied／not-found／validation／exception 都記錄 result 且缺少 target/reason 時不執行 business query
- [X] T025 [P] 在 `services/api/app/application/authentication/context_service.py` 與 `services/api/app/application/authentication/line_identity_service.py` 套用相同 effective predicate，禁止無效 volunteer 建立或維持 Active Context／Webhook Session
- [X] T026 在 `services/api/app/application/organization_management.py` 與 `services/api/app/api/organization_management.py` 拒絕既有 generic endpoint 建立／轉換無期限 VOLUNTEER，並回傳 validity/access-version
- [X] T027 在 `services/api/app/application/organization_management.py` 與 `services/api/app/persistence/repositories/organization_repository.py` 讓 organization 與 `OrganizationVolunteerAccessPolicy(applications_enabled=true, default_grant_duration_hours=168)` 在同一 transaction 建立，任一步驟失敗皆回滾且不採 lazy-create
- [X] T028 [P] 在 `services/api/app/application/volunteer_notification_service.py` 建立 domain transaction 內 outbox enqueue、唯一 event idempotency key 與 sanitized payload helper，不同步呼叫 LINE
- [X] T029 在 `scripts/seed_local.py` 建立 deterministic policy／entry references、未知 identity、停用申請入口、new／pending／rejected／future／active／expired／revoked、停用 user/org 未清理 context、跨 organization、所有通知事件失敗、100 筆人工批次及 1,200 筆 all-filtered fixtures，並保留既有 care data

**Checkpoint**：Foundation ready。新 organization 必有 168 小時初始 policy；資料庫不能存在 active 且無有限期限的 VOLUNTEER；pre-context resolver 只回單一候選 organization；所有受保護 request 使用同一 effective predicate；PLATFORM_ADMIN 的每次 management read/write 已具備 target/reason/result Audit。

---

## Phase 3：User Story 1－志工以 LINE 低門檻完成報名（Priority：P0）🎯 MVP

**Goal**：志工以 LINE 身分與收容所專屬入口查看自己的狀態、送出或撤回 pending 申請；只有 submit 原子建立／重用 User/Binding，單純 status 不持久化未知 identity；入口停用只阻止新 submit，且全程不載入任何受保護資料。

**Independent Test**：用 unknown、new、pending、rejected、withdrawn、expired fixtures 開啟 ORG-A entry，驗證 unknown status 不建 User/Binding、submit／duplicate／withdraw／reapply／own status；再以同 LINE identity 開 ORG-B 及停用申請入口，確認新 submit 被阻止但既有 applicant 仍可看 own status。全程 Membership、Session/context 與 protected API request 數為 0。

### Tests for User Story 1（先寫並確認失敗）

- [X] T030 [P] [US1] 在 `tests/contract/test_volunteer_access_contract.py` 驗證 status、submit、withdraw contract、duplicate 201/200 semantics、expected_version 與安全 403/404/409/422 schemas
- [X] T031 [P] [US1] 在 `tests/unit/test_volunteer_application_service.py` 驗證 entry purpose、首次 identity、duplicate client_request_id、terminal transition、reapply history 與 no-membership rules
- [X] T032 [P] [US1] 在 `tests/integration/test_volunteer_access_application.py` 驗證 unknown status 不建立 User/Binding、只有 submit 原子建立／重用 User + LineUserBinding + pending Application、unique race recovery、入口停用阻止新申請但保留既有 own status、withdraw、history link 與跨 organization 獨立 application
- [X] T033 [P] [US1] 在 `tests/security/test_unauthenticated_internal_data.py` 增加 pending／rejected／withdrawn onboarding 不可取得 animals/drafts/reports/list/count 且錯誤不洩漏其他 applicant 的 assertions
- [X] T034 [P] [US1] 在 `apps/web/features/volunteer-access/VolunteerApplicationPage.test.tsx` 建立繁中 new／pending／rejected／withdrawn／expired、withdraw/reapply、無帳密、無 protected content 與安全 loading/error tests
- [X] T035 [P] [US1] 在 `apps/web/e2e/volunteer-access-approval.spec.ts` 先建立首次報名、double-click/network retry、reload、ORG-A/ORG-B entry 與 protected request count=0 的 browser scenarios

### Implementation for User Story 1

- [X] T036 [P] [US1] 在 `services/api/app/application/ports/authentication.py` 定義 entry resolver port，只輸出 active reference id／候選 organization id，不輸出 role、Membership 或授權結果
- [X] T037 [US1] 在 `services/api/app/persistence/repositories/volunteer_access_repository.py` 串接 digest + purpose 的 SECURITY DEFINER resolver，解析後立即設定 organization scope，並實作 own current/history application queries
- [X] T038 [US1] 在 `services/api/app/application/volunteer_access_service.py` 實作 LINE identity flow：status/withdraw 只重用既有 Binding，unknown status 不持久化資料；只有 submit 可原子建立／重用 User + Binding + pending Application，並加入入口停用 submit gate、既有 own-status 例外、Audit/outbox 與 unique-violation recovery，且不建立 Membership/Session/context
- [X] T039 [US1] 在 `services/api/app/api/volunteer_access.py` 實作 `/v1/volunteer-applications/status`、`POST /v1/volunteer-applications`、withdraw endpoint 與最小資料 serializers，並在 `services/api/app/main.py` 註冊 router
- [X] T040 [P] [US1] 在 `apps/web/features/volunteer-access/volunteerAccess.ts` 實作 RFC3339→台灣時區、application/effective status、next-action 與安全 error mapping，不把 entry/client state 當成授權
- [X] T041 [US1] 在 `apps/web/features/volunteer-access/VolunteerApplicationPage.tsx` 實作 LINE identity status/apply/withdraw/reapply UI，身分解析前不掛載受保護 children
- [X] T042 [US1] 在 `apps/web/app/(volunteer-onboarding)/volunteer-application/page.tsx` 建立不依賴 Membership-protected layout 的 onboarding route，只傳入 LIFF identity 與 entry reference

**Checkpoint**：US1 可獨立 demo。志工能報名／查狀態／撤回／再次報名，但無法取得任何收容所資料或 Membership。

---

## Phase 4：User Story 2－收容所管理員批次審核報名者（Priority：P0）

**Goal**：SHELTER_ADMIN 或明確 target 的 PLATFORM_ADMIN 可篩選本 organization pending 名單，顯式選取最多 500 筆，或鎖定完整 all-filtered snapshot；套用 policy/common/per-item 期限後批次 approve/reject，並取得可恢復的逐項結果。

**Independent Test**：準備 100 筆 ORG-A pending + ORG-B 對照完成完整人工流程；另以 1,200 筆 all-filtered 建立不可變 snapshot，至少分 3 個不超過 500 筆 chunk，驗證確認後新增不納入、5 筆 stale conflict 不覆寫、成功項目不重做且所有 target 都有結果。

### Tests for User Story 2（先寫並確認失敗）

- [X] T043 [P] [US2] 在 `tests/contract/test_volunteer_access_contract.py` 增加 policy、application list、decision batch create/status/item-cursor、explicit 1..500、all-filtered、per-item override/result 與 operation conflict contract tests
- [X] T044 [P] [US2] 在 `tests/unit/test_volunteer_batch_decision.py` 驗證 request fingerprint、policy snapshot、common/per-item period merge、reject reason、expected_version、terminal item replay 與 batch count/status rules
- [X] T045 [P] [US2] 在 `tests/integration/test_volunteer_access_batch.py` 建立 repeatable-read immutable snapshot、逐項 transaction、95 success + 5 conflict、process interruption resume、same-operation replay 與 different-payload 409 tests
- [X] T046 [P] [US2] 在 `tests/performance/test_volunteer_access_batch.py` 驗證 100 筆流程及 1,200 筆 snapshot=1,200、每 chunk≤500、確認後新增排除、無遺失／重做與 cursor 結果完整率 100%
- [X] T047 [P] [US2] 在 `tests/security/test_volunteer_access_authorization.py` 驗證 STAFF、VOLUNTEER、ORG-B admin 與缺少 target/reason 的 PLATFORM_ADMIN 無法取得 ORG-A list/count/batch/resource-existence
- [X] T048 [P] [US2] 在 `apps/web/features/volunteer-access/ApplicationBatchWorkbench.test.tsx` 建立 filter、partial/all-filtered select、snapshot count、common period、10 筆 override、confirm、progress、cursor results、conflict 與 failed-only retry tests
- [X] T049 [P] [US2] 在 `apps/web/features/volunteer-access/VolunteerAccessPolicyForm.test.tsx` 建立 168 小時初始值、positive finite validation、expected-version conflict 與新 policy 不追溯既有 Batch/Grant tests
- [X] T050 [P] [US2] 在 `apps/web/e2e/volunteer-access-approval.spec.ts` 增加 100 筆批次、1,200 筆非同步進度、全篩選不降級目前頁、第二管理員 stale version、partial result 與 failed-only retry browser scenarios

### Implementation for User Story 2

- [X] T051 [US2] 在 `services/api/app/persistence/repositories/volunteer_access_repository.py` 實作 organization-scoped list filters/cursor、repeatable-read all-filtered Batch/Item snapshot、explicit limit、application `FOR UPDATE`、terminal result 與 resumable pending-item queries
- [X] T052 [US2] 在 `services/api/app/application/volunteer_batch_service.py` 實作 operation id/fingerprint、policy snapshot、完整 target freeze、每次最多 500 筆 claim、逐 item transaction、optimistic conflict、partial success 與 summary reconciliation
- [X] T053 [US2] 在 `services/api/app/application/volunteer_access_service.py` 實作單筆 approve/reject transaction：Application、Membership current projection、Grant、per-target Audit、outbox 與 BatchItem result 原子一致，並提供 policy read/update、管理員 application list及 policy version/duration snapshot
- [X] T054 [US2] 在 `services/api/app/api/volunteer_access.py` 實作 policy GET/PATCH、application GET、decision batch POST/GET 與 batch item cursor GET endpoints，並以 path organization + actor context 重新授權
- [X] T055 [P] [US2] 在 `services/worker/app/persistence/volunteer_access_repository.py` 實作 BatchItem `FOR UPDATE SKIP LOCKED` claim、stale claim recovery、terminal-result protection 與最多 500 筆 chunk persistence
- [X] T056 [US2] 在 `services/worker/app/handlers/volunteer_access_handler.py` 串接 logical batch chunk processing，程序中斷後只處理 pending item 且不變更 snapshot
- [X] T057 [P] [US2] 在 `apps/web/features/volunteer-access/VolunteerAccessPolicyForm.tsx` 實作 organization policy 顯示／修改、完整確認摘要、version conflict 與只影響後續決策說明
- [X] T058 [US2] 在 `apps/web/app/(management)/settings/volunteer-access/page.tsx` 串接 policy GET/PATCH，提供 applications enabled 與預設授權時數設定
- [X] T059 [P] [US2] 在 `apps/web/features/volunteer-access/ApplicationBatchWorkbench.tsx` 實作 100+ 筆 table、filter、explicit/all-filtered selection、完整 snapshot count、共同/個別期限、reject reason、確認、進度、cursor 結果與 retry payload
- [X] T060 [US2] 在 `apps/web/app/(management)/volunteers/applications/page.tsx` 串接 list/policy/batch APIs，保留未送出選取與 validation errors，並在 `apps/web/components/management/AppSidebar.tsx` 加入管理角色入口

**Checkpoint**：US2 可用直接建立的 pending fixtures 獨立驗證；100 筆人工操作與 1,200 筆完整 snapshot/chunk 均可重現。

---

## Phase 5：User Story 3－核准後取得明確且有限的志工權限（Priority：P0）

**Goal**：核准後志工取得明確開始／到期的 VOLUNTEER Membership；未覆寫時使用決策當下 organization policy，future start 不可提早使用，跨收容所各自判斷，own status 顯示期限，通知失敗不改變授權。

**Independent Test**：分別核准 initial 168h、ORG-A 72h policy、short、long、future 與 ORG-A+ORG-B grants；只有 active-unexpired target organization 通過 effective helper／request context，own status 顯示正確期限，LINE mock failure 時 CRM access 仍有效且無 duplicate Grant/Membership。

### Tests for User Story 3（先寫並確認失敗）

- [X] T061 [P] [US3] 在 `tests/unit/test_volunteer_grant_service.py` 驗證 approval commit time、policy snapshot/custom/future period、Membership projection、唯一 active Grant、role 不提升與 reactivation rules
- [X] T062 [P] [US3] 在 `tests/integration/test_volunteer_access_approval.py` 驗證 approved Application→Membership→Grant→Audit/outbox 原子一致、ORG-A/ORG-B 獨立、policy 變更不追溯與通知失敗不回滾
- [X] T063 [P] [US3] 在 `tests/contract/test_authentication_contract.py` 增加 005 effective Membership helper 對 active/future/expired/revoked 的 004 LIFF exchange handoff contract tests，不在 005 建立 route UI
- [X] T064 [P] [US3] 在 `tests/integration/test_active_shelter_context.py` 增加只有 active-unexpired VOLUNTEER 能建立/維持 target context，雙 organization 不混用且管理角色不套 volunteer expiry 的 tests
- [X] T065 [P] [US3] 在 `tests/contract/test_line_adapter_contract.py` 增加 LINE push port、local mock success/transient/terminal failure 與不含 protected payload tests
- [X] T066 [P] [US3] 在 `apps/web/features/volunteer-access/VolunteerApplicationPage.test.tsx` 增加 upcoming/active、organization、台灣時區完整期限、remaining duration、進入照護與 notification-failed 仍顯示 CRM 正式結果 tests
- [X] T067 [P] [US3] 在 `apps/web/e2e/volunteer-access-approval.spec.ts` 增加 initial/organization-policy/custom/future/cross-organization approval 與 own-status browser scenarios

### Implementation for User Story 3

- [X] T068 [US3] 在 `services/api/app/application/volunteer_access_service.py` 實作 Grant effective-status、own-status grant summary、remaining duration 與歷史週期讀取，重用 T053 的 approval transaction 且不重複建立或修改正式決策；直接依賴 T053
- [X] T069 [US3] 在 `services/api/app/api/volunteer_access.py` 實作 organization grant list endpoint 與 approved/upcoming/active own-status response，Membership/Grant 日期一律輸出 RFC3339 UTC
- [X] T070 [P] [US3] 在 `services/api/app/application/ports/line_messaging.py` 與 `services/api/app/infrastructure/line/messaging_api_adapter.py` 實作最少資料 LINE push contract，並在 `services/api/app/infrastructure/line/mock_adapter.py` 實作 deterministic failure modes
- [X] T071 [US3] 在 `services/worker/app/persistence/volunteer_access_repository.py` 與 `services/worker/app/handlers/volunteer_access_handler.py` 實作 notification `SKIP LOCKED` claim、ownership、bounded backoff、sent/retry_wait/failed 狀態且不重放 domain mutation
- [X] T072 [US3] 在 `apps/web/features/volunteer-access/VolunteerApplicationPage.tsx` 顯示 approved upcoming/active、目前收容所、台灣時區期限與剩餘時間，只有 effective active 才呈現交給 004 的「進入照護流程」下一步

**Checkpoint**：US1+US2+US3 構成核心 P0：報名、人工核准與限時有效授權；004 只需消費 effective Membership contract。

---

## Phase 6：User Story 4－管理員調整、撤銷與重新授權（Priority：P0）

**Goal**：管理員可延長／縮短 active Grant、確認立即失效、以原因撤銷；到期、撤銷或 user/org 停用後 request-time 立即拒絕，Worker 即使沒有後續 request 也在 60 秒內收斂 target Session/context 與適用 Audit/notification，保留其他 organization 與原始資料並支援新週期。

**Independent Test**：對 active/future Grant 執行 extend/shorten/immediate/revoke，使用注入 clock 觸發自然到期，並停用 user/organization 後不再送 request；驗證授權立即失效、Session/Webhook 仍在 60 秒內 scoped cleanup、另一 organization 不受影響、Draft/Report/Media 不變，重新報名核准產生新 Grant id；legacy migration 依各 policy 建立有限過渡週期。

### Tests for User Story 4（先寫並確認失敗）

- [X] T073 [P] [US4] 在 `tests/contract/test_volunteer_access_contract.py` 增加 grant list/PATCH discriminator、update_period、revoke、confirm_immediate_expiry、expected_version 與安全 conflict contract tests
- [X] T074 [P] [US4] 在 `tests/unit/test_volunteer_grant_mutation.py` 建立 extend/shorten/revoke/terminal immutability、blank reason、version increments 與 new-cycle rules tests
- [X] T075 [P] [US4] 在 `tests/integration/test_volunteer_access_expiration.py` 建立 request-time exact-boundary、自然到期與 user/org 停用後即時拒絕、沒有後續 request 時 Worker≤60 秒補償收斂、idempotent sweep、Session/Webhook scoped cleanup 與 other-org preservation tests
- [X] T076 [P] [US4] 在 `tests/integration/test_volunteer_access_history_preservation.py` 驗證 revoke/expire 不刪 Draft/CareReport/Media/source Application，重新報名核准建立新 Grant 且可追溯舊週期
- [X] T077 [P] [US4] 在 `tests/integration/test_volunteer_access_migration.py` 補齊 ORG-A 72h／ORG-B 168h legacy transition、policy snapshot、disabled／revoked／expired Membership 不啟用且 synthetic Application／Grant 數量為 0、原 active Membership 關聯與可後續調整／撤銷 tests
- [X] T078 [P] [US4] 在 `apps/web/features/volunteer-access/AccessGrantTable.test.tsx` 建立 extend/shorten/immediate confirm/revoke reason/version conflict、歷史週期與 preserved input tests
- [X] T079 [P] [US4] 在 `apps/web/e2e/volunteer-access-approval.spec.ts` 增加期限調整、立即失效、撤銷、自然到期、重新申請/授權與跨 organization context 保留 browser scenarios

### Implementation for User Story 4

- [X] T080 [US4] 在 `services/api/app/application/volunteer_access_service.py` 實作 Grant period mutation/revoke、新 Application/Grant cycle 規則、optimistic version、Audit/outbox 與 immediate scoped cleanup
- [X] T081 [US4] 在 `services/api/app/application/volunteer_expiration_service.py` 實作 due Grant row lock、inactive organization/disabled user 未收斂 context sweep、Membership/Grant transition、SessionRecord target context clear、WebhookSession expiry/revoke、適用 Audit/outbox 與 60 秒冪等補償收斂
- [X] T082 [US4] 在 `services/api/app/api/volunteer_access.py` 實作 Grant PATCH endpoint，縮短至 now 前要求 `confirm_immediate_expiry` 且 revoke reason 必填
- [X] T083 [US4] 在 `services/worker/app/handlers/volunteer_access_handler.py` 串接 expiry sweep、notification delivery、stale claim recovery 與單次 bounded work iteration
- [X] T084 [US4] 在 `services/worker/worker.py` 以不超過 60 秒 interval 啟動可取消的 volunteer batch/expiry/user-org invalidation/notification loop，保留既有 AI Worker 行為與 graceful shutdown
- [X] T085 [P] [US4] 在 `apps/web/features/volunteer-access/AccessGrantTable.tsx` 實作 Grant 篩選、期限修改、立即失效確認、revoke reason、conflict reload 與歷史週期顯示
- [X] T086 [US4] 在 `apps/web/app/(management)/volunteers/access/page.tsx` 串接 grant list/mutation APIs，顯示目前 CRM 狀態、期限、歷史週期與安全錯誤下一步

**Checkpoint**：US4 可獨立證明失效立即生效、60 秒內持久收斂、跨收容所 context 不互傷且原始照護資料完整保留。

---

## Phase 7：User Story 5－所有決策都受租戶隔離並可稽核（Priority：P0）

**Goal**：所有 application/grant/batch/notification read/write 都被單一 organization scope、repository filter 與 FORCE RLS 限制；PLATFORM_ADMIN 每次支援都有 target/reason/result Audit；管理員可在統一通知失敗清單篩選並冪等重試 1..500 筆，而不重做正式決策。

**Independent Test**：使用同名 applicant、同一 user 跨 ORG-A/ORG-B、猜測 UUID、漏 ORM filter、STAFF/other-admin/platform fixtures 與所有通知事件；跨租戶可見/修改數為 0，PLATFORM_ADMIN 缺 target/reason 成功數為 0，合法 read/write Audit 覆蓋率 100%，manual retry 只改 delivery/retry records。

### Tests for User Story 5（先寫並確認失敗）

- [X] T087 [P] [US5] 在 `tests/isolation/test_volunteer_access_isolation.py` 建立 application/list/count/grant/batch/item/notification/retry/Audit 的 ORG-A↔ORG-B read/write/id-guess matrix
- [X] T088 [P] [US5] 在 `tests/isolation/test_foundational_tenant_matrix.py` 增加直接 repository 漏 tenant filter 時由 FORCE RLS 阻擋所有 005 tables，以及 platform support scope 仍只見單一 target 的 assertions
- [X] T089 [P] [US5] 在 `tests/security/test_volunteer_access_authorization.py` 增加 SHELTER_ADMIN active-context、STAFF/VOLUNTEER deny、PLATFORM_ADMIN 每個 list/detail/mutation 必填 target/reason、禁止混合清單與 generic not-found/no-count-leak tests
- [X] T090 [P] [US5] 在 `tests/integration/test_volunteer_access_audit.py` 驗證 submit/withdraw/approve/reject/policy/period/expire/revoke/regrant、batch summary 與 platform read/write 的 actor/source/before/after/reason/result/operation-id coverage
- [X] T091 [P] [US5] 在 `tests/integration/test_volunteer_access_notifications.py` 建立所有 event type transient/terminal failure、organization failure filters、只有 failed 可 manual retry 1..500、retry_wait／sending／sent 或提交期間狀態改變回 per-item conflict、operation replay/conflict、stale claim 與 domain counts/version 不增加 tests
- [X] T092 [P] [US5] 在 `tests/security/test_observability_logging.py` 增加 id token、raw entry token、LINE user id、provider credential、other-applicant data 不得出現在 error/log/audit payload 的 tests
- [X] T093 [P] [US5] 在 `apps/web/features/volunteer-access/NotificationFailureQueue.test.tsx` 建立 event/status/time filters、cursor、只有 failed 可選取、retry_wait 顯示等待自動重試並停用選取、single/multi retry、operation replay、提交期間狀態改變的 partial conflict、最少收件人資訊與 keyboard/live-region tests
- [X] T094 [P] [US5] 在 `apps/web/e2e/volunteer-access-approval.spec.ts` 增加 STAFF/VOLUNTEER/ORG-B deep-link 不掛載名單、不發管理 request、PLATFORM_ADMIN target/reason Audit 與統一通知 failure/retry browser scenarios

### Implementation for User Story 5

- [X] T095 [US5] 在 `services/api/app/persistence/repositories/volunteer_access_repository.py` 對所有 resource/list/count/batch/notification/retry queries 強制 organization parameter、RLS scope 與 non-enumerating lookup，移除任何 unscoped fallback
- [X] T096 [US5] 在 `services/api/app/api/dependencies.py` 稽核所有 volunteer management routes 都使用 Foundational 的 PLATFORM_ADMIN target/reason/result Audit dependency，禁止 endpoint 略過、重複記錄或建立全租戶 platform scope；SHELTER_ADMIN 沿用 target Active Context 且不要求 support header
- [X] T097 [US5] 在 `services/api/app/application/volunteer_access_service.py` 統一 lifecycle/batch per-item Audit mapping，共用 operation id，並保存 platform target/reason/result 而不混入其他 organization
- [X] T098 [US5] 在 `services/api/app/application/volunteer_notification_service.py` 實作 organization-scoped 統一 failure list、event/status/time cursor filters、1..500 Retry Batch/Item、operation fingerprint、只允許仍為 failed 的 delivery 原子轉為 retry_wait，並讓其他狀態產生不變更 delivery 的 per-item conflict partial results
- [X] T099 [US5] 在 `services/api/app/api/volunteer_access.py` 實作 notification failure list 與 bulk retry endpoints，並集中 generic 403/404/409 回應與最少資料 serializer
- [X] T100 [US5] 在 `services/worker/app/persistence/volunteer_access_repository.py` 與 `services/worker/app/handlers/volunteer_access_handler.py` 完成 admin retry/stale notification claim 處理，只新增 attempt opportunity 且不呼叫 domain decision service
- [X] T101 [P] [US5] 在 `services/api/app/observability/logging.py` 加入 LINE id token、entry token、provider credential、recipient identifier 與 cross-tenant detail redaction
- [X] T102 [P] [US5] 在 `apps/web/features/volunteer-access/NotificationFailureQueue.tsx` 實作統一失敗表、event/status/time filters、cursor、只有 failed 可選取及 single/multi retry、retry_wait 等其他狀態停用選取、partial conflict results 與可理解 live feedback
- [X] T103 [US5] 在 `apps/web/app/(management)/volunteers/notifications/page.tsx` 串接 failure list/retry APIs，並在 `apps/web/app/(management)/volunteers/layout.tsx` 與 `apps/web/components/management/AppSidebar.tsx` 建立 management role mount-before-fetch boundary

**Checkpoint**：US5 可獨立證明 service + query + RLS 三層租戶隔離、PLATFORM_ADMIN 單一 target 支援稽核與通知重試不改變正式授權。

---

## Phase 8：Polish & Cross-Cutting Concerns

**Purpose**：完成跨故事 contract drift、responsive/accessibility/visual、migration regression、人工成功指標與完整品質 Gate。

- [X] T104 [P] 在 `tests/contract/test_generated_contract_types.py` 與 `tests/contract/test_openapi_contract.py` 增加 005 的 13 operations、35 schemas、platform support header、batch cursor 與 generated-type drift coverage
- [X] T105 [P] 在 `tests/integration/test_empty_database_bootstrap.py` 與 `tests/integration/test_shelter_status_and_membership.py` 加入 0024/0025 empty/legacy upgrade、新 organization policy 原子初始化、disabled／revoked／expired Membership 不建立 synthetic Application／Grant、suspended organization／disabled user 無 request cleanup、finite VOLUNTEER 與 existing non-volunteer regression
- [X] T106 [P] 在 `apps/web/e2e/p0-responsive.spec.ts` 加入 onboarding、100/1,200 筆 batch workbench、policy、Grant 與 notification queue 的 360x800、768x1024、1024x768、1440x900 scenarios
- [X] T107 [P] 在 `apps/web/e2e/p0-keyboard.spec.ts` 與 `apps/web/e2e/p0-a11y.spec.ts` 加入 filter/select-all/period override/dialog focus/return focus/live result/notification retry，要求 Axe critical/serious=0
- [ ] T108 [P] 在 `apps/web/e2e/p0-visual.spec.ts` 加入 onboarding states、batch confirmation/progress/partial result、policy、Grant 與 notification failure snapshots；只有 reviewer 確認 UI 後才更新 `apps/web/e2e/p0-visual.spec.ts-snapshots/`
- [X] T109 在 `apps/web/package.json` 將 `e2e/volunteer-access-approval.spec.ts` 納入 P0 e2e/a11y/visual commands，並維持既有 route/management/volunteer regression suites
- [ ] T110 依 `specs/005-volunteer-access-approval/quickstart.md` 執行至少 20 位首次志工（≥10 iOS、≥10 Android）SC-001 計時與至少 3 位管理員各 100 筆 SC-002 計時，將匿名原始記錄、介入、錯誤與可重算 pass rate 寫入 `specs/005-volunteer-access-approval/validation.md`
- [X] T111 在 `specs/005-volunteer-access-approval/checklists/requirements.md` 補上 FR-001～FR-027／SC-001～SC-015 對應的自動化測試或人工證據連結，不以勾選取代實際結果
- [X] T112 依 `specs/005-volunteer-access-approval/quickstart.md` 執行 migration、新 organization policy 原子初始化、policy staging、entry issue/rotation、unknown status/停用入口、seed、API/Web/Worker、100/1,200 筆 batch、expiry/user-org invalidation、notification failure、platform support、tenant isolation 與 004 handoff 預備驗收，將結果記錄於 `specs/005-volunteer-access-approval/validation.md`
- [ ] T113 執行 `uv run ruff check .`、`uv run ruff format --check .`、`uv run pytest`、`npm --prefix packages/contracts run check`、`npm --prefix apps/web run quality`、build、P0 Playwright、axe、visual 與 `./scripts/verify_local.sh`，把完整 command/result/known limitations 寫入 `specs/005-volunteer-access-approval/validation.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（Phase 1）**：無依賴，可立即開始。
- **Foundational（Phase 2）**：依賴 Setup；完成前阻擋所有故事。
- **US1～US5（Phase 3～7）**：測試、UI 與 fixture 準備都依賴 Foundational，完成後可由不同開發者平行進行；完整後端整合仍遵守下列直接依賴：US3 的 T068 依賴 US2 的 T053 approval transaction，US4 的管理操作與重新授權整合依賴 T053／T068，US5 的 endpoint hardening 與跨故事驗收必須等待相應 US1～US4 endpoints 完成。
- **Polish（Phase 8）**：依賴準備交付的所有故事；人工計時需使用固定完成版本。

### User Story Dependency Graph

```text
Setup
  └── Foundational
        ├── US1：LINE 報名／own status
        └── US2：管理員 policy／批次決策
              └── T053 approval transaction
                    └── US3 T068：限時授權／effective context
                          └── US4：管理操作／重新授權整合

US1～US4 相應 endpoints
  └── US5 final hardening：租戶隔離／平台稽核／通知失敗佇列

建議整合交付順序：US1 → US2 → US3 → US4 → US5 → Polish
```

- **US1**：Foundational 後可直接以 LINE/application fixtures 驗收，不依賴管理 UI。
- **US2**：Foundational 後可直接建立 pending fixtures 驗收；與 US1 整合後再驗證真實報名來源。
- **US3**：Foundational 後可直接建立 pending decision fixtures 撰寫測試；完整 service 實作的 T068 直接依賴 US2 的 T053 核准交易。
- **US4**：Foundational 後可直接建立 active/future grants 撰寫獨立測試；完整管理操作與重新授權整合依賴 T053／T068，重新報名另整合 US1。
- **US5**：Foundational 後可用 fixtures 開始 isolation/audit tests；endpoint hardening 與最終跨故事驗收必須等待相應 US1～US4 endpoints，並覆蓋其全部事件。

### Within Each User Story

1. 先寫該故事 tests 並確認在缺少實作時失敗。
2. 完成 repository/model dependency 後再完成 service。
3. service 完成後實作 API/Worker adapters。
4. contract types 穩定後完成 Web component/page。
5. 執行該故事 Independent Test，再進入整合交付。

---

## Parallel Opportunities

- Setup 的 T003 可與 canonical contract 工作 T001～T002 平行。
- Foundational tests T004～T011 可平行；T014、T018、T020、T022、T025、T028 修改不同檔案，可在其直接前置完成後平行。
- Foundational 完成後，各故事的 fixtures、獨立 tests、UI skeleton 與不同檔案工作可平行；正式 service/API 整合仍依 User Story Dependency Graph 與任務直接依賴執行，同一 service/repository 檔案的 tasks 依編號序列合併。
- 每個故事中標記 `[P]` 的 unit、integration、security、frontend 與 browser test 可平行撰寫。
- Phase 8 的 contract、migration、responsive、keyboard/a11y、visual 任務 T104～T108 可平行，人工計時 T110 必須等候固定版本。

### Parallel Example：User Story 1

```text
T030 contract test
T031 service unit test
T032 persistence integration test
T033 protected-data security test
T034 frontend unit test
T035 browser flow
```

### Parallel Example：User Story 2

```text
T043 contract test
T044 batch unit test
T045 integration test
T046 100/1,200-item performance test
T047 authorization test
T048 batch UI unit test
T049 policy UI unit test
T050 browser flow
```

### Parallel Example：User Story 3

```text
T061 grant service unit test
T062 approval integration test
T063 004 handoff contract test
T064 active-context integration test
T065 LINE adapter contract test
T066 frontend unit test
T067 browser flow
```

### Parallel Example：User Story 4

```text
T073 API contract test
T074 mutation unit test
T075 expiry integration test
T076 history-preservation test
T077 legacy migration acceptance test
T078 frontend unit test
T079 browser flow
```

### Parallel Example：User Story 5

```text
T087 cross-tenant matrix
T088 FORCE RLS test
T089 platform authorization test
T090 audit coverage test
T091 notification integration test
T092 redaction security test
T093 notification UI unit test
T094 browser flow
```

---

## Implementation Strategy

### MVP First（US1）

1. 完成 Setup。
2. 完成 Foundational，特別是新 organization policy 原子初始化、兩階段 migration、entry resolver、RLS、effective Membership 與 PLATFORM_ADMIN target/reason/result Audit lifecycle。
3. 完成 US1。
4. 停下並執行 US1 Independent Test：LINE 無帳密報名、own status、duplicate/withdraw/reapply、零 protected data。
5. 可展示低門檻報名 MVP，但不得宣稱已具備管理員核准或正式志工存取。

### Incremental Delivery

1. Setup + Foundational → 安全資料與授權基礎。
2. US1 → 志工可安全報名與查狀態。
3. US2 → 管理員可設定 policy 並完成 100/1,200 筆批次決策。
4. US3 → 核准結果成為可由 004 消費的限時有效授權。
5. US4 → 調整、撤銷、自然到期、user-org 停用收斂與 legacy transition 完整。
6. US5 → 平台支援稽核、租戶隔離證據與統一通知失敗佇列完整。
7. Polish → 人工 SC、可及性、visual、migration 與完整 regression Gate。

### Parallel Team Strategy

1. 團隊共同完成 Setup + Foundational。
2. Foundation ready 後，可分為 onboarding（US1）、batch/policy（US2）、grant/context（US3/US4）、security/notification（US5）四條工作流。
3. 共用 `volunteer_access_repository.py`、`volunteer_access_service.py`、`volunteer_access.py` API 與 Worker handler 依 task 編號整合，避免平行覆寫。
4. 每條工作流通過 Independent Test 後才進入 Phase 8 的固定版本驗收。

---

## Notes

- `[P]` 只代表檔案與直接依賴允許平行，不代表可跳過前一 phase。
- 所有 authorization 判斷使用 server/database UTC 與 CRM state；不得信任 URL、entry reference、client state 或 notification delivery 作為權限。
- 每個 tenant business table 與 query 必須帶 organization scope，並由 FORCE RLS 作最後防線。
- Tests 必須先失敗再實作；不得以刪除、skip、放寬 assertion 或只測 happy path 宣稱完成。
- 建議每個 task 或緊密邏輯群組完成後 commit，並在每個 Checkpoint 執行對應 Independent Test。
