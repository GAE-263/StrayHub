# 研究：前端體驗一致化與響應式 UI 基礎

**功能**：[spec.md](spec.md)

**研究日期**: 2026-08-13

## 決策 1：Tailwind CSS v4 使用 PostCSS 整合

**決策**：採 Tailwind CSS v4 的 `@tailwindcss/postcss` plugin，在 `apps/web/postcss.config.mjs` 啟用，並由 `app/globals.css` 的 `@import "tailwindcss";` 載入 utilities。

**理由**：

- 專案目前沒有 Tailwind 設定，v4 的官方 Next.js 路徑可以從最小 PostCSS 設定開始。
- CSS variables 可以直接作為語意 token，適合把既有 `--ink`、`--muted`、`--line`、`--surface`、`--accent` 等值逐步對映，而不用先重寫整份 legacy CSS。
- 不建立不必要的 `tailwind.config.ts`，降低設定重複與遷移面積。

**考慮過的替代方案**：

- **Tailwind v3 + `tailwind.config.ts`**：不採用，會導入額外 content／theme 設定且與目前官方 v4 路徑不一致。
- **只使用現有 CSS**：不採用，無法穩定建立跨頁面 utility、token 與 variant composition。

**參考資料**：[Tailwind CSS：Install with Next.js](https://tailwindcss.com/docs/installation/framework-guides/nextjs)

## 決策 2：在既有 Next.js 專案中初始化 shadcn/ui，使用 Radix base

**決策**：從 `apps/web` 執行 `npx shadcn@latest init --base radix`，保留 `@/*` alias、CSS variables、Next App Router 與目前的 `zh-Hant-TW` HTML 語言設定。由 CLI 產生的元件 source 直接放在 `apps/web/components/ui`，不使用 `--force`。

**理由**：

- shadcn/ui 官方支援 existing project，元件 source 由專案擁有，適合逐頁遷移與客製化 token。
- Radix primitives 對 Dialog、AlertDialog、Sheet、Tooltip、Select 等 P0 需要的 overlay／focus／keyboard 行為成熟，且一次固定 base 可避免混用不同 primitive contract。
- `@/*` 已存在於 `apps/web/tsconfig.json`，可直接對應 shadcn 的 components、ui、lib 與 hooks aliases。

**考慮過的替代方案**：

- **Base UI base**：保留未來評估空間，但本功能先以既有 React／Next runtime 的穩定 overlay 行為和較小遷移風險為優先。
- **ARIA base**：可作為後續特定元件需求的研究選項，但 P0 不混用兩種 base。
- **一次加入所有 shadcn 元件**：不採用，會擴大 lockfile、source 與維護面積，不符合 P0 低風險遷移。

**參考資料**：[shadcn/ui：Next.js installation](https://ui.shadcn.com/docs/installation/next)、[shadcn CLI](https://ui.shadcn.com/docs/cli)、[shadcn：Add components](https://ui.shadcn.com/docs/new)

## 決策 3：元件按 P0 需求加入，不安裝完整清單

**決策**：第一批加入 Button、Card、Badge、Breadcrumb、Field、Label、Input、Select、Textarea、Checkbox、Dialog、AlertDialog、Sheet、Table、Skeleton、Spinner、Alert、Toast、Tooltip、Sidebar、Separator；只有在實作 route 確實需要時才加入其他元件。空資料不加入 shadcn `Empty`，統一由 app-level `StatusView` 的 `empty` variant 呈現。

**理由**：

- 完整清單包含許多 P0 不需要的互動模式，會增加 review、dependency 與 upgrade 成本。
- 每個元件 source 可由專案直接修改，先建立最小且可驗收的 UI foundation 比一次安裝更容易維持一致性。
- `Field` composition 可統一 label、description、error、disabled 與 pending semantics，補足目前 `.field`／`.form-error` 分散的行為。

**考慮過的替代方案**：

- **保留原生元素直到所有頁面完成**：不採用，會延後共用 focus、status 與 responsive contract 的建立。
- **一次 `add --all`**：不採用，無法對應 P0 scope，也不利於 rollback。

## 決策 4：Lucide React 使用具名匯入與語意 icon map

**決策**：安裝 `lucide-react`；各 composition 只具名匯入實際使用的 icon，建立一份 route／action 對應表，icon-only 控制必須提供 aria-label，必要時加 Tooltip；狀態不可只用 icon。

**理由**：

- Lucide 官方提供 React package、可調整 size／stroke／color，並以 tree-shakable 方式只匯入需要的 icon。
- 具名匯入可讓 icon 意義與 bundle 使用清楚可追蹤。
- 對志工與管理者而言，搜尋、返回、展開、重試、編輯、停用、AI 與權限等操作需要一致的視覺提示，但文字仍是主要語意。

**考慮過的替代方案**：

- **emoji／文字箭頭**：不採用，跨平台外觀與語意不穩定。
- **icon font 或整包 icon library**：不採用，難以控制一致性、可及性與使用範圍。

**參考資料**：[Lucide](https://lucide.dev/)、[lucide-react package](https://www.npmjs.com/package/lucide-react)

## 決策 5：CSS variables 作為單一 design token 層

**決策**：在 `globals.css` 建立語意 token，至少涵蓋 background、foreground、muted、border、primary、secondary、success、warning、destructive、focus、surface、overlay、radius、shadow、spacing 與 typography；元件與頁面不得直接散落 brand 色碼。

**理由**：

- 現有 CSS 已有一組森林綠／米白／狀態色，先做 token 對映可降低視覺跳變。
- shadcn 的 CSS variable theming 與 Tailwind utilities 可共用相同語意層，讓 `Badge`、`Alert`、`Button` 與 focus ring 維持一致。
- token 層可在後續完成視覺調整、dark mode 評估或品牌校正時集中修改。

**考慮過的替代方案**：

- **頁面內直接寫色碼**：不採用，會延續目前跨頁面不一致與重複宣告問題。
- **建立獨立 design-system package**：不採用，P0 不需要第二個 workspace 或發布流程。

## 決策 6：過渡期保留 legacy class，按 route 遷移

**決策**：新舊樣式短期並存；每次只遷移一個共用層或 route，保留舊 class 作 fallback，完成 P0 browser／a11y／品質門檻後才刪除無引用的 `.button`、`.panel`、`.field`、`.badge`、`.state-card` 等宣告。

**理由**：

- 目前 `globals.css` 約 823 行且含重複宣告，直接重寫會讓資料行為與視覺回歸難以定位。
- 逐頁遷移可保持每個 checkpoint 可展示、可測試、可回退。
- P0 不依賴 P1，能避免為了設定頁或非核心頁面延後志工流程。
- P1 路由明確包含 `/shelters`；它沿用 P0 的 Shell、狀態、權限與 Active Shelter Context 契約，在 US5 P0 evidence 完成後即可與 P0 收尾平行，不是 P0 門檻的前置條件。

**考慮過的替代方案**：

- **一次全量重寫 `globals.css`**：不採用，風險不可控且不利於快速回退。
- **新增第二套完整 global CSS**：不採用，會形成長期 cascade 衝突。

## 決策 7：Vitest + Playwright + axe + manual VoiceOver 分工

**決策**：保留現有 Vitest／typecheck／format／build；新增 Playwright 做真實瀏覽器 smoke、keyboard、viewport 與 visual screenshot，加入 `@axe-core/playwright` 做自動無障礙 baseline，最後以 VoiceOver 與人工鍵盤 checklist 完成 sign-off。

實作依賴固定為 `@playwright/test`、`@axe-core/playwright` 與 Playwright Chromium browser binary；`apps/web/package.json` 必須提供 `test:e2e:p0`、`test:e2e:p0:list`、`test:visual`、`test:visual:update`、`test:a11y:browser`、`test:a11y:browser:list`、`test:axe`、`test:p1:e2e` 與 `test:p1:a11y` scripts。依賴、script 與 binary 版本都必須由 `apps/web/package-lock.json`、安裝命令與 browser smoke／axe list command 驗證；P0 scripts 不得載入 US6 的 P1 suite。

**理由**：

- 現有 tests 多數只確認 component/page 可建立，無法證明真實 focus、viewport overflow、Sheet／Dialog 行為與 screenshot 一致性。
- jsdom／axe 只能抓部分語意問題，不能取代瀏覽器 layout、鍵盤與輔助科技驗收。
- Playwright 的固定 viewport screenshot 與既有本機 seed 可提供可重複證據；manual VoiceOver 補足 live region、讀取順序與焦點體驗。

**考慮過的替代方案**：

- **只擴充 Vitest**：不採用，無法可靠驗證真實 responsive layout 與 visual regression。
- **只做人工檢查**：不採用，重複性與回歸偵測不足。

## 決策 8：Toast 只用於短暫回饋，重要狀態留在頁內

**決策**：表單錯誤、權限不足、資料載入失敗、AI 失敗與保存衝突使用頁內 Alert／StatusView；短暫成功或非阻斷提示才使用 Toast。P0 不額外引入 Sonner，先使用 shadcn Toast primitive。

**理由**：

- 重要狀態需要在使用者回頭查看時仍可找到，不能只存在於短暫通知。
- 不額外增加 toast runtime，降低 dependency 與 accessibility provider 的遷移面積。

**考慮過的替代方案**：

- **所有回饋都用 Toast**：不採用，會讓錯誤與保存衝突容易被忽略。
- **引入 Sonner**：暫不採用，除非後續 UI 研究證明 shadcn Toast 無法滿足 P0 的堆疊或操作需求。

## 已解決的未知事項

- Package manager：沿用 `apps/web/package-lock.json` 的 npm。
- CSS integration：Tailwind v4 PostCSS，不預設建立 legacy config。
- shadcn base：P0 固定 Radix，不混用 base。
- Component installation：按 P0 清單加入，不使用 `--all`。
- Icon library：`lucide-react`，具名匯入。
- Persistence／API：無新增資料模型與 endpoint。
- Browser validation：Playwright + axe；manual VoiceOver 為必要補充。
- Overlay terminology：產品語意的 Drawer 統一由 shadcn `Sheet` 實作；Dialog／AlertDialog 維持不同的焦點與風險用途。
- State rendering：`StatusView` 是 P0／P1 canonical state composition；既有 `EmptyState`、`ErrorState`、`StatusBanner` 只能作 adapter。
- P1 route scope：`/shelters` 與 AI／設定頁一起納入 P1；只驗證既有 organization context、角色與資料 scope 的呈現，不新增 shelter domain entity 或授權來源。
