# Implementation Plan：志工角色導向入口與管理路由隔離

**Branch**：`004-volunteer-entry-route-isolation` | **Date**：2026-08-14 | **Spec**：[spec.md](spec.md)

**Input**：`/specs/004-volunteer-entry-route-isolation/spec.md`

## Summary

本功能在既有 Next.js App Router 前端建立共用的登入情境邊界：以後端回傳的目前使用者、Membership 與 Active Shelter Context 推導有效角色，在任何管理頁內容掛載前完成入口判斷。志工完成登入後進入 `/animal-confirmation`；直接開啟管理 route 時也在管理 Shell、Dashboard 與頁面查詢開始前導回志工入口。工作人員、收容所管理者與平台管理員維持既有 `/` 管理首頁。

P0 沿用既有「每位志工、每個 Active Shelter Context 最多一筆 active draft」規則，使用既有目前草稿與動物名單契約，在 `/animal-confirmation` 提供「繼續回報／稍後處理」選擇。功能不新增資料表、不修改 OpenAPI、不改變後端授權或 LINE Bot 狀態機；前端 route guard 僅改善 UX，後端仍是唯一權限與租戶隔離邊界。

## Technical Context

**Language/Version**：TypeScript 5.7、React 19、Next.js 15.1；Python 3.11 後端只執行既有 regression gate，不規劃 Python 功能變更

**Primary Dependencies**：Next.js App Router、React、既有 `authFetch`／sessionStorage auth helper、既有 FastAPI Authentication／Draft／Animal Selection contracts、Playwright、Vitest、`@axe-core/playwright`

**Storage**：不新增儲存；正式 Session、Membership、Active Shelter Context、Animal 與 Draft 沿用 PostgreSQL CRM。sessionStorage 只保存既有 token 與 context 顯示 cache，不作為角色或授權來源

**Testing**：Vitest 2.1、TypeScript typecheck、Prettier、Next production build、Playwright 1.62、axe 4.13；既有 Pytest／Ruff／OpenAPI contract 與租戶隔離測試作回歸門檻

**Target Platform**：Next.js Web／LIFF 輔助介面；約 360px 手機寬度至 1440px 桌面；Chromium browser automation，人工 VoiceOver 補充驗收

**Project Type**：既有 Web application，前端 `apps/web` 搭配既有 FastAPI CRM；本功能主要修改前端 route composition 與測試 fixture

**Performance Goals**：志工管理 deep link 的首次可見內容為安全 loading／redirect 狀態；管理 Dashboard request 數為 0；既有管理使用者不得增加重複的 profile／context 查詢；所有 redirect flow 在有限狀態內終止且不形成 loop

**Constraints**：不修改 API schema、CRM model、後端 authorization、LINE Bot Conversation State Machine、Webhook、LIFF exchange；不以 pathname、query string 或 sessionStorage 擴大權限；P0 不依賴真實 LINE deployment；所有可見提示使用台灣繁體中文

**Scale/Scope**：4 個角色、2 個志工 route、9 類管理 route pattern（目前 12 個代表性 concrete route）、4 個 viewport、登入／deep link／reload／back／session 失效／context 缺少／active draft 等入口狀態

## Constitution Check

_Gate：Phase 0 前檢查；Phase 1 設計後再次檢查。_

| 原則 | Gate 判定 | 設計約束與證據 |
| --- | --- | --- |
| I. CRM 為唯一事實來源 | PASS | 不建立角色、context、draft 或動物資料副本；只組合既有後端回應 |
| II. 原始資料不得被衍生結果取代 | PASS | 草稿恢復沿用既有 Draft；前端不改寫原始答案或心得 |
| III. AI 不負責計算、診斷或最終判定 | PASS | 本功能不涉及 AI 判定 |
| IV. AI 結果必須驗證、標示與追溯 | PASS | 不改變 AI pipeline 或人工覆核邊界 |
| V. 志工回填必須低摩擦 | PASS | 志工登入後直接進入動物確認，並提供單一 active draft 恢復選擇 |
| VI. 歷史紀錄必須完整且可追溯 | PASS | 不修改 Care Report、Timeline 或歷史資料 |
| VII. LINE Bot 只是輸入通道 | PASS | 前端只使用既有後端 Session／Context／Draft contract，不承載授權或新的業務狀態 |
| VIII. 權限、隱私與稽核預設啟用 | PASS | 管理內容掛載前先完成角色 gate；後端 API 仍拒絕未授權存取，redirect 不視為安全邊界 |
| IX. P0 不得依賴 P1 或 P2 | PASS | local Web／LIFF fixture 可完成 P0；真實 LINE 與多筆草稿策略留在 P1 |
| X. 文件語言一致性與 Python 品質門檻 | PASS | 文件以台灣繁體中文撰寫；無 Python 功能變更，完整 regression 仍保留 Pytest／Ruff gate |
| XI. 多收容所資料隔離 | PASS | 有效角色只由 `/auth/me` 與後端驗證的 Active Shelter Context 推導；跨 context draft 不顯示也不恢復 |

**Pre-design gate result**：PASS。沒有需要核准的 Constitution 例外。

## Project Structure

### Documentation（本功能）

```text
specs/004-volunteer-entry-route-isolation/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
└── contracts/
    ├── README.md
    └── route-access.md
```

`tasks.md` 由後續 `$speckit-tasks` 產生，本階段不建立。

### Source Code（repository root）

```text
apps/web/
├── app/
│   ├── (management)/
│   │   ├── layout.tsx                 # 管理 route 在 children 掛載前執行角色 gate
│   │   └── page.tsx                   # 將 `/` 納入同一管理 route group
│   ├── (volunteer)/
│   │   ├── layout.tsx                 # 驗證 Session 與 Active Shelter Context
│   │   ├── animal-confirmation/
│   │   │   ├── page.tsx               # 動物名單與 active draft 恢復提示
│   │   │   └── page.test.tsx
│   │   └── care-report/
│   │       ├── page.tsx               # 沿用目前草稿恢復與保存流程
│   │       └── page.test.tsx
│   ├── login/
│   │   ├── page.tsx                   # context 建立後依 selected organization role 導向
│   │   └── page.test.tsx
│   ├── management-home.tsx            # 只保留 Dashboard content，不自行包第二層 layout
│   └── page.tsx                        # 實作時移除，由 route group page 接管 `/`
├── components/
│   ├── auth/
│   │   └── AuthenticatedRouteBoundary.tsx # 共用 profile/context loader 與安全 redirect state
│   └── management/
│       └── ManagementLayout.tsx        # 消費已驗證情境；允許後才載入 organizations
├── features/
│   └── line-bot/
│       └── ActiveDraftPrompt.tsx       # 單一 active draft 的志工選擇 UI
├── lib/
│   ├── auth.ts                         # 既有 token helper 與共用 auth types
│   └── route-access.ts                 # 純函式角色推導、route decision 與錯誤分類
└── e2e/
    ├── fixtures.ts                     # 可設定 role、context、session 與 draft 的 fixture
    ├── role-route-isolation.spec.ts    # 新增角色入口與 deep-link P0 suite
    ├── login-home.spec.ts
    ├── volunteer-core.spec.ts
    ├── p0-responsive.spec.ts
    ├── p0-keyboard.spec.ts
    ├── p0-a11y.spec.ts
    └── p0-visual.spec.ts

services/api/                         # 不規劃功能變更；只執行既有授權／隔離 regression
packages/contracts/                   # 不修改 generated OpenAPI types
tests/                                # 既有 security／isolation／contract tests
```

**Structure Decision**：維持單一 `apps/web` application，以一個共用 authenticated route boundary 供管理與志工 route group 使用。`/` 移入 `(management)` route group，使 Dashboard child 在角色 gate 通過前不會掛載；`ManagementLayout` 消費同一份已驗證情境，避免 profile／context 重複查詢。純角色與 route decision 放在 `lib/route-access.ts`，以 Vitest 驗證完整矩陣；任何正式授權仍保留在 FastAPI。

## Phase 0：Outline & Research

Phase 0 決策整理於 [research.md](research.md)。已解決的核心問題如下：

1. token 目前在 sessionStorage，Next middleware／Server Component 無法直接使用，因此採「不渲染 children 的 client route boundary」，不在本功能遷移 cookie auth。
2. 登入完成後可使用後端 `organizations[].role` 決定目的地；deep link／reload 則使用 `/auth/me` 加 `/auth/active-shelter-context` 重新推導有效角色。
3. 管理 boundary 先查 profile/context、先判斷角色，再載入 organizations 與管理 children；志工不會發出 Dashboard 或其他管理頁查詢。
4. `/` 必須與其他管理 route 共用同一 layout gate，不能再由會先執行 Dashboard effect 的 page 自行包 layout。
5. 志工 route group 只在有效 Session 與 Active Shelter Context 下掛載 children；管理角色仍可依既有後端權限使用志工輔助流程，但登入預設入口保持 `/`。
6. P0 active draft 使用既有 `/v1/line/care-report/drafts/current` 單一草稿 contract；多筆草稿不是 P0，且不修改既有單一 active draft domain rule。
7. 所有 401、context 缺少、role mismatch、暫時錯誤與 redirecting 都有有限且可觀察的 state；browser back／reload 重新執行相同 gate。

所有 Technical Context 未知事項均已解決；沒有未決設計問題。

## Phase 1：Design & Contracts

### Runtime data design

[data-model.md](data-model.md) 定義前端 runtime view：`AuthenticatedRouteContext`、`EffectiveRole`、`RouteAccessDecision`、`ProtectedRoutePolicy` 與 `ActiveDraftResumeView`。這些不是新的 CRM entity，也不持久化正式業務資料。

### UI／route contract

[contracts/route-access.md](contracts/route-access.md) 定義：

- 登入目的地與有效角色推導規則。
- 管理與志工 route matrix。
- profile/context/management request 的固定順序。
- redirect、loading、session 失效、context 缺少與暫時錯誤的可觀察結果。
- 單一 active draft 的可恢復條件與「繼續／稍後」行為。
- deep link、reload、browser back、360px、keyboard 與 screen reader 驗收。

OpenAPI 不變；contract 文件只描述既有介面組合後的新 UI 行為。

### Validation design

[quickstart.md](quickstart.md) 提供 local fixture、啟動命令、角色 route matrix、草稿恢復、session/context failure、network request assertion、responsive、keyboard、axe、visual 與完整 regression gate。P0 自動化必須加入 `role-route-isolation.spec.ts`，且不得以 UI redirect test 取代後端 security／isolation tests。

## Implementation Sequence

1. 先建立純 `route-access` decision 與 Vitest matrix，固定 role、context、destination、error 的有限狀態。
2. 建立共用 authenticated boundary，完成管理 route group 與 `/` 的掛載順序調整；驗證志工不產生管理 request。
3. 將登入成功目的地改為 role-directed，保留多 context 選擇與平台管理員既有行為。
4. 建立 volunteer route layout，讓動物／草稿查詢只在 Session 與 context 通過後開始。
5. 在 `/animal-confirmation` 組合目前草稿與今日動物名單，加入安全的恢復提示；`/care-report` 保留既有恢復與保存路徑。
6. 擴充 fixture 與 P0 browser matrix，再執行 responsive、keyboard、axe、visual、frontend quality、build 及完整 backend regression。

每一步都必須保持 P0 可獨立展示，不等待 P1 真實 LINE channel 或多筆草稿策略。

## Post-Design Constitution Re-check

| 檢查面向 | 結果 | Phase 1 證據 |
| --- | --- | --- |
| CRM／原始資料／AI 邊界 | PASS | data model 明確是 runtime view；OpenAPI、CRM、AI 與 Draft 業務語意不變 |
| 志工低摩擦 | PASS | 登入後直達動物確認；單一草稿先提示、由志工選擇是否繼續 |
| LINE 通道邊界 | PASS | 只組合既有 Session、Context、current draft contract；沒有前端正式業務狀態 |
| 權限與多租戶 | PASS | route contract 明列前端只縮小可見性；後端 scope、401／403／409 與 isolation tests 保留 |
| P0 獨立性 | PASS | quickstart 以 local fixture 驗收；P1 真實 LINE／多筆草稿均非依賴 |
| 文件與品質門檻 | PASS | 全部設計文件以台灣繁體中文為主；frontend 與 full regression commands 已列入 quickstart |

**Post-design gate result**：PASS。沒有未解決澄清、Constitution violation 或 Complexity Tracking 項目。

## Complexity Tracking

無。設計沿用既有 Next.js application、FastAPI contracts、CRM model 與測試工具；新增的 route boundary 與純 decision module 是避免重複查詢、管理內容先掛載及 redirect loop 所需的最小共用層。
