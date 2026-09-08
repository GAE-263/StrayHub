# UI 風格一致性檢視（重點：`/reports`）

> 分析日期：2026-09-08。純分析文件，尚未進行任何程式碼修改。

## 1. 目前的主流（canonical）風格模式

多數 `(management)` 路由共用同一套殼層與樣式系統：

- **共用頁面殼層**：`apps/web/app/(management)/layout.tsx` → `apps/web/components/management/ManagementLayout.tsx`，提供 `app-frame` / `app-header` / `app-body`（含側欄）/ `app-main` 結構（`ManagementLayout.tsx:340-395`）。`app-main` 的內容寬度為 `max-width: 1440px; padding: 36px clamp(20px,4vw,56px) 72px;`（`app/globals.css:243-248`）。
- **`app/globals.css`（約 3,364 行）作為設計 token + 共用 utility class 層**：
  - Root tokens：`--ink`、`--muted`、`--line`、`--surface`、`--accent`、`--danger`、`--warning`、`--radius-sm/md/lg`、`--control-height` 等（`globals.css:3-27`）。
  - 版面／文字：`.page-heading` / `.eyebrow`（`265-284`，h1 使用 `clamp(26px,4vw,38px)`）。
  - 元件語意 class：`.ui-button` 系列（`405-439`）、`.ui-card` / `.ui-card-padded` / `.ui-card-header` / `.ui-card-content` / `.ui-card-title`（`447-465`）、`.ui-field` / `.ui-label` / `.ui-input` / `.ui-textarea`（`565-589`）、`.ui-table` / `.ui-table-wrap`（`600-608`）、`.ui-badge`（`551-559`）、`.metric-grid` / `.metric-card`（`327-345`）、`.toolbar` / `.stack-*` / `.cluster`（`466-496`）。
- **`components/ui/*.tsx` 為薄封裝**：例如 `Card` 直接套用 `className="ui-card"`（`components/ui/card.tsx:6`）、`Button` 套用 `ui-button ui-button-{variant}`（`components/ui/button.tsx:14`）。這些元件把上述 global class 包裝成 React 元件供各頁面使用。
- **典型頁面示範**：`apps/web/app/(management)/animals/page.tsx` 完整示範這套模式——引入 `Badge/Button/Field/Input/Select/Table`（13-18 行）、`page-heading` + `eyebrow`（103-109）、`ui-card ui-card-padded`（110）、`toolbar`（111）、共用的 `Table` 元件（172）、`Badge`（212），並重用 `components/management/StateViews.tsx` 的 `EmptyState/ErrorState/LoadingState/PermissionDeniedState`。
  同樣模式也見於 `volunteers/**`、`settings/**`、`platform-admins`、`features/volunteer-access`、`features/medical-care`、`features/animal-timeline`。
- **較新的 feature 級 CSS Module 仍延續共用 token**：`features/growth-diary/growth-diary.module.css`、`features/adoption-inquiries/adoption-inquiries.module.css` 用 module 做版面 scope（`.page { max-width: 76rem; }`），但顏色仍引用 `var(--ink)`、`var(--muted)`、`var(--accent)`、`var(--surface-soft)`、`var(--radius-lg)`，甚至用 `:global(.ui-field)` 接回共用系統（`adoption-inquiries.module.css:76-78`、`growth-diary.module.css:86-88`）。間距單位為 `rem`。
- **獨立頁面（login、account）**：不用 CSS Module，改用 `globals.css` 內專屬 class（`.login-page`、`.login-card`，`45-88`），但仍使用同一組 token。

**結論**：canonical 模式 = 共用 `ManagementLayout` 殼層 + `page-heading/eyebrow/ui-card/toolbar` 等 global class 決定排版與字級 + 表單／表格／按鈕／徽章一律走 `components/ui/*`（不直接寫原生 `<button>/<input>/<select>`）+ 顏色／圓角／間距一律來自 `globals.css` 的 `:root` token。

## 2. `/reports` 與上述模式的差異

路由：`app/(management)/reports/page.tsx`（渲染 `ReportInbox`）與 `app/(management)/reports/[reportId]/page.tsx`（渲染 `ReportDetail`），元件皆在 `features/report-inbox/ReportInbox.tsx`，樣式在 `features/report-inbox/reports.module.css`。**外層殼層有共用 `ManagementLayout`（header/sidebar/app-main 一致）**，但內容區塊幾乎完全自成一套：

1. **互動元件未使用 `components/ui`**：直接寫原生 `<button>`（`ReportInbox.tsx:145, 303-317, 342, 422, 456`）、`<input>`（`150-157, 213-231`）、`<select>`（`161-209`）、`<textarea>`（`574-579, 656-662, 754-759`），完全靠 `reports.module.css` 上色，而不是其他管理頁一律使用的 `Button/Input/Select/Field/Textarea`。唯一引用的 `components/ui` 只有 `AlertDialog`（`ReportInbox.tsx:7`）。
2. **沒有用 `Card`/`ui-card`**：內容區塊用 `<article className={styles.card}>`（例如 `476, 621, 648` 行），對應 `reports.module.css:128-134`（`padding:24px; border-radius:12px;`，**無陰影**），相較 `ui-card` 用 `--radius-lg`（16px）並帶 `box-shadow: var(--shadow)`。
3. **沒有用 `Table`/`ui-table`**：列表用 `<Link>` + CSS Grid 列（`reports.module.css:88-100`，`grid-template-columns: 200px 1fr auto;`），與 `animals/page.tsx` 等頁使用的 `Table`/`ui-table-wrap` 不同。
4. **狀態徽章寫死 hex 色碼，未用設計 token**：`.urgent { background:#fce7e7; color:#963636; }`、`.review { background:#fff1d9; color:#885716; }`（`reports.module.css:107-127`），而 `globals.css` 已有語意對應的 `--danger`（`#a34040`）、`--warning`（`#a86d24`）（`globals.css:11-12`），其他頁的 `.status-warning`/`.state-warning`/`.batch-result-conflict` 都是引用這兩個 token。
5. **容器寬度不同**：`.page { max-width: 1180px; margin: auto; }`（`reports.module.css:1-4`），既不同於 `app-main` 的 `1440px`（`globals.css:245`），也不同於 `growth-diary`/`adoption-inquiries` 採用的 `76rem`（約 1216px）。
6. **間距／字級單位用 `px` 而非 `rem`**：例如 `font-size: 28px`、`padding: 20px`、`gap: 12px`（`reports.module.css:6, 44, 39`），與較新頁面（growth-diary、adoption-inquiries）的 `rem` 節奏不一致，觀感上字級／間距明顯不同。
7. **自訂標題規則取代共用 heading class**：`.page h1 { font-size: 28px; }`、`.page h2 { font-size: 20px; margin: 12px 0; }`、`.page h3 { font-size: 15px; }`（`reports.module.css:5-14`），重工了 `page-heading h1 { font-size: clamp(26px,4vw,38px); }`（`globals.css:271-275`）與 `.ui-card-title { font-size: 1.15rem; }` 已提供的規格，導致標題比其他頁面明顯小／比例不同。
8. **按鈕樣式未走 `ui-button` variant**：`.page button { border:1px solid var(--line); background:white; color:var(--accent); font-weight:600; }`（`reports.module.css:71-79`）是套獨立的「outline」樣式，沒有對應其他頁的 primary/secondary/destructive 區分——例如「封存回報」（破壞性操作）與「保存更正」外觀完全一樣，缺乏視覺上的風險提示。
9. **detail 頁的 breadcrumb 未用共用元件**：`ReportDetail` 用裸的 `<nav aria-label="Breadcrumb">` + 純連結（`ReportInbox.tsx:438-441`），而不是其他頁使用的 `components/ui/breadcrumb.tsx` / `components/management/Breadcrumbs.tsx` + `.breadcrumbs` class（`globals.css:3070-3074`）。

**整體觀感**：`/reports` 比其他管理頁更小、更扁平（無陰影）、圓角不同、狀態色不同、按鈕無層級區分、間距節奏更緊——即使外層殼層與其他頁相同。

### 需留意的干擾項：`/report-mockup`

`apps/web/app/report-mockup/page.tsx` + `page.module.css` 是**完全獨立的原型頁**，未使用 `ManagementLayout`，自己刻了一整套 header/sidebar/content（`page.tsx:142-362`：`styles.topbar`、`styles.sidebar`、`styles.content`）。若使用者曾看到這個路由，觀感差異會遠大於真正的 `/reports`，很可能是「風格差異很大」印象的來源之一。建議先確認這是設計草稿還是遺留頁面。

## 3. 其他（與 `/reports` 無關的）不一致現象

- **`globals.css` 內同時存在新舊兩套元件 class**：舊的 `.field`、`.button`、`.badge`（`1356-1385, 285-297, 2897-2905`）在檔案內明確註記為過渡狀態：「Legacy compatibility: P1 settings and observation vocabulary still use these selectors until their independent migration tasks are complete.」（`globals.css:1361-1362`）。目前 `settings/observation-options`、platform-admin 頁仍用舊的 `.field`/`.button`，`animals`/`volunteers` 則用新的 `.ui-*`——即使是「canonical」頁面彼此也不一致。
- **`globals.css` 本身是 3,364 行的巨石檔**，同時混雜 root token、通用 utility class，以及大量頁面／feature 專屬 selector（如 `.animal-profile-hero`、`.volunteer-service-date-option`、`.observation-category-toggle`、`.timeline-report-note`、`.membership-item`、`.platform-admin-item`），與 `reports.module.css`/`growth-diary.module.css`/`adoption-inquiries.module.css` 走 scoped module 的策略相反。目前沒有文件規範「什麼時候該放 globals.css，什麼時候該用 module」。
- **CSS Module 只在少數路由使用，覆蓋率不一致**：`animals/page.tsx`（`animal-profile.module.css`）、`settings/qr-codes/page.tsx`（`qr-codes.module.css`）、`app/access/page.tsx`、`app/account/page.tsx`、`app/account/invitations/page.tsx`、`login/LoginClient.tsx`、`features/adoption-inquiries`、`features/animal-management/AnimalBasicProfile.tsx`、`features/growth-diary/*`、`features/report-inbox/*`；其餘 feature（volunteer-access、medical-care、animal-timeline、observation-vocabulary）完全靠 global class，沒有 module。沒有明確界線決定哪些 feature「該」有 module。
- **`globals.css` 自己也有寫死的 hex 色碼**，違反自身的 token 制度：例如 `#eef0ef`/`#747b78`（`.platform-admin-item.is-disabled`，約第 1526 行）、`#e7c7c7`（`.error-state`、`.button-danger`）、`#fff5f4`、`#f0f3f2`、`#4b635c`（`.nav-link`，第 228 行）。
- **重複／近乎重複的區域色彩 token**：`growth-diary.module.css:1-13` 定義 `--diary-ink: #19332f`、`--diary-green: #16745c`、`--diary-mist: #e2f1e9`、`--diary-amber: #a86d24`，與 root 的 `--ink`、`--accent`、`--accent-soft`、`--warning`（`globals.css:4-12`）幾乎逐字元相同。相對地，`adoption-inquiries.module.css`（推測是較晚寫的姊妹 feature）已直接用 `var(--ink)`/`var(--muted)`/`var(--accent)`（第 2, 36, 46 行），像是「growth-diary 尚在往 adoption-inquiries 模式遷移中」的中間狀態（兩檔目前皆為 `git status` 顯示的已修改檔案）。
- `animal-profile.module.css`（實際內容在 `globals.css` 的 `.animal-profile-page` 區塊）也重複這個「影子 token」問題：`--profile-accent: #166a55`、`--profile-ink: #18332d`、`--profile-mint: #e7f2ed`、`--profile-amber: #b86712`（`globals.css:1645-1649`），與 root token 十六進位值些微不同，屬於第二個獨立案例。
- **容器最大寬度沒有統一數值**：`app-main` = 1440px；`.volunteer-page` = 960px（`globals.css:1568-1575`）；`.volunteer-application-page` = 560px（`globals.css:2106-2115`）；`.volunteer-review-page` = 1240px（`globals.css:2384-2386`）；`reports.module.css` `.page` = 1180px；`growth-diary`/`adoption-inquiries` `.page` = 76rem（約 1216px）；`.observation-audit-panel` = 980px（`globals.css:1290-1292`）。沒有一套文件化的寬度尺度，每個頁面各自挑數字。
- **`reports.module.css`、`growth-diary.module.css`、`adoption-inquiries.module.css` 各自獨立重做了幾乎相同的「eyebrow／header-mark／篩選列／分頁」樣式**（比較三者的 `.filters`/`.actions`/`.pagination`），class 命名不同、數值略有出入，概念上是同一個「清單頁工具列」元件，卻有三份平行、略微分歧的實作。

## 4. 建議優先順序

1. **把 `ReportInbox`/`ReportDetail` 改用 `components/ui` 元件**（`Button`、`Input`、`Select`、`Field`、`Card`/`CardContent`、`Table`、`Badge`、`Breadcrumb`）取代原生 HTML 元素 + `reports.module.css` 手刻樣式。這是影響最大的一項，能同時修正按鈕／卡片／表格三處視覺落差。
2. **`reports.module.css` 的狀態色改用既有 token**：`.urgent`/`.review`/`.normal` 改為 `var(--danger)`、`var(--warning)`、`var(--accent-soft)`/`var(--accent)`，讓狀態色與 `.state-danger`/`.state-warning`/其他頁徽章一致。
3. **改用共用的 `page-heading`/`eyebrow` 標題區塊與 `ui-card`/`ui-card-padded` 卡片樣式**，取代 `.page h1/h2/h3` 與自訂的 `.card`/`.row`，恢復一致的字級（`clamp(26px,4vw,38px)`）與卡片陰影／圓角（`--radius-lg`、`--shadow`）。
4. **統一間距單位與容器寬度**：`reports.module.css` 由 `px` 改為 `rem`；`.page` 最大寬度建議統一採用 `growth-diary`/`adoption-inquiries`（較新完成的兩個清單頁）已使用的 `76rem`。
5. **釐清 `apps/web/app/report-mockup`**：確認它是否為正式功能的一部分。若只是設計草稿，建議移除或明確標示為非正式頁面（例如移到被排除的路徑或加上提示 banner）；若代表未來設計方向，應反過來用它做為 `/reports` 重新設計的依據，避免同時存在兩份差異很大的「reports」體驗。
6. **決定並文件化「global class vs. CSS Module」的選用原則**，避免新／改的 feature 繼續分裂成兩派；同時規劃把 `globals.css` 中僅屬單一頁面／feature 的 selector（timeline、animal-profile、volunteer-*、observation-*）逐步搬到各自的 module，比照 `growth-diary`/`adoption-inquiries`/`report-inbox` 現行做法。
7. **完成 `globals.css:1361` 提到的舊 `.field`/`.button`/`.badge` → `.ui-field`/`.ui-button`/`.ui-badge` 遷移**，讓所有頁面（不只 `animals`/`volunteers`）都用同一套基礎元件 class。
8. **清掉重複的區域色彩 token**：移除 `--diary-*`（growth-diary）與 `--profile-*`（animal-profile）中只是重述 root token 的宣告，改直接引用 `var(--ink)`、`var(--accent)` 等，比照 `adoption-inquiries.module.css` 已採用的做法。

---

*本文件為分析結果，尚未進行任何實作變更。若要開始修正，建議先處理第 1、2 點（`/reports` 元件與色彩 token），影響範圍最集中、風險最低。*
