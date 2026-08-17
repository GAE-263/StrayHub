# Implementation Plan：志工角色導向入口與管理路由隔離

**Branch**：`004-volunteer-entry-route-isolation` | **Date**：2026-08-16 | **Spec**：[spec.md](spec.md)

**Input**：`/specs/004-volunteer-entry-route-isolation/spec.md`

## Summary

本功能完成兩條互相配合的 P0 邊界。正式志工從共用 LIFF App 下的收容所專屬 `/volunteer-entry?entry=…` 進入；前端初始化 LIFF、取得 raw ID token，後端以 005 提供的 opaque entry reference resolver 解析候選 organization，並在同一資料庫交易內驗證 LINE Binding、使用者、收容所及該 organization 的有效限時 `VOLUNTEER` Membership／Grant。全部通過後才建立 Session，且 `SessionRecord.active_organization_id` 同時成為 Active Shelter Context；任一失敗均不留下 Session、Refresh Token 或 context。

登入後入口與受保護 route 使用共用的 authenticated boundary。志工預設進入 `/animal-confirmation`，直接開啟任何 `(management)` route 時在管理 Shell 與 page request 掛載前導回志工入口；工作人員、收容所管理者與平台管理員維持 `/` 管理工作台。志工 route 在 Session/context 驗證完成後才讀取動物與 current draft，並清楚顯示目前收容所。正式 LIFF Session 失效時，以 single-flight recovery 每次失效事件最多重新 exchange 一次；失敗或再次 401 後安全終止，不形成 loop。

P0 沿用 005 的 Membership／Grant、entry reference 與有效期限規則，以及既有 CRM、Draft、LINE Bot 與後端 authorization。除 `LiffExchangeRequest` 新增 `shelter_entry_reference` 外，不新增資料表、不改變其他 API schema，也不建立新的 LINE Bot 狀態機。

## Technical Context

**Language/Version**：TypeScript 5.7、React 19、Next.js 15.1；Python 3.11、FastAPI 0.115+、SQLAlchemy 2.x

**Primary Dependencies**：Next.js App Router、`@line/liff`（新增前端 runtime dependency）、既有 `authFetch`／sessionStorage auth helper、FastAPI、Pydantic、既有 `LineIdentityVerifierPort`／`VolunteerEntryResolverPort`、PostgreSQL RLS、Playwright、Vitest、Pytest、`@axe-core/playwright`

**Storage**：不新增資料表。沿用 PostgreSQL CRM 的 `LineUserBinding`、`OrganizationMembership`、`VolunteerAccessGrant`、`ShelterEntryReference`、`SessionRecord`、`RefreshTokenRecord`、Animal 與 Draft。瀏覽器 sessionStorage 只保存既有 Session token、後端確認後的 context 顯示 cache，以及正式 LIFF 單次恢復所需的 entry reference；不得保存 role、Membership 狀態或期限作為授權來源

**Testing**：Pytest 8.3（unit／integration／contract／security／isolation）、Ruff、OpenAPI generated-type drift；Vitest 2.1、TypeScript typecheck、Prettier、Next production build；Playwright 1.62、axe 4.13、四種 viewport、鍵盤與受控 LINE／LIFF 人工驗收

**Target Platform**：Linux FastAPI API、PostgreSQL、Next.js Web／LIFF；共用 LINE Official Account、Messaging API channel、Webhook 與 LIFF App；約 360px 手機至 1440px 桌面

**Project Type**：既有 Web application，`apps/web` 前端搭配 `services/api` CRM API；本功能同時修改 authentication exchange、前端 route composition 與驗收 fixtures

**Performance Goals**：志工開啟管理 deep link 時管理 page-specific request 數為 0；route decision 不增加重複 profile/context 查詢；LIFF exchange 僅執行一個候選 organization 的 identity/access transaction；每次 Session 失效事件自動 exchange 數不超過 1；所有 redirect/recovery flow 在有限狀態內終止

**Constraints**：entry reference 不是憑證；後端不得信任 pathname、query、sessionStorage、organization id 或 client role；只允許 FR-022 的 LIFF exchange request additive change；不建立／核准／延長／撤銷 Membership；不改 LINE Bot Conversation State Machine、Webhook signature/idempotency、CRM 原始資料與 AI 人工覆核邊界；正式 LIFF 必須使用 raw ID token 而非 decoded profile；所有提示以台灣繁體中文為主

**Scale/Scope**：4 個角色、2 個收容所正式入口、1 個共用 LIFF App、2 個志工主要 route、整個 `(management)` route group、pending／rejected／revoked／expired／future／active-unexpired access matrix、登入／deep link／reload／back／401 recovery／context 缺少／active draft 等狀態

## Constitution Check

_Gate：Phase 0 前檢查；Phase 1 設計後再次檢查。_

| 原則 | Gate 判定 | 設計約束與證據 |
| --- | --- | --- |
| I. CRM 為唯一事實來源 | PASS | entry reference、Binding、Membership、Grant、Session/context 與 Draft 均讀寫既有 CRM；LIFF 與 client cache 不保存正式授權 |
| II. 原始資料不得被衍生結果取代 | PASS | route 與草稿恢復只讀既有原始答案；不覆蓋照護回報 |
| III. AI 不負責計算、診斷或最終判定 | PASS | 本功能不使用 AI 作角色、Membership、context 或入口決策 |
| IV. AI 結果必須驗證、標示與追溯 | PASS | 不改 AI pipeline、結果保存或人工覆核 |
| V. 志工回填必須低摩擦 | PASS | LINE 無帳密 exchange 後直達動物確認；可恢復草稿先提供繼續／稍後選擇 |
| VI. 歷史紀錄必須完整且可追溯 | PASS | 授權失效只阻止存取，不刪 Draft、Report、Media 或歷史資料 |
| VII. LINE Bot 只是輸入通道 | PASS | LINE/LIFF 只提供已驗證 identity 與候選 entry；Session/context 與授權判斷集中在後端 |
| VIII. 權限、隱私與稽核預設啟用 | PASS | exact organization 的有效 Membership/Grant 與 active user/org 全部在 server transaction 驗證；管理 UI guard 不取代 API/RLS |
| IX. P0 不得依賴 P1 或 P2 | PASS | P0 依賴已完成的 005 P0 contract，但不依賴 P1 獨立 LINE infrastructure、多筆草稿或品牌客製 |
| X. 文件語言一致性與 Python 品質門檻 | PASS | 設計文件以台灣繁體中文為主；Python 變更納入 Ruff、Pytest 與完整 regression gate |
| XI. 多收容所資料隔離 | PASS | entry resolver 只產生單一候選 organization，隨即設定 RLS scope；exchange 鎖定 exact Membership/Grant，跨收容所失敗不建立部分 Session/context |

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
    ├── liff-exchange.openapi.yaml
    └── route-access.md
```

`tasks.md` 由後續 `$speckit-tasks` 依本版設計重新產生；本階段不修改 implementation tasks。

### Source Code（repository root）

```text
apps/web/
├── app/
│   ├── (management)/
│   │   ├── layout.tsx                     # children 掛載前執行 management role gate
│   │   └── page.tsx                       # 由 route group 接管 `/`
│   ├── (volunteer)/
│   │   ├── layout.tsx                     # Session/context、LIFF recovery 與 shelter label boundary
│   │   ├── animal-confirmation/page.tsx   # 今日動物與 current draft prompt
│   │   └── care-report/page.tsx            # 沿用既有恢復／保存並顯示 shelter label
│   ├── (volunteer-entry)/
│   │   └── volunteer-entry/page.tsx        # 公開 LIFF bootstrap；只送 raw token + entry reference
│   ├── login/page.tsx                      # local fixture 依 selected organization role 導向
│   ├── management-home.tsx                 # 只保留 Dashboard content
│   └── page.tsx                            # 實作時移除，由 route-group page 接管 `/`
├── components/auth/
│   ├── AuthenticatedRouteBoundary.tsx      # 共用 profile/context loader 與有限 route state
│   └── ProtectedRouteState.tsx             # checking／redirect／error／re-entry 可及狀態
├── features/
│   ├── liff/LiffSessionProvider.tsx        # init、raw ID token、single-flight exchange/recovery
│   └── line-bot/ActiveDraftPrompt.tsx      # current draft 的 continue/later UI
├── lib/
│   ├── auth.ts                             # token/context cache 與 401 event，不保存授權結論
│   ├── liff-session.ts                     # LIFF 狀態、entry reference 與 recovery epoch
│   └── route-access.ts                     # 純函式角色、route 與錯誤 decision
└── e2e/
    ├── fixtures.ts
    ├── liff-route-isolation.spec.ts
    ├── login-home.spec.ts
    ├── volunteer-core.spec.ts
    ├── p0-responsive.spec.ts
    ├── p0-keyboard.spec.ts
    ├── p0-a11y.spec.ts
    └── p0-visual.spec.ts

services/api/app/
├── api/authentication.py                   # LiffExchangeRequest additive field 與 transaction commit
├── application/
│   ├── authentication/session_service.py   # exact organization atomic exchange
│   └── ports/authentication.py              # 既有 entry resolver port
├── infrastructure/line/
│   └── entry_reference_adapter.py           # 使用 005 digest/resolver，解析後立即套用 org scope
└── persistence/repositories/
    └── authentication_repository.py         # 鎖定 effective Membership/Grant 的 exact-org query

packages/contracts/src/openapi.ts            # canonical OpenAPI 更新後重新生成
specs/001-volunteer-care-report/contracts/openapi.yaml
tests/
├── contract/test_authentication_contract.py
├── integration/test_authentication_session.py
├── security/test_liff_exchange_authorization.py
└── isolation/test_liff_entry_isolation.py
```

**Structure Decision**：維持既有 Next.js + FastAPI 單體邊界。005 的 entry reference resolver 與 effective volunteer predicate 是唯一授權依賴；004 只新增 authentication orchestration、LIFF client bootstrap 與 route boundary。`/` 移入 `(management)` route group，讓所有現在與未來管理 route 共用同一 mount-before-check 防護。正式 entry 與已登入 volunteer routes 分開，避免未建立 Session 的 LIFF bootstrap 誤觸動物或管理查詢。

## Phase 0：Outline & Research

Phase 0 決策整理於 [research.md](research.md)，已解決下列問題：

1. 正式入口以 LIFF SDK `init()` 後的 `getIDToken()` 取得 raw token；外部瀏覽器使用 LIFF login flow，不接受 decoded profile 或 URL 中的 id token作正式身分。
2. shelter entry reference 使用 005 的 digest-at-rest resolver，只解析候選 organization；交換 transaction 鎖定 exact `VOLUNTEER` Membership 與 active Grant，拒絕跨租戶與非有效期限。
3. `SessionRecord.active_organization_id` 與 Session／Refresh Token 在同一 commit 建立；失敗 transaction 不得留下任何一項部分狀態。
4. 正式 401 recovery 以單一 recovery epoch 合併並行 401，每個事件最多 exchange 一次；成功後重新載入原 shelter flow，mutation 不自動重播；再次 401 安全終止。
5. access token 仍位於 sessionStorage，因此 route isolation 採不掛載 children 的 client boundary；本功能不擴張為 cookie-auth migration。
6. management role 通過前不取得 organizations、Dashboard 或 page-specific data；`/` 併入 `(management)` route group。
7. current draft 沿用既有單一 draft contract；context 驗證後才讀取，continue/later 不改變 Draft business state。
8. LINE Bot 已確認 context 時沿用既有 dog-first flow；未確認時沿用 requires-LIFF/context 驗證，不新增 Conversation State。
9. local adapter 提供 deterministic token/reference matrix；P0 另在一個共用受控 LINE channel／LIFF App 驗證 ORG-A、ORG-B 與跨收容所拒絕。

所有 Technical Context 未知事項均已解決；沒有 `[NEEDS CLARIFICATION]`。

## Phase 1：Design & Contracts

### Runtime 與 transaction data design

[data-model.md](data-model.md) 定義既有 CRM entity 在 exchange transaction 中的關係，以及前端 runtime 的 `LiffEntryBootstrap`、`AuthenticatedRouteContext`、`RouteAccessDecision`、`LiffRecoveryEpoch` 與 `ActiveDraftResumeView`。這些 runtime view 不建立新的正式資料表。

### API 與 UI contracts

- [contracts/liff-exchange.openapi.yaml](contracts/liff-exchange.openapi.yaml) 定義 `POST /v1/auth/liff/exchange` 唯一 additive request field、既有 response 相容性與安全錯誤族群。
- [contracts/route-access.md](contracts/route-access.md) 定義正式 LIFF bootstrap、atomic exchange、登入目的地、management/volunteer route matrix、request ordering、current draft、single-flight 401 recovery、LINE Bot regression 及 accessibility 行為。
- [contracts/README.md](contracts/README.md) 說明 canonical OpenAPI 合併與 generated type 流程。

### Validation design

[quickstart.md](quickstart.md) 提供 local migration/seed、API/Web 啟動、exchange failure matrix、角色 deep link、management request count、draft、401 recovery、LINE Bot regression、responsive/a11y/visual，以及共用受控 LINE／LIFF 的 ORG-A／ORG-B 驗收。Browser mock 只證明 UI contract，不取代後端 transaction、security、isolation 與受控 LINE 證據。

## Implementation Sequence

1. 先更新 canonical OpenAPI 的 `LiffExchangeRequest`，加入 additive contract/security/isolation tests，重新生成 TypeScript types。
2. 以既有 `VolunteerEntryResolverPort` 串接 005 resolver；新增 exact organization、effective `VOLUNTEER` Membership/Grant lock query。
3. 重構 `exchange_line_identity`，在單一 request transaction 驗證 reference、LINE Binding、user/org、Membership/Grant，最後一起建立 Session/context/Refresh Token；建立全失敗矩陣與零部分狀態 assertion。
4. 新增 `/volunteer-entry` LIFF bootstrap 與 runtime `LIFF_ID` 注入；只把 raw ID token + entry reference 送至 exchange，成功後儲存 Session/context recovery hints 並前往 `/animal-confirmation`。
5. 建立純 `route-access` decision 與共用 authenticated boundary；將 `/` 移入 `(management)`，確保志工不掛載 Management Shell 或發出管理 requests。
6. 調整 local login role-directed destination；建立 volunteer layout，讓 shelter label、animals、draft 與 care-report 只在後端 context 通過後掛載。
7. 加入 single-flight 401 recovery；成功後安全回到原流程，mutation 不重播，失敗／重複 401 顯示「重新進入／回到 LINE」。
8. 組合 current draft prompt，執行 local browser matrix、LINE Bot regression、後端 security/isolation、四 viewport/a11y/visual，再完成受控共用 LINE／LIFF 的兩收容所驗收。

每一步都必須保持後端 authorization 與 RLS 可獨立拒絕越權；不得以 UI redirect 或 LIFF entry reference 取代 server-side Membership 驗證。

## Post-Design Constitution Re-check

| 檢查面向 | 結果 | Phase 1 證據 |
| --- | --- | --- |
| CRM／原始資料／AI 邊界 | PASS | data model 無新業務 store；Session/context、Membership/Grant、Draft 均沿用 CRM；AI 不變 |
| 志工低摩擦 | PASS | 正式 LINE 無帳密 exchange、直達動物確認、current draft continue/later |
| LINE 通道邊界 | PASS | raw LINE token 只送後端驗證；decoded profile/client state 不授權；Bot state machine 不變 |
| 權限與多租戶 | PASS | contract 明列 resolver 最小輸出、exact-org lock、RLS、零部分 Session/context 與後端 regression |
| P0 獨立性 | PASS | 005 P0 是已定義前置 contract；local fixture 與受控共用 LIFF 均可驗收，不依賴 P1 |
| 文件與品質門檻 | PASS | 文件為台灣繁中；quickstart 包含 Ruff、Pytest、frontend quality、OpenAPI drift 與完整驗證 |

**Post-design gate result**：PASS。沒有未解決澄清、Constitution violation 或 Complexity Tracking 項目。

## Complexity Tracking

無。新增 LIFF bootstrap、exchange orchestration 與共用 route boundary，分別對應正式 identity/context 建立、原子授權及 mount-before-check；均沿用既有 application、database 與 port/repository 邊界，沒有新增服務或資料事實來源。
