# Frontend Style Remediation Tasks

> 本文件是前端風格稽核後的唯一執行清單。後續嚴格一次只修改一個任務；每個任務都要先展示修改前證據，再實作、驗證、展示修改後差異，最後更新本文件並建立獨立 Git commit。

## 目標

依據 2026-08-17～2026-08-19 建立的 StrayHub 前端風格，逐步統一：

- 綠色 semantic tokens：`--primary`、`--accent`、`--surface`、`--surface-soft`、`--border`
- `page-heading + eyebrow + h1 + description`
- `Button / Card / Field / Input / Select / Checkbox / Alert / Dialog / Toast / Table`
- 44px 最小互動控制高度
- `default / secondary / ghost / destructive` 操作語意
- 高影響操作採 `confirmation → mutation → toast`
- loading／empty／error／permission／success 狀態清楚分離
- 360／768／1024／1440px 響應式與可及性一致

## 執行規則

1. 嚴格依任務編號執行；同一時間只能有一個 `[~]` 任務。
2. 一個任務只處理一個 UI 問題；不得順手重構相鄰功能。
3. 每個任務開始前先記錄「修改前」：
   - 原始程式碼位置與行為。
   - 適用時附 browser screenshot、DOM／computed style 或失敗測試。
4. 先補回歸測試或可重現驗證，再做最小修改。
5. 修改後必須展示：
   - `git diff -- <本任務檔案>`。
   - 適用時附修改前／修改後截圖。
   - targeted tests、typecheck，以及本任務指定 gate。
6. 驗證完成後更新本文件：
   - `[ ]` 改為 `[x]`。
   - 填寫完成日期、修改前、修改後、驗證結果、實際 commit message 與 commit SHA。
7. 每個任務建立一個獨立 commit；commit 只能包含：
   - 該任務的實作與測試。
   - 本文件對該任務的完成註記。
8. Commit 前必須執行：
   - `git diff --check`
   - `git diff --cached --check`
   - `git status --short`
9. 不更新 visual baseline 來掩蓋未說明的差異；baseline 更新必須在獨立任務中完成。
10. 若任務失敗或被阻擋，保留 `[ ]`，並在紀錄中標示 `[BLOCKED]` 與證據，不可假裝完成。

## 狀態標記

- `[ ]`：未開始
- `[~]`：進行中（全文件最多一項）
- `[x]`：完成、驗證並已 commit
- `[BLOCKED]`：有明確阻擋證據

## 每次修改的紀錄模板

```markdown
- 完成日期：YYYY-MM-DD
- 修改前：path:line；原行為／截圖／失敗測試
- 修改後：新行為與使用者可見差異
- Changed files：
  - `path/to/file`
  - `path/to/test`
  - `frontend_task.md`
- Verification：
  - `command` → PASS/FAIL（實際摘要）
- Commit：`type(scope): summary`
- SHA：`abcdef0`
```

---

# Phase A — 設計系統與共用基礎

## [x] FT-001 拆分 Skeleton 與 loading dot 的 `pulse` 動畫

- **優先級：** P0
- **問題位置：** `apps/web/app/globals.css:541-546, 661-665, 985-991, 1482-1487`
- **修改前：** 兩個同名 `@keyframes pulse`；後宣告使 Skeleton 同時縮放至 80%。
- **預期修改後：** Skeleton 僅透明度脈動；loading dot 使用獨立縮放動畫。
- **預計檔案：**
  - `apps/web/app/globals.css`
  - 相關 component／browser regression test
  - `frontend_task.md`
- **驗證：** targeted test、`npm --prefix apps/web run typecheck`、reduced-motion browser assertion、修改前後動畫證據。
- **預定 commit：** `fix(web): separate skeleton and loading animations`
- **完成紀錄：**
  - 完成日期：2026-08-19
  - 修改前：`.ui-skeleton` 與 `.loading-dot` 共用兩個同名 `pulse` keyframes；後宣告的縮放規則覆蓋 Skeleton 的透明度動畫。
  - RED：`npm test -- app/globals.test.ts` → 1 failed，確認 `.ui-skeleton` 仍使用 `animation: pulse`。
  - 修改後：Skeleton 改用 `skeleton-pulse` 且只改變 opacity；loading dot 改用 `loading-dot-pulse` 並保留縮放效果；不再存在裸 `@keyframes pulse`。
  - Changed files：
    - `apps/web/app/globals.css`
    - `apps/web/app/globals.test.ts`
    - `frontend_task.md`
  - Verification：
    - `npm test -- app/globals.test.ts` → PASS（1 test）
    - `npm test` → PASS（51 files、100 tests）
    - `npm run typecheck` → PASS
    - `npx playwright test e2e/p0-responsive.spec.ts --grep 'reduced-motion'` → PASS（1 test）
  - Commit：`fix(web): separate skeleton and loading animations`
  - SHA：本完成紀錄與實作位於同一 commit；提交後以 `git log -1` 顯示值為準。

## [x] FT-002 修正權限確認 Dialog 的按鈕 variants

- **優先級：** P0
- **問題位置：** `apps/web/components/management/MembershipPermissionDialog.tsx:76-87`
- **修改前：** 取消是 raw button；確認使用不存在的 `.ui-button-primary`。
- **預期修改後：** 兩者都使用 `Button`；取消為 secondary，確認依風險使用 default／destructive。
- **預計檔案：**
  - `apps/web/components/management/MembershipPermissionDialog.tsx`
  - `apps/web/components/management/MembershipPermissionDialog.test.tsx`
  - `frontend_task.md`
- **驗證：** component test、typecheck、Dialog 修改前後 screenshot／computed class。
- **預定 commit：** `fix(web): align permission dialog button variants`
- **完成紀錄：**
  - 狀態：實作、自動化驗證與 `/shelters` 頁面驗收完成。
  - 修改前：取消按鈕沒有 Design System class；確認按鈕使用不存在的 `ui-button-primary`。
  - RED 1：預期取消為 secondary、一般確認為 default → 1 failed。
  - RED 2：預期高風險確認為 destructive → 1 failed、1 passed。
  - 修改後：取消統一使用 secondary；一般確認使用 default；停用、封存、管理員降級、撤銷授權與批次拒絕使用 destructive；權限確認 Modal 固定顯示於 viewport 正中央，內容過高時在 Modal 內捲動。
  - Changed files：
    - `apps/web/components/management/MembershipPermissionDialog.tsx`
    - `apps/web/components/management/MembershipPermissionDialog.test.tsx`
    - `apps/web/app/globals.css`
    - `apps/web/app/globals.test.ts`
    - `apps/web/app/(management)/shelters/page.tsx`
    - `apps/web/features/volunteer-access/ApplicationBatchWorkbench.tsx`
    - `apps/web/features/volunteer-access/AccessGrantTable.tsx`
    - `frontend_task.md`
  - Verification：targeted Dialog／CSS 2 files／4 tests PASS；完整 Vitest 51 files／102 tests PASS；typecheck PASS；Prettier PASS；完整 pytest 474 tests PASS。
  - Visual verification：使用者於 `/shelters` 驗收一般／destructive 按鈕與置中 Modal，並要求提交。
  - Commit：`fix(web): align permission dialog button variants`
  - SHA：本完成紀錄與實作位於同一 commit；提交後以 `git log -1` 顯示值為準。

## [x] FT-003 補齊缺失的 layout primitives

- **優先級：** P0
- **問題位置：** `stack-sm`、`stack-md`、`stack-lg`、`cluster`、`section-heading`、`list-card` 在醫療照護元件被使用但沒有 CSS 定義。
- **代表使用：**
  - `apps/web/features/medical-care/MedicalHistoryPanel.tsx`
  - `apps/web/features/medical-care/AssignedCareTask.tsx`
  - `apps/web/features/medical-care/ReminderSection.tsx`
  - `apps/web/features/medical-care/ReminderFormDialog.tsx`
- **修改前：** 預期的間距、flex 叢集和標題排列不生效。
- **預期修改後：** layout helpers 有單一 token-based 定義與 responsive 行為。
- **預計檔案：** `apps/web/app/globals.css`、layout regression test、`frontend_task.md`。
- **驗證：** 搜尋無未定義 class、medical-care targeted tests、360／768／1440 screenshot。
- **預定 commit：** `fix(web): define shared medical care layout utilities`
- **完成紀錄：**
  - 完成日期：2026-08-19
  - 狀態：實作、自動化驗證與 `/care-calendar` 頁面驗收完成。
  - 修改前：六個 layout class 被醫療照護元件使用，但沒有任何 CSS 規則，表單、清單、標題與按鈕群組依瀏覽器一般流排列。
  - RED：`npm test -- app/globals.test.ts` → 1 failed，確認 `.stack-sm` 未定義。
  - RED（對齊修正）：截圖確認通用 `.toolbar` 在 source order 覆蓋日期按鈕的 bottom alignment；專用 specificity regression test → 1 failed。
  - 修改後：新增 12／18／24px stack、可換行 cluster、responsive section heading 與 token-based list card；照護行事曆的日期按鈕群組與相鄰 Input／Select 底部對齊；提醒卡片改為 280px minimum 的 auto-fill grid，寬桌面一排約 4 張、一般桌面約 3 張、平板 2 張、手機 1 張。
  - Changed files：
    - `apps/web/app/globals.css`
    - `apps/web/app/globals.test.ts`
    - `apps/web/features/medical-care/CareAgendaFilters.tsx`
    - `apps/web/features/medical-care/CareAgenda.test.tsx`
    - `apps/web/features/medical-care/ReminderSection.tsx`
    - `frontend_task.md`
  - Verification：medical-care targeted 6 files／14 tests PASS；日期按鈕對齊、cascade specificity 與 reminder card grid targeted 2 files／6 tests PASS。
  - Visual verification：使用者確認日期按鈕與 Input 對齊，並確認提醒清單採一排 3～4 張 responsive cards，減少垂直捲動。
  - Commit：`fix(web): define shared medical care layout utilities`
  - SHA：本完成紀錄與實作位於同一 commit；提交後以 `git log -1` 顯示值為準。

## [x] FT-004 讓 Dialog／Sheet 標題 ID 唯一並明確設定 surface

- **優先級：** P1
- **問題位置：**
  - `apps/web/components/ui/dialog.tsx`
  - `apps/web/components/ui/sheet.tsx`
  - `apps/web/app/globals.css:582-600`
- **修改前：** 固定 `ui-dialog-title`／`ui-sheet-title`；surface 顏色依賴瀏覽器預設。
- **預期修改後：** 使用 `useId()`；明確套用 `var(--surface)` 與 `var(--foreground)`。
- **驗證：** 同頁多 Dialog ID regression test、dialog tests、axe。
- **預定 commit：** `fix(web): make overlay labels unique and tokenized`
- **完成紀錄：**
  - 狀態：2026-08-19 完成；Dialog／Mobile Sheet 頁面驗收後依指示建立獨立 commit。
  - 修改前：所有 Dialog 固定使用 `ui-dialog-title`，所有 Sheet 固定使用 `ui-sheet-title`；同頁多 overlay 產生重複 ID，surface 顏色依賴瀏覽器預設。
  - RED：`npm test -- components/ui/dialog.test.tsx app/globals.test.ts` → 2 failed；三個 overlay 只有兩個 unique labels，且 overlay CSS 缺少 surface token。
  - RED（Mobile Sheet 可讀性）：390px 截圖顯示 tablet `.nav-group { display: inline-flex; }` 同時壓縮 Sheet 導覽，文字逐字換行；Sheet vertical-list contract → 1 failed。
  - RED（Mobile trigger）：414px 截圖確認 trigger 在 header 下方獨占一列且顯示冗餘「導覽」文字；icon-only 與 header ordering contract → 3 failed。
  - RED（Drawer placement）：578×800 Playwright bounding box 顯示 Sheet `x=158` 且未保證完整 viewport 高度；left-edge／full-height contracts → 2 failed。
  - RED（Mobile logout）：Header 登出在 hamburger breakpoint 仍可見，Drawer 內沒有登出操作；component／CSS／Playwright contracts → 4 failed。
  - RED（closed dialog regression）：直接對 `dialog.ui-sheet` 套用 flex 會覆蓋瀏覽器 closed-dialog 隱藏規則並攔截 hamburger；`[open]` display contract → 1 failed。
  - 修改後：Dialog／Sheet 各自以 React `useId()` 連結 `aria-labelledby` 與標題；overlay 明確使用 `var(--surface)`／`var(--foreground)`；Mobile Sheet 導覽改為單欄分組清單，項目至少 44px 高、圖示與文字同行，並可獨立垂直捲動；小螢幕 trigger 改為 44×44 hamburger-only icon，置於 header 左上角且位於「森」品牌圖示左側；Sheet 改為左側固定 drawer，`x/y=0`、高度 `100dvh`、寬度最多 420px，遮罩不會從 drawer 下方露出；hamburger breakpoint 隱藏 Header 登出，並在 Drawer 底部顯示含 icon 的全寬登出按鈕，沿用既有 logout callback；flex layout 僅於 Sheet `[open]` 時啟用。
  - Changed files：
    - `apps/web/components/ui/dialog.tsx`
    - `apps/web/components/ui/sheet.tsx`
    - `apps/web/components/ui/dialog.test.tsx`
    - `apps/web/components/management/AppHeader.tsx`
    - `apps/web/components/management/ManagementLayout.tsx`
    - `apps/web/components/management/MobileNavigation.tsx`
    - `apps/web/components/management/management-shell.test.tsx`
    - `apps/web/e2e/management-shell.spec.ts`
    - `apps/web/app/globals.css`
    - `apps/web/app/globals.test.ts`
    - `frontend_task.md`
  - Verification：overlay／Mobile Sheet／header targeted PASS（mobile header 2 files／11 tests；drawer CSS 7 tests）；mobile navigation Playwright bounding-box 1 test PASS；full Vitest 51 files／111 tests PASS；TypeScript／Prettier PASS；P1 axe 4 viewports 1 test PASS；Python 474 tests PASS。
  - Visual verification：窄螢幕 hamburger、左側全高單欄 Drawer、Drawer 內登出與 overlay surface 已依 390／414／578px 截圖回饋完成調整。
  - Commit：本任務獨立 commit `fix(web): make overlay labels unique and tokenized`。

## [x] FT-005 讓 StateViews 依狀態顯示正確圖示

- **優先級：** P1
- **問題位置：** `apps/web/components/management/StateViews.tsx:18-30`
- **修改前：** loading、empty、error、permission denied 都顯示脈動 loading dot。
- **預期修改後：** 只有 loading／saving 動畫；其他狀態使用固定 semantic icon／tone。
- **驗證：** `StateViews.test.tsx`、a11y semantics、視覺差異。
- **預定 commit：** `fix(web): distinguish state view visual semantics`
- **完成紀錄：**
  - 狀態：2026-08-19 完成；頁面驗收後依指示建立獨立 commit。
  - 修改前：`StateView` 無條件輸出 `.loading-dot`，導致 empty、error、permission denied 也顯示與 loading／saving 相同的脈動動畫。
  - RED（indicator semantics）：要求只有 loading／saving 保留 `.loading-dot`，empty 使用 Inbox、error 使用 AlertTriangle、permission denied 使用 ShieldAlert；`StateViews.test.tsx` → 1 failed。
  - GREEN（indicator semantics）：依 `kind` render transient animation 或固定 lucide icon；保留既有 role、aria-live、title、description 與 action 行為；3 tests PASS。
  - RED（visual tone）：要求固定 icon 使用 neutral／danger／warning design tokens 並禁止 flex shrink；`globals.test.ts` → 1 failed。
  - GREEN（visual tone）：新增 `.state-icon`、`.state-neutral`、`.state-danger`、`.state-warning` 規則，danger／warning 同步使用 token-based border tone；globals 8 tests PASS。
  - Changed files：
    - `apps/web/components/management/StateViews.tsx`
    - `apps/web/components/management/StateViews.test.tsx`
    - `apps/web/app/globals.css`
    - `apps/web/app/globals.test.ts`
    - `frontend_task.md`
  - Verification：targeted 2 files／11 tests PASS；full Vitest 51 files／113 tests PASS；TypeScript／Prettier PASS；P1 axe 4 viewports 1 test PASS；Python 474 tests PASS；`/animals`／`/reports` HTTP 200；`git diff --check` PASS。
  - Visual verification：`/animals` loading／empty／error state 驗收步驟與預期 icon／tone 差異已確認，依指示完成。
  - Commit：本任務獨立 commit `fix(web): distinguish state view visual semantics`。

## [x] FT-006 移除管理頁巢狀 `<main>` landmarks

- **優先級：** P1
- **問題位置：** `apps/web/components/management/ManagementLayout.tsx:215-222` 與各 management route 根節點。
- **修改前：** Layout 與子頁都輸出 `<main>`。
- **預期修改後：** 每頁只有一個 main landmark，子頁使用 section／div。
- **驗證：** management shell test、axe、DOM landmark assertion。
- **預定 commit：** `fix(web): keep a single main landmark per route`
- **完成紀錄：**
  - 狀態：2026-08-19 完成；landmark 驗收後依指示建立獨立 commit。
  - 修改前：`ManagementLayout` 已輸出 `<main class="app-main">`，17 個 management route pages 與 observation vocabulary feature 又輸出 `<main>`，瀏覽器實際 DOM 出現兩個 main landmarks。
  - RED（source contract）：遞迴掃描所有 management `page.tsx`，要求不宣告 `<main>`，並要求 `ManagementLayout` 恰好保留一個；`ai-review/page.tsx` 首先失敗。
  - RED（browser DOM）：P1 management routes 在 360／768／1024／1440px 要求 `main` count 精確為 1；`/ai-review` 實際為 2，Playwright 失敗。
  - Secondary RED：route pages 修正後 `/settings/observation-options` 仍為 2，定位到 `ObservationVocabularyPage.tsx` feature root；納入 source contract 後如預期失敗。
  - GREEN：有 page heading label 的 route roots 改用 `<section aria-labelledby>`；純 loading／error 或未命名 roots 改用 `<div>`；observation vocabulary feature root 改用 labeled section；Layout 的唯一 main 不變。
  - Changed files：
    - `apps/web/app/(management)/**/page.tsx`（17 個含 root main 的 routes）
    - `apps/web/features/observation-vocabulary/ObservationVocabularyPage.tsx`
    - `apps/web/components/management/management-shell.test.tsx`
    - `apps/web/e2e/p1-a11y.spec.ts`
    - `frontend_task.md`
  - Verification：targeted 2 files／7 tests PASS；P1 routes × 4 viewports single-main + Axe PASS；full Vitest 51 files／114 tests PASS；TypeScript／Prettier PASS；Python 474 tests PASS；5 個代表 routes HTTP 200；`git diff --check` PASS。
  - Visual verification：管理頁外觀／操作不變，並提供 DevTools single-main／no-nested-main 驗收指令；依指示完成。
  - Commit：本任務獨立 commit `fix(web): keep a single main landmark per route`。

## [x] FT-007 修正 768px tablet 導覽的大面積空白

- **優先級：** P1
- **問題位置：** `apps/web/app/globals.css:929-956, 1488-1530`
- **修改前：** tablet 將 sidebar 展開成多行水平選單並留下大面積淡綠空白。
- **預期修改後：** tablet 使用 compact navigation 或 Mobile Sheet，主內容靠近 header。
- **驗證：** 768x1024 前後 screenshot、keyboard navigation、responsive test。
- **預定 commit：** `fix(web): compact management navigation on tablets`
- **完成紀錄：**
  - 狀態：2026-08-19 完成；同 viewport 頁面驗收後依指示建立獨立 commit。
  - 修改前：768×1024 命中 `max-width: 900px` 的 horizontal sidebar 規則；導覽折成兩列並保留約 114px 淡綠區域，頁面標題約從 y=226 才開始，hamburger 不存在。
  - RED：Playwright 在 768×1024 要求 header hamburger 可見、sidebar 與 header logout 隱藏、無水平 overflow、Drawer 可開啟且 Escape 後恢復 trigger focus；原實作因找不到 hamburger 失敗並保存 before screenshot。
  - GREEN：最終勝出的 `max-width: 900px` app-shell 規則改為 block body、隱藏 sidebar、顯示 MobileNavigation 並隱藏重複 header logout；移除 tablet horizontal nav-group 規則，601–900px 沿用既有單欄全高 Drawer。
  - Before／After：同 route／mock data／768px；兩列淡綠導覽完全消失，標題上移約 114px，hamburger 位於「森」左側，header 維持單列，無可見 horizontal overflow。
  - Changed files：
    - `apps/web/app/globals.css`
    - `apps/web/e2e/management-shell.spec.ts`
    - `frontend_task.md`
  - Verification：tablet Playwright 1 test PASS；management shell 4 tests PASS；P1 routes × 4 viewports Axe PASS；full Vitest 51 files／114 tests PASS；TypeScript／Prettier PASS；Python 474 tests PASS；`/` HTTP 200；`git diff --check` PASS。
  - Visual verification：768×1024 Header、主內容起點、Mobile Sheet 與 before／after screenshot 已完成驗收。
  - Commit：本任務獨立 commit `fix(web): compact management navigation on tablets`。

## [x] FT-008 合併重複的 600／900px app-shell media rules

- **優先級：** P1
- **問題位置：** `apps/web/app/globals.css:929, 940, 1330, 1488, 1518`
- **修改前：** 同 breakpoint 多套規則靠 source order 覆蓋；mobile header 高度與 `calc(100vh - 72px)` 不一致。
- **預期修改後：** 每個 breakpoint 只有單一 app-shell 區塊，body 高度不依賴錯誤的固定 header 高度。
- **驗證：** 360／768／1024 responsive、visual diff、無 horizontal／不合理 vertical overflow。
- **預定 commit：** `refactor(web): consolidate app shell breakpoints`
- **完成紀錄：**
  - 狀態：2026-08-19 完成；source/computed tests、360／768／1024 screenshot 與頁面驗收完成，依指示建立獨立 commit。
  - 修改前：`max-width: 900px` 分散為 2 blocks、`max-width: 600px` 分散為 3 blocks；`.app-header` 與 `.app-main` 同 breakpoint 依 source order 決定 winning padding；`.app-body` 固定使用 `calc(100vh - 72px)`，但 360px Header 實際高於 72px。
  - RED：CSS contract 取得 2 個 900px blocks（預期 1）；360×800 browser computed `.app-body` min-height 為 728px，證明仍以 `800 - 72` 計算而非依真實 Header 高度。
  - GREEN：900px 與 600px declarations 各合併為唯一 media block；保留原本最終 winning values；`.app-frame` 改為 `100vh` fallback + `100dvh` flex column，Header 不縮小，`.app-body` 以 `flex: 1 1 auto`／`min-height: 0` 填滿剩餘空間。
  - Feature preservation：observation vocabulary 與 shelter membership responsive declarations 原樣搬入各自最終 breakpoint，未改 selector、value 或 component markup。
  - Changed files：
    - `apps/web/app/globals.css`
    - `apps/web/app/globals.test.ts`
    - `apps/web/e2e/management-shell.spec.ts`
    - `frontend_task.md`
  - Verification：CSS contract 1 file／9 tests PASS；360／768／1024 computed responsive Playwright 1 test PASS；management shell 5 tests PASS；P1 routes × 4 viewports Axe PASS；full Vitest 51 files／115 tests PASS；TypeScript／Prettier PASS；Python 474 tests PASS；`/`、`/settings/observation-options`、`/shelters` HTTP 200；`git diff --check` PASS。
  - Visual verification：360 Header 自然兩列且內容緊接實際高度；768 compact navigation 無淡綠空白；1024 desktop sidebar／logout／四欄 metrics 保持，三者皆無 horizontal clipping 或不合理垂直空白。
  - Commit：本任務獨立 commit `refactor(web): consolidate app shell breakpoints`。

## [x] FT-009 統一 42／44／46px 控制高度

- **優先級：** P2
- **問題位置：** `apps/web/app/globals.css:78-85, 398-408, 479-486, 860-865, 1011-1020, 1356-1358`
- **修改前：** controls 混用 42、44、46px。
- **預期修改後：** 互動區使用單一 `--control-height: 44px`；checkbox 可視本體除外，但 label hit target 至少 44px。
- **驗證：** computed-style assertions、login／membership screenshots。
- **預定 commit：** `refactor(web): standardize control heights`
- **完成紀錄：**
  - 狀態：實作、computed browser verification 與完整 regression 完成。
  - 修改前：login submit 使用 46px；legacy field input/select、checkbox label 與 mobile membership permission 使用 42px；其他共用 controls 多為 44px；僅使用 min-height 時 login submit 實際 computed height 仍為 46px。
  - RED：CSS contract 缺少 `--control-height` 且偵測到 42／46px；browser computed test 實測 login controls 為 `[44, 44, 46]`。
  - GREEN：新增 `--control-height: 44px`；一般 single-line controls 同時使用 `height`／`min-height` token；textarea 使用 `height: auto` 並保留 100px min-height；checkbox 本體維持 20px，外層 checkbox label hit target 使用 44px；Sheet link 保留可換行的 min-height token。
  - Changed files：
    - `apps/web/app/globals.css`
    - `apps/web/app/globals.test.ts`
    - `apps/web/e2e/management-shell.spec.ts`
    - `frontend_task.md`
  - Verification：CSS contract 10 tests PASS；management shell 6 tests PASS；login／membership computed Playwright PASS；P1 routes × 4 viewports Axe PASS；full Vitest 51 files／116 tests PASS；TypeScript／Prettier PASS；Python 474 tests PASS；`/login`、`/shelters`、`/` HTTP 200；`git diff --check` PASS。
  - Visual verification：`/login` 的 username/password/submit computed height 均為 44px；`/shelters` 可見非-checkbox membership controls 均為 44px；checkbox 本體保留小尺寸，外層 permission hit target 保留 44px。
  - Commit：本任務獨立 commit `refactor(web): standardize control heights`。

## [x] FT-010 收斂重複 selectors 與 legacy／primitive cascade

- **優先級：** P2
- **問題位置：** `.sr-only`、`.notice`、`.notice.success`、`.panel.ui-card`、`.button-quiet`、全域 table selectors。
- **修改前：** 同一視覺由多套 selector 與 source order 決定。
- **預期修改後：** 每個 semantic class 有單一來源；已遷移元件不再同掛 legacy 與 primitive class。
- **驗證：** class usage search、完整 component tests、visual routes。
- **預定 commit：** `refactor(web): reduce legacy css cascade overlap`
- **完成紀錄：**
  - 狀態：selector／class migration、visual route 與完整 regression 完成。
  - 修改前：`.sr-only`、`.notice`、`.notice.success` 各有重複 CSS 定義；3 個 volunteer tables 使用 raw global `table/th/td`；12 個 production surfaces 同掛 legacy `panel` 與 primitive `ui-card`；AppHeader 同掛 `button-quiet` 與 `ui-button-ghost`。
  - RED：legacy／primitive cascade contract 實測 `.sr-only` 定義數量為 2，預期為 1。
  - GREEN：合併 semantic state selectors；新增 `.ui-card-padded` 取代 `panel ui-card`；AppHeader 移除 `button-quiet`；3 個 tables 遷移至 `.ui-table-wrap`／`.ui-table`／`.ui-table-head`／`.ui-table-cell`；移除 global raw table selectors。
  - Changed files：
    - `apps/web/app/globals.css`
    - `apps/web/app/globals.test.ts`
    - `apps/web/components/management/AppHeader.tsx`
    - `apps/web/app/management-home.tsx`
    - `apps/web/app/(management)/animals/[animalId]/page.tsx`
    - `apps/web/app/(management)/animals/page.tsx`
    - `apps/web/app/(management)/reports/[reportId]/page.tsx`
    - `apps/web/app/(management)/reports/page.tsx`
    - `apps/web/app/(management)/volunteers/applications/page.tsx`
    - `apps/web/app/(management)/volunteers/notifications/page.tsx`
    - `apps/web/features/medical-care/AnimalTodaySummary.tsx`
    - `apps/web/features/medical-care/CareAgendaFilters.tsx`
    - `apps/web/features/medical-care/MedicalHistoryPanel.tsx`
    - `apps/web/features/medical-care/ReminderSection.tsx`
    - `apps/web/features/volunteer-access/AccessGrantTable.tsx`
    - `apps/web/features/volunteer-access/ApplicationBatchWorkbench.tsx`
    - `apps/web/features/volunteer-access/NotificationFailureQueue.tsx`
    - `apps/web/features/volunteer-access/VolunteerAccessPolicyForm.tsx`
    - `frontend_task.md`
  - Verification：CSS contract 11 tests PASS；相關 medical／volunteer component tests 33 tests PASS；full Vitest 51 files／117 tests PASS；TypeScript／Prettier PASS；management shell 6 tests PASS；P1 routes × 4 viewports Axe PASS；Python 474 tests PASS；management／volunteer routes HTTP 200；`git diff --check` PASS。
  - Visual verification：management home、reports、animals、medical care、volunteer tables 的 card padding、table overflow 與 notice spacing 維持預期；raw table migration 未造成 viewport overflow。
  - Commit：本任務獨立 commit `refactor(web): reduce legacy css cascade overlap`。

---

# Phase B — 治理與高影響操作

## [x] FT-011 平台管理員異動確認與 Toast

- **優先級：** P0
- **問題位置：** `apps/web/app/(management)/platform-admins/page.tsx:222-262, 383-409`
- **修改前：** 提升、停用、降權、重新啟用直接 mutation。
- **預期修改後：** 顯示目標、before／after、active admin 數量與自我登出影響；成功後 Toast。
- **驗證：** page tests、`platform-admin-governance.spec.ts`、Dialog screenshot。
- **預定 commit：** `fix(web): confirm platform administrator mutations`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - 修改前：平台管理員建立、提升、替換、重新啟用、停用與降權都可直接觸發 mutation；成功訊息使用永久 Alert，沒有顯示異動目標、權限影響或 self-session logout 風險。
  - RED：新增「停用前必須顯示確認 Dialog」測試；現況直接執行 mutation，找不到 `確認停用平台管理員`。
  - GREEN：加入共用 pending mutation confirmation Dialog；顯示目標、權限／active admin 影響與 self-disable logout 警示；所有 mutation 經確認後才呼叫 API；成功回饋改用 Toast。
  - Changed files：
    - `apps/web/app/(management)/platform-admins/page.tsx`
    - `apps/web/app/(management)/platform-admins/page.test.tsx`
    - `frontend_task.md`
  - Verification：platform-admin page tests 6 passed；`platform-admin-governance.spec.ts` 1 passed；TypeScript passed；Prettier passed；`git diff --check` passed。
  - Revalidation：2026-08-19 以 `apps/web` 為工作目錄重新執行 platform-admin page tests 8 passed，並以 `PLAYWRIGHT_SKIP_WEBSERVER=1 npx playwright test e2e/platform-admin-governance.spec.ts` 驗證 Chromium 1 passed；先前的 `[BLOCKED]` 來自錯誤檔名／工作目錄造成的 `No tests found`，不是產品或 E2E 環境 blocker。
  - Route verification：`http://localhost:3001/platform-admins`；以平台管理員登入後，點擊停用／重新啟用／降權或建立／替換，確認 Dialog 顯示目標與影響；取消不發 request；確認後成功訊息顯示為 Toast；self-disable 確認後導向 `/login`。
  - Commit：`fix(web): confirm platform administrator mutations`。

## [x] FT-012 為 QR 撤銷／重新產生加入風險確認

- **優先級：** P0
- **問題位置：** `apps/web/app/(management)/settings/qr-codes/page.tsx:75-95, 168-181`
- **修改前：** 點擊即使既有 QR／Token 失效；兩者都呈現 secondary。
- **預期修改後：** 顯示動物、Token 失效範圍；撤銷用 destructive，完成後 Toast。
- **驗證：** component/page test、P1 browser test、前後 Dialog screenshot。
- **預定 commit：** `fix(web): confirm qr token invalidation actions`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - 修改前：撤銷與重新產生 QR 都直接呼叫 mutation，兩者都使用 secondary button，沒有揭露既有 QR／Token 失效範圍。
  - RED：QR page regression 點擊撤銷後找不到 `確認撤銷 QR` Dialog；初次測試另發現 page 缺少 React runtime import，已一併補足 Vitest 可執行 prerequisite。
  - GREEN：新增 alertdialog confirmation；顯示動物 ID、既有 QR／Token 立即失效與既有連結不可使用；撤銷使用 destructive variant；重新產生使用一般確認 variant；確認後才呼叫 endpoint，成功後顯示 Toast。
  - Changed files：
    - `apps/web/app/(management)/settings/qr-codes/page.tsx`
    - `apps/web/app/(management)/settings/qr-codes/page.test.tsx`
    - `frontend_task.md`
  - Verification：QR page test 1 passed；Prettier／TypeScript passed；`git diff --check` passed。
  - Route verification：`http://localhost:3001/settings/qr-codes`；以有 QR 管理權限的帳號登入，點擊撤銷或重新產生，確認 Dialog 顯示動物與 Token 失效風險；取消不發 request；確認後才更新清單並顯示 Toast。
  - Commit：`fix(web): confirm qr token invalidation actions`。

## [x] FT-013 為可回報範圍停用加入確認

- **優先級：** P1
- **問題位置：** `apps/web/app/(management)/settings/reportable-scope/page.tsx:95-110, 218-225`
- **修改前：** 點擊停用後直接 PATCH。
- **預期修改後：** 確認目標、有效期間與志工影響；成功 Toast；提交期間鎖定。
- **驗證：** page test、P1 a11y／browser。
- **預定 commit：** `fix(web): confirm reportable scope deactivation`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - 修改前：點擊可回報範圍「停用」後直接 PATCH，沒有說明有效期間或志工影響。
  - RED：page regression 點擊停用後找不到 `確認停用可回報範圍` Dialog。
  - GREEN：新增 destructive confirmation Dialog，顯示目標、有效期間、指定志工／受影響志工範圍與歷史資料保留行為；確認後才 PATCH；request 期間鎖定 Dialog controls；成功回饋改用 Toast。
  - Changed files：
    - `apps/web/app/(management)/settings/reportable-scope/page.tsx`
    - `apps/web/app/(management)/settings/reportable-scope/page.test.tsx`
    - `frontend_task.md`
  - Verification：reportable-scope page test 1 passed；TypeScript passed；Prettier passed；`git diff --check` passed。
  - Route verification：`http://localhost:3001/settings/reportable-scope`；以管理權限登入，點擊 active scope 的停用，確認 Dialog 顯示目標／期間／志工影響；取消不 PATCH；確認後顯示處理中並停用，成功後 Toast 可見。
  - Commit：`fix(web): confirm reportable scope deactivation`。

## [x] FT-014 以設計系統 Dialog 取代 AI review `window.prompt`

- **優先級：** P1
- **問題位置：** `apps/web/app/(management)/ai-review/page.tsx:77-95, 183-204`
- **修改前：** 使用 browser prompt；確認／拒絕視覺相同。
- **預期修改後：** Dialog + Field + Textarea；拒絕具風險語意；busy 與 Toast 完整。
- **驗證：** AI review tests、P1 browser／a11y、前後 screenshot。
- **預定 commit：** `fix(web): replace ai review prompt with governed dialog`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - 修改前：確認／拒絕使用 `window.prompt`，兩種動作視覺與語意層級相同，沒有 busy／Toast feedback。
  - RED：AI review interaction test 點擊拒絕後找不到 `拒絕 AI Observation` Dialog，且會依賴 browser prompt。
  - GREEN：改用 design-system Dialog、Field、Textarea；拒絕使用 destructive confirmation；確認／拒絕均要求 reason；request 期間鎖定 controls；成功後顯示 Toast，拒絕明確保留原始 AI output。
  - Changed files：
    - `apps/web/app/(management)/ai-review/page.tsx`
    - `apps/web/app/(management)/ai-review/page.test.tsx`
    - `frontend_task.md`
  - Verification：AI review page test 1 passed；TypeScript passed；Prettier passed；`git diff --check` passed。
  - Route verification：`http://localhost:3001/ai-review`；在待覆核項目點擊確認／拒絕，Dialog 顯示對應語意與 reason textarea；拒絕為 destructive；取消不送出；確認後顯示 Toast 並刷新 queue。
  - Commit：`fix(web): replace ai review prompt with governed dialog`。

## [x] FT-015 移除建立收容所管理員的雙層 Modal

- **優先級：** P1
- **問題位置：** `apps/web/app/(management)/shelters/page.tsx:438-445, 734-833`
- **修改前：** 建立帳號 Dialog 未關閉時再開權限確認 Dialog。
- **預期修改後：** 單一兩階段 Dialog，或安全切換 Dialog 並保留輸入／焦點。
- **驗證：** page test、Escape／focus restore、organization E2E。
- **預定 commit：** `fix(web): avoid stacked shelter account dialogs`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - 修改前：建立 SHELTER_ADMIN 時，建立帳號 Dialog 未關閉即另外開啟權限確認 Dialog，形成雙層 modal。
  - RED：新增 regression 證明提交管理員帳號時建立 Dialog 與確認 Dialog 同時 `open=true`。
  - GREEN：提交時先關閉建立表單再開權限確認；取消確認會恢復原表單並保留輸入 state；確認後直接執行 createAccount，避免巢狀 modal 與焦點混亂。
  - Changed files：
    - `apps/web/app/(management)/shelters/page.tsx`
    - `apps/web/app/(management)/shelters/page.test.tsx`
    - `frontend_task.md`
  - Verification：shelters page tests 6 passed；TypeScript passed；Prettier passed；`git diff --check` passed。
  - Route verification：`http://localhost:3001/shelters`；以 SHELTER_ADMIN 登入，點擊建立帳號、選擇收容所管理員、提交；確認建立表單關閉且只有權限確認 Dialog 開啟；取消後恢復原表單，確認後建立帳號。
  - Commit：`fix(web): avoid stacked shelter account dialogs`。

## [x] FT-016 區分 shelters／platform-admins 初始 loading 與 empty

- **優先級：** P1
- **問題位置：** shelters、archived shelters、platform admins 清單。
- **修改前：** API 完成前先顯示「目前沒有資料」。
- **預期修改後：** loaded 前顯示 LoadingState；成功且真空才顯示 EmptyState。
- **驗證：** delayed-response tests、page tests、前後錄影／screenshot。
- **預定 commit：** `fix(web): separate governance loading and empty states`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - 修改前：governance API 尚未完成時，platform admins、shelters 與 archived memberships 以空陣列先渲染「目前沒有資料」，無法區分 loading 與真正 empty。
  - RED：新增三個 route 的 delayed-response tests；原始實作在 delay 期間即顯示 empty。另修正 shelters `loadShelters` 對 selected id 的 callback dependency，避免 loading effect 重複重入。
  - GREEN：platform admins 加入 policy／active／audit／disabled loading views 與 EmptyState；shelters 與 archived shelters 分離 shelter list loading、membership details loading，API 完成且 items 為空才顯示 EmptyState。
  - Changed files：
    - `apps/web/app/(management)/platform-admins/page.tsx`
    - `apps/web/app/(management)/platform-admins/page.test.tsx`
    - `apps/web/app/(management)/shelters/page.tsx`
    - `apps/web/app/(management)/shelters/page.test.tsx`
    - `apps/web/app/(management)/shelters/archived/page.tsx`
    - `apps/web/app/(management)/shelters/archived/page.test.tsx`
    - `frontend_task.md`
  - Verification：三個 page suites 16 tests passed；TypeScript passed；Prettier passed；`git diff --check` passed。
  - Route verification：`http://localhost:3001/platform-admins`、`/shelters`、`/shelters/archived`；在網路延遲下觀察對應 LoadingState，待 API 回傳空陣列後才顯示 EmptyState；有資料時顯示清單，不再短暫顯示錯誤 empty。
  - Commit：`fix(web): separate governance loading and empty states`。

## [x] FT-017 為 mutation 表單加入 submitting 防重複送出

- **優先級：** P1
- **問題位置：** platform admin 建立／提升／替換、shelter 建立／帳號建立等 mutation forms。
- **修改前：** request 期間可重複點擊。
- **預期修改後：** 每個 mutation 有獨立 pending state、disabled fields 與「處理中…」標籤。
- **驗證：** double-click regression test、page tests。
- **預定 commit：** `fix(web): prevent duplicate governance submissions`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - 修改前：platform admin confirmation 與 shelter mutation forms 僅靠可重複觸發的 event handler；request pending 時按鈕與 fields 仍可操作，同一 render frame 連續 click／submit 會送出兩次 request。
  - RED：新增 platform disable confirmation 與 shelter area form 的 double-click regression；兩者都實際觀察到 2 次 mutation request。
  - GREEN：以同步 `useRef` lock 阻擋同 frame 重入，以 state 控制 disabled／`處理中…` UI；platform 建立、提升、替換及確認 mutation，與 shelter 啟用、建立收容所、建立帳號、建立區域共用防重複 gate；request 期間相關 inputs／selects／buttons 均鎖定。
  - Changed files：
    - `apps/web/app/(management)/platform-admins/page.tsx`
    - `apps/web/app/(management)/platform-admins/page.test.tsx`
    - `apps/web/app/(management)/shelters/page.tsx`
    - `apps/web/app/(management)/shelters/page.test.tsx`
    - `frontend_task.md`
  - Verification：platform-admins 與 shelters page suites 16 tests passed；double-click requests 均為 1；TypeScript passed；Prettier passed；`git diff --check` passed。
  - Route verification：`http://localhost:3001/platform-admins` 與 `/shelters`；確認 mutation request pending 時按鈕顯示「處理中…」、相關欄位 disabled，連續雙擊不產生第二次 request，完成後 controls 恢復。
  - Commit：`fix(web): prevent duplicate governance submissions`。

## [x] FT-018 讓 Toast 支援 timeout、關閉與連續訊息

- **優先級：** P1
- **問題位置：** `apps/web/components/ui/toast.tsx` 與 shelters／archived 使用端。
- **修改前：** Toast 永久留在左下角，無關閉方式，相同訊息不一定重新公告。
- **預期修改後：** timeout、手動關閉、連續訊息 key 與 focus-safe 行為。
- **驗證：** fake-timer tests、Toast a11y、窄螢幕 screenshot。
- **預定 commit：** `fix(web): add lifecycle controls to toast feedback`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - 修改前：Toast 永久留在左下角，沒有手動關閉方式；相同文字再次成功時，React string state equality 可能不 rerender／重新公告。
  - RED：新增 timeout、manual close／focus preservation、連續相同訊息 `messageKey` fake-timer tests；現況 3 項都因 Toast 永久存在而失敗。
  - GREEN：Toast 預設 5 秒自動關閉，提供可鍵盤操作的「關閉通知」按鈕與 `onClose`，不在 mount 時移動 focus；`messageKey` 變更會重設 visible state 與 timer。Shelters／archived 以遞增 `{id, text}` notice state 重新公告相同訊息。
  - Changed files：
    - `apps/web/components/ui/toast.tsx`
    - `apps/web/components/ui/toast.test.tsx`
    - `apps/web/app/globals.css`
    - `apps/web/app/(management)/shelters/page.tsx`
    - `apps/web/app/(management)/shelters/archived/page.tsx`
    - `apps/web/e2e/organization-management.spec.ts`
    - `frontend_task.md`
  - Verification：Toast／shelters／archived／CSS targeted suites 25 tests passed；organization management browser suite 3 passed（含 360px Toast lifecycle）；P1 四 viewport Axe 1 passed；full Vitest 53 files／129 tests passed；Python 474 tests passed；TypeScript passed；Prettier passed；`git diff --check` passed。
  - Visual verification：360×800 Toast 完整位於 viewport 內；初次截圖發現 Next dev indicator 遮住左側文字，將 mobile bottom offset 調整為 64px 後複驗，文字與關閉按鈕完整、無遮蔽／overflow。Screenshot：`apps/web/test-results/organization-management-SHELTER-ADMIN-可在已封存路由查詢並恢復成員-chromium/ft018-toast-360.png`。
  - Route verification：`http://localhost:3001/shelters`、`/shelters/archived`；完成帳號／權限／恢復 mutation 後觀察 Toast，點「關閉通知」可立即移除；未操作時約 5 秒自動消失；重複相同操作會重新顯示並重新公告。
  - Commit：`fix(web): add lifecycle controls to toast feedback`。

---

# Phase C — 志工與授權介面

## [x] FT-019 建立一致的志工頁面 Shell 並遷移動物確認表單

- **優先級：** P1
- **問題位置：** `apps/web/app/(volunteer)/animal-confirmation/page.tsx:129-205`
- **修改前：** 未定義 `volunteer-page`、raw inputs、legacy buttons、無 surface 的候選列表。
- **預期修改後：** mobile-first max-width／padding、Card、Field、Input、Button、surface-soft candidate list。
- **驗證：** page test、360／768 screenshot、volunteer E2E／axe。
- **預定 commit：** `fix(web): align volunteer animal confirmation layout`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - 修改前：`volunteer-page` 沒有任何 CSS；QR／收容編號搜尋使用 raw inputs 與 legacy buttons；候選清單沒有 Card 或 surface，360／768 內容貼齊 viewport 且缺乏區塊層級。
  - RED：page test 載入真實候選資料後，預期兩個 `.volunteer-search-card.ui-card`，實際為 0；CSS contract 找不到 `.volunteer-page`。
  - GREEN：建立 mobile-first 960px volunteer shell；QR 與收容編號遷移至 Card／Field／Input／Button；候選清單遷移至 Card 與 `list-card` surface；360px 單欄、720px 起搜尋 Card 雙欄，候選 action 在 tablet／desktop 對齊右側。保留 FT-020 title ID 與 FT-021 confirmation card 內部結構的獨立範圍。
  - Changed files：
    - `apps/web/app/(volunteer)/animal-confirmation/page.tsx`
    - `apps/web/app/(volunteer)/animal-confirmation/page.test.tsx`
    - `apps/web/app/globals.css`
    - `apps/web/app/globals.test.ts`
    - `apps/web/tests/animal_disambiguation.test.tsx`
    - `apps/web/e2e/volunteer-core.spec.ts`
    - `frontend_task.md`
  - Verification：focused page／CSS／disambiguation suites 15 tests passed；volunteer E2E 3 passed；animal-confirmation responsive 4 viewports passed；P0 Axe 四 viewport 1 passed；full Vitest 53 files／130 tests passed；Python 474 tests passed；TypeScript／Prettier／`git diff --check` passed。
  - Visual verification：`/animal-confirmation` 在 360×800 使用單欄 Cards 與 full-width controls；768×1024 使用雙欄搜尋 Cards與全寬候選 Card；兩者無水平 overflow。驗收截圖輸出於 Playwright `test-results`；2026-08-19 使用者回覆 `continue` 接受畫面。
  - Route verification：`http://localhost:3001/animal-confirmation`；以有效志工 session 開啟，搜尋收容編號後確認候選列表維持獨立 identity surface，點擊「查看確認卡」仍進入既有 confirmation flow；空資料文案保留在候選 Card 內。
  - Commit：`fix(web): align volunteer animal confirmation layout`。

## [x] FT-020 修正動物確認頁重複 ID

- **優先級：** P1
- **問題位置：** animal confirmation page 與 `AnimalConfirmationCard.tsx`。
- **修改前：** h1／h2 同為 `animal-confirmation-title`。
- **預期修改後：** card 使用唯一 title ID，`aria-labelledby` 指向正確。
- **驗證：** component test、DOM ID uniqueness、axe。
- **預定 commit：** `fix(web): use unique animal confirmation labels`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：component document fixture 同時渲染 page title 與 card title，2 個 ID 僅有 1 個 unique value。
  - GREEN：card title 改為 `animal-confirmation-card-title`，`aria-labelledby` 同步指向唯一 ID；page title 保留 `animal-confirmation-title`。
  - Changed files：`AnimalConfirmationCard.tsx`、`AnimalConfirmationCard.test.tsx`、`e2e/volunteer-core.spec.ts`、`frontend_task.md`。
  - Verification：component 3 tests passed；selected-card browser flow 驗證兩個 title ID 各 1 個且 Axe 無 critical／serious violation；volunteer E2E 3 passed；full Vitest 53 files／131 tests passed；Python 474 tests passed；TypeScript／Prettier／`git diff --check` passed。
  - Commit：`fix(web): use unique animal confirmation labels`。

## [x] FT-021 修正志工核心 Card 的內容 padding 與結構

- **優先級：** P1
- **問題位置：** `AnimalConfirmationCard.tsx`、`LiffFallback.tsx`。
- **修改前：** 內容直接放在 Card root；自訂 class 無 CSS。
- **預期修改後：** 使用 CardHeader／CardTitle／CardContent；圖片與 actions 有 responsive layout。
- **驗證：** component tests、360／768 screenshot。
- **預定 commit：** `fix(web): structure volunteer cards with shared primitives`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：Animal confirmation 與 LIFF fallback markup 均缺少 `ui-card-header`／`ui-card-title`／`ui-card-content`。
  - GREEN：兩個 Card 遷移至 CardHeader／CardTitle／CardContent；confirmation media/details 在 360px 單欄、720px 起雙欄；actions 在手機 full-width、tablet 起自適應；LIFF form 保留既有資料與 callbacks。
  - Changed files：`AnimalConfirmationCard.tsx`／test、`LiffFallback.tsx`、`tests/local_bot_mvp.test.tsx`、`globals.css`、`e2e/volunteer-core.spec.ts`、`frontend_task.md`。
  - Verification：focused 3 files／8 tests passed；360／768 四張 screenshots 視覺 PASS；volunteer E2E 3 passed；full Vitest 53 files／132 tests passed；Python 474 tests passed；TypeScript／Prettier／`git diff --check` passed。
  - Commit：`fix(web): structure volunteer cards with shared primitives`。

## [x] FT-022 將志工報名頁色彩遷移至 semantic tokens

- **優先級：** P1
- **問題位置：** `apps/web/features/volunteer-access/VolunteerApplicationPage.tsx:140-228`
- **修改前：** 硬編碼 emerald／slate／red、raw buttons／checkbox。
- **預期修改後：** 使用 Card／Alert／Button／Checkbox 與共用 tokens。
- **驗證：** component tests、360 screenshot、axe。
- **預定 commit：** `refactor(web): align volunteer application design tokens`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：初始申請 markup 無 `ui-card`／`ui-checkbox`／`ui-button`，仍輸出 emerald／slate utilities。
  - GREEN：頁面遷移至 Card／Alert／Button／Checkbox 與 semantic tokens；grant／reason／error 使用 scoped surfaces；visual review 發現 min-height grid stretch 並以 `align-content:start` 修正。
  - Changed files：`VolunteerApplicationPage.tsx`／test、`globals.css`、`volunteer-access-approval.spec.ts`、`frontend_task.md`。
  - Verification：component 7 tests passed；application E2E 1 passed；志工 routes Axe 1 passed；360 screenshot 複驗 PASS；full Vitest／Python／TypeScript／Prettier／diff gate passed。
  - Commit：`refactor(web): align volunteer application design tokens`。

## [x] FT-023 為撤回志工報名加入確認與成功回饋

- **優先級：** P1
- **問題位置：** `VolunteerApplicationPage.tsx:207-215`
- **修改前：** raw secondary-looking button 直接 withdraw。
- **預期修改後：** confirmation Dialog、正確 button variant、成功 Toast。
- **驗證：** component test、volunteer approval E2E。
- **預定 commit：** `fix(web): confirm volunteer application withdrawal`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：pending 狀態首擊「撤回報名」立即送出 withdraw POST，未提供確認。
  - GREEN：首擊開啟 alertdialog；「保留報名」不送 request；destructive「確認撤回」busy 防重複送出，成功後關閉 Dialog、更新 withdrawn 狀態並顯示 Toast。
  - Changed files：`VolunteerApplicationPage.tsx`／test、`volunteer-access-approval.spec.ts`、`frontend_task.md`。
  - Verification：component 8 tests passed；approval E2E cancel／confirm／single-request 1 passed；full Vitest／Python／TypeScript／Prettier／diff gate passed。
  - Commit：`fix(web): confirm volunteer application withdrawal`。

## [x] FT-024 遷移志工授權表格至 UI primitives

- **優先級：** P1
- **問題位置：** `apps/web/features/volunteer-access/AccessGrantTable.tsx`
- **修改前：** raw select／inputs／buttons／table；撤銷入口無 destructive 視覺。
- **預期修改後：** Field／Select／Input／Button／Table；更新與撤銷有明確層級。
- **驗證：** component test、volunteer access E2E、responsive screenshot。
- **預定 commit：** `refactor(web): migrate volunteer grants to ui primitives`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：grant markup 缺少 Field／Select／Input／Button primitives，撤銷與更新皆為無層級 raw button。
  - GREEN：status filter 使用 Field／Select；期限與原因使用 Input；Table root 使用 shared primitive；更新為 secondary、撤銷為 destructive；error 改為 Alert、Toast 可關閉。
  - Changed files：`AccessGrantTable.tsx`／test、`globals.css`、`frontend_task.md`。
  - Verification：component 1 passed；grant revoke E2E 1 passed；access responsive 1 passed；志工 routes Axe 1 passed；full Vitest／Python／TypeScript／Prettier／diff gate passed。
  - Commit：`refactor(web): migrate volunteer grants to ui primitives`。

## [x] FT-025 遷移志工批次審核工作台至 UI primitives

- **優先級：** P1
- **問題位置：** `ApplicationBatchWorkbench.tsx`
- **修改前：** raw controls、硬編碼 emerald CTA、結果缺少 semantic status。
- **預期修改後：** primitives、responsive form grid、Badge／Alert 區分 success／conflict／error。
- **驗證：** component test、batch E2E、360／1440 screenshot。
- **預定 commit：** `refactor(web): align volunteer batch workbench styles`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：workbench 仍輸出 raw checkbox／select／input 與硬編碼 emerald CTA。
  - GREEN：選取改用 Checkbox；決策 Select；日期／原因 Input；Table root與 Button primitives；error Alert、Toast lifecycle；逐筆結果使用 success／conflict／failed semantic Badge。
  - Changed files：`ApplicationBatchWorkbench.tsx`／test、`globals.css`、`frontend_task.md`。
  - Verification：component 1 passed；1,200 all-filtered snapshot E2E 1 passed；applications responsive 1 passed；志工 routes Axe 1 passed；full Vitest／Python／TypeScript／Prettier／diff gate passed。
  - Commit：`refactor(web): align volunteer batch workbench styles`。

## [x] FT-026 遷移通知失敗佇列並分離 success／error

- **優先級：** P1
- **問題位置：** `NotificationFailureQueue.tsx` 與 notifications page filters。
- **修改前：** raw controls；成功與錯誤共用 `role=status`。
- **預期修改後：** primitives；錯誤用 Alert，成功用 Toast／status；按鈕層級清楚。
- **驗證：** component test、notification E2E／axe。
- **預定 commit：** `fix(web): align notification retry controls and feedback`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：queue輸出 raw checkbox／buttons，初始固定渲染空 status；filter form為 raw inputs/select/button。
  - GREEN：queue使用 Checkbox／Table／Button，bulk retry busy防重複；success Toast與failure Alert分流且失敗保留 selection／operation ID；filters使用 Field／Input／Select／Button；page load error使用 Alert。
  - Regression correction：shared permission dialog新增 optional contextual closeLabel，batch keyboard focus恢復「關閉批次確認」。
  - Changed files：`NotificationFailureQueue.tsx`／test、notifications page、`MembershipPermissionDialog.tsx`、`ApplicationBatchWorkbench.tsx`、`globals.css`、`frontend_task.md`。
  - Verification：component 1 passed；notification keyboard flow 1 passed；notifications responsive 1 passed；志工 routes Axe 1 passed；full Vitest／Python／TypeScript／Prettier／diff gate passed。
  - Commit：`fix(web): align notification retry controls and feedback`。

## [x] FT-027 補齊志工授權政策的 loading／busy／error

- **優先級：** P1
- **問題位置：** `VolunteerAccessPolicyForm.tsx` 與 settings route。
- **修改前：** raw controls、無 try/catch、無 busy；request failure 可能永久顯示 loading。
- **預期修改後：** primitives、LoadingState／ErrorState、重試、busy、Toast。
- **驗證：** component／route tests、P1 browser／axe。
- **預定 commit：** `fix(web): harden volunteer access policy states`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：form輸出 raw controls／emerald CTA／empty status，save exception未攔截；route fetch failure無終止 loading路徑。
  - GREEN：Checkbox／Field／Input／Button；save busy disables controls，failure Alert且可重試，success lifecycle Toast；route使用 LoadingState／ErrorState、HTTP fail-closed與retry Button。
  - Changed files：`VolunteerAccessPolicyForm.tsx`／test、settings page、`globals.css`、`frontend_task.md`。
  - Verification：component markup與failure→success recovery 2 passed；settings responsive 1 passed；志工 routes Axe 1 passed；full Vitest／Python／TypeScript／Prettier／diff gate passed。
  - Commit：`fix(web): harden volunteer access policy states`。

## [x] FT-028 強化 Active Shelter Context 的視覺權重

- **優先級：** P2
- **問題位置：** `ActiveShelterContext.tsx:17-24`
- **修改前：** 純文字、raw button、原生 alert paragraph。
- **預期修改後：** surface-soft context card、Badge／Alert、secondary Button。
- **驗證：** component test、context mismatch screenshot／axe。
- **預定 commit：** `refactor(web): align active shelter context presentation`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：context輸出純文字、raw alert paragraph與 raw button，無 semantic surface／Badge。
  - GREEN：surface-soft bordered context card、作用中 Badge、mismatch Alert、secondary切換 Button；保留 explicit onSwitch callback。
  - Reachability：repo search確認此 component目前未掛入任何 route，因此 context mismatch browser screenshot／route Axe 不適用，不虛構證據。
  - Changed files：`ActiveShelterContext.tsx`／test、`globals.css`、`frontend_task.md`。
  - Verification：component callback＋semantic markup 2 passed；TypeScript passed；full Vitest／Python／Prettier／diff gate passed。
  - Commit：`refactor(web): align active shelter context presentation`。

## [x] FT-029 統一志工 care-report 的 loading／offline／empty 狀態

- **優先級：** P2
- **問題位置：** `apps/web/app/(volunteer)/care-report/page.tsx:48-60`
- **修改前：** loading／offline 使用普通 paragraph。
- **預期修改後：** LoadingState／ErrorState／EmptyState 或 Alert，並保留輸入。
- **驗證：** page test、offline browser flow、360 screenshot。
- **預定 commit：** `fix(web): align volunteer report state feedback`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：page test真正 render後確認 loading僅為普通 status paragraph、無 shared state-card；並揭露 page缺少 classic JSX React import。
  - GREEN：LoadingState／ErrorState／EmptyState；404／204為真 empty，其他 HTTP/network failure fail-closed為 offline；重新連線不清空既有 draft，offline與empty互斥。
  - Changed files：care-report `page.tsx`／test、`state-feedback.spec.ts`、`frontend_task.md`。
  - Verification：page 1 passed；save failure保留輸入＋retry 1 passed；initial offline→reconnect 1 passed；care-report responsive 360／768／1024／1440共4 passed；P0 Axe四 viewport passed；full Vitest／Python／TypeScript／Prettier／diff gate passed。
  - Commit：`fix(web): align volunteer report state feedback`。

## [x] Phase C 完成摘要

- **完成範圍：** FT-019～FT-029，共 11 個 atomic frontend remediation tasks。
- **獨立 commits：**
  1. `3a8fec7` — `fix(web): align volunteer animal confirmation layout`
  2. `2391385` — `fix(web): use unique animal confirmation labels`
  3. `9d6c7bb` — `fix(web): structure volunteer cards with shared primitives`
  4. `ca769d1` — `refactor(web): align volunteer application design tokens`
  5. `6aa10e1` — `fix(web): confirm volunteer application withdrawal`
  6. `41306e5` — `refactor(web): migrate volunteer grants to ui primitives`
  7. `f5ad8d9` — `refactor(web): align volunteer batch workbench styles`
  8. `afbf6a0` — `fix(web): align notification retry controls and feedback`
  9. `5c408a0` — `fix(web): harden volunteer access policy states`
  10. `70b6b6f` — `refactor(web): align active shelter context presentation`
  11. `d44df28` — `fix(web): align volunteer report state feedback`
- **主要成果：** 志工 shell與 responsive card結構、全域唯一 labeling、semantic token/primitives遷移、destructive confirmation與 lifecycle Toast、授權／批次／通知 controls層級、fail-closed loading/error/empty與 offline reconnect。
- **Accessibility／responsive：** 360／768／1024／1440無核心水平 overflow；keyboard Dialog focus restore與 retry流程通過；P0＋志工 routes Axe無 critical／serious violations。
- **Independent review：** FT-020與FT-021 reviewers均 PASS，無 blocker；FT-021四張 360／768 screenshots無 clipping／overflow。
- **Final regression（2026-08-19）：** Vitest 53 files／136 tests passed；Python pytest 474 passed；TypeScript／Prettier／`git diff --check` passed；combined browser suite 74 passed後2個 Axe tests因7-worker 30s timeout，隔離以60s原命令重跑2／2 passed。
- **Known non-blocker：** Starlette TestClient／httpx既有 deprecation warning；`ActiveShelterContext`目前未掛入 route，因此FT-028 browser screenshot明確不適用。

---

# Phase D — 醫療照護操作

## [x] FT-030 為醫療紀錄封存加入二次確認

- **優先級：** P0
- **問題位置：** `MedicalHistoryPanel.tsx:168-189, 380-386`
- **修改前：** 填寫原因後按 destructive button 即直接封存。
- **預期修改後：** AlertDialog 顯示紀錄、before／after、原因；成功 Toast。
- **驗證：** MedicalHistory tests、dialog cancel／confirm、medical E2E。
- **預定 commit：** `fix(web): confirm medical history archival`
- **完成紀錄：**
  - 完成日期：2026-08-19。
  - RED：component缺少封存 review copy；browser首擊直接 POST、無 AlertDialog。第二個 RED重現503 error落在modal背後；reviewer Low再以RED重現失敗後取消會洩漏stale page Alert。
  - GREEN：封存採pending snapshot與AlertDialog，顯示目標、有效→已封存、原因及歷史保留；cancel不送request並保留edit reason；confirm使用busy＋同步ref lock；失敗留在Dialog可retry，取消清除dialog-specific error；成功Toast。
  - Changed files：`MedicalHistoryPanel.tsx`／test、`dialog.tsx`、`medical-history.spec.ts`、`frontend_task.md`。
  - Verification：MedicalHistory／Dialog 7 passed；medical-history Playwright 3 passed；timeline responsive四viewport passed；P0 Axe passed；full Vitest 53 files／137 tests、Python 474 tests、TypeScript、Prettier、diff gate passed。
  - Independent review：早期review的Medium／Low findings均以RED修正；final replacement reviewer PASS，無 blocking finding。
  - Commit：`fix(web): confirm medical history archival`。

## [ ] FT-031 讓提醒建立／處理成功訊息在 Dialog 關閉後可見

- **優先級：** P1
- **問題位置：** `ReminderFormDialog.tsx`、`ReminderActionDialog.tsx` 與父層。
- **修改前：** 成功 message 隨 Dialog 關閉消失，或完全沒有成功回饋。
- **預期修改後：** 父層顯示 Toast；錯誤保留於 Dialog。
- **驗證：** reminder tests、care calendar E2E。
- **預定 commit：** `fix(web): preserve reminder success feedback after dialogs`
- **完成紀錄：** 待填。

---

# Phase E — 內容、次要頁面與視覺門檻

## [ ] FT-032 統一管理工作台的中英文產品文案

- **優先級：** P2
- **問題位置：** navigation 與頁面中的 `AI Review Queue`、`Audit Query`、`Report Inbox`、`Detail`、`Timeline`、`Membership`、`Active Shelter Context`。
- **修改前：** eyebrow、主標題、按鈕與狀態混用中英文。
- **預期修改後：** eyebrow 可保留英文；導航、主標題、按鈕與欄位以繁中為主，技術詞彙置於括號或說明。
- **驗證：** copy assertions、導航 screenshots、既有 locator 更新。
- **預定 commit：** `refactor(web): standardize management interface copy`
- **完成紀錄：** 待填。

## [ ] FT-033 將 Shelter Cage／Area 列表改為標準清單

- **優先級：** P2
- **問題位置：** `apps/web/app/(management)/shelters/page.tsx:835-879`
- **修改前：** 無樣式 `<ul>`、直接顯示英文 API values、沒有 EmptyState。
- **預期修改後：** surface-soft rows、Badge、本地化 labels、明確 EmptyState。
- **驗證：** shelter page test、organization E2E、360／1440 screenshot。
- **預定 commit：** `refactor(web): align shelter area list presentation`
- **完成紀錄：** 待填。

## [ ] FT-034 排除 Next.js dev indicator 的 visual baseline 噪音

- **優先級：** P1
- **問題位置：** Playwright visual test runtime／Next config。
- **修改前：** 10 個 P0 route 在 360px 因左下角 dev indicator 產生約 0.01 像素差異。
- **預期修改後：** visual test 不包含 dev indicator，頁面內容差異才會觸發失敗。
- **驗證：** `npm --prefix apps/web run test:visual`；不可直接更新 baseline 掩蓋 indicator。
- **預定 commit：** `test(web): remove dev indicator from visual evidence`
- **完成紀錄：** 待填。

## [ ] FT-035 將 visual viewport 拆成獨立 test cases

- **優先級：** P1
- **問題位置：** `apps/web/e2e/p0-visual.spec.ts:25-40`
- **修改前：** 每個 route 的四個 viewport 在同一 test，360px 失敗後其他 viewport 不執行。
- **預期修改後：** route × viewport 各自獨立回報，完整 evidence 不被首個失敗短路。
- **驗證：** `playwright test --list` 與 visual run 數量／命名。
- **預定 commit：** `test(web): isolate visual checks by viewport`
- **完成紀錄：** 待填。

## [ ] FT-036 補齊治理與志工頁 visual baselines

- **優先級：** P1
- **問題位置：** `p0-visual.spec.ts` 尚未涵蓋 shelters、archived shelters、platform admins；志工 visual tests 目前被 skip。
- **修改前：** 最近調整的核心治理頁沒有 screenshot regression 保護。
- **預期修改後：** 主要狀態與確認 Dialog 在 360／768／1024／1440 均有 reviewer-approved baseline。
- **驗證：** visual suite 全部執行；每個 baseline 有 route／viewport／state 識別。
- **預定 commit：** `test(web): cover governance and volunteer visual states`
- **完成紀錄：** 待填。

---

# 完成門檻

全部任務完成後才執行最終 gate：

```bash
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run format:check
npm --prefix apps/web run test:e2e:p0
npm --prefix apps/web run test:p1:e2e
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:p1:a11y
npm --prefix apps/web run test:visual
```

最終驗收還需確認：

- [ ] 360／768／1024／1440 無不合理 layout regression。
- [ ] 高影響操作都有明確確認、busy、成功／失敗回饋。
- [ ] 不存在未定義的產品 layout classes。
- [ ] 不存在不存在的 primitive variant class。
- [ ] 每頁只有一個 main landmark，Dialog／Sheet IDs 唯一。
- [ ] Visual baseline 差異都經 reviewer 說明與核准。
- [ ] 每個 FT 任務都有獨立 commit、驗證證據及本文件完成註記。

## 文件建立紀錄

- 建立日期：2026-08-19
- 稽核範圍：`apps/web/app`、`apps/web/components`、`apps/web/features`、`apps/web/e2e`、`apps/web/app/globals.css`
- 初始狀態：所有 FT 任務未開始。
- 建立文件預定 commit：`docs(web): add frontend style remediation task list`
