---
description: "前端 UX 基礎與響應式 UI 遷移的實作任務"
---

# 任務清單：前端體驗一致化與響應式 UI 基礎

**輸入**：設計文件位於 `/specs/003-frontend-ux-foundation/`

**前置文件**：[plan.md](plan.md)、[spec.md](spec.md)、[research.md](research.md)、[data-model.md](data-model.md)、[contracts/ui-behavior.md](contracts/ui-behavior.md)、[quickstart.md](quickstart.md)

**測試**：本功能的 spec／plan／quickstart 明確要求 component、browser、visual、axe、keyboard、VoiceOver 與既有品質門檻證據，因此各階段包含對應驗證任務；不採用必須先寫失敗測試的 TDD 流程。

**組織方式**：任務依使用者故事分組，讓每個故事都能獨立實作與驗收。

## 任務摘要

| 區段 | 任務數 | 交付結果 |
| --- | ---: | --- |
| 設定 | 6 | Tailwind、shadcn、Lucide、Playwright 基礎設定 |
| 基礎建設 | 8 | token、UI primitives、狀態與 icon contract |
| US1 P0 | 10 | 管理工作台 Shell、登入與管理首頁 |
| US2 P0 | 5 | 志工手機動物確認與照護回報 |
| US3 P0 | 8 | 動物、回報與 Timeline 管理核心 |
| US4 P0 | 5 | 跨頁面狀態與回饋一致性 |
| US5 P0 | 9 | responsive、keyboard、screen reader 與 visual regression |
| US6 P1 | 4 | AI Queue、`/shelters` 與設定頁套用共用模式 |
| P0 收尾 | 5 | legacy CSS 收斂、文件、P0 門檻 |
| **Total** | **60** | P0 可獨立交付，P1／P2 後續增量套用 |

---

## 階段 1：設定（共用基礎設施）

**目的**：建立可回滾的 UI migration 起點與必要工具設定。所有使用者故事都依賴本階段完成。

- [X] T001 在 `specs/003-frontend-ux-foundation/quickstart.md` 建立實作前 baseline 記錄，執行現有 `npm --prefix apps/web run quality`、`npm --prefix apps/web run build`，並保存 P0 routes 的 viewport 截圖與既有失敗項目。
- [X] T002 在 `apps/web/package.json` 與 `apps/web/package-lock.json` 安裝 `tailwindcss`、`@tailwindcss/postcss`、`postcss`，確認 npm lockfile 只包含本次 UI foundation 所需變更。
- [X] T003 在 `apps/web/postcss.config.mjs` 設定 Tailwind v4 PostCSS plugin，並在 `apps/web/app/globals.css` 加入 Tailwind import；保留既有 CSS 規則以支援未遷移頁面。
- [X] T004 在 `apps/web/components.json` 初始化 shadcn/ui existing-project 設定，固定 Radix base、CSS variables、`@/*` alias 與 `apps/web/components/ui` 目標，不使用 force overwrite。
- [X] T005 在 `apps/web/package.json` 與 `apps/web/package-lock.json` 加入 `lucide-react`，確認 named import、tree-shaking 與既有 package scripts 可使用；不建立或修改 `apps/web/components/management/icon-map.ts`，該檔案由 T012 統一負責。
- [X] T006 在 `apps/web/package.json`、`apps/web/package-lock.json`、`apps/web/playwright.config.ts`、`apps/web/e2e/tooling-smoke.spec.ts` 與 `apps/web/e2e/README.md` 安裝並驗證 `@playwright/test`、`@axe-core/playwright` 與 Chromium browser binary；新增 `test:e2e:tooling`、`test:e2e`、`test:e2e:list`、`test:e2e:p0`、`test:e2e:p0:list`、`test:visual`、`test:visual:update`、`test:a11y:browser`、`test:a11y:browser:list`、`test:axe`、`test:p1:e2e` 與 `test:p1:a11y` scripts。`tooling-smoke.spec.ts` 必須啟動 Chromium、建立並操作最小 page、成功載入 `AxeBuilder`，並對最小 HTML page 執行一次 axe scan 取得 violations 結果陣列；不得依賴登入、API、seed、P0 route 或 P1 route。執行 `npx playwright install chromium`、`npx playwright --version`、`npm run test:e2e:tooling`，只確認 runner、Chromium 與 axe import 可載入；T006 不執行 P0／P1 route spec、P0 list 或任何 P1 command。P0 list 由 T059 在 P0 specs 建立後驗證，P1 scripts 由 T053 在 P1 specs 建立後獨立驗證。

**檢查點**：Tailwind import、shadcn config、Lucide、Playwright 骨架與 baseline 已可檢查；尚未遷移任何既有頁面。

---

## 階段 2：基礎建設（阻塞性前置條件）

**目的**：建立所有使用者故事共用的 token、primitive、狀態、icon 與測試邊界。此階段完成前不得開始 route migration。

**⚠️ 重要**：使用者故事實作依賴本階段完成。

- [X] T007 在 `apps/web/app/globals.css` 建立 semantic CSS variables，將現有 `--ink`、`--muted`、`--line`、`--surface`、`--accent`、`--warning`、`--danger` 對映至 background、foreground、surface、border、primary、success、warning、destructive、focus、overlay、radius、shadow、typography 與 spacing token。
- [X] T008 在 `apps/web/lib/utils.ts` 建立 shadcn `cn`／class composition helper，並確認 `apps/web/tsconfig.json` 的 `@/*` alias 可解析 `components/ui` 與 `lib`。
- [X] T009 在 `apps/web/components/ui/` 按 P0 清單加入 Button、Card、Badge、Breadcrumb、Field、Label、Input、Select、Textarea、Checkbox、Dialog、AlertDialog、Sheet、Table、Skeleton、Spinner、Alert、Toast、Tooltip、Sidebar、Separator，並檢查 generated source 未引入未批准的完整元件集合。
- [X] T010 在 `apps/web/components/management/ui-status.ts` 定義 `UIStatusState`、status-to-tone／label mapping 與 `aria-live` 規則，涵蓋 loading、canonical `saving`、canonical `success`、empty、no-results、error、permission-denied、processing、`ai-failed` 與 needs-review；`saving` 必須與讀取 `loading` 分開，保留輸入並防止重複提交，成功轉為 `success`、失敗轉為 `error`；AI 狀態使用 polite、只在首次狀態變更或主動重試後播報，且 `ai-failed` 文案必須說明原始回報已保存。
- [X] T011 在 `apps/web/components/management/StateViews.tsx` 與 `apps/web/components/management/StatusBanner.tsx` 建立共用 StatusView／Alert composition，統一 title、description、action、錯誤保留內容與下一步，不讓 error 冒充 empty。
- [X] T012 唯一建立並維護 `apps/web/components/management/icon-map.ts`，完成搜尋、返回、展開、收合、編輯、停用、重試、設定、AI、權限與導覽 icon map；所有 icon-only helper 必須輸出 accessible name 或 Tooltip contract。T005 不得重複修改此檔案，T013 只負責測試。
- [X] T013 在 `apps/web/components/management/ui-status.test.tsx`、`apps/web/components/management/StateViews.test.tsx` 與 `apps/web/components/management/icon-map.test.tsx` 補上 status mapping、`loading`／`saving` 區分、`saving` 的輸入保留／成功／失敗轉換、aria-live（含 AI `processing`／`ai-failed`／`needs-review` 的 polite 與不重複播報規則）、錯誤／空資料區分與 icon accessible name 的 component regression tests。
- [X] T014 在 `specs/003-frontend-ux-foundation/contracts/ui-behavior.md` 與 `specs/003-frontend-ux-foundation/data-model.md` 對照實作結果，補記任何 shadcn CLI 元件名稱、token 命名或 status mapping 的必要偏差，並確認沒有改變 API、權限或資料 entity。

**檢查點**：`components/ui`、token、StatusView、icon map 與 component tests 可獨立使用；既有 routes 仍可依賴 legacy CSS。

---

## 階段 3：使用者故事 1－在管理工作台辨識目前情境並找到下一步（優先級：P0）— 第一個可展示 checkpoint

**目標**：建立桌面與手機都能辨識目前收容所、角色、頁面、導覽與登出的管理工作台 Shell。

**獨立驗收**：使用 `local-staff-a`、`local-shelter-admin-a` 與 `local-platform-admin`，在 360px、768px 與 1024px 開啟管理頁面、切換 ORG-A／ORG-B、使用 mobile Sheet、查看角色導覽並登出；所有資料與操作範圍符合既有授權。

### 使用者故事 1 的測試

- [X] T015 [US1] 擴充 `apps/web/components/management/management-shell.test.tsx`、`apps/web/app/login/page.test.tsx` 與 `apps/web/app/page.test.tsx`，驗證 Header、Sidebar、Breadcrumb、role-filter、active route、context label、登入表單與管理首頁 route composition。
- [X] T016 [US1] 建立 `apps/web/e2e/management-shell.spec.ts`，驗證管理 Shell 在 desktop 與 mobile viewport 的導覽、Active Shelter Context 切換、permission visibility、Sheet close 與 logout smoke flow。

### 登入與管理首頁實作

- [X] T017 [US1] 將 `apps/web/app/login/page.tsx` 遷移至 Field、Input、Select、Button、Alert、StatusView 與 Lucide composition，保留既有登入、Active Shelter Context 選擇、多收容所切換、session storage、redirect、錯誤與重試行為。
- [X] T018 [US1] 將 `apps/web/app/page.tsx` 與 `apps/web/app/management-home.tsx` 遷移至 ManagementLayout、Card、Badge、Table／mobile Card、Button、StatusView 與 Lucide composition，保留 Dashboard query、快速入口、recent reports、權限、租戶 context 與 401 redirect 行為。

### 使用者故事 1 的實作

- [X] T019 [US1] 將 `apps/web/components/management/AppHeader.tsx` 遷移至 Button／Select／Badge／Lucide composition，保留目前收容所、使用者名稱、登出、切換失敗與 `zh-Hant-TW` 文案。
- [X] T020 [P] [US1] 將 `apps/web/components/management/AppSidebar.tsx` 遷移至 Sidebar composition，保留既有 role filter、nested pathname active state、工作台／設定與治理分組與可見中文 label。
- [X] T021 [US1] 在 `apps/web/components/management/MobileNavigation.tsx` 建立手機 Sheet 導覽，提供 menu trigger、focus trap、Escape、close、active route 與 focus restore；不以 `display:none` 取代導覽。
- [X] T022 [US1] 將 `apps/web/components/management/ManagementLayout.tsx` 接入新的 Header、Sidebar、MobileNavigation、StatusView 與 context switch feedback，保留既有 `authFetch`、session expiration、organization scope 與 logout 行為。
- [X] T023 [P] [US1] 將 `apps/web/components/management/Breadcrumbs.tsx` 遷移至 Breadcrumb composition，保留動物、回報與 Timeline 的既有返回路徑與 accessible navigation label。
- [X] T024 [US1] 在 `apps/web/components/management/management-shell.test.tsx` 與 `apps/web/e2e/management-shell.spec.ts` 驗證 US1 的 context switch failure、role visibility、mobile Sheet focus 與登出後不可繼續查看受保護內容。

**檢查點**：Management Shell 可獨立展示與回退；這是第一個可展示 checkpoint，不代表完整 P0；US1 完成不依賴動物、回報或設定頁的新視覺遷移。

---

## 階段 4：使用者故事 2－志工在手機上完成動物確認與照護回報（優先級：P0）

**目標**：以 360px 手機優先遷移動物確認、草稿恢復、照護回報與失敗重試，不遺失原始輸入。

**獨立驗收**：使用 `local-volunteer-a`，以今日名單、QR Code、收容編號找到動物，確認身分、恢復草稿、保存回報，並在 network／save failure 情境下檢查輸入保留、錯誤、重試與 AI 狀態。

### 使用者故事 2 的測試

- [X] T025 [P] [US2] 擴充 `apps/web/app/(volunteer)/animal-confirmation/page.test.tsx` 與 `apps/web/features/animal-selection/AnimalConfirmationCard.test.tsx`，驗證 candidate identity、可回報狀態、確認／重新選擇、錯誤與主要 action label。
- [X] T026 [P] [US2] 擴充 `apps/web/app/(volunteer)/care-report/page.test.tsx` 與 `apps/web/tests/liff_animal_confirmation.test.tsx`，並建立 `apps/web/e2e/volunteer-core.spec.ts`，驗證今日名單、QR Code、收容編號搜尋、重新選擇、草稿恢復、保存失敗保留輸入、重試成功、未授權動物不洩漏資料，以及保存中連續點擊只產生一次提交；同時確認後端回應與 CRM 結果沒有重複回報，前端 pending／disabled 不被視為唯一冪等性保證；若後端冪等性 evidence 失敗，P0 gate 必須標記 blocked，不得以僅有 UI 防線視為通過。

### 使用者故事 2 的實作

- [X] T027 [US2] 將 `apps/web/features/animal-selection/AnimalConfirmationCard.tsx` 遷移至 Card、Badge、Button、Alert 與 Lucide composition，保持動物名稱、收容編號、cage／area、可回報狀態與確認／重新選擇語意。
- [X] T028 [US2] 將 `apps/web/app/(volunteer)/animal-confirmation/page.tsx` 遷移至手機優先 layout，保留今日名單、QR resolve、shelter number search、confirmation token、錯誤／成功回饋與不洩漏未授權資料的行為。
- [X] T029 [US2] 將 `apps/web/app/(volunteer)/care-report/page.tsx` 與 `apps/web/features/line-bot/LiffFallback.tsx` 遷移至 Field／Button／StatusView，保留 draft loading、canonical `saving`、offline save、原始輸入、重試與 AI processing／failure 的非同步語意。

**檢查點**：志工核心流程可獨立在 360px 展示與回退；不依賴管理設定頁或 P1 頁面。

---

## 階段 5：使用者故事 3－工作人員快速找到動物、回報與近期歷程（優先級：P0）

**目標**：遷移管理核心資料頁，統一搜尋、篩選、列表／卡片、Breadcrumb、日期 Timeline 與原始資料閱讀。

**獨立驗收**：使用代表性 ORG-A seed，完成動物搜尋、區域／狀態篩選、回報日期／狀態篩選、回報 detail、動物 profile 與同日多筆 Timeline 展開，確認資料與既有 mapping 完整保留。

### 使用者故事 3 的測試

- [X] T030 [US3] 擴充 `apps/web/app/(management)/animals/page.test.tsx`、`apps/web/app/(management)/reports/page.test.tsx`、`apps/web/app/(management)/reports/[reportId]/page.test.tsx` 與 `apps/web/app/(management)/animals/[animalId]/timeline/page.test.tsx`，驗證搜尋／篩選／返回／資料 mapping 與 route composition，並確認快速變更條件時較舊 request 最後完成也不得覆蓋目前條件。
- [X] T031 [US3] 擴充 `apps/web/features/animal-timeline/AnimalTimeline.test.tsx`、`apps/web/tests/animal_timeline.test.tsx` 與 `apps/web/tests/animal_disambiguation.test.tsx`，驗證同日多筆、當日無回報、snapshot、AI／人工狀態與動物辨識語意。
- [X] T032 [US3] 建立 `apps/web/e2e/management-core.spec.ts`，驗證 `/animals`、`/reports`、`/reports/[reportId]`、`/animals/[animalId]` 與 Timeline 的搜尋、篩選、Breadcrumb、空結果、錯誤與資料閱讀；快速切換兩組條件並刻意讓第一個 request 較晚完成時，只呈現最後一次條件的結果。

### 使用者故事 3 的實作

- [X] T033 [US3] 將 `apps/web/app/(management)/animals/page.tsx` 遷移至 Field、Select、Input、Table／mobile Card、Badge、Pagination Button，保留既有 query、area、status、page、total 與動物／Timeline 深連結。
- [X] T034 [US3] 將 `apps/web/app/(management)/reports/page.tsx` 遷移至日期 Field、Select、Table／mobile Card、Badge、StatusView 與主要 detail action，保留 report status、AI job status、submitted time 與 pagination contract。
- [X] T035 [P] [US3] 將 `apps/web/app/(management)/animals/[animalId]/page.tsx` 與 `apps/web/app/(management)/reports/[reportId]/page.tsx` 遷移至 Card、Badge、Alert、Button 與 Breadcrumb，明確區分原始回報、AI raw／validated／human review 與 mutation feedback。
- [X] T036 [US3] 將 `apps/web/features/animal-timeline/TimelineFilters.tsx` 與 `apps/web/features/animal-timeline/AnimalTimeline.tsx` 遷移至 Field、Button、Card、Collapsible-equivalent interaction 與 Badge，保留日期範圍、同日多筆、snapshot、照片數量、AI／人工狀態與「當日無回報」。
- [X] T037 [US3] 將 `apps/web/app/(management)/animals/[animalId]/timeline/page.tsx` 的 Breadcrumb、date range、loading／error／empty、回到動物檔案與資料載入 feedback 接入共用 UI contract，保留既有 `authFetch` 與 timeline query。

**檢查點**：管理核心查詢與歷程可獨立展示；US3 完成後不應出現資料被合併、舊結果冒充新篩選或歷史 snapshot 被目前名稱覆蓋。

---

## 階段 6：使用者故事 4－在所有核心頁面理解資料與操作狀態（優先級：P0）

**目標**：將 loading、saving、empty、no-results、error、permission、success、AI processing、`ai-failed` 與 needs-review 契約套用到 P0 routes。

**獨立驗收**：以固定 state fixtures 對管理 Shell、志工頁、動物、回報、detail 與 Timeline 注入各狀態，確認文案、tone、live region、保留內容與下一步一致。

### 使用者故事 4 的測試

- [X] T038 [US4] 建立 `apps/web/tests/ui-state-matrix.test.tsx`，以 route × state matrix 驗證 P0 頁面不把 loading／saving／empty／no-results／error／permission 混用，並驗證 saving 與 AI 狀態和原始回報保存分離。
- [X] T039 [US4] 建立 `apps/web/e2e/state-feedback.spec.ts`，驗證 loading delay、canonical saving、empty、no results、network error、permission denied、context failure、save success、AI processing、`ai-failed` 與 needs-review 的畫面回饋與下一步；以 browser assertions 驗證 saving 保留輸入、禁止重複提交、成功／失敗轉換與 `aria-live="polite"` 不重複播報，並驗證 AI 狀態的首次變更／主動重試才播報、背景輪詢不重複播報，以及 `ai-failed` 不被呈現為原始回報保存失敗。
- [X] T040 [US4] 在 `apps/web/app/login/page.tsx`、`apps/web/app/management-home.tsx` 與 `apps/web/components/management/StateViews.tsx` 補齊路由專屬 state contract：登入初始／canonical `saving`／成功／帳密錯誤／無收容所授權／Active Shelter Context 失敗，以及管理首頁 loading／empty recent reports／dashboard error／401 redirect／permission denied；所有狀態提供繁體中文下一步。

### 使用者故事 4 的實作

- [X] T041 [US4] 將 `apps/web/components/management/StateViews.tsx`、`apps/web/components/management/StatusBanner.tsx` 與 P0 page state branches 統一接入 `ui-status.ts` 的 semantic label、tone、action、aria-live 與 retry semantics；`saving` 必須是獨立於 `loading` 的 canonical state，保存失敗時保留輸入並回到可重試的 `error`。
- [X] T042 [US4] 將 `apps/web/features/ai-observation/AIObservationPanel.tsx`、`apps/web/app/(management)/reports/[reportId]/page.tsx` 與 `apps/web/features/animal-timeline/AnimalTimeline.tsx` 的 AI processing／failure／needs-review 呈現統一，確保 AI 失敗不阻止原始回報與人工流程。

**檢查點**：P0 所有主要狀態具備一致的使用者下一步；失敗狀態不再以空資料或成功訊息冒充。

---

## 階段 7：使用者故事 5－在不同裝置與輔助方式下完成核心操作（優先級：P0）

**目標**：完成 360px、768px、1024px、1440px responsive、keyboard、screen reader、focus、reduced motion 與 visual regression 證據。

**獨立驗收**：在固定 P0 route matrix 與四組 viewport 完成 responsive、axe 與 visual 驗收；另在 360x800 mobile navigation 與 1024x768 desktop navigation，以鍵盤完成登入、導覽、搜尋、篩選、動物確認、表單修正與保存、Dialog／Sheet、Timeline 展開、返回與錯誤重試，並以 VoiceOver 完成人工輔助科技檢查。

### 使用者故事 5 的測試

- [X] T043 [P] [US5] 建立 `apps/web/e2e/p0-responsive.spec.ts`，對完整 P0 route matrix 的 `/login`、`/`、`/animals`、`/animals/[animalId]`、`/animals/[animalId]/timeline`、`/reports`、`/reports/[reportId]`、`/animal-confirmation` 與 `/care-report`，使用正確的未登入／管理角色／志工／tenant fixture，逐一在 360x800、768x1024、1024x768、1440x900 執行 horizontal overflow assertion、主要操作可見性與 route-specific state smoke；此測試只可保留失敗時的診斷截圖，不得建立或維護 visual baseline，完整 baseline 由 T048 唯一負責，且不得以部分 route 通過代表完整 P0 responsive coverage。
- [X] T044 [P] [US5] 建立 `apps/web/e2e/p0-keyboard.spec.ts`，使用正確的管理角色／志工／tenant fixture，分別在 360x800 mobile navigation 與 1024x768 desktop navigation 驗證 P0 核心鍵盤流程：登入、管理導覽、搜尋與篩選、動物確認、照護表單修正與保存、開啟回報、Timeline 展開、返回及錯誤重試；同時驗證 Tab order、visible focus、Sheet／Dialog／AlertDialog focus trap、Escape、取消與 focus restore。所有必要操作不得依賴滑鼠或觸控，任一核心流程無法完成時必須阻擋 P0 驗收。
- [X] T045 [P] [US5] 建立並唯一維護 `apps/web/e2e/p0-a11y.spec.ts`，以正確的管理角色／志工／tenant fixture，對七個已登入 P0 routes：`/animals`、`/animals/[animalId]`、`/animals/[animalId]/timeline`、`/reports`、`/reports/[reportId]`、`/animal-confirmation`、`/care-report`，逐一在 360x800、768x1024、1024x768、1440x900 執行 `@axe-core/playwright` scan；對 heading、label、description、error、loading／saving／success status、icon-only control、AI `processing`／`ai-failed`／needs-review live-region、原始回報保存文案與 critical／serious violations 建立阻斷條件。`/login` 與 `/` 由 T047 唯一負責，不得以部分 route 或單一 viewport 通過代表完整 P0 a11y coverage。
- [X] T046 [P] [US5] 建立 `apps/web/e2e/login-home.spec.ts`，專責驗證 `/login` 與 `/` 在 360x800、768x1024、1024x768、1440x900 的未登入 redirect、登入 canonical `saving`／成功／帳密錯誤／無收容所授權、Active Shelter Context 選擇／失敗、管理首頁 dashboard loading／empty／error／permission 狀態與主要入口連結；`/login` 與 `/` 的四 viewport 結果必須獨立記錄，不由 T043 的其他 route coverage 取代。
- [X] T047 [P] [US5] 建立並唯一維護 `apps/web/e2e/login-home-a11y.spec.ts`，使用正確的未登入／管理角色／tenant fixture，對 `/login` 與 `/` 分別在 360x800、768x1024、1024x768、1440x900 執行 `@axe-core/playwright` scan，以及 heading hierarchy、form label／description／error association、aria-live、keyboard focus、登入錯誤與 dashboard state announcement assertions；critical／serious violations 必須阻擋 P0 驗收，不得以部分 route 或單一 viewport 通過代表完整 coverage，且不得修改 T045 所有的檔案或測試案例。
- [X] T048 [P] [US5] 建立 `apps/web/e2e/p0-visual.spec.ts` 與 `apps/web/e2e/p0-visual.spec.ts-snapshots/`，依 `specs/003-frontend-ux-foundation/quickstart.md` 的完整 P0 route matrix，對 `/login`、`/`、`/animals`、`/animals/[animalId]`、`/animals/[animalId]/timeline`、`/reports`、`/reports/[reportId]`、`/animal-confirmation`、`/care-report` 使用正確的未登入／管理角色／志工／tenant fixture，逐一建立 360x800、768x1024、1024x768、1440x900 baseline；每筆 evidence 必須可辨識 route、viewport、role／tenant 與 state fixture，baseline 只可由 reviewer 審核後更新，且只接受已說明的設計差異，不得以部分 route 或 viewport 取代完整 P0 visual coverage。

### 使用者故事 5 的實作

- [X] T049 [US5] 更新 `apps/web/app/globals.css` 與 P0 page composition，實作 mobile base、compact mobile、tablet、desktop、wide desktop 的 token／layout 規則，確保 360px 不產生非必要水平溢出且 touch target 至少 44 CSS px。
- [X] T050 [US5] 更新 `apps/web/components/management/MobileNavigation.tsx`、`apps/web/components/ui/dialog.tsx`、`apps/web/components/ui/alert-dialog.tsx`、`apps/web/components/ui/sheet.tsx` 與 P0 form composition，補齊 focus、Escape、reduced motion、aria-label 與 live region 行為。
- [ ] T051 [US5] 在 `specs/003-frontend-ux-foundation/quickstart.md` 完成 VoiceOver、人工鍵盤、窄螢幕、長中文、放大文字與 Reduce Motion checklist，並記錄 `/login` 與管理首頁無法自動化的驗收項目與結果。

**檢查點**：P0 responsive／a11y／visual evidence 完成；若任何 critical／serious accessibility 或核心 layout regression 存在，不得進入 legacy cleanup。

---

## 階段 8：使用者故事 6－逐步套用一致體驗到次要管理頁面（優先級：P1）

**目標**：在 US5 的 P0 responsive、keyboard、screen reader 與 visual evidence 完成後，將 AI Queue、`/shelters`、觀察詞彙、QR、可回報範圍與稽核頁套用相同 Shell、form、state、dialog、responsive 與 permission contract；可與 P0 收尾平行，不阻塞 P0 門檻。

**獨立驗收**：在 US5 的 P0 responsive、keyboard、screen reader 與 visual evidence 完成後，以收容所管理者、平台管理員、工作人員與不同收容所帳號開啟 `/ai-review`、`/shelters`、各 P1 settings routes，驗證既有資料、權限、Active Shelter Context、租戶隔離、稽核、歷史快照與操作行為不變；P1 可與 P0 收尾平行，未完成不得阻塞 P0 門檻。

### 使用者故事 6 的測試

- [X] T052 [P] [US6] 擴充 `apps/web/app/(management)/ai-review/page.test.tsx`、`apps/web/features/ai-observation/AIObservationPanel.test.tsx` 與 `apps/web/app/(management)/settings/management-settings.test.tsx`，驗證 AI 與管理設定頁的共用狀態、權限與覆核文案。
- [X] T053 [P] [US6] 擴充 `apps/web/features/observation-vocabulary/ObservationAccessibility.test.tsx`、`apps/web/features/observation-vocabulary/ObservationOptionForm.test.tsx`、`apps/web/features/observation-vocabulary/ObservationLifecycleDialog.test.tsx`，並建立 `apps/web/e2e/p1-management.spec.ts` 與 `apps/web/e2e/p1-a11y.spec.ts`，驗證 `/ai-review`、`/shelters` 與 settings 的 browser state、permission、tenant scope、Dialog／form／status／mobile contract 與 axe baseline 不破壞既有詞彙、收容所管理、稽核資料與歷史規則；P1 specs 建立後再執行 `npm --prefix apps/web run test:p1:e2e` 與 `npm --prefix apps/web run test:p1:a11y`，將結果記錄為獨立 P1 evidence，不得納入或阻塞 P0 gate。

### 使用者故事 6 的實作

- [X] T054 [P] [US6] 遷移 `apps/web/app/(management)/ai-review/page.tsx` 與 `apps/web/features/ai-observation/AIObservationPanel.tsx` 至 Table／Card、Badge、Alert、Button、Tooltip 與既有 AI 狀態 mapping，保留人工覆核邊界。
- [X] T055 [P] [US6] 依序遷移 `apps/web/app/(management)/settings/observation-options/page.tsx`、`apps/web/features/observation-vocabulary/`、`apps/web/app/(management)/settings/qr-codes/page.tsx`、`apps/web/app/(management)/settings/reportable-scope/page.tsx`、`apps/web/app/(management)/settings/audit/page.tsx` 與 `apps/web/app/(management)/shelters/page.tsx`，保留歷史 snapshot、audit、role、organization scope、optimistic concurrency 與 destructive confirmation 行為。

**檢查點**：P1 頁面可逐頁套用 P0 foundation，不反向修改 P0 data／permission contract；未完成的 P1 頁面可繼續保留 legacy CSS，P2 仍不在本階段必要範圍。

---

## 階段 9：P0 收尾與跨故事工作

**目的**：在 US1～US5 的 P0 頁面通過獨立驗收後，清理 legacy CSS、更新文件並完成 P0 門檻。US6 的 P1 頁面可在 US5 完成後獨立進行，不得成為本階段或 T060 的前置條件。

- [X] T056 [P] 在 `apps/web/app/globals.css` 與全 repository 以 `rg` 清理已完成遷移且無引用的 `.button`、`.panel`、`.field`、`.badge`、`.state-card`、`.dialog-backdrop`、`.observation-dialog` 與重複 token 宣告；未遷移頁面保留的 class 必須記錄原因。
- [X] T057 [P] 在 `README.md` 補充 Tailwind／shadcn／Lucide 開發規則、P0 responsive viewport、browser test scripts、component source ownership 與不得修改 API／tenant boundary 的 UI migration 注意事項。
- [X] T058 [P] 在 `specs/003-frontend-ux-foundation/quickstart.md`、`specs/003-frontend-ux-foundation/contracts/ui-behavior.md`、`specs/003-frontend-ux-foundation/data-model.md` 與 `specs/003-frontend-ux-foundation/plan.md` 更新實作後的實際 component 名稱、StatusView／Sheet mapping、screen evidence、usability metrics protocol、FR/SC traceability matrix、例外與未完成 P2 範圍。
- [X] T059 在 `apps/web/package.json`、`apps/web/package-lock.json`、`apps/web/playwright.config.ts` 與 `apps/web/e2e/` 確認 `@playwright/test`、`@axe-core/playwright`、Chromium browser binary，以及 P0 tooling scripts 可從根目錄重複執行；只執行 `test:e2e:tooling`、`test:e2e:p0:list` 與 `test:a11y:browser:list`，確認 P0 對應 specs 已建立。T059 不執行、等待或驗證 `test:p1:e2e`／`test:p1:a11y`；P1 script 驗證由 T053 負責。`test:visual:update` 只能在 reviewer 審核後更新 snapshot，並移除未使用的 UI／test dependency。
- [ ] T060 在 `apps/web/`、`specs/003-frontend-ux-foundation/quickstart.md` 與 `specs/003-frontend-ux-foundation/contracts/` 執行並記錄完整 `npm run quality`、`npm run build`、`npm run test:e2e:p0`、`npm run test:visual`、`npm run test:a11y:browser`、`npm run test:axe`、VoiceOver checklist、usability metrics sample／timing evidence、`./scripts/verify_local.sh`、租戶隔離、後端冪等性／CRM 單一提交與 AI failure evidence；若後端冪等性／CRM 單一提交 evidence 失敗，P0 gate 必須標記 blocked，不得宣稱完成；確認所有 P0 success criteria 可追溯，包含 `/login` 與管理首頁。T060 只執行與判定 P0 gate，不執行、等待或引用 P1 tooling／route evidence。

> **目前 P0 gate 狀態：BLOCKED（外部證據與 visual baseline review 未完成）**。前端自動化 quality、build、69 個 P0 functional browser cases、9 個 axe cases、tooling smoke，以及 `./scripts/verify_local.sh` 的 backend／CRM／ORG-A／ORG-B isolation evidence 均通過；visual regression 目前 7/9 route tests 通過，`/` 與 `/reports/report-a` 的 360px baseline drift 待 reviewer 審核且未更新 snapshot。T060 仍需 VoiceOver／人工 checklist 與 SC-001／SC-002 usability sample，並需完成上述 visual baseline review，才能將 P0 gate 標記完成。P1 T052～T055 不屬於此 blocker，也不得成為 P0 依賴。

**最終檢查點**：T060 只需 US1～US5、P0 browser／a11y 門檻與 T056～T059 完成即可執行。P0 可獨立展示、測試、回滾與驗收；US6 的 P1 未完成項目有明確範圍，不得阻止已完成 P0 交付。

---

## 依賴與執行順序

### 階段依賴

- **設定階段（階段 1）**：無前置依賴；T002～T006 依序處理 package、CSS、shadcn、Lucide 與 browser tooling。
- **基礎建設階段（階段 2）**：依賴設定階段完成，阻塞所有使用者故事；T007～T014 建立 token、primitives、state 與 icon contract。
- **US1（階段 3）**：依賴基礎建設階段；是第一個可展示 checkpoint，可獨立展示，但不代表完整 P0。
- **US2（階段 4）**：只依賴基礎建設階段；與 P0-3 管理 Shell 為兄弟工作流，可平行開發。US2 不等待或匯入 ManagementLayout、Header、Sidebar、Breadcrumb；共用 UI primitives、StatusView、Field 與 icon contract 需先由基礎建設階段凍結，避免互相改寫。
- **US3（階段 5）**：依賴基礎建設階段與管理 Shell 的 routing／Breadcrumb contract；可在 US1 檢查點後開始。
- **US4（階段 6）**：依賴 US1～US3 的 P0 route composition，統一跨頁面狀態。
- **US5（階段 7）**：依賴 P0 routes 與 US4 state contract；在所有 P0 layout 穩定後執行 visual／a11y 強化。
- **US6（階段 8）**：依賴 US5；P1 不得成為 P0 完成依賴。
- **P0 收尾（階段 9）**：依賴 US1～US5、P0 browser／a11y 門檻與 P0 route composition；legacy cleanup 不能早於 P0 browser／a11y 門檻。T056～T060 不依賴 US6。
- **US6 P1 完成**：依賴 US5，可與 P0 收尾平行或在 T060 後執行；T052～T055 的完成不屬於 P0 門檻。

### 使用者故事完成順序

1. US1 管理 Shell（第一個可展示 checkpoint）
2. US2 志工手機流程
3. US3 管理核心查詢與 Timeline
4. US4 狀態與回饋一致性
5. US5 responsive／a11y／visual evidence
6. US6 P1 AI 與設定頁（不阻塞 P0 門檻）

### 平行工作機會

- 設定階段完成後，T015～T016 的 US1 tests 可先行；基礎建設階段完成後，P0-3 管理 Shell 與 US2 志工手機流程可從同一個 P0-2 checkpoint 分叉，US2 的 T025～T029 不等待 P0-3；US3 的 T030～T031 仍等待管理 Shell 的 routing／Breadcrumb contract。
- US1 的 T020／T023 可平行，因為分別修改 Sidebar 與 Breadcrumb；T017／T018／T019／T022 仍需依 route、Header／Shell integration 順序完成。
- US2 的兩組 tests 可平行；AnimalConfirmationCard 與 care report presentation 也可在共用 state contract 不變時平行。
- US3 的 T035 可與 T033／T034 平行，但 T036／T037 必須等其資料頁 composition 完成。
- P0 的 responsive、keyboard、管理 Shell、志工核心、管理核心、狀態回饋、login-home、login-home a11y、axe 與 visual browser specs 可在各自檔案中平行撰寫；T045 只寫 `p0-a11y.spec.ts`、T047 只寫 `login-home-a11y.spec.ts`、T026 只寫 `volunteer-core.spec.ts`、T032 只寫 `management-core.spec.ts`，不共用可寫入的檔案。所有 browser tests 共用 `playwright.config.ts`，因此設定完成後再分工。
- US6 的 AI Queue 與 settings／observation-vocabulary 遷移可平行，但不可同時修改同一份 `globals.css` token contract。
- P0 收尾的 T056～T058 可平行；T059／T060 必須等清理與文件更新完成，且不等待 US6。

## 平行執行範例

### 第一個 P0 checkpoint：US1 管理 Shell

```text
T015 apps/web/components/management/management-shell.test.tsx
T016 apps/web/e2e/management-shell.spec.ts
T017 apps/web/app/login/page.tsx
T018 apps/web/app/page.tsx + apps/web/app/management-home.tsx
```

測試與兩個 route implementation 可在基礎建設完成後分工；T019～T024 需依測試與共用 `ui-status.ts` contract 逐步整合。

### US2 志工手機流程

```text
T025 apps/web/app/(volunteer)/animal-confirmation/page.test.tsx
T026 apps/web/app/(volunteer)/care-report/page.test.tsx + apps/web/e2e/volunteer-core.spec.ts
T027 apps/web/features/animal-selection/AnimalConfirmationCard.tsx
```

測試與 confirmation card 可平行準備；T028／T029 在 shared StatusView 與 Field contract 穩定後整合。

US2 與 P0-3 管理 Shell 不共享同一批 route implementation；若需要調整 `globals.css`、token 或共用 primitive，先由負責 foundation 的工作者整合，再由兩條工作流各自驗證，避免以 P0-3 完成作為 US2 的隱性前置條件。

### US3 管理核心

```text
T030 apps/web/app/(management)/animals/page.test.tsx + reports/page.test.tsx
T031 apps/web/features/animal-timeline/AnimalTimeline.test.tsx
T033 apps/web/app/(management)/animals/page.tsx
T034 apps/web/app/(management)/reports/page.tsx
T035 apps/web/app/(management)/animals/[animalId]/page.tsx + reports/[reportId]/page.tsx
```

列表、detail 與 Timeline 可以分工，但共用 table／card、status mapping 與 Breadcrumb contract 不可分叉。

### US5 響應式／無障礙

```text
T043 apps/web/e2e/p0-responsive.spec.ts
T044 apps/web/e2e/p0-keyboard.spec.ts
T045 apps/web/e2e/p0-a11y.spec.ts
T046 apps/web/e2e/login-home.spec.ts
T047 apps/web/e2e/login-home-a11y.spec.ts
T048 apps/web/e2e/p0-visual.spec.ts
```

各組 browser evidence 可平行；T045 與 T047 分別擁有不同的 a11y spec 檔案，T026 與 T032 也各自擁有 volunteer／management spec，不再有平行檔案衝突。T049／T050 的 CSS 與 overlay 修正需根據失敗結果集中整合，避免互相覆蓋。

## 實作策略

### 優先完成第一個 P0 checkpoint

1. 完成階段 1 設定。
2. 完成階段 2 基礎建設，不開始半套 route migration。
3. 完成階段 3 US1 管理 Shell。
4. 停止並用 `quickstart.md` 的 US1 independent test 驗證 desktop、mobile、role、context 與 logout。
5. US1 通過後代表管理 Shell 這個第一個 P0 checkpoint 可展示，不代表完整 P0；完整 P0 仍須完成 US1～US5 與 T060。

### 漸進式交付

1. US1：管理 Shell，可獨立展示。
2. US2：志工手機回報，可獨立驗證草稿與失敗保留。
3. US3：管理核心查詢與 Timeline，可獨立驗證歷史資料閱讀。
4. US4：跨頁面狀態一致性，補齊所有 P0 state matrix。
5. US5：responsive、keyboard、axe、visual 與 VoiceOver 完成後才清理 legacy CSS。
6. US6：P1 頁面依同一 foundation 後續遷移；P2 不在本次任務必要範圍。

### 回滾規則

- 每個階段檢查點以單一可回退 commit 或可獨立回退的變更集合交付。
- 未遷移頁面繼續使用舊版 CSS；不要因新 component 安裝而強迫全站切換。
- 任何資料、權限、tenant、AI 或歷史 snapshot regression 都優先回退該 route 的 presentation change，不回退或修改 CRM／API。
- 只有所有 P0 route 不再引用某個 legacy class 且 evidence 通過後，才刪除該 class。

## 備註

- `[P]` 只標記可在不同檔案、沒有未完成依賴且不會互相覆蓋的任務。
- `[US1]`～`[US6]` 對應 `spec.md` 的六個使用者故事；Setup、Foundational、P0 收尾不使用故事標籤。
- 每個 task 都以 `- [ ] Txxx` 開始，並包含故事標籤（若屬使用者故事）與至少一個明確 repository path。
- 任務只描述實作與驗證，不在本文件中直接修改應用程式碼。
