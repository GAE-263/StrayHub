# 實作計畫：前端體驗一致化與響應式 UI 基礎

**分支**：`003-frontend-ux-foundation` | **日期**：2026-08-13 | **規格**：[spec.md](spec.md)

**輸入**：功能規格位於 `/specs/003-frontend-ux-foundation/spec.md`

## 摘要

本計畫將 `apps/web` 從目前以單一 `globals.css` 與自訂 class 為主的 UI，逐步遷移至可重用的 Tailwind CSS v4、shadcn/ui 與 Lucide Icons 基礎。遷移採「先建立相容基礎，再逐頁替換」策略：保留現有資料讀寫、路由、權限與租戶範圍，先完成 design tokens、共用元件與 UX 狀態，再依 P0 順序遷移管理 Shell、管理頁面與志工手機流程。

shadcn/ui 元件由 CLI 直接加入專案並由專案擁有其 source code；本計畫只加入 P0 實際需要的元件，不一次安裝完整元件庫。Tailwind 以 CSS variables 與 utility classes 管理視覺 token，Lucide 以具名匯入提供一致且可辨識的操作圖示。既有 class 在所有使用頁面完成遷移並通過回歸後才移除。

## 技術脈絡

**語言／版本**：TypeScript 5.7、React 19、Next.js 15 App Router；維持既有 `apps/web/tsconfig.json` 與 `@/*` alias。

**主要依賴**：Tailwind CSS v4、`@tailwindcss/postcss`、PostCSS、shadcn/ui CLI、Radix primitives（由 shadcn 元件按需帶入）、`lucide-react`、shadcn 產生的 `cn`／variant utilities、`@playwright/test`、`@axe-core/playwright`。

**儲存**：本功能不適用；既有 FastAPI／PostgreSQL CRM、MinIO／GCS 與既有回報草稿／歷程資料完全沿用，不新增資料表或前端業務資料副本。

**測試**：既有 Vitest、TypeScript、Prettier、Next production build；新增 `@playwright/test` browser smoke／visual screenshot 與 `@axe-core/playwright` 無障礙檢查，固定安裝 Chromium browser binary，並以人工鍵盤與 VoiceOver 驗收補足自動化範圍。

**目標平台**：Next.js web application，最低以約 360px 手機寬度驗收，另驗證 768px 平板、1024px 管理桌面與 1440px 寬桌面。

**專案類型**：具備管理工作台與志工手機流程的響應式 web application。

**效能目標**：不增加 P0 頁面的不必要網路請求或資料重取；在代表性本機資料下維持既有載入與查詢體驗，介面狀態可在請求完成或失敗後立即呈現，不以 skeleton 掩蓋錯誤或空資料。

**約束**：不改變 CRM 資料語意、既有路由、API／服務契約、權限與多收容所隔離；P0 不依賴 P1；360px 不得有核心內容的非必要水平捲動；所有使用者文字採台灣繁體中文；既有 CSS 必須以可回滾方式逐頁淘汰。

**規模／範圍**：`apps/web` 的 9 條 P0 routes、共用管理 Shell、共用狀態元件、動物／回報／Timeline／志工核心功能，以及後續 P1 的 AI Queue、`/shelters` 與設定頁；不包含後端或資料模型 migration。

### 交付層級定義

- **P0**：本次必須先完成且可獨立展示、測試與驗收的登入、管理首頁、管理 Shell、志工流程、動物／回報／Timeline 與共用狀態及無障礙 foundation；對應 spec 的 US1～US5。
- **P1**：完成 US5 的 P0 responsive、keyboard、screen reader 與 visual evidence 後即可開始的下一階段路由，包含 AI Queue、`/shelters`、觀察詞彙、QR、可回報範圍與稽核；可與 P0 收尾平行，但不得成為 P0 門檻的依賴。
- **P2**：本計畫未列入 P0／P1 路由的後續改善，例如第二輪資訊密度、偏好設定與依使用數據驅動的視覺細節優化；P2 不得改變既有資料、權限或 AI 邊界。

> 名稱約定：本計畫與 spec 使用同一套分級；US1～US5 的故事優先級與交付層級均為 P0，US6 的故事優先級與交付層級均為 P1。P2 僅代表本次不納入的後續改善；實作順序以本節交付層級、P0 路由矩陣與依賴表為準。

## 憲章檢查

### 研究前門檻

| 原則 | 判定 | 規劃依據 |
| --- | --- | --- |
| I. CRM 為唯一事實來源 | PASS | UI foundation 只消費既有資料，不建立可與 CRM 分離的業務副本。 |
| II. 原始資料不得被衍生結果取代 | PASS | 元件與狀態設計分開呈現原始回報、AI 結果與人工狀態。 |
| III. AI 不負責最終判定 | PASS | AI badge、loading、失敗與覆核狀態只反映流程，不新增自動決策。 |
| IV. AI 結果必須驗證、標示與追溯 | PASS | AIObservationPanel 與回報詳細頁保留來源、狀態與人工覆核區分。 |
| V. 志工回填必須低摩擦 | PASS | P0 先遷移手機回報與草稿恢復，保留輸入並避免不必要操作。 |
| VI. 歷史紀錄必須完整且可追溯 | PASS | Timeline 的同日多筆、無回報與 snapshot 顯示契約不變。 |
| VII. LINE Bot 只是輸入通道 | PASS | 不把 UI state 或元件層改成業務規則；LIFF／fallback 仍透過既有服務。 |
| VIII. 權限、隱私與稽核預設啟用 | PASS | Shell、導覽與頁面只改善已授權資料的可見性，後端仍是隔離邊界。 |
| IX. P0 不得依賴 P1 或 P2 | PASS | Tailwind／shadcn foundation 與 P0 核心流程先完成，P1 頁面只是後續套用。 |
| X. 正體中文與 Python 品質門檻 | PASS | 規劃文件使用台灣正體中文；前端沿用 npm quality，未新增 Python 變更。 |
| XI. 多收容所資料隔離 | PASS | Active Shelter Context、角色過濾與既有資料查詢不改變，並加入跨租戶 UI 回歸驗收。 |

**門檻結果**：PASS。沒有需要以複雜度例外或範圍擴張方式處理的憲章違反。

## 專案結構

### 本功能文件

```text
specs/003-frontend-ux-foundation/
├── plan.md                 # 本文件
├── research.md             # 階段 0 技術決策與替代方案
├── data-model.md           # UI state、context、token 與不變條件
├── quickstart.md           # 本機與瀏覽器驗證指南
├── contracts/
│   ├── README.md
│   └── ui-behavior.md      # UI／互動／可及性契約
└── tasks.md                # 由 $speckit-tasks 產生，不在本次建立
```

### 原始碼（儲存庫根目錄）

```text
apps/web/
├── app/
│   ├── globals.css                    # Tailwind import、CSS variables、過渡期舊版樣式層
│   ├── layout.tsx                     # html lang、全域 UI provider（若需要）
│   ├── (management)/                  # 管理工作台既有 routes
│   └── (volunteer)/                   # 志工手機流程既有 routes
├── components/
│   ├── ui/                            # shadcn/ui 產生且由專案擁有的 primitives
│   └── management/                    # AppHeader、AppSidebar、Layout、StateViews 等組合元件
├── features/
│   ├── animal-selection/
│   ├── animal-timeline/
│   ├── ai-observation/
│   ├── line-bot/
│   ├── shelter-context/
│   └── observation-vocabulary/
├── lib/
│   ├── auth.ts                         # 既有授權與 token boundary，不改業務語意
│   ├── api.ts                          # 既有資料請求 boundary
│   └── utils.ts                        # shadcn `cn` 與 class composition helper
├── tests/                              # 既有 Vitest／mobile／a11y tests
├── e2e/                                # P0／P1 Playwright smoke、keyboard、visual tests
├── playwright.config.ts                # browser viewport、baseURL、screenshot policy
├── components.json                     # shadcn/ui 專案設定
└── postcss.config.mjs                  # Tailwind v4 PostCSS plugin
```

**結構決策**：維持既有單一 `apps/web` Next.js application；新增 `components/ui` 作為 shadcn primitives，保留 `components/management` 與 `features` 作為業務組合層。不得把 API、權限或 CRM domain logic 搬進 UI primitives。

## 階段 0：研究決策

階段 0 產出已整理於 [research.md](research.md)。主要決策如下：

1. 使用 Tailwind CSS v4 的 PostCSS 方式；不建立不必要的 legacy `tailwind.config.ts`。
2. 從 `apps/web` 的既有 Next.js 專案初始化 shadcn/ui，固定使用同一種 primitives base；本計畫採 Radix，並保留既有 `@/*` alias。
3. 以 CSS variables 定義語意 token；頁面不直接散落 brand 色碼、陰影與圓角。
4. 先加入 Button、Card、Badge、Breadcrumb、Field／Label／Input／Select／Textarea、Dialog、AlertDialog、Sheet、Table、Skeleton、Spinner、Alert、Toast、Tooltip、Sidebar、Separator；不加入未被 P0 使用的元件。
5. 重要錯誤與權限狀態使用頁面內 Alert／StateView；Toast 只用於短暫成功或非阻斷提示。
6. Vitest 保留給元件與資料 mapping；Playwright + axe 負責真實瀏覽器、鍵盤、視窗尺寸與視覺回歸；VoiceOver 由人工完成。

## 安裝與設定計畫

以下是實作階段的命令順序；本次只記錄計畫，不執行安裝。

### 1. 建立安全檢查點

```bash
git status --short --branch
npm --prefix apps/web run quality
npm --prefix apps/web run build
```

在安裝前保存目前 quality／build 結果與現有主要頁面截圖，作為回歸基準。若 baseline 已有失敗，先記錄並不得將其歸因於 UI foundation。

### 2. 安裝並驗證 Playwright／axe 瀏覽器工具

在 `apps/web` 安裝可提交至 lockfile 的 browser test 與 axe 依賴，並固定 Chromium 作為本功能的驗收 browser：

```bash
npm --prefix apps/web install --save-dev @playwright/test @axe-core/playwright
cd apps/web
npx playwright install chromium
npx playwright --version
```

在 `apps/web/package.json` 明確新增以下 scripts。P0 gate 只使用 `test:e2e:p0`、`test:visual` 與 `test:a11y:browser` 及其 list／tooling 輔助命令；P1 scripts 雖可在同一輪 tooling setup 中登記，但只供 US6 的獨立驗收使用。`test:e2e` 可涵蓋所有已建立的 browser tests，`test:axe` 只作 P0 axe suite 的可讀別名：

```json
{
  "scripts": {
    "test:e2e": "playwright test",
    "test:e2e:list": "playwright test --list",
    "test:e2e:tooling": "playwright test e2e/tooling-smoke.spec.ts",
    "test:e2e:p0": "playwright test e2e/management-shell.spec.ts e2e/volunteer-core.spec.ts e2e/management-core.spec.ts e2e/state-feedback.spec.ts e2e/login-home.spec.ts e2e/p0-responsive.spec.ts e2e/p0-keyboard.spec.ts",
    "test:e2e:p0:list": "playwright test e2e/management-shell.spec.ts e2e/volunteer-core.spec.ts e2e/management-core.spec.ts e2e/state-feedback.spec.ts e2e/login-home.spec.ts e2e/p0-responsive.spec.ts e2e/p0-keyboard.spec.ts --list",
    "test:visual": "playwright test e2e/p0-visual.spec.ts",
    "test:visual:update": "playwright test e2e/p0-visual.spec.ts --update-snapshots",
    "test:a11y:browser": "playwright test e2e/p0-a11y.spec.ts e2e/login-home-a11y.spec.ts",
    "test:a11y:browser:list": "playwright test e2e/p0-a11y.spec.ts e2e/login-home-a11y.spec.ts --list",
    "test:axe": "npm run test:a11y:browser",
    "test:p1:e2e": "playwright test e2e/p1-management.spec.ts",
    "test:p1:a11y": "playwright test e2e/p1-a11y.spec.ts"
  }
}
```

驗證條件：`package.json` 與 `package-lock.json` 同時包含兩個套件；`package.json` 包含上述 scripts；`playwright.config.ts` 可載入；Chromium binary 可被 Playwright 找到；T006 先以 `test:e2e:tooling` 驗證 runner、Chromium 與 axe import 可載入。`test:e2e:tooling` 只驗證測試工具鏈，不驗證產品流程；其成功不得被解讀為 P0 route 或 accessibility gate 通過。

- **P0 tooling**：待 P0 specs 建立後，由 T059 執行 `test:e2e:tooling`，確認 runner、Chromium 與 axe 工具鏈仍可載入，並執行 `test:e2e:p0:list`、`test:a11y:browser:list` 確認 P0 specs 已完整登記；再由 T060 執行 `test:e2e:p0`、`test:visual`、`test:a11y:browser` 與 `test:axe`。T059／T060 均不得呼叫、等待或引用任何 P1 script 或 route evidence。
- **P1 tooling**：`test:p1:e2e` 與 `test:p1:a11y` 只在 T053 建立 US6 的 P1 specs 後驗證與執行，並以獨立 P1 evidence 記錄。P1 specs 尚未存在時，P1 commands 不得被 T006、T059 或 T060 執行，也不得被列為 P0 setup、P0 list 或 P0 gate 的成功條件。

`test:visual:update` 只能由 reviewer 明確更新 baseline，不得作為 CI gate。CI／本機 workflow 必須重複執行 browser install 或使用已快取且版本一致的 binary。

### 3. 安裝 Tailwind CSS v4 基礎

從 `apps/web` 執行官方 Next.js v4 路徑：

```bash
npm --prefix apps/web install tailwindcss @tailwindcss/postcss postcss
```

新增 `apps/web/postcss.config.mjs`，啟用 `@tailwindcss/postcss`；在 `apps/web/app/globals.css` 以 `@import "tailwindcss";` 啟用 utilities。保留既有 CSS 規則，先將既有 `:root` 色彩對映到語意 token，再逐頁移除 legacy class。

### 4. 初始化 shadcn/ui

在 `apps/web` 內執行既有專案初始化，確認不使用 force overwrite：

```bash
cd apps/web
npx shadcn@latest init --base radix
```

初始化確認事項：

- `components.json` 指向 `components/ui`、`lib/utils.ts` 與既有 `@/*` alias。
- 啟用 CSS variables；將產生的 semantic variables 與 StrayHub token 合併，不覆蓋既有 brand／狀態語意。
- 維持 `zh-Hant-TW`、React 19、Next App Router 與現有 `tsconfig`。
- 不使用 `--force`；若 CLI 企圖覆蓋 `globals.css`，先保留 legacy 規則並人工合併 diff。
- 將 CLI 寫入的 package-lock 變更視為單獨 checkpoint，便於回滾。

### 5. 加入 Lucide 圖示與 P0 元件

```bash
npm --prefix apps/web install lucide-react
cd apps/web
npx shadcn@latest add button card badge breadcrumb input label select textarea checkbox field dialog alert-dialog sheet table skeleton spinner alert toast tooltip sidebar separator
```

實作時應依 CLI 當下 registry 驗證元件名稱；若某元件名稱已由新版 CLI 改名，採其官方等價元件並記錄於 `research.md`／tasks。不要用 `add --all`。

`lucide-react` 的安裝由 T005 負責；`apps/web/components/management/icon-map.ts` 的建立、icon semantic map、icon-only accessible name 與 Tooltip contract 統一由 T012 負責，T005 不修改該檔案，T013 只負責其 regression tests。

### 6. 建立 token 與類別組合規則

- 在 `globals.css` 保留一份語意 token：background、foreground、muted、border、primary、secondary、success、warning、destructive、focus、surface 與 overlay。
- 將 spacing、radius、shadow、typography 以 token 或 utility composition 管理；頁面不得重新定義同名 brand 值。
- `lib/utils.ts` 提供 `cn`，元件 variant 使用 shadcn 產生的 composition pattern；不把業務判斷塞入 primitives。
- 既有 `--ink`、`--muted`、`--line`、`--surface`、`--accent`、`--warning`、`--danger` 先建立對映，確認畫面無明顯跳色後再刪除重複宣告。

## 共用元件盤點與遷移對照

| UI 需求 | 新基礎元件／組合 | 既有來源 | 遷移策略 |
| --- | --- | --- | --- |
| 管理 Shell | `Sidebar`、`Sheet`、`Button`、`Tooltip` | `AppHeader.tsx`、`AppSidebar.tsx`、`ManagementLayout.tsx` | 桌面保留固定導覽；手機以 Sheet 開啟，保留 role filter、active route 與 context 行為。 |
| 頁面階層 | `Breadcrumb`、`Card`、Typography utilities | `Breadcrumbs.tsx`、各頁 `page-heading` | 先遷移 P0 header／breadcrumb，再處理頁內內容。 |
| 主要／次要／危險操作 | `Button` variants、`Button asChild` | `.button`、`.button-secondary`、`.button-danger`、`.button-quiet` | 將動詞與 tone 對映至 variant；危險操作保持明確文字，不只顯示 icon。 |
| 指標與內容區塊 | `Card`、`CardHeader`、`CardContent`、`CardFooter` | `.panel`、`.metric-card`、`.link-card`、`.ai-card` | 先保留 HTML 語意，再替換外觀與間距；不要將所有區塊變成同一種卡片。 |
| 狀態標籤 | `Badge` variants | `.badge`、`.badge-source`、status 文字 | 建立 status mapping；文字與 tone 同時存在，不能只靠顏色。 |
| 表單欄位 | `Field`、`FieldLabel`、`FieldDescription`、`FieldError`、`Input`、`Select`、`Textarea`、`Checkbox` | `.field`、`label`、input/select/textarea、`.form-error` | 先建立欄位錯誤與 `aria-describedby` 規則，再遷移設定與搜尋表單。 |
| 重要確認 | `Dialog`、`AlertDialog` | `.dialog-backdrop`、`.observation-dialog`、Lifecycle／Option Form | 一般編輯用 Dialog；停用、封存、登出等不可逆或高風險操作用 AlertDialog。 |
| 手機側欄／次要操作 | `Sheet` | 小螢幕目前隱藏 `.app-sidebar` | 不再以 `display:none` 移除導覽；提供開啟、關閉、焦點回復與目前頁面標示。 |
| 資料列表 | `Table`；手機用 `Card`／可展開 row | `.table-wrap`、原生 `table` | 桌面保留欄位層級；360px 只呈現主要欄位，次要內容移至 detail／expand。 |
| 載入狀態 | `Skeleton`、`Spinner`、`StatusView` | `LoadingState`、`.loading-dot`、`.metric-card-loading` | 用內容形狀 skeleton 表示等待；長請求仍提供可讀取的 status。 |
| 空資料／錯誤／權限 | `StatusView`、`Alert`、`Button` | `EmptyState`、`ErrorState`、`StatusBanner` | `StatusView` 統一 title、description、action、tone 與 aria-live；不加入 shadcn `Empty`；錯誤不可冒充空資料。 |
| 成功與短暫回饋 | `Toast` + inline `Alert` | `.notice.success`、`.status-banner` | 保存結果、權限與錯誤保留頁內訊息；純成功或非阻斷提示才使用 Toast。 |
| 操作提示 | `Tooltip` | 目前沒有統一 tooltip | 只給 icon-only 或不明顯的次要控制；主要動作仍保留可見文字。 |
| 分隔與資訊密度 | `Separator`、`Tabs`（只在有明確分頁需求時） | border、dashed border、手刻區段 | 不為了套元件而增加互動；優先使用語意標題與 spacing。 |
| 操作圖示 | Lucide named imports | 目前使用文字箭頭或無圖示 | 建立 icon map：導覽、搜尋、返回、展開、編輯、刪除／停用、重新載入、AI、權限；每個圖示需有動詞語意。 |

### 統一狀態與 overlay 對照

- `StatusView` 是 P0／P1 頁面的唯一 app-level state composition，負責 `loading`、`saving`、`empty`、`no-results`、`error`、`permission-denied`、`success`、`processing`、`ai-failed` 與 `needs-review` 的 title、description、action、tone 與 `aria-live`。`saving` 是獨立於讀取 `loading` 的 canonical state。
- `Alert` 是頁內持續性或重要提示的呈現 primitive；`Toast` 只用於短暫成功或非阻斷回饋。既有 `EmptyState`、`ErrorState` 與 `StatusBanner` 透過 `StatusView` adapter 遷移，不另建立平行狀態契約。
- P0 不加入 shadcn `Empty` 元件；「空資料」是 `StatusView` 的 `empty` variant，不是另一套 `Empty` component API。這避免 `Empty`、`EmptyState` 與 `StatusView` 三套語意並存。
- 產品規格中的 **Drawer** 是互動語意；在本計畫中統一由 shadcn `Sheet` 實作手機側向面板。`Dialog` 用於置中編輯／補充內容，`AlertDialog` 用於高風險確認；不得再引入另一個 Drawer primitive。

## 舊版 CSS 遷移策略

### 相容期間

1. 將 Tailwind import 與新的 semantic variables 加入 `globals.css`，保留舊 class，確保未遷移頁面維持原樣。
2. 新元件只在已遷移的頁面使用；不得同一個元素同時依賴新 variant 與舊 class 改同一個視覺屬性，除非該 class 是明確的 transitional alias。
3. 每個頁面完成後，以 `rg` 確認該頁不再依賴 `.button`、`.panel`、`.field`、`.badge`、`.state-card` 等 legacy class，再移除該頁的相容 alias。

### 對照規則

- `.button*` → `Button` variant；`Link` 透過 `Button asChild` 保留導覽語意。
- `.panel`／`.metric-card`／`.link-card`／`.ai-card` → `Card` 的不同 composition，不建立一個過度通用的 `Panel` 巨型元件。
- `.field` → `Field` composition；每個欄位保留 label、description、error 與 disabled/pending 語意。
- `.badge`／原始 status → domain-to-UI status mapping；禁止直接把後端 wire value 當成使用者主要文字。
- `.state-card`／`.notice`／`.status-banner` → `StatusView`、`Alert` 或 `Toast`，依 persistent／transient 行為決定。
- `.dialog-backdrop`／`.observation-dialog` → `Dialog`／`AlertDialog`；保留 trigger、focus restore、取消與錯誤狀態。
- `.app-sidebar` → desktop `Sidebar` + mobile `Sheet`；角色過濾與 active route 邏輯維持在 management composition 層。

### 移除門檻

只有在下列條件全部通過後，才可刪除 legacy declarations：

- P0 頁面與共用 components 的搜尋結果不再依賴該 class。
- P0 mobile／keyboard／visual screenshots 通過。
- `npm --prefix apps/web run quality`、typecheck、build 通過。
- 沒有回歸到既有管理、志工、AI fallback 或租戶隔離測試。
- PR 內列出移除的 class 與對應新元件，便於回溯。

## P0 遷移順序與回滾檢查點

| 階段 | 依賴 | 內容 | 驗證證據 | 回滾方式 |
| --- | --- | --- | --- | --- |
| P0-0 基準 | 無 | 保存 quality/build、截圖、舊版 class 清單、P0 路由 smoke 結果。 | 基準報告、截圖、`git diff --check`。 | 不改 runtime；刪除僅新增的紀錄。 |
| P0-1 工具／tokens | P0-0 | Tailwind v4、PostCSS、shadcn config、Lucide、CSS variables、`cn`；保留舊版 CSS。 | typecheck、build、首頁與 login 截圖不變。 | 回退 package／lock、`postcss.config.mjs`、`components.json` 與 token diff。 |
| P0-2 基礎元件／狀態契約 | P0-1 | 加入選定 shadcn primitives、共用 status／button／field composition；先以 isolated tests 驗證。 | component tests、keyboard semantics、axe component smoke。 | 不切換既有頁面；移除新增 primitives 或保留未使用 source。 |
| P0-3 Management Shell | P0-2 | 遷移 Header、Sidebar、mobile Sheet、Breadcrumb、ManagementLayout、StateViews、StatusBanner。 | role matrix、context switch、logout、360／768／1024 screenshots、keyboard focus。 | 逐檔回退 Shell composition；legacy class 仍保留作 fallback。 |
| P0-4 Management core | P0-3 | 依序遷移 `/`、`/animals`、`/reports`、`/reports/[reportId]`、`/animals/[animalId]`、Timeline。 | search/filter、empty/error/loading／saving、same-day reports、AI status、visual／a11y。 | 一次只回退一個 route；不刪除資料請求與 mapping。 |
| P0-5 Volunteer mobile | P0-2 | 遷移 `/animal-confirmation`、`/care-report`、AnimalConfirmationCard、LiffFallback；優先 360px。可與 P0-3 管理 Shell 平行；只依賴 P0-2 的共用 primitives、StatusView、Field 與 icon contract。 | draft resume、save failure、wrong tenant、touch、keyboard、VoiceOver。 | 回退志工頁 presentation；保留既有 draft／save flow。 |
| P0-6 P0 強化 | P0-4、P0-5 | 移除已無引用的 legacy declarations，補齊 visual baseline、a11y、品質門檻與文件。 | full frontend quality、build、browser suite、manual sign-off。 | 按 class 或 route 小批次回退，不做全量 reset。 |

P0-3 管理 Shell 與 P0-5 志工手機流程是從 P0-2 分叉的兩條平行工作流；US2 不得匯入 `ManagementLayout`、管理導覽或等待管理 Shell 完成。兩者只在 P0-6 收尾時共同接受 P0 browser／responsive／keyboard／screen reader／visual evidence；P0-4 管理核心仍依賴 P0-3，P0-6 則依賴 P0-4 與 P0-5 都完成。

P1（AI Queue、`/shelters`、觀察詞彙、QR、可回報範圍、稽核）在 US5 的 P0 browser／responsive／keyboard／screen reader／visual evidence 完成後即可依同一遷移對照表逐頁處理；可與 P0-6 收尾平行，不得反向成為 P0 門檻的依賴。P1 的證據可獨立累積，但不會改變 P0 門檻的必要條件。

## 響應式規則

| 模式 | 寬度 | Layout／導覽 | 資訊與操作規則 |
| --- | --- | --- | --- |
| Mobile base | 360px 起 | 單欄；Header 保留品牌、目前情境與 menu trigger；Sidebar 改用 Sheet。 | 主要動作靠近內容；touch target 至少 44 CSS px；表格改卡片／展開 row；不依賴 hover。 |
| Compact mobile | 480–639px | 維持單欄；表單與 filter 垂直堆疊；次要操作進入 Sheet／Dropdown。 | 長標籤可換行；錯誤與 success 保持在相關表單附近；保留可返回位置。 |
| Tablet | 768px | 可用兩欄內容；導覽可保留窄版或由產品選擇是否固定；Header 不得因 context selector 溢出。 | 資料表只在足夠寬度顯示次要欄位；filter 可分兩行，不能壓縮欄位到不可讀。 |
| Desktop | 1024px | 固定 Sidebar + main content；Header、Breadcrumb、page heading 層級固定。 | 管理操作完整呈現；Card／Table 有明確內容寬度與最大閱讀寬度。 |
| Wide desktop | 1280–1440px | 保留內容 max width，避免資料與操作過度分散。 | 可並列摘要、結果與次要資訊，但不增加不必要的裝飾或空白。 |

跨所有模式：核心內容不得被截斷或覆蓋；頁面放大文字、長中文名稱、長錯誤與大量 filter 仍要有可操作的替代呈現；狀態文字與 icon 必須同時支援視覺與輔助科技閱讀。

## 無障礙與互動測試策略

### 自動化

- 保留現有 Vitest component／mapping tests，補測 Button variants、Badge status mapping、StatusView state branches、Dialog focus semantics 與 mobile navigation state。
- 新增 Playwright browser tests：Tab order、Sheet open/close、Dialog／AlertDialog focus restore、form error association、loading／saving／empty／error／permission／AI state；保存失敗時驗證輸入保留與可重試。
- AI `processing`、`ai-failed` 與 `needs-review` 必須各自驗證 `aria-live="polite"`、僅在首次狀態變更或使用者主動重試後播報、背景輪詢不重複播報，以及 `ai-failed` 明確說明原始回報已保存。
- `p0-a11y.spec.ts` 只負責已登入的核心 P0 routes；`login-home-a11y.spec.ts` 只負責 `/login` 與 `/`。兩個檔案各自有單一 task owner，避免 T045／T047 同時修改同一檔案。
- 以 `@axe-core/playwright` 對兩組 P0 a11y specs 執行 automated scan；critical／serious issues 直接阻擋驗收。
- 每個 P0 viewport 執行 `toHaveScreenshot` 或等價 visual baseline；差異必須由 reviewer 判定是預期設計變更或 regression。
- 加入 overflow assertion：核心 viewport 下 `scrollWidth` 不得因非必要 layout 產生水平溢出；必要的資料閱讀捲動需在契約中明確標示。

### 人工驗收

- 鍵盤：從頁面入口開始，完成導覽、搜尋、篩選、動物確認、表單錯誤修正、保存、Dialog 確認與返回。
- VoiceOver：驗證標題階層、目前收容所、導覽目前項目、欄位 label／description／error、status live region、展開／收合與 icon-only label。
- Reduced motion：啟用系統減少動態設定，確認 loading、Sheet、Dialog 與成功回饋不依賴動畫理解。
- 觸控：360px 真機或等價瀏覽器模擬，確認主要控制可點擊、危險操作不易誤觸、沒有 hover-only action。

## API、權限、租戶與資料保護

- 不新增 API endpoint、不修改既有 response shape、不將 UI token 或 component state 寫入 CRM。
- `authFetch`、Active Shelter Context、現有登入／登出與 organization scope 是唯一資料請求 boundary；UI 不接受 URL、sessionStorage 或 query string 作為授權真相。
- `saving` 的 pending／disabled UI 只負責降低重複操作，不是資料一致性的唯一保證；既有後端服務的冪等性或唯一性保護仍是重複提交的正式防線。P0 evidence 必須同時記錄前端操作結果與 CRM 資料結果。
- Shell 只過濾可見導覽與操作，後端仍必須執行真正的授權與租戶隔離；所有 A／B 收容所 regression 以相同 stable id／shelter number 情境驗證。
- `StatusView` 與 `Badge` 的 status mapping 只負責顯示，不改變 backend wire value、資料狀態或 AI 決策。
- 動物 Timeline 與報告 detail 只重排既有資料，不合併同日多筆、不以目前名稱覆蓋歷史 snapshot、不丟失原始心得／照片／人工修正。
- 志工 draft／save flow 先以既有 service 行為為基準，presentation migration 不得清除草稿或改變送出重試語意。
- 登出、權限錯誤、context switch failure 與 session expiration 必須清除或阻止繼續查看受保護內容的 UI 狀態。

## 驗證與驗收證據

### P0 收尾必要命令（T059／T060；不含 P1 tooling）

```bash
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run test:mobile
npm --prefix apps/web run test:a11y
npm --prefix apps/web run format:check
npm --prefix apps/web run build
npm --prefix apps/web exec -- playwright --version
npm --prefix apps/web run test:e2e:tooling
npm --prefix apps/web run test:e2e:p0:list
npm --prefix apps/web run test:a11y:browser:list
npm --prefix apps/web run test:e2e:p0
npm --prefix apps/web run test:visual
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:axe
git diff --check
```

P1 的 `test:p1:e2e` 與 `test:p1:a11y` 不列入上述命令，也不列入 P0 gate。它們只在 T053 建立 P1 specs 後由 US6 自己驗證，P1 結果另存於 P1 evidence；P1 tooling 或 P1 route 失敗不得改寫 P0 gate 結果。

### P0 gate 判定

- 照護回報的 P0 evidence 必須同時證明前端重複操作受到控制，以及後端冪等性／唯一性保護與 CRM 實際資料結果沒有重複回報。
- 若後端冪等性／唯一性驗證或 CRM 單一提交 evidence 失敗，P0 gate 必須標記為 `blocked`，不得宣稱 P0 完成，也不得以前端 pending／disabled、UI 測試或視覺證據替代。
- 此 gate failure 不授權本功能修改後端；應保留失敗證據並將後端缺口列為獨立 blocker，待既有後端服務補足可驗證保護後重新執行 P0 gate。

### 瀏覽器證據

- P0 route matrix：login、management home、animals、animal profile、timeline、reports、report detail、animal confirmation、care report。
- Viewports：360x800、768x1024、1024x768、1440x900。
- Roles：local volunteer、local staff、shelter admin、platform admin；至少包含 ORG-A／ORG-B 隔離案例。
- States：loading、saving、success、empty、no results、error、permission denied、context switch failure、AI processing、`ai-failed`、needs review、draft save failure。
- Evidence：Playwright result、screenshots、axe summary、keyboard checklist、VoiceOver checklist、既有 Vitest／typecheck／build output。
- P1 路由矩陣（不屬於 P0 門檻）：`/ai-review`、`/shelters`、`/settings/observation-options`、`/settings/qr-codes`、`/settings/reportable-scope`、`/settings/audit`；P1 可在 US5 P0 evidence 完成後執行 `test:p1:e2e`／`test:p1:a11y`，並沿用相同的 role、tenant、state 與 accessibility evidence 格式。

### 驗收對照

| Spec outcome | Evidence |
| --- | --- |
| SC-001／SC-002 task speed | 依下方 usability metrics protocol 執行，保存每位測試者的角色、任務、起訖時間、完成／失敗與協助紀錄；不以 unit test 取代使用者測試。 |
| SC-003 responsive readability | 四種 viewport screenshot、overflow assertion、人工窄螢幕檢查。 |
| SC-004 keyboard completion | Playwright keyboard flow + manual checklist。 |
| SC-005 state consistency | P0 route × state fixture matrix 與 component tests。 |
| SC-006 accessibility | axe report、VoiceOver checklist、focus／label assertions。 |
| SC-007 data／permission regression | existing frontend tests、local seed、A／B tenant smoke 與 API response comparison。 |
| SC-008 P0 independence | P0 quickstart 不啟用 P1 route 也能完成。 |
| SC-009 支援基準 | 先建立改版前基準，再於發布後 30 天比較；此為發布後 KPI，不阻塞 P0 實作門檻。 |

## 可用性指標執行規範

本 protocol 用於讓 SC-001／SC-002 可重複驗證；若樣本、資料或錄製條件不足，結果必須標記為 preliminary，不得宣稱達成。

### 參與者與測試設定

- 志工組至少 10 位代表性測試者；工作人員組至少 10 位代表性測試者。每組至少 9 位在門檻內完成，才可判定達到 90%。
- 使用固定的 local seed、固定瀏覽器與 network profile；志工使用 `local-volunteer-a` 類型帳號，工作人員使用 `local-staff-a` 類型帳號，管理入口案例固定在 ORG-A。
- 測試前清除前一次草稿、session 與 route state；測試者不得取得操作教學，只能閱讀頁面提供的文字。若提供協助，該次標記為 assisted，不列入成功分母，但保留於原始紀錄。
- 每次測試保存 participant code（不保存不必要個資）、role、viewport、開始／結束 timestamp、是否完成、錯誤次數、是否協助與備註；證據放在不提交個資的本機或受控驗收位置。

### 任務腳本與計時規則

| 指標 | 任務腳本 | 起始點 | 完成點 | 通過門檻 |
| --- | --- | --- | --- | --- |
| SC-001 | 從 `/animal-confirmation` 找到指定動物，確認身分，進入 `/care-report`，填寫基本照護回報並保存 | 目標 route 已可操作且測試資料已載入 | 看見原始回報已保存的明確成功狀態；AI processing 不影響保存成功判定 | 每位未受協助志工 ≤ 90 秒；每組至少 9/10 通過 |
| SC-002 | 從管理首頁找到指定動物、回報詳細頁或近期 Timeline | 管理首頁主要內容已載入且指定目標已給定 | 開啟正確 detail／Timeline，且頁面中的動物或回報識別資訊與目標一致 | 每位未受協助工作人員 ≤ 30 秒；每組至少 9/10 通過 |

計時以螢幕錄影或測試主持人時間戳為準；不得把登入、seed 載入、測試環境故障或主持人協助時間混入任務時間。另以相同資料執行保存失敗、network error 與 permission denied 情境，這些情境驗證 SC-005／SC-007，不以成功速度取代資料保存與權限驗收。

### 報告與基準

- T058 建立 protocol、FR/SC traceability matrix 與 evidence index；T060 記錄 P0 門檻是否具備足夠證據。
- 若實際參與者少於每組 10 人、測試資料不完整或無法取得可靠起訖時間，報告必須列出缺口、實際樣本與 preliminary 結果，並建立後續補測任務。
- SC-009 另以改版前 30 日與發布後 30 日的支援回報分類比較，不與 SC-001／SC-002 的任務速度樣本混用。

## FR／SC 追溯矩陣

下表把 spec 的每一個 FR／SC 對應到實作、state、browser、a11y 或資料保護任務。任務未在文字中重複 FR ID 時，以下為計畫層的明確追溯關係。

| Requirement | 範圍 | 主要任務／證據 |
| --- | --- | --- |
| FR-001 | P0 | T019、T022、T024 |
| FR-002 | P0 | T019、T022 |
| FR-003 | P0/P1 | T019、T020、T022、T024、T028、T055 |
| FR-004 | P0 | T019、T022、T024 |
| FR-005 | P0 | T020、T021、T022、T044、T050 |
| FR-006 | P0 | T019～T024 |
| FR-007 | P0 | T025、T027、T028 |
| FR-008 | P0 | T025、T027、T028 |
| FR-009 | P0 | T026、T029 |
| FR-010 | P0 | T029、T042 |
| FR-011 | P0 | T028、T029 |
| FR-012 | P0 | T026、T029、T060 |
| FR-013 | P0 | T030、T032～T034 |
| FR-014 | P0 | T010、T011、T038～T041 |
| FR-015 | P0 | T030、T032～T037 |
| FR-016 | P0 | T031、T036、T037、T042 |
| FR-017 | P0 | T031、T036、T037 |
| FR-018 | P0 | T030、T032～T037 |
| FR-019 | P0 | T010、T011、T038～T041 |
| FR-020 | P0 | T010、T011、T038、T041 |
| FR-021 | P0 | T011、T033、T034、T038、T041 |
| FR-022 | P0 | T010、T011、T041 |
| FR-023 | P0 | T011、T026、T029、T041 |
| FR-024 | P0 | T010～T013、T041 |
| FR-025 | P0 | T010、T013、T029、T039、T041、T042；涵蓋 canonical `saving` mapping、component／browser state transition、輸入保留、防重複提交、`success`／`error` 轉換與 AI 狀態分離 |
| FR-026 | P0 | T043、T049、T051 |
| FR-027 | P0 | T043、T049 |
| FR-028 | P0 | T033、T034、T036、T049 |
| FR-029 | P0 | T049、T050 |
| FR-030 | P0 | T049、T051 |
| FR-031 | P0 | T036、T049、T050 |
| FR-032 | P0 | T013、T025、T026、T045、T047 |
| FR-033 | P0 | T044、T049、T050 |
| FR-034 | P0 | T044、T050；Drawer 語意由 Sheet 實作驗證 |
| FR-035 | P0/P1 | T010、T013、T042、T045、T047 |
| FR-036 | P0/P1 | T012、T044、T045、T047 |
| FR-037 | P0 | T050、T051 |
| FR-038 | P0/P1 | T014、T024、T029、T037、T042、T055、T060 |
| FR-039 | P0/P1 | T026、T029、T035、T042、T055、T060 |
| FR-040 | P0/P1 | T020、T022、T024、T028、T042、T054、T055 |
| FR-041 | P0/P1 | T022、T024、T028、T029、T055、T060 |
| FR-042 | P0/P1 | T023、T032～T037 |
| FR-043 | P0 | T035、T036、T042、T060 |
| FR-044 | P1 | T053、T055 |
| SC-001 | P0 | T025～T029、T051、T058、T060；usability protocol |
| SC-002 | P0 | T030～T037、T058、T060；usability protocol |
| SC-003 | P0 | T043、T048、T049、T051、T060 |
| SC-004 | P0 | T044、T050、T051 |
| SC-005 | P0 | T038～T042 |
| SC-006 | P0 | T044、T045、T047、T050、T051 |
| SC-007 | P0 | T024、T026、T029、T035、T042、T060 |
| SC-008 | P0 | T015、T016、T024、T025、T032、T060 |
| SC-009 | 發布後 | T001、T058、T060；發布後 30 日比較，不阻塞 P0 門檻 |

SC-007 的 P0 traceability 只保留 P0 Shell、志工回報、管理核心、狀態與最終 gate 證據；T054／T055 是 US6 的 P1 route extension，另以 FR-044 與 P1 evidence 追蹤，不得混入 SC-007 的 P0 完成判定。

## 風險、依賴與不納入範圍

### 風險與緩解措施

- **shadcn CLI 版本或 component registry 變更**：使用 lockfile、記錄 CLI 版本與 generated diff；只在本地 checkpoint 後加入元件，不依賴線上 runtime registry。
- **Tailwind import／CSS cascade 破壞 legacy page**：P0-1 保留 legacy rules，先以單頁遷移與 screenshot baseline 驗證；不得一次重寫 823 行 `globals.css`。
- **新 primitives 與既有 React／Next 行為衝突**：先以隔離元件測試與 P0-3 Shell smoke 驗證，Dialog／Sheet 不與業務 state 混合。
- **視覺重構掩蓋資料回歸**：每個 route migration 同時跑 data mapping／tenant／`ai-failed` tests；UI diff 不可單獨代表功能完成。
- **自動化 accessibility 不等於真實輔助科技體驗**：axe 與 Playwright 只作阻擋式基線，VoiceOver／鍵盤人工驗收仍是完成條件。
- **P0 範圍過大**：固定 P0 route order，每個 route 可獨立回退；P1 settings 不得阻塞 P0。

### 依賴

- 現有 Node.js、npm、Next.js、React、Vitest、API proxy、local seed 與登入帳號可正常使用。
- 安裝階段需要可取得 npm registry；若無網路，不能宣稱 Tailwind／shadcn／Lucide setup 已完成。
- P0 browser validation 需要本機 API、PostgreSQL／MinIO seed 與可登入的 A／B tenant fixtures。
- Playwright／axe 的新增 devDependencies 與 browser binary 需要在 lockfile、CI／local workflow 中同步確認。
- P0 依賴既有照護回報後端具備可驗證的冪等性或唯一性保護；本功能不修改後端，但若此驗證 evidence 失敗，該缺口必須標記為 P0 blocker，不得由前端 pending／disabled 狀態替代。

### 不納入範圍

- 後端 API、資料表、資料 migration、CRM business rules、AI prompt／model／review rules。
- LINE Bot 對話規則與 LIFF domain flow 的重新設計。
- P1／P2 頁面在 US5 P0 responsive、keyboard、screen reader 與 visual evidence 尚未完成前的完整遷移；US5 證據完成後，P1 可依本計畫與 P0 收尾平行進行。
- 深色模式、多語言、設計稿或外部 Design System package 的發布。
- 以 `add --all` 或一次性大爆量元件安裝取代按需加入。

## 設計後憲章檢查

| 原則 | 結果 | 設計證據 |
| --- | --- | --- |
| CRM、原始資料、AI 邊界 | PASS | 無新增資料模型；UI contract 明確區分原始、AI 與人工狀態。 |
| 志工低摩擦與歷史追溯 | PASS | P0-5 先處理手機草稿與保存；Timeline mapping 保留同日多筆與 snapshot。 |
| 權限、稽核與租戶隔離 | PASS | UI 不取代後端授權；quickstart 含 A／B、role、context switch regression。 |
| P0 獨立性 | PASS | P0-1 至 P0-6 皆不依賴 P1 settings 或 AI Queue 的完成。 |
| 正體中文與品質門檻 | PASS | 文件與介面 copy 規則使用台灣正體中文；quality／typecheck／build／browser evidence 均列為品質門檻。 |

**設計後門檻結果**：PASS。`tasks.md` 已產生，可進入 implementation。

## 複雜度追蹤

無需例外。此方案維持單一 `apps/web` 專案，以逐頁遷移與短期相容層控制風險，沒有新增服務、資料庫或第二套 UI runtime。
