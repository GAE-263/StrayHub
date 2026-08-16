# Implementation Plan：動物就醫歷史與照護提醒行事曆

**Branch**: `dev/animal_record` | **Date**: 2026-08-15 | **Spec**: [spec.md](./spec.md)

**Input**: `/specs/006-medical-history-reminders/spec.md`

## Summary

在既有多收容所 CRM 中加入簡單的自由文字醫療歷史、單次與週期照護提醒、今日 Agenda、指定日期行事曆及動物整合時間軸。實作沿用 FastAPI／PostgreSQL、Next.js 管理工作台、Media、Audit、RLS 與 OpenAPI 產生流程；週期 occurrence 由後端依收容所時區在查詢時計算，只持久化單次覆寫與人工處理結果，不依賴 Worker 或外部通知。完整醫療資料由單一 capability 保護，志工只取得被指派事項的最小 projection。本功能不提供診斷、處方或藥量計算。

## Technical Context

**Language/Version**: Python 3.11+；TypeScript 5.7；React 19；Next.js 15.1  
**Primary Dependencies**: FastAPI、Pydantic、SQLAlchemy 2 async、asyncpg、Alembic、Python `zoneinfo`、Next.js App Router、既有 UI primitives、openapi-typescript；不新增 calendar／recurrence runtime 套件  
**Storage**: PostgreSQL 作正式 CRM 與稽核資料；既有 private object storage 保存通過清理的 JPEG／PNG／WebP 附件  
**Testing**: Pytest、Ruff、mypy、Vitest、Playwright、axe、OpenAPI drift check、Alembic bootstrap／upgrade  
**Target Platform**: Linux API／Worker、PostgreSQL、現代桌面與行動瀏覽器（360–1440px）；提醒核心不依賴 Worker  
**Project Type**: Monorepo web application（FastAPI API + Next.js web + shared generated contracts）  
**Performance Goals**: 固定 100 隻動物／500 筆 mixed-state occurrence 驗收資料，以單一服務程序與已暖機的本機 PostgreSQL 執行 Agenda server-side 查詢、recurrence projection 及 response serialization；每輪先暖機 5 次，再連續量測 100 次並完整執行 3 輪，每輪 p95 均 MUST ≤ 1 秒。量測不含 migration、seed、程序啟動、網路傳輸或瀏覽器 render；行事曆單次範圍 ≤ 366 日、page ≤ 100；長期 daily series 不逐日全展開  
**Constraints**: CRM 為唯一事實來源；UTC instant + IANA 收容所時區；歷史不可無痕刪除；所有正式資料異動需稽核；修改或結案既有正式資料需 optimistic concurrency，高風險 occurrence action 另需冪等；首次建立以租戶範圍、驗證及唯一約束防止重複或錯誤關聯；跨租戶回應不可洩漏存在性；附件第一階段僅沿用安全圖片 allowlist；不得產生醫療判斷  
**Scale/Scope**: 5 個可獨立驗收 User Stories、4 類角色、7 種醫療歷史類型、6 種提醒類型、6 種週期表示；驗收 fixture 至少 2 個收容所、100 隻動物、500 筆不同狀態 occurrence

## Constitution Check

_Gate：Phase 0 前檢查；Phase 1 後再次檢查。_

| 原則 | 結果 | 本計畫如何符合 |
|---|---|---|
| I. CRM 為唯一事實來源 | PASS | PostgreSQL 保存 series、正式紀錄、單次例外與 action；UI／Worker 不另存正式狀態。 |
| II. 原始資料不得被衍生結果取代 | PASS | 自由文字、體重與操作者輸入原樣保存；Agenda／occurrence 為可重建 projection。 |
| III. AI 不負責計算、診斷或最終判定 | PASS | 不使用 AI，也不計算藥量、判斷漏藥或安全性。 |
| IV. AI 結果必須驗證、標示與追溯 | PASS（不適用） | 本功能沒有 AI 輸出；管理員文字明確標示為人工輸入。 |
| V. 志工回填必須低摩擦 | PASS | 指派頁只顯示單次任務最少資訊，完成可在三個主要步驟內提交。 |
| VI. 歷史紀錄必須完整且可追溯 | PASS | 正式紀錄只封存；所有 before／after、action、actor、時間與來源均可稽核，Timeline 至少涵蓋 14 日。 |
| VII. LINE Bot 只是輸入通道 | PASS（不適用） | 第一階段沒有 LINE 或外部通知依賴。 |
| VIII. 權限、隱私與稽核預設啟用 | PASS | Active Organization context、醫療 capability、最小志工 projection、重要拒絕與 mutation audit。 |
| IX. P0 不得依賴 P1 或 P2 | PASS | 功能 additive；既有志工回報與動物流程不依賴本功能。 |
| X. 文件語言一致性與 Python 品質門檻 | PASS | 規格與介面採台灣正體中文；Python 變更通過 Ruff、mypy、Pytest。 |
| XI. 多收容所資料隔離 | PASS | 所有新 tenant table 顯式帶 organization_id、複合約束、repository predicate 與 FORCE RLS。 |

無需憲章例外。

## Project Structure

### Documentation (this feature)

```text
specs/006-medical-history-reminders/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── README.md
│   ├── authorization.md
│   ├── timeline-and-calendar.md
│   └── medical-care.openapi.yaml
├── checklists/
│   └── requirements.md
└── tasks.md
```

`tasks.md` 已由 `$speckit-tasks` 產生，作為依賴排序的實作清單。

### Source Code (repository root)

下列列出主要模組邊界與代表性檔案；實作階段的完整新增／修改路徑以 [tasks.md](./tasks.md) 為準。

```text
services/api/
├── migrations/versions/
│   └── 0027_medical_history_reminders.py
└── app/
    ├── api/
    │   ├── medical_records.py
    │   ├── care_reminders.py
    │   ├── assigned_care.py
    │   ├── animal_timeline.py              # additive response
    │   └── organization_management.py      # timezone / capability administration
    ├── main.py                             # router registration
    ├── application/
    │   ├── medical_record_service.py
    │   ├── care_reminder_service.py
    │   ├── care_agenda_service.py
    │   ├── assigned_care_service.py
    │   └── timeline_service.py
    ├── domain/
    │   ├── care_recurrence.py
    │   ├── care_reminder_state.py
    │   └── medical_care_access.py
    └── persistence/
        ├── models/
        │   ├── medical_care.py
        │   └── identity.py                 # organization timezone / membership capability
        └── repositories/
            ├── medical_record_repository.py
            ├── care_reminder_repository.py
            └── timeline_repository.py

apps/web/
├── app/(management)/
│   ├── care-calendar/page.tsx
│   └── animals/[animalId]/
│       ├── page.tsx                        # 今日摘要與快速動作
│       └── timeline/page.tsx               # 整合既有時間軸
├── app/(volunteer)/assigned-care/[occurrenceId]/page.tsx
├── components/management/
│   ├── AppSidebar.tsx
│   └── MobileNavigation.tsx
└── features/medical-care/
    ├── api.ts
    ├── types.ts
    ├── mapping.ts
    ├── CareAgenda.tsx
    ├── ReminderFormDialog.tsx
    ├── ReminderActionDialog.tsx
    ├── SeriesScopeDialog.tsx
    ├── MedicalHistoryFormDialog.tsx
    └── AnimalTodaySummary.tsx

packages/contracts/
└── src/openapi.ts                          # 僅由 canonical OpenAPI 重新產生

tests/
├── unit/
│   ├── test_care_recurrence.py
│   └── test_care_reminder_state.py
├── contract/test_medical_care_contract.py
├── integration/
│   ├── test_medical_records.py
│   ├── test_care_reminders.py
│   ├── test_care_agenda.py
│   ├── test_medical_timeline.py
│   └── test_assigned_care.py
├── isolation/test_cross_tenant_resource_matrix.py
└── performance/test_care_agenda_performance.py

apps/web/features/medical-care/
└── *.test.tsx

apps/web/e2e/
├── medical-care.spec.ts
├── p0-responsive.spec.ts
├── p0-keyboard.spec.ts
├── p0-a11y.spec.ts
└── p0-visual.spec.ts

scripts/
└── seed_medical_care.py
```

**Structure Decision**：沿用現有 API → application → domain／repository 分層、Next.js App Router 管理 shell、單一 canonical OpenAPI 與 generated TypeScript contracts。既有 Timeline 以 additive contract 擴充，不建立第二套醫療時間軸；既有 Worker 不新增提醒 materialization job。

## Phase 0：Research 結果

完整決策與替代方案見 [research.md](./research.md)。關鍵結論：

1. `Organization.timezone` 是後端判定今天的權威來源，預設 `Asia/Taipei`；正式 instant 存 UTC。
2. recurrence 以 series + deterministic virtual occurrence 計算；僅持久化覆寫與 action，避免無期限預展開。
3. 新增單一 `medical_care_access` capability；管理員完整管理，授權員工維護紀錄與處理事項，志工只取被指派最小資料。
4. 醫療紀錄使用 current projection + 既有 Audit before／after；不提供 hard delete。
5. 附件沿用已清理的 JPEG／PNG／WebP；任意文件另立規格。
6. Agenda 採 mobile-first 卡片清單；完整歷史整合既有 Timeline；不新增大型行事曆套件。

## Phase 1：Design 產物

- [data-model.md](./data-model.md)：欄位、關聯、索引、狀態機、recurrence identity、RLS 與 migration／backfill。
- [contracts/medical-care.openapi.yaml](./contracts/medical-care.openapi.yaml)：additive HTTP 契約；實作時併入 canonical OpenAPI 後重新產生 TypeScript。
- [contracts/authorization.md](./contracts/authorization.md)：角色／capability／指派資料的可見性與拒絕語意。
- [contracts/timeline-and-calendar.md](./contracts/timeline-and-calendar.md)：Agenda bucket、時區、virtual occurrence 與 Timeline actual／scheduled union。
- [quickstart.md](./quickstart.md)：本機啟動、seed、主要流程、隔離／衝突／時區／效能與 UI 驗收；以固定 100／500 fixture 對授權工作人員執行 SC-003 兩分鐘找齊待辦的真人計時驗收，expected manifest 同時保留內部 occurrence identity 與畫面可見比對欄位；另固定 Playwright 真實 API 的 repo-root、loopback test DB 與 `/healthz` 前置條件，並提供可追溯的驗收紀錄區。

## Implementation Sequence

1. 先合併 feature OpenAPI 至 canonical contract，建立 request／response model 與 generated TypeScript drift gate。
2. 新增 migration：Organization timezone、Membership capability、medical／reminder／association／action tables、constraint、index 與 FORCE RLS；補 backfill 與 A/B isolation fixture。
3. 實作 recurrence、短月份／DST、穩定 occurrence ordinal、狀態轉移與 exact overdue pagination 的 pure domain tests。
4. 實作 repository 與 application transaction：scope、animal active guard、capability、idempotency、version、row lock、Audit、Media association。
5. 實作 medical records、series、Agenda／Calendar、occurrence actions，以及獨立 assigned volunteer API。
6. 以收容所 local day 擴充既有 Timeline，保留舊 `reports` 欄位並新增 actual events／scheduled items／open reminders。
7. 建立 `/care-calendar` agenda-first UI、動物今日摘要、醫療紀錄與提醒 dialogs，統一使用 `apiFetch` 與 generated DTO。
8. 完成 Pytest、RLS、contract、Vitest、Playwright、responsive、keyboard、axe、visual、500 occurrence performance gate，以及 SC-001～SC-004／SC-009 的代表性使用者計時驗收與證據紀錄。

## Post-Design Constitution Check

Phase 1 設計後重新檢查 11 項原則，結果全部 PASS。資料模型為每個 tenant resource 保存 `organization_id` 並要求 FORCE RLS；契約不接受 client organization scope；Agenda 是 projection 而非第二事實來源；人工結果、原始文字、附件及稽核均可追溯；志工 API 與完整醫療 API 分離；核心提醒不依賴 Worker、外部通知或 AI。因此沒有新增 Complexity Tracking 例外。
