# StrayHub Phase B 完成摘要

- **Phase：** Phase B — 治理與高影響操作
- **範圍：** FT-011～FT-018
- **完成日期：** 2026-08-19
- **Branch：** `dev/frontend_review`
- **狀態：** 8／8 任務已完成、驗證並各自建立獨立功能 commit。

## Commit 索引

| FT | 主題 | Commit |
|---|---|---|
| FT-011 | 平台管理員異動確認與 Toast | `22573b4 fix(web): confirm platform administrator mutations` |
| FT-012 | QR 撤銷／重新產生風險確認 | `4e50c21 fix(web): confirm qr token invalidation actions` |
| FT-013 | 可回報範圍停用確認 | `f08f462 fix(web): confirm reportable scope deactivation` |
| FT-014 | AI review Dialog 取代 `window.prompt` | `2e24bea fix(web): replace ai review prompt with governed dialog` |
| FT-015 | 移除建立收容所管理員雙層 Modal | `e531df1 fix(web): avoid stacked shelter account dialogs` |
| FT-016 | 分離 governance loading 與 empty states | `c673aaf fix(web): separate governance loading and empty states` |
| FT-017 | Mutation submitting 防重複送出 | `9167f0d fix(web): prevent duplicate governance submissions` |
| FT-018 | Toast timeout、關閉與連續訊息 | `8987d16 fix(web): add lifecycle controls to toast feedback` |

FT-011 ledger 曾因錯誤 Playwright 檔名／工作目錄造成 `No tests found` 而被後續 commit 誤標為 `[BLOCKED]`；正確命令重新驗證通過後，以 `23b2b99 docs: correct FT-011 completion status` 移除 stale blocker 與重複紀錄。這不是產品或 E2E 環境 blocker。

---

## FT-011 平台管理員異動確認與 Toast

### 修改元件

- `apps/web/app/(management)/platform-admins/page.tsx`
- `apps/web/app/(management)/platform-admins/page.test.tsx`

### 修改內容

- 平台管理員建立、提升、替換、重新啟用、停用與降權均先開啟共用 confirmation Dialog。
- Dialog 顯示操作目標、before／after 權限影響、active admin 數量影響。
- Self-disable／self-demote 明確警告目前 session 將失效；確認後清除登入狀態並導向 `/login`。
- 取消不送出 mutation；成功結果改用 Toast。

### Route 與操作驗證

- URL：`http://localhost:3001/platform-admins`
- 以平台管理員登入。
- 點擊建立、提升、替換、重新啟用、停用或降權。
- 確認 Dialog 顯示正確目標與影響；取消後不應送出 request。
- 確認後應顯示成功 Toast；對自己停用／降權時應導向 `/login`。

### 驗證

- 原功能 slice：platform-admin page tests 6 passed；Playwright governance 1 passed。
- 最新重新驗證：platform-admin page tests 8 passed；Chromium governance 1 passed。
- TypeScript、Prettier、`git diff --check` passed。

---

## FT-012 QR 撤銷／重新產生風險確認

### 修改元件

- `apps/web/app/(management)/settings/qr-codes/page.tsx`
- `apps/web/app/(management)/settings/qr-codes/page.test.tsx`

### 修改內容

- 撤銷與重新產生 QR 不再直接 mutation。
- Confirmation Dialog 顯示動物 ID、既有 QR／Token 立即失效及既有連結不可使用等影響。
- 撤銷使用 destructive variant；重新產生使用一般確認 variant。
- 成功後更新清單並顯示 Toast。

### Route 與操作驗證

- URL：`http://localhost:3001/settings/qr-codes`
- 以有 QR 管理權限的帳號登入。
- 點擊撤銷或重新產生，確認風險文案與動物 ID。
- 取消後不應發 request；確認後才更新資料並顯示 Toast。

### 驗證

- QR page test 1 passed。
- TypeScript、Prettier、`git diff --check` passed。

---

## FT-013 可回報範圍停用確認

### 修改元件

- `apps/web/app/(management)/settings/reportable-scope/page.tsx`
- `apps/web/app/(management)/settings/reportable-scope/page.test.tsx`

### 修改內容

- 停用 active scope 前顯示 destructive confirmation Dialog。
- 顯示停用目標、有效期間、指定／受影響志工範圍及歷史資料保留行為。
- Request pending 時鎖定 Dialog controls。
- 確認後才 PATCH；成功後顯示 Toast。

### Route 與操作驗證

- URL：`http://localhost:3001/settings/reportable-scope`
- 點擊 active scope 的「停用」。
- 確認 Dialog 的目標、期間與志工影響。
- 取消後不 PATCH；確認後顯示處理中，完成後顯示 Toast。

### 驗證

- Reportable-scope page test 1 passed。
- TypeScript、Prettier、`git diff --check` passed。

---

## FT-014 AI Review governed Dialog

### 修改元件

- `apps/web/app/(management)/ai-review/page.tsx`
- `apps/web/app/(management)/ai-review/page.test.tsx`

### 修改內容

- 移除 `window.prompt`，改用 design-system Dialog、Field 與 Textarea。
- 確認／拒絕都要求 reason；拒絕使用 destructive confirmation。
- Request pending 時鎖定 controls。
- 成功後顯示 Toast 並刷新 queue；拒絕時保留原始 AI output。

### Route 與操作驗證

- URL：`http://localhost:3001/ai-review`
- 對待覆核項目點擊確認或拒絕。
- Dialog 應顯示對應語意與 reason textarea；拒絕應有 destructive 視覺。
- 取消不送出；確認後顯示 Toast 並刷新清單。

### 驗證

- AI review page test 1 passed。
- TypeScript、Prettier、`git diff --check` passed。

---

## FT-015 移除建立收容所管理員雙層 Modal

### 修改元件

- `apps/web/app/(management)/shelters/page.tsx`
- `apps/web/app/(management)/shelters/page.test.tsx`

### 修改內容

- 建立 `SHELTER_ADMIN` 時，先關閉建立帳號 Dialog，再開權限確認 Dialog。
- 不再同時存在兩個 `open=true` 的 modal。
- 取消確認會恢復建立表單並保留輸入 state。
- 確認後直接建立帳號，避免巢狀 modal 與焦點混亂。

### Route 與操作驗證

- URL：`http://localhost:3001/shelters`
- 以 shelter admin 登入，開啟「建立帳號」並選擇收容所管理員。
- 提交後應只有權限確認 Dialog；原建立表單關閉。
- 取消後表單與輸入值恢復；確認後建立帳號。

### 驗證

- Shelters page tests 6 passed。
- TypeScript、Prettier、`git diff --check` passed。

---

## FT-016 分離 Governance Loading 與 Empty State

### 修改元件

- `apps/web/app/(management)/platform-admins/page.tsx`
- `apps/web/app/(management)/platform-admins/page.test.tsx`
- `apps/web/app/(management)/shelters/page.tsx`
- `apps/web/app/(management)/shelters/page.test.tsx`
- `apps/web/app/(management)/shelters/archived/page.tsx`
- `apps/web/app/(management)/shelters/archived/page.test.tsx`

### 修改內容

- Platform policy、active admins、audit、disabled admins 使用各自 LoadingState。
- Shelters 清單與 membership details 使用獨立 loading state。
- Archived shelters 清單與 archived memberships 使用獨立 loading state。
- 只有 request 成功完成且 items 真正為空時才顯示 EmptyState。
- 修正 `loadShelters` 對 selected ID 的 callback dependency，避免 loading effect 重複重入。

### Route 與操作驗證

- URLs：
  - `http://localhost:3001/platform-admins`
  - `http://localhost:3001/shelters`
  - `http://localhost:3001/shelters/archived`
- 在 Network throttling 下重新整理。
- Response pending 時只應顯示對應 LoadingState，不應短暫顯示「目前沒有資料」。
- Empty response 完成後才顯示 EmptyState；有資料時顯示清單。

### 驗證

- 三個 page suites 16 tests passed，包含 delayed-response regressions。
- TypeScript、Prettier、`git diff --check` passed。

---

## FT-017 Mutation Submitting 防重複送出

### 修改元件

- `apps/web/app/(management)/platform-admins/page.tsx`
- `apps/web/app/(management)/platform-admins/page.test.tsx`
- `apps/web/app/(management)/shelters/page.tsx`
- `apps/web/app/(management)/shelters/page.test.tsx`

### 修改內容

- Platform admin confirmation 與 shelter forms 加入同步 `useRef` lock，阻擋同一 render frame 重入。
- State 控制 request pending UI、disabled fields 與「處理中…」標籤。
- 涵蓋 platform admin 建立／提升／替換／確認 mutation，以及 shelter 啟用／建立收容所／建立帳號／建立區域。
- RED 實際證明單靠 React state 時連續 click／submit 會送出兩次 request；GREEN 後各只送出一次。

### Route 與操作驗證

- URLs：
  - `http://localhost:3001/platform-admins`
  - `http://localhost:3001/shelters`
- 開啟任一 mutation flow 並快速雙擊 submit／confirm。
- Request pending 時按鈕顯示「處理中…」，相關 inputs／selects／buttons disabled。
- Network 面板中同一 mutation 應只有一個 request；完成後 controls 恢復。

### 驗證

- Platform-admins 與 shelters page suites 16 tests passed。
- Double-click regressions 的 mutation request count 均為 1。
- TypeScript、Prettier、`git diff --check` passed。

---

## FT-018 Toast Lifecycle

### 修改元件

- `apps/web/components/ui/toast.tsx`
- `apps/web/components/ui/toast.test.tsx`
- `apps/web/app/globals.css`
- `apps/web/app/(management)/shelters/page.tsx`
- `apps/web/app/(management)/shelters/archived/page.tsx`
- `apps/web/e2e/organization-management.spec.ts`

### 修改內容

- Toast 預設 5 秒自動關閉。
- 提供可鍵盤操作且有明確 accessible name 的「關閉通知」按鈕。
- 支援 `onClose` 與 `messageKey`；message key 變更會重新顯示、重設 timer 並再次公告。
- Mount 時不自動移動 focus。
- Shelters／archived 使用遞增 `{id, text}` notice state，使相同訊息也能重新顯示。
- Mobile Toast 提高至 bottom 64px，避免 Next dev indicator 遮住左側文字。

### Route、Viewport 與操作驗證

- URLs：
  - `http://localhost:3001/shelters`
  - `http://localhost:3001/shelters/archived`
- Viewport：360×800、768px、desktop。
- 完成帳號／權限／恢復 mutation 後確認 Toast 出現。
- 點擊「關閉通知」應立即移除；不操作時約 5 秒後自動消失。
- 重複同一操作應重新顯示並重新公告相同訊息。
- 360×800 screenshot 確認文字與關閉按鈕完整、無遮蔽／overflow。

### 驗證

- Toast／shelters／archived／CSS targeted suites：25 tests passed。
- Organization management Chromium browser suite：3 passed。
- P1 四 viewport Axe：1 passed。
- Full Vitest：53 files／129 tests passed。
- Python：474 tests passed，另有 1 個既有 Starlette／httpx deprecation warning。
- TypeScript、Prettier、`git diff --check` passed。

---

## Phase B 最終驗證基準

FT-018 完成後，以 Phase B 最終工作樹執行：

```bash
cd apps/web
npm test
npm run typecheck
npm run format:check
PLAYWRIGHT_SKIP_WEBSERVER=1 npx playwright test e2e/organization-management.spec.ts
PLAYWRIGHT_SKIP_WEBSERVER=1 npm run test:p1:a11y

cd ../..
unset DATABASE_URL PYTHONPATH
uv run pytest
```

結果：

```text
Vitest：53 files／129 tests passed
TypeScript：passed
Prettier：passed
Organization management browser：3 passed
P1 four-viewport Axe：1 passed
Python pytest：474 passed
Git diff checks：passed
```

## Phase B 驗收結論

Phase B 已將 governance 高影響操作由直接 mutation 改為可預期的確認流程，補足 loading／empty 狀態邊界、同 frame 防重複送出，以及可關閉、會 timeout、可重複公告的 Toast lifecycle。FT-011～FT-018 均有獨立功能 commit、RED→GREEN 證據、route 操作方式與最新 regression evidence；Phase C 尚未開始。
