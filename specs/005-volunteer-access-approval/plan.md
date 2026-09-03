# Implementation Plan：志工報名與限時授權

**Branch**：`005-volunteer-access-approval` | **Date**：2026-08-15 | **Spec**：[spec.md](spec.md)

**Input**：`/specs/005-volunteer-access-approval/spec.md`

## Summary

本功能在既有共用 LINE Official Account／LIFF 與 FastAPI CRM 上建立「收容所專屬入口、LINE 無帳密報名、管理員人工批次審核、organization 可設定預設期限的限時授權」流程。新 organization 在建立 transaction 內同步取得初始 168 小時 policy，管理員可修改 organization policy，也可在單次核准覆寫；停用申請入口只阻止新申請，既有申請人仍可查看 own status。未核准者只有自己的申請狀態，不建立 Organization Membership，也不能取得動物、草稿、回報或管理資料。只有 submit 可原子建立／重用 User + LINE Binding + pending Application，單純 status lookup 不持久化未知 identity。核准後才建立或重新啟用 `VOLUNTEER` Membership，且每次授權都有明確開始與到期時間。

技術上保留每位 user／organization 唯一一筆 Membership 作目前授權投影，另外新增不可覆寫的 Application、Access Grant Cycle、Batch Decision／Item 快照與 Notification Delivery 紀錄。每個受保護 request 都直接檢查 Membership、organization、user 狀態與 UTC 有效期間；背景 Worker 每分鐘收斂自然到期及 organization/user 停用、清除該收容所 Session/context、寫入適用 Audit Log 並處理 LINE 通知，因此安全性不依賴排程準時或使用者再次發出 request。顯式選取最多 500 筆；「目前篩選結果全部」由 server 在確認 transaction 鎖定完整 target snapshot，再以每段最多 500 筆處理。所有批次使用 `operation_id`、逐筆交易與 optimistic version 防止重送及並行覆寫，並提供單一邏輯批次的進度與逐筆結果。

## Technical Context

**Language/Version**：Python 3.12、TypeScript 5.7、React 19、Next.js 15.1

**Primary Dependencies**：FastAPI、Pydantic、SQLAlchemy 2 async、Alembic、asyncpg、既有 LINE identity／Messaging API adapters、Next.js App Router、React、openapi-typescript、Playwright、Vitest、`@axe-core/playwright`

**Storage**：PostgreSQL CRM；新增 tenant-scoped volunteer access tables、Membership 有效期間／版本欄位與通知 outbox。瀏覽器與 LINE client state 不保存正式申請或授權事實

**Testing**：Pytest unit／integration／contract／security／isolation／performance、Ruff、Alembic empty database + upgrade migration、Vitest、TypeScript typecheck、Prettier、Next production build、Playwright responsive／keyboard／axe／visual、generated OpenAPI drift check

**Target Platform**：Linux FastAPI／Worker、PostgreSQL、Next.js Web／LIFF；約 360px 手機至 1440px 桌面；共用 LINE channel 的受控測試環境與 local mock adapter

**Project Type**：既有 Web application，包含 `services/api`、`services/worker`、`apps/web` 與 `packages/contracts`

**Performance Goals**：管理員可在 5 分鐘內完成 100 筆 pending 的篩選、全選、期限設定、確認與結果檢查；至少 1,200 筆全選可建立 100% target snapshot，並以每段最多 500 筆完成且不遺失／重做項目；授權到期、撤銷、organization 停用或 user 停用後任何新 request 立即拒絕，持久狀態與 Session/context 即使沒有後續 request 也於 1 分鐘內收斂；跨租戶資料洩漏率為 0%

**Constraints**：每筆志工授權必須有限期；organization policy 在 organization 建立 transaction 內以 168 小時初始化、可由管理員修改且只影響後續決策，單次核准仍可覆寫；`applications_enabled=false` 只阻止 submit、不隱藏既有 own status；只有 submit 可建立 User/LINE Binding；不得由 AI、entry reference、URL、前端 state 或通知結果決定授權；PLATFORM_ADMIN 必須為每個 target organization request 提供支援原因並在所有 management endpoint 啟用前具備完整 result Audit；LINE 失敗不得回滾 CRM 決策；所有時間以 UTC 儲存、台灣正體中文顯示；既有草稿與回報在失效時保留；P0 可使用 local fixture 獨立驗收

**Scale/Scope**：2 個收容所隔離 fixture、同一 LINE user 跨 organization、100 筆人工流程與至少 1,200 筆全選快照／分段批次、Application／Grant 完整狀態矩陣、PLATFORM_ADMIN／SHELTER_ADMIN／STAFF／VOLUNTEER 四種 actor、LIFF 與管理 Web 兩個操作面、API 與 Worker 兩個執行程序、統一通知失敗清單

## Constitution Check

_Gate：Phase 0 前檢查；Phase 1 設計後再次檢查。_

| 原則 | Gate 判定 | 設計約束與證據 |
| --- | --- | --- |
| I. CRM 為唯一事實來源 | PASS | Application、Membership、Grant、Batch、通知狀態與 Audit 全部寫入同一 PostgreSQL CRM；LIFF 只送驗證資料與動作 |
| II. 原始資料不得被衍生結果取代 | PASS | 到期／撤銷只關閉存取，不刪除或改寫既有草稿、回報、照片與歷史 |
| III. AI 不負責計算、診斷或最終判定 | PASS | 核准／拒絕只能由 SHELTER_ADMIN 或指定單一 organization 並填寫支援原因的 PLATFORM_ADMIN 執行；legacy migration 只限時化既存人工授權，不是新核准 |
| IV. AI 結果必須驗證、標示與追溯 | PASS | 本功能不建立或消費 AI 決策，既有 AI pipeline 不變 |
| V. 志工回填必須低摩擦 | PASS | 正式志工以 LINE 身分和收容所入口報名，不建立或輸入 StrayHub 帳密；只填必要確認 |
| VI. 歷史紀錄必須完整且可追溯 | PASS | 新申請與授權週期 append-only；重新報名／授權不覆寫舊狀態，Audit 記錄前後值 |
| VII. LINE Bot 只是輸入通道 | PASS | LINE id token 由後端驗證；申請、授權、冪等、到期與通知重試均在後端／CRM |
| VIII. 權限、隱私與稽核預設啟用 | PASS | pending 不建 Membership；request-time grant gate、RLS、最小個資、逐筆 Audit、platform support read/write Audit 與通用 404／403 回應預設啟用 |
| IX. P0 不得依賴 P1 或 P2 | PASS | local LINE verifier、mock notification 與 deterministic fixtures 可獨立完成 P0；活動、排班、提醒與獨立 LINE infra 留在 P1 |
| X. 文件語言一致性與 Python 品質門檻 | PASS | 文件以台灣正體中文為主；實作完成需通過 Ruff format/check 與 Pytest |
| XI. 多收容所資料隔離 | PASS | 所有新 business table 帶 `organization_id` 並啟用 FORCE RLS；後端由 actor/context 重新判定 scope，不信任 path 或 entry reference；PLATFORM_ADMIN 不得取得混合清單 |

**Pre-design gate result**：PASS。沒有需要核准的 Constitution 例外。

## Project Structure

### Documentation（本功能）

```text
specs/005-volunteer-access-approval/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
└── contracts/
    ├── README.md
    ├── authorization.md
    └── volunteer-access.openapi.yaml
```

`tasks.md` 由後續 `$speckit-tasks` 產生，本階段不建立。

### Source Code（repository root）

```text
services/api/
├── migrations/versions/
│   ├── 0024_volunteer_access_expand.py      # tables／policy／nullable Membership projection
│   └── 0025_volunteer_access_enforce.py     # policy-aware legacy backfill／constraints
└── app/
    ├── api/
    │   ├── dependencies.py                  # effective grant 與 platform target/reason gate
    │   └── volunteer_access.py              # LIFF 報名、管理審核與授權 API
    ├── application/
    │   ├── organization_management.py       # organization 與初始志工 policy 原子建立
    │   ├── authentication/
    │   │   ├── context_service.py           # context switch 重新驗證限時授權
    │   │   └── line_identity_service.py     # LINE session 只取有效 Membership
    │   ├── volunteer_access_service.py      # 報名、期限與撤銷
    │   ├── volunteer_batch_service.py       # target snapshot 與每段 500 筆 claim
    │   ├── volunteer_expiration_service.py  # 到期／user-org 停用收斂與 scoped session 清理
    │   └── volunteer_notification_service.py# 統一失敗清單／outbox retry
    ├── domain/
    │   └── volunteer_access.py              # 時間、狀態與 decision validation
    ├── infrastructure/line/
    │   ├── messaging_api_adapter.py         # LINE push message
    │   └── mock_adapter.py                  # P0 local deterministic delivery
    └── persistence/
        ├── models/
        │   ├── identity.py                  # Membership 目前有效期投影
        │   └── volunteer_access.py          # Application／Grant／Batch／Notification
        └── repositories/
            ├── authentication_repository.py# effective Membership query
            ├── organization_repository.py  # organization + 初始 policy transaction
            └── volunteer_access_repository.py

services/worker/
├── worker.py                                # BatchItem、每分鐘到期與通知 claim loop
└── app/
    ├── handlers/volunteer_access_handler.py
    └── persistence/volunteer_access_repository.py

apps/web/
├── app/
│   ├── (volunteer-onboarding)/
│   │   └── volunteer-application/page.tsx   # 無 Membership 的 LIFF 報名／狀態頁
│   └── (management)/
│       ├── settings/
│       │   └── volunteer-access/page.tsx    # 入口開關與 organization 預設期限
│       └── volunteers/
│           ├── applications/page.tsx        # 篩選、完整快照全選、批次核准／拒絕
│           ├── access/page.tsx              # 期限調整與撤銷
│           └── notifications/page.tsx       # 統一通知失敗清單／批次重試
├── components/management/AppSidebar.tsx     # 僅管理角色可見志工授權入口
├── features/volunteer-access/
│   ├── VolunteerApplicationPage.tsx
│   ├── ApplicationBatchWorkbench.tsx
│   ├── AccessGrantTable.tsx
│   ├── NotificationFailureQueue.tsx
│   ├── VolunteerAccessPolicyForm.tsx
│   └── volunteerAccess.ts                    # 純狀態／期限／結果 mapping
└── e2e/
    └── volunteer-access-approval.spec.ts

packages/contracts/
└── src/openapi.ts                            # 由 canonical OpenAPI 重新生成

scripts/
├── configure_volunteer_access_policy.py      # staged migration 前的可選 organization policy 設定
├── issue_volunteer_entry_reference.py        # 發行／輪替 organization opaque entry reference
└── seed_local.py                             # pending／active／expired／1,200 筆／跨租戶 fixtures

tests/
├── contract/test_volunteer_access_contract.py
├── integration/test_volunteer_access_*.py
├── isolation/test_volunteer_access_isolation.py
├── performance/test_volunteer_access_batch.py
├── security/test_volunteer_access_authorization.py
└── unit/test_volunteer_access_*.py
```

**Structure Decision**：維持既有四個 workspace 邊界。FastAPI 負責唯一正式狀態、同步 authorization 與 Batch target snapshot；Worker 只 claim CRM 已持久化的 pending BatchItems、到期項目與通知，不建立獨立業務事實。Next.js onboarding route 不使用既有 Membership-protected layout，管理頁沿用 Management Shell；OpenAPI 仍以 `specs/001-volunteer-care-report/contracts/openapi.yaml` 為 canonical source，實作時合併本功能新增 contract 並重新生成 TypeScript。

## Phase 0：Outline & Research

Phase 0 決策整理於 [research.md](research.md)。核心結果如下：

1. 每個 user／organization 維持唯一 Membership；目前 `VOLUNTEER` 有效期間放在 Membership，歷史週期另存 `VolunteerAccessGrant`，兩者在同一交易更新。organization policy 在新 organization 建立 transaction 內以 168 小時初始化，修改後只影響新決策，Batch／Grant 快照實際採用的 policy version 與 duration。
2. 只有既有 active、unbounded VOLUNTEER Membership 於 migration 產生 `legacy_migration` Application／Grant，期限取該 organization 遷移當時 policy，而不是硬編碼 168；disabled／revoked／expired 等非有效 Membership 保持原狀且不建立 synthetic Application／Grant，避免永久權限，也不把 migration 當成新自動核准規則。
3. LIFF onboarding 每次提交 id token 與 opaque `shelter_entry_reference` 給後端；reference 只解析候選 organization，不能建立 Membership。P0 使用可輪替、只存 digest 的 organization entry reference 與 deterministic local fixture，004 使用同一 verifier contract。
4. 同一 LINE user／organization 以 partial unique index 保證最多一筆 pending；只有 submit 可原子建立 User + LineUserBinding + pending Application，status lookup 對未知 identity 不持久化資料，且申請入口停用時既有 applicant 仍可查 own status。
5. 批次審核以 client `operation_id`、Batch／Item 持久化紀錄、逐項 transaction、row lock 與 `expected_version` 保證重送安全。顯式選取最多 500 筆；全選 filter 由 API transaction 建立不限分頁的 target snapshot，Worker 每次 claim 最多 500 個 pending items。
6. request guard 直接判斷 `status == active && valid_from <= now < expires_at` 以及 organization/user active；Worker 或停用 transaction 每 60 秒內把自然到期、organization/user 停用的 Session/context、Audit 與通知收斂，即使沒有後續 request 也不保留可繼續使用的 target context，且不清除其他 organization。
7. 通知採 transactional outbox；CRM 決策先提交，Worker 以 `SKIP LOCKED` 與 idempotency key 推送。所有事件的 failed delivery 進入 organization 統一失敗清單，可篩選並冪等重試單筆／多筆。
8. PLATFORM_ADMIN 角色即平台授權，但每個 volunteer management read/write request 都必須指定單一 organization、提供 `X-Platform-Support-Reason`，並在任何 management story endpoint 開放前完成包含 request result／exception 的 platform-support Audit lifecycle；SHELTER_ADMIN 不需該 header。
9. SC-001 以至少 20 位首次測試志工、SC-002 以至少 3 位收容所管理員執行受控計時驗收；詳細起訖點與成功門檻放在 quickstart，避免只用 API latency 代替人工可用性。

所有 Technical Context 未知事項均已解決；沒有未決設計問題。

## Phase 1：Design & Contracts

### Runtime data design

[data-model.md](data-model.md) 定義 `OrganizationVolunteerAccessPolicy`、可輪替的 `ShelterVolunteerEntryReference`、`VolunteerApplication`、Membership 有效期間投影、`VolunteerAccessGrant`、帶不可變 target snapshot 的 `VolunteerDecisionBatch`／Item、`VolunteerNotificationDelivery`／Retry Batch，以及 `AuditRecord` system actor 擴充，包含 constraints、indexes、狀態轉換、RLS、migration 與 retention 原則。

### API 與 authorization contracts

[contracts/volunteer-access.openapi.yaml](contracts/volunteer-access.openapi.yaml) 定義：

- LIFF 身分＋收容所 reference 的狀態解析、申請與 pending 撤回。
- organization-scoped 申請查詢、顯式選取或全部 filter snapshot、非同步批次進度與逐項結果。
- active／expired／revoked Grant 查詢、期限調整與撤銷。
- access policy 讀寫、統一通知失敗清單與單筆／多筆重試。
- PLATFORM_ADMIN 單一 target organization 與必填支援原因 header／Audit 語意。
- `operation_id`、`expected_version`、UTC date-time、錯誤碼與不洩漏資源存在性的回應。

[contracts/authorization.md](contracts/authorization.md) 定義有效 Membership predicate、不同入口的資料可見性、Session/context 清除、批次 transaction、平台管理 scope、通知 outbox 與 004 整合邊界。實作時把 additive OpenAPI 合併到 canonical contract，再執行 `packages/contracts` generate/check。

### Validation design

[quickstart.md](quickstart.md) 提供 migration、organization policy、entry reference、seed、API／Web／Worker 啟動、local LINE fixture、100 筆人工批次、1,200 筆全選快照／分段處理、並行衝突、到期／撤銷、Session/context、統一通知失敗清單、platform support Audit、跨租戶、SC-001／SC-002 計時、360px、keyboard、axe、visual 與完整 regression gate。

## Implementation Sequence

1. 先將 additive OpenAPI 合併至 canonical contract，執行 schema validation、operation/path count 與 generated contract drift check，讓後續 API 與 Web 實作使用同一契約基線。
2. 建立 domain 時間／狀態規則、organization policy／entry reference、資料模型與 seed fixtures；讓新 organization 與初始 168 小時 policy 原子建立；migration 採 0024 expand → 可選 organization policy 設定 → 0025 policy-aware legacy backfill/enforce，並驗證 RLS 與 `SYSTEM_MIGRATION` Audit。
3. 建立 effective Membership repository/predicate，接入 API request context、Active Shelter Context 與 LINE session resolution；同時完成 PLATFORM_ADMIN 單一 target/reason/result Audit lifecycle，先讓 expired／revoked／disabled user-org 在所有受保護路徑失效。
4. 建立 LIFF application identity flow；status/withdraw 只重用既有 Binding，只有 submit 原子 create/reuse User + LineUserBinding + pending Application，並實作入口停用時阻止新申請但保留既有 own status、pending unique/idempotency。
5. 建立管理查詢與逐筆 decision service，再加入顯式選取／全 filter target snapshot、Batch／Item chunk orchestration、optimistic version、partial success、進度查詢與完整 Audit。
6. 建立期限調整／撤銷、organization-scoped Session/context 清理，以及 Worker 的自然到期與 organization/user 停用 sweep；驗證沒有後續 request 時仍在 60 秒內收斂。
7. 建立 notification outbox、LINE push／mock adapter、Worker retry、organization 統一失敗清單與管理員單筆／多筆 retry；確認通知失敗不回滾正式決策。
8. 依已合併的 canonical OpenAPI 重新生成 TypeScript contract，建立 LIFF onboarding、organization policy、管理批次／授權與通知失敗 UI，並執行 generated contract drift check。
9. 完成 unit、contract、integration、security、isolation、performance、frontend、browser、accessibility、visual、migration 與完整 local verification。

每一步都必須維持 P0 可獨立執行，並保持 004 只消費 effective Membership contract，不反向把入口路由當成授權來源。

## Post-Design Constitution Re-check

| 檢查面向 | 結果 | Phase 1 證據 |
| --- | --- | --- |
| CRM／原始資料／AI 邊界 | PASS | data-model 將所有正式狀態置於 CRM；失效不刪原始照護資料；authorization contract 排除 AI／自動核准 |
| 志工低摩擦與 LINE 通道 | PASS | onboarding contract 只要求 LINE 驗證、收容所確認與送出；LINE adapter 不持有正式狀態 |
| 權限、稽核與多租戶 | PASS | effective predicate、FORCE RLS、actor scope、PLATFORM_ADMIN target/reason/result read-write Audit 在 management endpoint 前置完成、per-item Audit、generic not-found 與 isolation matrix 均有明確 contract |
| 歷史與失敗處理 | PASS | Application／Grant 不覆寫舊週期；全選 snapshot 與通知佇列可中斷續跑；到期或 user/org 停用即使無後續 request 仍於 60 秒清理 target context；草稿／回報保存不受權限失效影響 |
| P0 獨立性 | PASS | quickstart 使用 local verifier、mock messaging、兩收容所、100 筆人工與 1,200 筆全選 fixture，不依賴 P1 排班、提醒或 production LINE rollout |
| 文件與品質門檻 | PASS | 全部設計 artifacts 以台灣正體中文為主，並列出 Ruff、Pytest、contract generation、frontend 與 browser gate |

**Post-design gate result**：PASS。沒有未解決澄清、Constitution violation 或 Complexity Tracking 項目。

## Complexity Tracking

無 Constitution violation。新增歷史 Grant、organization policy／entry reference、Batch／Item snapshot 與 Notification outbox 是規格明訂的歷史追溯、可設定期限、完整全選、部分成功與外部通知失敗隔離所需持久化邊界，不是額外服務或獨立事實來源。
