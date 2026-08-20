# StrayHub Frontend Phase E 完成摘要

- **Phase：** Phase E — 內容、次要頁面與視覺門檻
- **範圍：** FT-032～FT-036
- **完成日期：** 2026-08-20
- **Branch：** `dev/frontend_review`
- **狀態：** 5／5 任務已完成、驗證並各自建立獨立 commit。

## Commit 索引

| 任務   | 主題                                   | Commit                                                            |
| ------ | -------------------------------------- | ----------------------------------------------------------------- |
| FT-032 | 統一管理工作台產品文案                 | `7c4fc61 refactor(web): standardize management interface copy`    |
| FT-033 | 標準化 Shelter Cage／Area 清單         | `79f2866 refactor(web): align shelter area list presentation`     |
| FT-034 | 排除 Next.js dev indicator visual 噪音 | `0da3c7a test(web): remove dev indicator from visual evidence`    |
| FT-035 | 將 viewport 拆為獨立 visual cases      | `9f899b0 test(web): isolate visual checks by viewport`            |
| FT-036 | 補齊治理與志工 visual baselines        | `a0d8fd0 test(web): cover governance and volunteer visual states` |

---

## FT-032 管理工作台產品文案

### 修改內容

- 導航、頁面主標題、按鈕、欄位與狀態改以繁中產品語言為主。
- `AI Review Queue`／`AI Queue` 統一為「AI 人工覆核」。
- `Audit Query`、`Report Inbox`、`Detail`、`Timeline`、`Membership`、`Active Shelter Context`改為一致繁中；必要技術詞留在括號或輔助說明。
- 新增集中式copy contract，避免主要產品文案再次漂移或混用「審核／覆核」。

### RED → GREEN

- RED：新增copy contract與rendered heading assertion後，舊英文主標題、`Timeline →`與不一致用詞均失敗。
- GREEN：導航、首頁、AI覆核、稽核、回報詳情、近期歷程、成員資格與目前收容所文案一致；locator與E2E同步更新。

### URL 與操作驗收

- URL：`http://127.0.0.1:3001/`、`/animals`、`/ai-review`、`/settings/audit`、`/reports`、`/reports/report-a`。
- 操作：依序檢查側邊導覽、頁面主標題、欄位、主要action及error/loading states。
- 預期差異：eyebrow可保留英文；所有使用者決策與主要資訊層級以一致繁中呈現。

### 驗證與 review

- 360／1440共10個acceptance assertions通過，人工pixel review無截斷、overflow或異常換行。
- 初次review的2個Medium與1個Low均修正；replacement reviewer PASS。

---

## FT-033 Shelter Cage／Area 標準清單

### 修改內容

- `/shelters`「籠舍／區域」改為semantic `<ul>/<li>`及`.list-card` surface rows。
- API values仍維持`area`／`cage`；顯示層以繁中類型與狀態Badge呈現。
- 補上明確EmptyState；details載入期間優先顯示loading，不會短暫誤報empty或殘留舊rows。

### RED → GREEN

- RED：empty/non-empty contracts證明舊版raw list、英文values與缺少EmptyState；reviewer finding另以RED重現details pending時的false EmptyState。
- GREEN：非空、空白與延遲載入三種邊界都有獨立測試；表單送出的API values不受顯示層本地化影響。

### URL 與操作驗收

- URL：`http://127.0.0.1:3001/shelters`。
- 操作：以SHELTER_ADMIN選擇含資料與空資料的收容所，觀察loading、清單rows、Badges、EmptyState與建立表單。
- 預期差異：修改前是無樣式英文raw list；修改後為可掃讀的單欄／橫列清單、繁中Badge與清楚狀態邊界。

### 驗證與 review

- Organization E2E於360／1440通過且無horizontal overflow；人工pixel review確認rows、Badges與表單對齊。
- 初次review的Medium loading finding已修正；replacement reviewer PASS。

---

## FT-034 Visual runtime 去除dev indicator

### 修改內容

- Next 15.5依官方設定加入`devIndicators: false`。
- 新增config contract與fresh dev runtime test。
- 每次`toHaveScreenshot`前都assert `nextjs-portal`不可見；不以mask、CSS注入或baseline update隱藏indicator。

### RED → GREEN

- RED：config為`undefined`且fresh runtime存在visible `nextjs-portal`。
- GREEN：config contract、runtime guard與人工screenshot均確認左下Next indicator消失。
- 此任務刻意不更新snapshot；舊baseline與已接受產品UI的真實差異留給FT-035／036完整回報與review。
- 獨立source reviewer PASS，確認沒有以mask、CSS注入或baseline更新掩蓋indicator，且未提前進入FT-035／036範圍。

### URL 與操作驗收

- URL：`http://127.0.0.1:3001/login`及所有visual matrix routes。
- 操作：啟動fresh dev server，確認頁面左下不出現Next dev indicator，再執行visual test。
- 預期差異：baseline只反映產品pixels，不含開發工具overlay。

---

## FT-035 Viewport case isolation

### 修改內容

- 將每個route內串行執行四viewport的單一test，改為route × viewport獨立Playwright tests。
- Test title包含完整route與`width×height`；snapshot filenames維持`${slug}-${width}.png`相容格式。
- 每個case保留token init、API mock、navigation、main visibility、indicator guard與screenshot流程。

### RED → GREEN

- RED：`playwright --list`只有17 tests，route title無viewport；360 failure會短路同route其餘viewport。
- GREEN：list增至62 tests；40個P0 route × viewport cases可獨立完成並各自回報snapshot差異。
- Fresh server serial evidence證明40個P0 cases全部執行，不再被第一個failure短路。
- Caveat：第一次parallel run因先前`next build`破壞reuse中的dev `.next`而得到HTTP 500；health檢查與重啟後，以Playwright-managed fresh server、`--workers=1`執行的serial run才是authoritative evidence。

### 驗收重點

- 任一viewport差異只使自己的case失敗；同route其他viewport仍會執行。
- Snapshot命名與既有baseline相容；FT-035沒有更新任何PNG。
- 獨立source reviewer PASS，無severity findings。

---

## FT-036 治理與志工 visual baselines

### Coverage

| 類別                               |                  Matrix | Snapshots |
| ---------------------------------- | ----------------------: | --------: |
| 既有P0主頁                         | 10 routes × 4 viewports |        40 |
| 治理主頁                           |  3 routes × 4 viewports |        12 |
| 志工主頁                           |  5 routes × 4 viewports |        20 |
| Batch confirmation／partial result |  2 states × 4 viewports |         8 |
| **總計**                           |                         |    **80** |

治理routes：

- `/shelters`
- `/shelters/archived`
- `/platform-admins`

志工routes：

- `/volunteer-application?entry=entry&id_token=id-token`
- `/volunteers/applications`
- `/settings/volunteer-access`
- `/volunteers/access`
- `/volunteers/notifications`

### Fixture與state evidence

- 新增visual-only governance fixture，沿用已測試organization/platform governance response shapes。
- Fixture提供PLATFORM_ADMIN、active shelter context及非空memberships、areas、archived shelters、platform admins；不修改production或通用fixture。
- Batch confirmation直接截取真正的`alertdialog`。
- Batch partial result等待「批次已建立」，scroll至「逐筆結果」後截取viewport，避免100-row full-page背景稀釋訊號。

### RED → GREEN與baseline governance

- RED：visual list由62擴至77 tests；12治理、20志工主頁、4 batch cases均因missing snapshots失敗，證明coverage缺口，沒有UI/assertion failure。
- 先將12治理、20志工主頁及8 batch state candidates製成contact sheets做pixel review。
- 初版batch full-page evidence因Dialog被超長背景稀釋而不批准；改成focused `alertdialog`與result viewport後重新review才通過。
- 確認無錯誤頁、Next indicator或明顯overflow後，才執行explicit snapshot update。
- `test:visual:update -- --workers=1`：82 passed；緊接normal no-update run：82 passed。
- 最終snapshot inventory為80 PNGs，route／viewport／state命名唯一，無stale batch names。
- 獨立source reviewer PASS，無severity findings或baseline-masking risk。

### URL 與操作驗收

1. 啟動web app：`npm --prefix apps/web run dev`。
2. 開啟上述治理與志工URLs。
3. 依序切換360×800、768×1024、1024×768、1440×900。
4. 檢查主內容、桌面／行動導覽、list/table controls、Badges、EmptyState及長清單。
5. 在志工applications選擇「目前篩選結果全部」，開啟「確認並建立批次」。
6. 確認AlertDialog內容、取消／送出按鈕均完整可見；送出後scroll至「逐筆結果」，確認進度、success/conflict badges與Toast。
7. 預期畫面沒有Next dev indicator、水平overflow、錯誤頁或被截斷的主要controls。

---

## Phase E 最終驗證基準

```bash
cd apps/web
npm run test
npm run typecheck
npm run format:check
npm run test:e2e:p0
npm run test:p1:e2e
npm run test:a11y:browser
npm run test:p1:a11y
npm run test:visual

cd ../..
unset DATABASE_URL PYTHONPATH
uv run pytest
```

2026-08-20於全部五個FT commits完成後fresh執行結果：

```text
Vitest：55 files／140 tests passed
TypeScript：passed
Prettier：passed
P0 E2E：94 passed
P1 E2E：2 passed
P0 browser accessibility：15 passed
P1 browser accessibility：1 passed
Visual：82 passed（default 7 workers、no snapshot update）
Python pytest：474 passed
```

Python suite仍有1個既有Starlette TestClient／httpx deprecation warning，不影響pass結果。

## Phase E 驗收結論

Phase E已完成管理工作台產品文案一致化、Shelter次要清單資訊層級、visual runtime去噪、viewport failure isolation，以及治理／志工主要狀態與確認流程的四viewport baseline。所有FT任務均有獨立commit、RED→GREEN證據、適用任務的URL／manual acceptance步驟、fresh regression gates及獨立review。最終80張baseline包含40張既有P0 accepted UI刷新，以及經本任務contact-sheet review後建立的40張新治理／志工／batch candidates；normal visual suite在不更新snapshot的情況下82／82通過。

Phase E至此停止；未包含後續phase或未要求的產品功能擴充。
