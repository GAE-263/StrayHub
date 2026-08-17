# Specification Quality Checklist: 志工報名與限時授權

**Purpose**: 在進入規劃前驗證本功能規格的完整性、可測試性與範圍邊界

**Created**: 2026-08-14

**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] 沒有指定語言、框架、API schema 或檔案結構等實作細節
- [x] 聚焦志工、收容所管理員、限時授權、資料安全與業務需求
- [x] 以非技術利害關係人可理解的台灣繁體中文撰寫
- [x] 所有 mandatory sections 均已完成

## Requirement Completeness

- [x] 沒有未解決的 `[NEEDS CLARIFICATION]` 標記
- [x] Functional Requirements 可測試且沒有歧義
- [x] Success Criteria 可量測
- [x] Success Criteria 不依賴框架、語言、資料庫或其他實作細節
- [x] 所有使用者故事均有獨立驗收方式與 Given／When／Then 情境
- [x] 已識別重複報名、並行決策、批次部分失敗、期限邊界、通知失敗與授權中途失效等 edge cases
- [x] P0、P1 與 Out of Scope 邊界清楚
- [x] 已記錄 LINE 身分、Membership、Audit Log、CRM 與 `004-volunteer-entry-route-isolation` 依賴及合理假設

## Feature Readiness

- [x] 每項 functional requirement 都有對應的使用者情境、edge case 或成功標準
- [x] 使用者故事涵蓋志工報名、批次審核、限時 Membership、期限／撤銷與租戶稽核
- [x] Feature 的 P0 具備可獨立展示、測試與驗收的 measurable outcomes
- [x] 規格未把 LINE 入口、前端隱藏或通知描述成安全邊界

## Validation Notes

- 第一輪驗證已由後續 clarification 與設計更新取代。
- 2026-08-15 remediation 驗證 16/16 通過：5 個 user stories 均可獨立驗收；27 項 FR 涵蓋報名、批次決策、有限期限、新 organization policy 原子初始化、並行衝突、到期／撤銷、停用後 60 秒持久化 context 清理、通知失敗、Audit Log 與多收容所隔離；15 項 SC 具體量測時間、批次規模、拒絕率、期限完整率、稽核與可及性。
- 無 `[NEEDS CLARIFICATION]`；入口停用時既有 own status、只有 submit 可建立 User/Binding、預設 7 天、無期限禁止、批次逐筆結果與 `004-volunteer-entry-route-isolation` 依賴均已記錄於規格。

## Requirement Evidence Matrix

以下連結是可重跑的實際證據；人工成功指標維持 pending，不以本 checklist 的勾選狀態代替測量結果。完整 command、結果與限制見 [validation.md](../validation.md)。

| Requirement | Evidence |
| --- | --- |
| FR-001 | [application integration](../../../tests/integration/test_volunteer_access_application.py)、[browser onboarding](../../../apps/web/e2e/volunteer-access-approval.spec.ts) |
| FR-002 | [entry-reference security](../../../tests/security/test_volunteer_access_entry_reference.py)、[authorization](../../../tests/security/test_volunteer_access_authorization.py) |
| FR-003 | [application service](../../../tests/unit/test_volunteer_application_service.py)、[application integration](../../../tests/integration/test_volunteer_access_application.py) |
| FR-004 | [application integration](../../../tests/integration/test_volunteer_access_application.py)、[onboarding UI states](../../../apps/web/features/volunteer-access/VolunteerApplicationPage.test.tsx) |
| FR-005 | [application integration](../../../tests/integration/test_volunteer_access_application.py)、[history preservation](../../../tests/integration/test_volunteer_access_history_preservation.py) |
| FR-006 | [authorization matrix](../../../tests/security/test_volunteer_access_authorization.py)、[tenant isolation](../../../tests/isolation/test_volunteer_access_isolation.py)、[platform audit](../../../tests/unit/test_platform_scope_audit.py) |
| FR-007 | [batch integration](../../../tests/integration/test_volunteer_access_batch.py)、[1,200-item performance matrix](../../../tests/performance/test_volunteer_access_batch.py) |
| FR-008 | [organization/policy integration](../../../tests/integration/test_shelter_status_and_membership.py)、[migration integration](../../../tests/integration/test_volunteer_access_migration.py)、[policy UI](../../../apps/web/features/volunteer-access/VolunteerAccessPolicyForm.test.tsx) |
| FR-009 | [time rules](../../../tests/unit/test_volunteer_access_time.py)、[grant service](../../../tests/unit/test_volunteer_grant_service.py) |
| FR-010 | [approval integration](../../../tests/integration/test_volunteer_access_approval.py)、[decision rules](../../../tests/unit/test_volunteer_batch_decision.py) |
| FR-011 | [batch decisions](../../../tests/unit/test_volunteer_batch_decision.py)、[grant mutations](../../../tests/unit/test_volunteer_grant_mutation.py)、[accessible confirmation](../../../apps/web/e2e/p0-keyboard.spec.ts) |
| FR-012 | [batch integration](../../../tests/integration/test_volunteer_access_batch.py)、[1,200-item snapshot/chunks](../../../tests/performance/test_volunteer_access_batch.py)、[batch browser flow](../../../apps/web/e2e/volunteer-access-approval.spec.ts) |
| FR-013 | [batch concurrency](../../../tests/integration/test_volunteer_access_batch.py)、[grant optimistic version](../../../tests/unit/test_volunteer_grant_mutation.py) |
| FR-014 | [effective membership](../../../tests/security/test_volunteer_access_effective_membership.py)、[request context](../../../tests/security/test_request_context.py) |
| FR-015 | [grant mutations](../../../tests/unit/test_volunteer_grant_mutation.py)、[approval/grant integration](../../../tests/integration/test_volunteer_access_approval.py)、[grant UI](../../../apps/web/features/volunteer-access/AccessGrantTable.test.tsx) |
| FR-016 | [expiration integration](../../../tests/integration/test_volunteer_access_expiration.py)、[request context](../../../tests/security/test_request_context.py) |
| FR-017 | [history preservation](../../../tests/integration/test_volunteer_access_history_preservation.py) |
| FR-018 | [application history](../../../tests/integration/test_volunteer_access_history_preservation.py)、[grant integration](../../../tests/integration/test_volunteer_access_approval.py) |
| FR-019 | [tenant isolation](../../../tests/isolation/test_volunteer_access_isolation.py)、[authorization matrix](../../../tests/security/test_volunteer_access_authorization.py) |
| FR-020 | [audit integration](../../../tests/integration/test_volunteer_access_audit.py)、[batch audit](../../../tests/integration/test_volunteer_access_batch.py) |
| FR-021 | [notification integration](../../../tests/integration/test_volunteer_access_notifications.py)、[notification queue UI](../../../apps/web/features/volunteer-access/NotificationFailureQueue.test.tsx)、[LINE adapter contract](../../../tests/contract/test_line_adapter_contract.py) |
| FR-022 | [authorization matrix](../../../tests/security/test_volunteer_access_authorization.py)、[observability redaction](../../../tests/security/test_observability_logging.py) |
| FR-023 | [responsive](../../../apps/web/e2e/p0-responsive.spec.ts)、[keyboard](../../../apps/web/e2e/p0-keyboard.spec.ts)、[axe](../../../apps/web/e2e/p0-a11y.spec.ts) |
| FR-024 | [decision rules](../../../tests/unit/test_volunteer_batch_decision.py)、[approval integration](../../../tests/integration/test_volunteer_access_approval.py) |
| FR-025 | [effective membership handoff](../../../tests/security/test_volunteer_access_effective_membership.py)、[entry reference contract](../../../tests/security/test_volunteer_access_entry_reference.py) |
| FR-026 | [application integration](../../../tests/integration/test_volunteer_access_application.py)、[application service](../../../tests/unit/test_volunteer_application_service.py) |
| FR-027 | [migration integration](../../../tests/integration/test_volunteer_access_migration.py)、[empty bootstrap](../../../tests/integration/test_empty_database_bootstrap.py) |
| SC-001 | **人工證據 pending**：需依 [quickstart](../quickstart.md#sc-001志工低門檻報名) 完成 20 位參與者計時；自動流程證據為 [browser onboarding](../../../apps/web/e2e/volunteer-access-approval.spec.ts) |
| SC-002 | **人工證據 pending**：需依 [quickstart](../quickstart.md#sc-002管理員-100-筆批次) 完成 3 位管理員計時；一致性／規模證據為 [batch performance matrix](../../../tests/performance/test_volunteer_access_batch.py) |
| SC-003 | [application integration](../../../tests/integration/test_volunteer_access_application.py)、[batch idempotency](../../../tests/integration/test_volunteer_access_batch.py) |
| SC-004 | [effective membership matrix](../../../tests/security/test_volunteer_access_effective_membership.py)、[tenant isolation](../../../tests/isolation/test_volunteer_access_isolation.py) |
| SC-005 | [time rules](../../../tests/unit/test_volunteer_access_time.py)、[migration](../../../tests/integration/test_volunteer_access_migration.py)、[organization initialization](../../../tests/integration/test_shelter_status_and_membership.py) |
| SC-006 | [expiration/disable cleanup](../../../tests/integration/test_volunteer_access_expiration.py)、[request context](../../../tests/security/test_request_context.py) |
| SC-007 | [batch integration](../../../tests/integration/test_volunteer_access_batch.py)、[performance matrix](../../../tests/performance/test_volunteer_access_batch.py) |
| SC-008 | [audit lifecycle](../../../tests/integration/test_volunteer_access_audit.py) |
| SC-009 | [volunteer isolation](../../../tests/isolation/test_volunteer_access_isolation.py)、[full cross-tenant matrix](../../../tests/isolation/test_full_cross_tenant_matrix.py) |
| SC-010 | [history preservation](../../../tests/integration/test_volunteer_access_history_preservation.py) |
| SC-011 | [responsive](../../../apps/web/e2e/p0-responsive.spec.ts)、[keyboard](../../../apps/web/e2e/p0-keyboard.spec.ts)、[axe](../../../apps/web/e2e/p0-a11y.spec.ts)；新 visual baseline 等 reviewer 確認 |
| SC-012 | [notification integration](../../../tests/integration/test_volunteer_access_notifications.py)、[queue browser controls](../../../apps/web/e2e/p0-keyboard.spec.ts) |
| SC-013 | [migration integration](../../../tests/integration/test_volunteer_access_migration.py)、[empty bootstrap](../../../tests/integration/test_empty_database_bootstrap.py) |
| SC-014 | [platform authorization](../../../tests/security/test_volunteer_access_authorization.py)、[platform audit lifecycle](../../../tests/unit/test_platform_scope_audit.py) |
| SC-015 | [1,200-item snapshot/chunks](../../../tests/performance/test_volunteer_access_batch.py)、[browser all-filtered snapshot](../../../apps/web/e2e/volunteer-access-approval.spec.ts) |
