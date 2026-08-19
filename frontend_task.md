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

## [ ] FT-002 修正權限確認 Dialog 的按鈕 variants

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
- **完成紀錄：** 待填。

## [ ] FT-003 補齊缺失的 layout primitives

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
- **完成紀錄：** 待填。

## [ ] FT-004 讓 Dialog／Sheet 標題 ID 唯一並明確設定 surface

- **優先級：** P1
- **問題位置：**
  - `apps/web/components/ui/dialog.tsx`
  - `apps/web/components/ui/sheet.tsx`
  - `apps/web/app/globals.css:582-600`
- **修改前：** 固定 `ui-dialog-title`／`ui-sheet-title`；surface 顏色依賴瀏覽器預設。
- **預期修改後：** 使用 `useId()`；明確套用 `var(--surface)` 與 `var(--foreground)`。
- **驗證：** 同頁多 Dialog ID regression test、dialog tests、axe。
- **預定 commit：** `fix(web): make overlay labels unique and tokenized`
- **完成紀錄：** 待填。

## [ ] FT-005 讓 StateViews 依狀態顯示正確圖示

- **優先級：** P1
- **問題位置：** `apps/web/components/management/StateViews.tsx:18-30`
- **修改前：** loading、empty、error、permission denied 都顯示脈動 loading dot。
- **預期修改後：** 只有 loading／saving 動畫；其他狀態使用固定 semantic icon／tone。
- **驗證：** `StateViews.test.tsx`、a11y semantics、視覺差異。
- **預定 commit：** `fix(web): distinguish state view visual semantics`
- **完成紀錄：** 待填。

## [ ] FT-006 移除管理頁巢狀 `<main>` landmarks

- **優先級：** P1
- **問題位置：** `apps/web/components/management/ManagementLayout.tsx:215-222` 與各 management route 根節點。
- **修改前：** Layout 與子頁都輸出 `<main>`。
- **預期修改後：** 每頁只有一個 main landmark，子頁使用 section／div。
- **驗證：** management shell test、axe、DOM landmark assertion。
- **預定 commit：** `fix(web): keep a single main landmark per route`
- **完成紀錄：** 待填。

## [ ] FT-007 修正 768px tablet 導覽的大面積空白

- **優先級：** P1
- **問題位置：** `apps/web/app/globals.css:929-956, 1488-1530`
- **修改前：** tablet 將 sidebar 展開成多行水平選單並留下大面積淡綠空白。
- **預期修改後：** tablet 使用 compact navigation 或 Mobile Sheet，主內容靠近 header。
- **驗證：** 768x1024 前後 screenshot、keyboard navigation、responsive test。
- **預定 commit：** `fix(web): compact management navigation on tablets`
- **完成紀錄：** 待填。

## [ ] FT-008 合併重複的 600／900px app-shell media rules

- **優先級：** P1
- **問題位置：** `apps/web/app/globals.css:929, 940, 1330, 1488, 1518`
- **修改前：** 同 breakpoint 多套規則靠 source order 覆蓋；mobile header 高度與 `calc(100vh - 72px)` 不一致。
- **預期修改後：** 每個 breakpoint 只有單一 app-shell 區塊，body 高度不依賴錯誤的固定 header 高度。
- **驗證：** 360／768／1024 responsive、visual diff、無 horizontal／不合理 vertical overflow。
- **預定 commit：** `refactor(web): consolidate app shell breakpoints`
- **完成紀錄：** 待填。

## [ ] FT-009 統一 42／44／46px 控制高度

- **優先級：** P2
- **問題位置：** `apps/web/app/globals.css:78-85, 398-408, 479-486, 860-865, 1011-1020, 1356-1358`
- **修改前：** controls 混用 42、44、46px。
- **預期修改後：** 互動區使用單一 `--control-height: 44px`；checkbox 可視本體除外，但 label hit target 至少 44px。
- **驗證：** computed-style assertions、login／membership screenshots。
- **預定 commit：** `refactor(web): standardize control heights`
- **完成紀錄：** 待填。

## [ ] FT-010 收斂重複 selectors 與 legacy／primitive cascade

- **優先級：** P2
- **問題位置：** `.sr-only`、`.notice`、`.notice.success`、`.panel.ui-card`、`.button-quiet`、全域 table selectors。
- **修改前：** 同一視覺由多套 selector 與 source order 決定。
- **預期修改後：** 每個 semantic class 有單一來源；已遷移元件不再同掛 legacy 與 primitive class。
- **驗證：** class usage search、完整 component tests、visual routes。
- **預定 commit：** `refactor(web): reduce legacy css cascade overlap`
- **完成紀錄：** 待填。

---

# Phase B — 治理與高影響操作

## [ ] FT-011 為平台管理員異動加入確認與 Toast

- **優先級：** P0
- **問題位置：** `apps/web/app/(management)/platform-admins/page.tsx:222-262, 383-409`
- **修改前：** 提升、停用、降權、重新啟用直接 mutation。
- **預期修改後：** 顯示目標、before／after、active admin 數量與自我登出影響；成功後 Toast。
- **驗證：** page tests、`platform-admin-governance.spec.ts`、Dialog screenshot。
- **預定 commit：** `fix(web): confirm platform administrator mutations`
- **完成紀錄：** 待填。

## [ ] FT-012 為 QR 撤銷／重新產生加入風險確認

- **優先級：** P0
- **問題位置：** `apps/web/app/(management)/settings/qr-codes/page.tsx:75-95, 168-181`
- **修改前：** 點擊即使既有 QR／Token 失效；兩者都呈現 secondary。
- **預期修改後：** 顯示動物、Token 失效範圍；撤銷用 destructive，完成後 Toast。
- **驗證：** component/page test、P1 browser test、前後 Dialog screenshot。
- **預定 commit：** `fix(web): confirm qr token invalidation actions`
- **完成紀錄：** 待填。

## [ ] FT-013 為可回報範圍停用加入確認

- **優先級：** P1
- **問題位置：** `apps/web/app/(management)/settings/reportable-scope/page.tsx:95-110, 218-225`
- **修改前：** 點擊停用後直接 PATCH。
- **預期修改後：** 確認目標、有效期間與志工影響；成功 Toast；提交期間鎖定。
- **驗證：** page test、P1 a11y／browser。
- **預定 commit：** `fix(web): confirm reportable scope deactivation`
- **完成紀錄：** 待填。

## [ ] FT-014 以設計系統 Dialog 取代 AI review `window.prompt`

- **優先級：** P1
- **問題位置：** `apps/web/app/(management)/ai-review/page.tsx:77-95, 183-204`
- **修改前：** 使用 browser prompt；確認／拒絕視覺相同。
- **預期修改後：** Dialog + Field + Textarea；拒絕具風險語意；busy 與 Toast 完整。
- **驗證：** AI review tests、P1 browser／a11y、前後 screenshot。
- **預定 commit：** `fix(web): replace ai review prompt with governed dialog`
- **完成紀錄：** 待填。

## [ ] FT-015 移除建立收容所管理員的雙層 Modal

- **優先級：** P1
- **問題位置：** `apps/web/app/(management)/shelters/page.tsx:438-445, 734-833`
- **修改前：** 建立帳號 Dialog 未關閉時再開權限確認 Dialog。
- **預期修改後：** 單一兩階段 Dialog，或安全切換 Dialog 並保留輸入／焦點。
- **驗證：** page test、Escape／focus restore、organization E2E。
- **預定 commit：** `fix(web): avoid stacked shelter account dialogs`
- **完成紀錄：** 待填。

## [ ] FT-016 區分 shelters／platform-admins 初始 loading 與 empty

- **優先級：** P1
- **問題位置：** shelters、archived shelters、platform admins 清單。
- **修改前：** API 完成前先顯示「目前沒有資料」。
- **預期修改後：** loaded 前顯示 LoadingState；成功且真空才顯示 EmptyState。
- **驗證：** delayed-response tests、page tests、前後錄影／screenshot。
- **預定 commit：** `fix(web): separate governance loading and empty states`
- **完成紀錄：** 待填。

## [ ] FT-017 為 mutation 表單加入 submitting 防重複送出

- **優先級：** P1
- **問題位置：** platform admin 建立／提升／替換、shelter 建立／帳號建立等 mutation forms。
- **修改前：** request 期間可重複點擊。
- **預期修改後：** 每個 mutation 有獨立 pending state、disabled fields 與「處理中…」標籤。
- **驗證：** double-click regression test、page tests。
- **預定 commit：** `fix(web): prevent duplicate governance submissions`
- **完成紀錄：** 待填。

## [ ] FT-018 讓 Toast 支援 timeout、關閉與連續訊息

- **優先級：** P1
- **問題位置：** `apps/web/components/ui/toast.tsx` 與 shelters／archived 使用端。
- **修改前：** Toast 永久留在左下角，無關閉方式，相同訊息不一定重新公告。
- **預期修改後：** timeout、手動關閉、連續訊息 key 與 focus-safe 行為。
- **驗證：** fake-timer tests、Toast a11y、窄螢幕 screenshot。
- **預定 commit：** `fix(web): add lifecycle controls to toast feedback`
- **完成紀錄：** 待填。

---

# Phase C — 志工與授權介面

## [ ] FT-019 建立一致的志工頁面 Shell 並遷移動物確認表單

- **優先級：** P1
- **問題位置：** `apps/web/app/(volunteer)/animal-confirmation/page.tsx:129-205`
- **修改前：** 未定義 `volunteer-page`、raw inputs、legacy buttons、無 surface 的候選列表。
- **預期修改後：** mobile-first max-width／padding、Card、Field、Input、Button、surface-soft candidate list。
- **驗證：** page test、360／768 screenshot、volunteer E2E／axe。
- **預定 commit：** `fix(web): align volunteer animal confirmation layout`
- **完成紀錄：** 待填。

## [ ] FT-020 修正動物確認頁重複 ID

- **優先級：** P1
- **問題位置：** animal confirmation page 與 `AnimalConfirmationCard.tsx`。
- **修改前：** h1／h2 同為 `animal-confirmation-title`。
- **預期修改後：** card 使用唯一 title ID，`aria-labelledby` 指向正確。
- **驗證：** component test、DOM ID uniqueness、axe。
- **預定 commit：** `fix(web): use unique animal confirmation labels`
- **完成紀錄：** 待填。

## [ ] FT-021 修正志工核心 Card 的內容 padding 與結構

- **優先級：** P1
- **問題位置：** `AnimalConfirmationCard.tsx`、`LiffFallback.tsx`。
- **修改前：** 內容直接放在 Card root；自訂 class 無 CSS。
- **預期修改後：** 使用 CardHeader／CardTitle／CardContent；圖片與 actions 有 responsive layout。
- **驗證：** component tests、360／768 screenshot。
- **預定 commit：** `fix(web): structure volunteer cards with shared primitives`
- **完成紀錄：** 待填。

## [ ] FT-022 將志工報名頁色彩遷移至 semantic tokens

- **優先級：** P1
- **問題位置：** `apps/web/features/volunteer-access/VolunteerApplicationPage.tsx:140-228`
- **修改前：** 硬編碼 emerald／slate／red、raw buttons／checkbox。
- **預期修改後：** 使用 Card／Alert／Button／Checkbox 與共用 tokens。
- **驗證：** component tests、360 screenshot、axe。
- **預定 commit：** `refactor(web): align volunteer application design tokens`
- **完成紀錄：** 待填。

## [ ] FT-023 為撤回志工報名加入確認與成功回饋

- **優先級：** P1
- **問題位置：** `VolunteerApplicationPage.tsx:207-215`
- **修改前：** raw secondary-looking button 直接 withdraw。
- **預期修改後：** confirmation Dialog、正確 button variant、成功 Toast。
- **驗證：** component test、volunteer approval E2E。
- **預定 commit：** `fix(web): confirm volunteer application withdrawal`
- **完成紀錄：** 待填。

## [ ] FT-024 遷移志工授權表格至 UI primitives

- **優先級：** P1
- **問題位置：** `apps/web/features/volunteer-access/AccessGrantTable.tsx`
- **修改前：** raw select／inputs／buttons／table；撤銷入口無 destructive 視覺。
- **預期修改後：** Field／Select／Input／Button／Table；更新與撤銷有明確層級。
- **驗證：** component test、volunteer access E2E、responsive screenshot。
- **預定 commit：** `refactor(web): migrate volunteer grants to ui primitives`
- **完成紀錄：** 待填。

## [ ] FT-025 遷移志工批次審核工作台至 UI primitives

- **優先級：** P1
- **問題位置：** `ApplicationBatchWorkbench.tsx`
- **修改前：** raw controls、硬編碼 emerald CTA、結果缺少 semantic status。
- **預期修改後：** primitives、responsive form grid、Badge／Alert 區分 success／conflict／error。
- **驗證：** component test、batch E2E、360／1440 screenshot。
- **預定 commit：** `refactor(web): align volunteer batch workbench styles`
- **完成紀錄：** 待填。

## [ ] FT-026 遷移通知失敗佇列並分離 success／error

- **優先級：** P1
- **問題位置：** `NotificationFailureQueue.tsx` 與 notifications page filters。
- **修改前：** raw controls；成功與錯誤共用 `role=status`。
- **預期修改後：** primitives；錯誤用 Alert，成功用 Toast／status；按鈕層級清楚。
- **驗證：** component test、notification E2E／axe。
- **預定 commit：** `fix(web): align notification retry controls and feedback`
- **完成紀錄：** 待填。

## [ ] FT-027 補齊志工授權政策的 loading／busy／error

- **優先級：** P1
- **問題位置：** `VolunteerAccessPolicyForm.tsx` 與 settings route。
- **修改前：** raw controls、無 try/catch、無 busy；request failure 可能永久顯示 loading。
- **預期修改後：** primitives、LoadingState／ErrorState、重試、busy、Toast。
- **驗證：** component／route tests、P1 browser／axe。
- **預定 commit：** `fix(web): harden volunteer access policy states`
- **完成紀錄：** 待填。

## [ ] FT-028 強化 Active Shelter Context 的視覺權重

- **優先級：** P2
- **問題位置：** `ActiveShelterContext.tsx:17-24`
- **修改前：** 純文字、raw button、原生 alert paragraph。
- **預期修改後：** surface-soft context card、Badge／Alert、secondary Button。
- **驗證：** component test、context mismatch screenshot／axe。
- **預定 commit：** `refactor(web): align active shelter context presentation`
- **完成紀錄：** 待填。

## [ ] FT-029 統一志工 care-report 的 loading／offline／empty 狀態

- **優先級：** P2
- **問題位置：** `apps/web/app/(volunteer)/care-report/page.tsx:48-60`
- **修改前：** loading／offline 使用普通 paragraph。
- **預期修改後：** LoadingState／ErrorState／EmptyState 或 Alert，並保留輸入。
- **驗證：** page test、offline browser flow、360 screenshot。
- **預定 commit：** `fix(web): align volunteer report state feedback`
- **完成紀錄：** 待填。

---

# Phase D — 醫療照護操作

## [ ] FT-030 為醫療紀錄封存加入二次確認

- **優先級：** P0
- **問題位置：** `MedicalHistoryPanel.tsx:168-189, 380-386`
- **修改前：** 填寫原因後按 destructive button 即直接封存。
- **預期修改後：** AlertDialog 顯示紀錄、before／after、原因；成功 Toast。
- **驗證：** MedicalHistory tests、dialog cancel／confirm、medical E2E。
- **預定 commit：** `fix(web): confirm medical history archival`
- **完成紀錄：** 待填。

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
