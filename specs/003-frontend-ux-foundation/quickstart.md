# 快速開始：前端 UX Foundation 驗證

本指南用於實作完成後驗證 P0。它不建立新的後端資料，也不取代既有完整本機門檻。

## 前置條件

- 位於專案根目錄 `/Users/js/gae_cowork_project/StrayHub`。
- Docker Desktop、Node.js、npm、Python／uv 可用。
- 已依 README 啟動 PostgreSQL／MinIO、完成 migration、local seed 與必要的 timeline seed。
- 可登入下列本機帳號：

| 帳號 | 用途 |
| --- | --- |
| `local-volunteer-a` | 志工手機確認與照護回報 |
| `local-staff-a` | ORG-A 工作人員管理流程 |
| `local-shelter-admin-a` | ORG-A 設定與管理權限 |
| `local-platform-admin` | 切換 ORG-A／ORG-B 與平台情境 |
| `local-staff-b` | 驗證 ORG-B 租戶隔離 |

密碼沿用 README 的 local-only password；不得使用正式環境 credentials。

## 設定驗證

實作階段首次安裝後，確認 package lock 與生成設定存在，再執行：

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run test
npm --prefix apps/web run format:check
npm --prefix apps/web run build
```

預期結果：既有頁面可 build，新增 UI primitives 可被 `@/*` alias 匯入，未遷移頁面視覺與資料行為沒有明顯變化。

安裝並建立 `apps/web/package.json` scripts 後，先驗證測試工具鏈；此階段不要求 P0／P1 spec 已全部建立：

```bash
npm --prefix apps/web exec -- playwright --version
npm --prefix apps/web run test:e2e:tooling
```

預期結果：`@playwright/test`、`@axe-core/playwright` 與 Chromium binary 可被載入，tooling smoke 可完成。完成對應 P0／P1 browser spec 後，再執行完整 gate：

```bash
npm --prefix apps/web run test:e2e:p0:list
npm --prefix apps/web run test:a11y:browser:list
npm --prefix apps/web run test:e2e:p0
npm --prefix apps/web run test:visual
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:axe
```

預期結果：P0 list scripts 能列出登入／管理首頁、Management Shell、志工核心、管理核心、狀態回饋、響應式與 keyboard tests；P0 browser smoke、固定 viewport screenshot 與 axe baseline 通過。`test:axe` 必須與 `test:a11y:browser` 使用同一組 P0 axe tests；首次建立 baseline 時只能由 reviewer 審核截圖後執行 `test:visual:update`。P1 另由 `test:p1:e2e` 與 `test:p1:a11y` 驗證，不納入 P0 gate。

## 手動驗收流程

### 1. 管理 Shell 與 Active Shelter Context

1. 以未登入狀態開啟 `/login`，完成登入後以 `local-staff-a` 開啟 `/`、`/animals`、`/animals/[animalId]`、`/animals/[animalId]/timeline`、`/reports` 與 `/reports/[reportId]`。
2. 確認每頁都能辨識目前頁面、目前收容所、登入者與返回位置。
3. 以 `local-platform-admin` 切換 ORG-A／ORG-B，確認切換中、成功與失敗訊息；切換後不顯示另一收容所資料。
4. 以不同角色檢查 Sidebar 只顯示被授權的項目。
5. 在 360px 寬度開啟與關閉 mobile Sheet，確認目前項目、Escape、focus restore 與內容閱讀順序。

### 2. 動物、回報與 Timeline

1. 在 `/animals` 以名稱、收容編號、區域與狀態搜尋／篩選。
2. 驗證 loading、成功、空資料、搜尋無結果與錯誤都不是同一種呈現。
3. 開啟動物檔案、回報清單、回報詳細頁與 Timeline，確認 Breadcrumb、返回、主要 action 與目前篩選脈絡保持一致。
4. 用包含同日多筆回報的動物資料展開 Timeline，確認日期、每筆原始心得、觀察、照片數量、AI 狀態與人工狀態均保留。
5. 檢查「當日無回報」不會被顯示成「未觀察到明顯訊號」。

### 3. 志工手機流程

1. 以 `local-volunteer-a` 在 360px 寬度開啟 `/animal-confirmation`。
2. 以今日名單、QR Code 與部分收容編號分別找到候選動物，確認卡能清楚辨識身分並提供重新選擇。
3. 進入 `/care-report`，輸入代表性回報內容，確認草稿恢復與 canonical `saving` 狀態的 disabled／pending 行為；`saving` 不得與讀取中的 `loading` 混淆。
4. 模擬保存失敗或離線，確認原始輸入保留、錯誤靠近相關區域且提供重試。
5. 確認 AI processing／AI failure 不會被顯示成原始回報保存失敗，也不阻止人工流程。

### 4. 響應式矩陣

以下九個 route 構成完整 P0 route matrix；每個 route 都必須在四個 viewport 執行 screenshot、核心內容 overflow 與主要操作可用性檢查。需要登入的 route 使用既定 role／tenant fixture；`/login` 使用未登入狀態；志工 route 使用 `local-volunteer-a`。

| P0 route | 主要驗證內容 |
| --- | --- |
| `/login` | 未登入入口、欄位錯誤、canonical `saving`、登入成功、無授權與錯誤下一步 |
| `/` | 管理首頁 loading、empty、error、permission、Active Shelter Context 與主要入口 |
| `/animals` | 名稱／收容編號／區域／狀態搜尋、篩選、結果數量、空資料與無結果 |
| `/animals/[animalId]` | 動物身分、目前狀態、主要 action、Breadcrumb 與返回 |
| `/animals/[animalId]/timeline` | 日期、同日多筆、當日無回報、AI／人工狀態與展開閱讀 |
| `/reports` | 回報搜尋／篩選、狀態、日期、分頁與 detail link |
| `/reports/[reportId]` | 原始回報、照片、AI raw／validated、人工覆核、錯誤與權限狀態 |
| `/animal-confirmation` | 今日名單、QR Code、收容編號搜尋、身分確認與重新選擇 |
| `/care-report` | 草稿恢復、表單輸入、canonical `saving`、保存成功／失敗、重試與 AI 狀態 |

| Viewport | 必驗項目 |
| --- | --- |
| 360x800 | 單欄、Sheet 導覽、卡片／展開 row、44px touch target、無非必要水平溢出 |
| 768x1024 | 兩欄／filter 分組、長名稱換行、主要 action 仍易找 |
| 1024x768 | 完整管理 Sidebar、Breadcrumb、表格主要欄位與主要 action |
| 1440x900 | max content width、摘要與內容密度、無過度分散 |

每個 viewport 都要檢查長動物名稱、長錯誤訊息、放大文字與大量 filter。

P0 route coverage 不得以只通過 `/` 或清單頁代表完成；九個 route 必須各自留下 route name、viewport、登入角色／tenant、state fixture、screenshot／overflow 結果與失敗備註。

### 5. 鍵盤／螢幕閱讀器

1. 從頁面最上方只用 Tab 完成導覽、搜尋、篩選、動物確認、表單修正、保存與返回。
2. 開啟 Sheet、Dialog 與 AlertDialog，確認 focus trap、Escape、取消與 focus restore。
3. 確認欄位 label、description、error、loading、saving、success、permission 與 AI 狀態可被讀取；同一保存請求不得重複播報 `saving`。
4. 使用 macOS VoiceOver 完成志工回報與管理 Timeline 的主要閱讀流程；記錄標題順序、目前頁面、狀態與按鈕名稱。
5. 啟用 Reduce Motion，確認不靠動畫理解 loading、Sheet、Dialog 或成功訊息。

### 6. 可用性指標執行規範

- 志工與工作人員各至少 10 位代表性測試者；每組至少 9 位未受協助完成才可判定 90% 通過。
- SC-001：從 `/animal-confirmation` 找到指定動物、確認、填寫基本照護回報並保存；從 route 可操作開始計時，到看見原始回報已保存成功為止，門檻 90 秒。
- SC-002：從管理首頁找到指定動物、回報詳細頁或近期 Timeline；從管理首頁可操作開始計時，到開啟正確 detail／Timeline 並確認識別資訊為止，門檻 30 秒。
- 記錄 participant code、role、viewport、起訖時間、完成／失敗、錯誤、協助與備註；樣本不足或無可靠時間戳時標記 preliminary。

## 租戶與資料回歸

- ORG-A 與 ORG-B 建立相同 shelter number／相近名稱情境，確認頁面不顯示對方資料、筆數、狀態或存在性。
- 以 `local-staff-a` 嘗試開啟 `/shelters`、管理設定、AI Queue 與稽核頁面，確認沒有未授權管理操作。
- 以 `local-shelter-admin-a` 與 `local-platform-admin` 開啟 `/shelters`，確認可見操作符合既有角色與已驗證 Active Shelter Context；切換 ORG-A／ORG-B 或重新載入深連結後不得跨租戶顯示資料。
- 以平台管理員切換 context 後重新載入深連結，確認頁面依已驗證 context 重新取得內容。
- 檢查同日多筆 Timeline、原始心得、照片、AI raw／validated／human review 與草稿內容沒有因 UI migration 消失或被目前名稱覆蓋。

## P1 額外驗證（不納入 P0 門檻）

當 US5 的 P0 browser、responsive、keyboard、screen reader 與 visual evidence 已完成後，可獨立執行 `npm --prefix apps/web run test:p1:e2e` 與 `npm --prefix apps/web run test:p1:a11y`，驗證以下 P1 route：`/ai-review`、`/shelters`、`/settings/observation-options`、`/settings/qr-codes`、`/settings/reportable-scope`、`/settings/audit`。P1 沿用 P0 的 state、overlay、tenant 與 accessibility checklist；P1 未完成不得回頭阻擋已具備證據的 P0 門檻。

## 品質門檻

```bash
npm --prefix apps/web run quality
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e:p0
npm --prefix apps/web run test:visual
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:axe
./scripts/verify_local.sh
```

預期結果：前端 tests、typecheck、mobile／a11y tests、format、production build，以及完整本機資料／權限／租戶／AI failure 門檻通過。若只有文件或未遷移 P1 頁面尚未完成，不得以 P1 未完成阻擋已獨立驗收的 P0；但 P0 evidence 必須完整。

## 完成判定

- [ ] P0 route matrix 的所有 viewport screenshot 已審核。
- [ ] Playwright keyboard、Sheet／Dialog focus 與 axe browser baseline 通過。
- [ ] VoiceOver 與人工窄螢幕 checklist 完成。
- [ ] 志工 draft／save failure、AI failure、Timeline history 與 ORG-A／ORG-B isolation regression 通過。
- [ ] 既有 `npm run quality`、build 與完整 local 門檻通過。
- [ ] 已遷移頁面不再依賴對應 legacy class；尚未遷移頁面的 legacy CSS 有明確保留理由。
