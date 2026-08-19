# StrayHub Frontend Phase D 完成摘要

- **Phase：** Phase D — 醫療與提醒高風險操作
- **範圍：** FT-030～FT-031
- **完成日期：** 2026-08-19
- **Branch：** `dev/frontend_review`
- **狀態：** 2／2 任務已完成、驗證並各自建立獨立功能 commit。

## Commit 索引

| 類型              | 主題                               | Commit                                                               |
| ----------------- | ---------------------------------- | -------------------------------------------------------------------- |
| FT-030            | 醫療紀錄封存二次確認               | `04e672b fix(web): confirm medical history archival`                 |
| FT-031            | Reminder Dialog 關閉後保留成功回饋 | `07b3476 fix(web): preserve reminder success feedback after dialogs` |
| Final gate repair | 補齊登入後 session E2E fixture     | `b5ff243 test(web): complete login session fixture`                  |

---

## FT-030 醫療紀錄封存二次確認

### 修改元件

- `apps/web/components/ui/dialog.tsx`
- `apps/web/features/medical-care/MedicalHistoryPanel.tsx`
- `apps/web/features/medical-care/MedicalHistory.test.tsx`
- `apps/web/e2e/medical-history.spec.ts`
- `frontend_task.md`

### 修改內容

- 「封存」不再直接送出 mutation，而是先開啟 native modal `alertdialog`。
- 確認畫面顯示目標紀錄、`有效 → 已封存`、編輯原因，以及歷史資料保留說明。
- 取消不送出 request，且保留醫療紀錄編輯表單與原因。
- Confirm 才送出 archive request；同步 ref lock 與 busy state 阻擋同一 render frame 重複提交。
- Request pending 時鎖定 confirm、cancel、close 與 Escape-driven close。
- 503 失敗時保留 Dialog、目標與原因，錯誤在 Dialog 內以 Alert 顯示，可直接 retry。
- 失敗後取消會清除 archive error，不會將 stale error 洩漏為頁面級 Alert。
- 成功後關閉 Dialog、重新載入資料並顯示 lifecycle Toast。

### RED → GREEN 證據

- RED 證明原本點擊「封存」會立即送出 POST，沒有 confirmation boundary。
- 第二個 RED 證明 archive error 原先只出現在 modal 背後，不可見／不可存取。
- 第三個 RED 證明 503 後取消會將 stale archive error 洩漏到頁面。
- GREEN browser flow涵蓋：
  - 開啟確認前與取消後 request count 為 0。
  - Dialog 顯示目標、before／after、reason 與 retention copy。
  - 首次503保留Dialog、reason與inline Alert。
  - Retry成功且總archive request count精確為2。
  - 成功Toast可見。

### URL 與操作驗收

- URL：`http://localhost:3001/animals/animal-a`
- Viewports：360×800、768×1024、1024×768、1440×900。
- 操作：
  1. 以有醫療紀錄管理權限的帳號登入。
  2. 在醫療紀錄輸入封存原因並點擊「封存」。
  3. 確認 AlertDialog 顯示紀錄目標、`有效 → 已封存`、原因與歷史保留說明。
  4. 點擊取消；確認沒有 request，原編輯原因仍保留。
  5. 再次封存並確認；request pending 時 controls 應鎖定。
  6. 成功後確認 Dialog 關閉且 Toast 出現。
- 預期前後差異：修改前點擊 destructive action 即執行；修改後必須經過明確、可取消、可重試且不可重複提交的確認邊界。

### 驗證

- Dialog／MedicalHistory focused Vitest：2 files／7 tests passed。
- Medical history Playwright：3 passed。
- Phase D routes responsive：animal profile與care calendar共8個viewport cases passed。
- Final source-only reviewer：PASS，無 blocking findings。

---

## FT-031 Reminder success feedback lifecycle

### 修改元件

- `apps/web/app/(management)/animals/[animalId]/page.tsx`
- `apps/web/features/medical-care/ReminderFormDialog.tsx`
- `apps/web/features/medical-care/ReminderActionDialog.tsx`
- `apps/web/features/medical-care/CareAgenda.tsx`
- `apps/web/e2e/care-reminder-series.spec.ts`
- `apps/web/e2e/care-agenda.spec.ts`
- `frontend_task.md`

### 修改內容

- Reminder Form／Action Dialog不再擁有會隨Dialog卸載的success message。
- Dialog成功後以localized callback message通知父層；animal profile與CareAgenda擁有lifecycle Toast。
- Dialog關閉後，成功Toast仍可見並由Toast lifecycle控制。
- Action success依操作顯示：
  - `提醒已完成`
  - `提醒已略過`
  - `提醒已取消`
  - `提醒已改期`
- 建立提醒成功顯示 `提醒已建立`。
- 建立失敗改用Dialog內Alert；Action failure也保留在Dialog內。
- Failure不關閉Dialog；retry成功後才關閉並顯示父層Toast。

### RED → GREEN 證據

- RED 證明create/action mutation成功且Dialog關閉後，success status不存在。
- 第二個 RED 證明create 422原本只有status paragraph，缺少Dialog內Alert語意。
- GREEN browser flows涵蓋：
  - Create首次422：Dialog與error保留；retry成功後關閉並顯示 `提醒已建立`。
  - Action首次503：Dialog與error保留；retry成功後關閉並顯示 `提醒已完成`。
  - Create/action mutation request count均精確為2。

### URL 與操作驗收

#### 建立提醒

- URL：`http://localhost:3001/animals/animal-a`
- 操作：
  1. 點擊「建立提醒」。
  2. 填寫類型、標題、第一次執行時間與重複週期。
  3. 提交成功後確認Dialog關閉，頁面外仍顯示 `提醒已建立` Toast。
  4. 模擬失敗時確認Dialog保持開啟，錯誤Alert與表單值保留。

#### 處理提醒

- URL：`http://localhost:3001/care-calendar`
- 操作：
  1. 在提醒卡片點擊「處理」。
  2. 選擇完成、略過、取消或改期並確認。
  3. 成功後確認Dialog關閉，對應成功Toast仍可見。
  4. 模擬失敗時確認Dialog與錯誤保留，可直接retry。

### 驗證

- Reminder focused Vitest：3 files／5 tests passed。
- Create／Action Playwright：3 passed。
- Phase D routes responsive：8 passed。
- Final source-only reviewer：PASS，無 blocking findings。

---

## Final gate repair：登入後 E2E fixture

Phase D final P0 gate揭露既有 `mockLoginApi` 不完整：login與context mutation雖回200，redirect到 `/` 後的 `/v1/auth/me`、`/v1/organizations`、`/v1/management/dashboard` 會落到真實server並回401，導致auth state被清除、頁面導回 `/login`。部分viewport先前只因URL assertion搶在401前執行而偶發通過。

### 根因與修正

- Playwright trace逐層證實三個未mock boundaries及401 response。
- `mockLoginApi`補齊登入後profile、organizations與empty dashboard responses。
- 一般收容所使用者使用 `platform_role: null`；組織角色保留在membership。
- Membership依傳入organizations生成，保留各自role/status。
- Dashboard role跟隨第一個active organization role，避免遮蔽SHELTER_ADMIN UI。
- 三個新增的read-only handlers限制為GET；非預期method回405，避免fixture遮蔽frontend HTTP method regression。

### 驗證與 review

- RED：login-home tests會在redirect後回到 `/login`。
- GREEN：login-home單worker 9／9 passed。
- Canonical P0 E2E：94／94 passed。
- Final source-only reviewer：PASS，無 reliability或correctness finding。

---

## Phase D 最終驗證基準

```bash
cd apps/web
npm test
npm run typecheck
npm run format:check
PLAYWRIGHT_SKIP_WEBSERVER=1 npm run test:e2e:p0
PLAYWRIGHT_SKIP_WEBSERVER=1 npm run test:p1:e2e
PLAYWRIGHT_SKIP_WEBSERVER=1 npm run test:a11y:browser
PLAYWRIGHT_SKIP_WEBSERVER=1 npm run test:p1:a11y
PLAYWRIGHT_SKIP_WEBSERVER=1 npx playwright test \
  e2e/medical-history.spec.ts \
  e2e/care-reminder-series.spec.ts \
  e2e/care-agenda.spec.ts

cd ../..
unset DATABASE_URL PYTHONPATH
uv run pytest
```

結果：

```text
Full Vitest：53 files／137 tests passed
TypeScript：passed
Prettier：passed
FT-030/031 browser flows：6 passed
Canonical P0 E2E：94 passed
P1 E2E：2 passed
P0 browser accessibility：15 passed
P1 browser accessibility：1 passed
Python pytest：474 passed
Git diff checks：passed
```

Python suite仍有1個既有Starlette／httpx deprecation warning；不影響pass結果。

Visual snapshot更新與全頁面視覺基線屬Phase E（FT-034～FT-036），未用snapshot更新掩蓋Phase D功能變更。

## Phase D 驗收結論

Phase D已將醫療紀錄封存改為具備明確影響說明、取消邊界、busy lock、inline failure recovery與成功Toast的governed mutation；同時將提醒建立／處理成功回饋提升至父層lifecycle，使Dialog關閉後仍可見，並確保錯誤留在Dialog內可重試。FT-030與FT-031均有獨立功能commit、RED→GREEN browser證據、四viewport responsive與Axe evidence、final independent review，以及最新full frontend／Python regression evidence。
