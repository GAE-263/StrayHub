# Quickstart：動物就醫歷史與照護提醒行事曆

本文件是 feature 006 實作完成後的本機驗收流程。指令沿用專案既有工具；`scripts.seed_medical_care` 與新測試會在本功能實作階段新增。

## 1. 啟動依賴與建立資料

```bash
docker compose -f infra/local/docker-compose.yml up -d postgres minio
uv sync
uv run alembic upgrade head
uv run python -m scripts.seed_local
uv run python -m scripts.seed_medical_care
npm --prefix apps/web install
```

`scripts.seed_medical_care` 無參數時即使用可重複執行的 `full` profile；本機權限矩陣帳號沿用 `local-only-password`。若要保存可機器比對的 occurrence ID、畫面欄位與各 bucket 精確總數，執行：

```bash
uv run python -m scripts.seed_medical_care --expected-output /tmp/medical-care-full-manifest.json
```

seed 必須固定建立：

- ORG-A（`Asia/Taipei`）與 ORG-B，且兩者都有相同格式但不同 id 的動物／紀錄／提醒。
- SHELTER_ADMIN、已授權 STAFF、未授權 STAFF、被指派 VOLUNTEER、未指派 VOLUNTEER。
- active 與非 active 動物。
- 單次、每天、每週、每月 31 日、每三個月、每年與無結束日 series。
- 今天待處理、較早逾期、今天完成／略過／取消、改期及未來七日 occurrence。
- 同一動物同日多筆 medical record 與既有 care report。
- 至少 100 隻動物／500 筆 mixed-state occurrence performance fixture。

## 2. 啟動 API 與 Web

分別在兩個終端執行：

```bash
uv run uvicorn services.api.app.main:app --reload
```

```bash
npm --prefix apps/web run dev
```

提醒的核心 Agenda／Calendar 不需要啟動 Worker；第一階段沒有外部通知或 occurrence materialization job。

### Playwright 真實 API 驗收前置

Care Agenda 的 100／500 Playwright suite 會使用真實 API 與固定本機 seed，不使用 production 或共用遠端資料。啟動 API 與 Web 前，在 repo root 設定：

```bash
export STRAYHUB_TEST_DATABASE_URL=postgresql://strayhub:strayhub@127.0.0.1:65432/strayhub
export DATABASE_URL=postgresql+asyncpg://strayhub:strayhub@127.0.0.1:65432/strayhub
export API_INTERNAL_URL=http://127.0.0.1:8000
export STRAYHUB_MEDICAL_E2E_SEED_ALLOWED=1
```

- `scripts.seed_medical_care` 在 `agenda-e2e` profile 下 MUST 要求 `STRAYHUB_MEDICAL_E2E_SEED_ALLOWED=1`，並拒絕 host 不是 `127.0.0.1`／`localhost` 的測試資料庫 URL。
- Playwright seed helper MUST 從 `apps/web/e2e/fixtures/medical-care.ts` 解析 repository root，將其作為 subprocess `cwd`；不得依賴 `npm --prefix apps/web` 啟動後的目前目錄。
- Next.js 沿用 `API_INTERNAL_URL` 將 `/v1` 轉送至 API。執行 suite 前必須確認 `http://127.0.0.1:8000/healthz` 回傳 `{"status":"ok"}`；API 未啟動、環境缺少或 seed guard 拒絕時，測試應回報前置條件失敗，不得顯示成 Agenda UI assertion failure。
- 若由 Playwright 自動啟動 Web，API 仍須依本節另行啟動；若 API 與 Web 已手動啟動，使用既有 `PLAYWRIGHT_SKIP_WEBSERVER=1` 避免重複啟動 Web。

## 3. Contract-first Gate

實作前先將 `contracts/medical-care.openapi.yaml` 合併到 canonical OpenAPI，之後執行：

```bash
npm --prefix packages/contracts install
npm --prefix packages/contracts run generate
npm --prefix packages/contracts run check
```

不得手動編輯 `packages/contracts/src/openapi.ts`。FastAPI runtime schema、canonical YAML 與前端 generated type 必須一致。

## 4. 主要人工驗收

### A. 一分鐘內建立醫療歷史

1. 以 ORG-A 管理員登入，開啟單一動物頁。
2. 點「新增醫療紀錄」，只填發生時間、類型、標題與自由文字後儲存。
3. 驗證一分鐘內完成、同日第二筆不覆蓋第一筆，Timeline 以「已發生」呈現。
4. 選填輸入公斤體重，確認沒有藥量、警告或提醒內容被自動計算。
5. 修改後查看 Audit before／after；封存後確認沒有 hard-delete 操作。

### B. 一分鐘內建立每月／每三個月提醒

1. 在動物頁點「建立提醒」。
2. 建立每月 31 日提醒；查看 2 月落在最後一日、3 月恢復 31 日。
3. 建立 `monthly + interval=3`，確認 UI 顯示「每 3 個月」。
4. 確認藥名／固定劑量文字標示為「管理員輸入」，系統沒有劑量建議。
5. 確認第一階段表單沒有提前提醒設定，API 對舊 client 提交的 `advance_notice_days` 回傳驗證錯誤。

### C. 今日 Agenda 與完成三步驟

1. 開啟 `/care-calendar`，確認四區互斥：今天待處理、已逾期、今天已處理、未來七天；今天已處理卡片仍分別標示完成、略過或取消。
2. 每張卡可用動物名稱、完整收容編號、類型、時間與狀態識別；無照片／負責人仍可操作。
3. 對一筆提醒執行「處理 → 完成 → 確認」，可選填實際完成時間；確認三個主要步驟內完成，並分別記錄 `actual_completed_at`、server `recorded_at` 與 actor。
4. 逾期吃藥只顯示待處理／逾期，不得顯示漏藥或已給藥。
5. 測試略過、改期、取消都要求原因；改期保留原／新預定時間。

### D. 修改單次與未來

1. 對週期 occurrence 選「只修改這一次」，確認相鄰 occurrence 不變。
2. 選「修改這一次及未來提醒」，確認新 segment 從目標 ordinal 生效。
3. 已完成的過去 occurrence、action、scheduled snapshot 與 Timeline 都不變。
4. 停止 series 後不再產生未來待辦，過去仍可查。

### E. 動物今日摘要／Timeline

在同一動物驗證五個狀態：完全無事件、有事件但無待辦、仍有待辦、有逾期、載入失敗。Timeline 必須同時找到 care report、medical record、reminder action 與 pending scheduled item，且「已發生」／「預定」不能只靠顏色區分。

## 5. 權限與隔離驗收

1. 已授權 STAFF 可讀／維護 medical record 與處理 occurrence，但不可修改未來 series。
2. 未授權 STAFF 即使直接輸入 URL，也不得先取得 medical payload；回應不洩漏內容或存在性。
3. 被指派 VOLUNTEER 只看到單次 animal identity、時間、標題、指示與狀態；看不到完整 Timeline、體重、診所、附件或其他提醒。
4. 撤銷 membership／改指派後，舊頁重新送出必須被拒絕。
5. 以 ORG-A session 查 ORG-B animal、record、media、series、occurrence id，全部不得查看、修改或推測存在性。
6. 使用 runtime DB role 執行 isolation matrix，確認 FORCE RLS 阻擋跨 tenant association／action。
7. 未授權 STAFF 查詢 `/v1/management/audit?resource_type=MedicalRecord&resource_id=...` 時，不得取得 before／after 或推測紀錄存在；授權 STAFF 可從醫療紀錄的只讀 Audit 面板追溯修改。

```bash
uv run pytest tests/isolation/test_cross_tenant_resource_matrix.py -q
```

## 6. 並行、冪等與附件

- 兩位人員以相同 `expected_version` 同時完成同一 virtual occurrence：只允許一位成功；另一位收到 409 與最新安全狀態，且只有一筆正常 terminal projection。
- 相同 `Idempotency-Key` + 相同 payload 重送：回原結果；相同 key + 不同 payload：409。
- 完成時未填 `actual_completed_at` 應等於 server `recorded_at`；可記錄較早的實際時間，但晚於 `recorded_at + 5 分鐘` 必須拒絕。
- 修改或封存 stale MedicalRecord version：409，未送出的文字仍保留在 UI。
- 上傳有效 JPEG／PNG／WebP：清理 EXIF、只回短效 signed URL；跨 tenant media id、未 formal media、偽裝 MIME 與不支援文件被拒絕。
- 附件送出失敗時，文字內容不能被空白成功狀態取代，UI 明確提示可重試附件。

## 7. 時區與 recurrence 驗收

- `Asia/Taipei` 凌晨事件依收容所本地日分組，不落到 UTC 前一日。
- 以具有 DST 的測試 timezone 驗證 gap 移到第一個有效 instant、fold 採第一次 instant。
- timezone 改變後，future occurrence 保持 local wall-clock、UTC 改變、occurrence id 不變；已結案 snapshot 不變。
- 舊 cursor 遇 `timezone_version` 改變回 409，刷新後無重複／遺漏。
- 建立跨多年的 daily series 與 completed／skipped／rescheduled exceptions，走完 overdue cursor：`total_count` 精確、頁間無重複／遺漏，且不 materialize 全部 occurrence。

## 8. 自動測試與品質門檻

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy services scripts
uv run pytest
npm --prefix apps/web run test
npm --prefix apps/web run test:e2e:p0
npm --prefix apps/web run test:axe
npm --prefix apps/web run test:visual
npm --prefix packages/contracts run check
```

Feature 專屬測試至少涵蓋：

```bash
uv run pytest \
  tests/unit/test_organization_timezone.py \
  tests/unit/test_care_recurrence.py \
  tests/unit/test_care_reminder_state.py \
  tests/contract/test_medical_care_contract.py \
  tests/contract/test_medical_records_contract.py \
  tests/contract/test_care_reminder_series_contract.py \
  tests/contract/test_care_agenda_contract.py \
  tests/contract/test_medical_timeline_contract.py \
  tests/integration/test_medical_care_migration.py \
  tests/integration/test_medical_records.py \
  tests/integration/test_care_reminder_series.py \
  tests/integration/test_care_agenda.py \
  tests/integration/test_care_reminder_actions.py \
  tests/integration/test_care_reminder_concurrency.py \
  tests/integration/test_medical_timeline.py \
  tests/integration/test_medical_care_audit.py \
  tests/security/test_medical_care_authorization.py \
  tests/security/test_medical_record_media_scope.py \
  tests/security/test_assigned_care_authorization.py \
  tests/security/test_medical_content_boundaries.py \
  tests/isolation/test_cross_tenant_resource_matrix.py \
  tests/performance/test_care_agenda_performance.py
```

Playwright 需將 `/care-calendar`、動物今日摘要／Timeline、管理 dialogs 與 assigned-care 頁納入 360／768／1024／1440 viewport、鍵盤、axe 與 visual baseline；dialog 驗證 focus trap、Escape、focus restore、busy 防重送與 live status。

## 9. 代表性使用者驗收方法

- 至少邀請 10 名代表性收容所管理員完成 SC-001、SC-002 與 SC-009；至少 10 名授權工作人員完成 SC-003 與 SC-004，同一人可參與多個適用情境，但管理員與工作人員兩個群體分開統計。
- 「第一次使用」表示未看過該功能操作示範，只能閱讀畫面文字；測試者不得在計時中接受引導。
- 每個情境記錄開始／完成時間、主要操作步驟、是否成功、是否求助及觀察備註；對明載 90% 門檻的 SC-001、SC-002、SC-004 與 SC-009，10 人中至少 9 人符合門檻才達標；SC-003 依下列獨立規則判定。
- 若實際可招募人數不足 10，不得宣稱 90% 達標；先將結果標示為探索性證據並安排補測。

### SC-003 兩分鐘找齊待辦流程

1. 使用 T017 的固定 `agenda-e2e` profile 建立 100 隻動物／500 筆 mixed-state occurrence，並由 seed 產生不向受測者顯示的 expected manifest。每個 `today_pending`／`overdue` 項目同時包含內部 `occurrence_id`，以及畫面可見的 bucket、動物名稱、完整收容編號、提醒類型、標題、organization-local 預定時間與狀態；manifest 另保存各 bucket 精確總筆數。
2. 受測工作人員從未套用篩選的 `/care-calendar` 開始；主持人只說明「請找出所有今天待處理及已逾期事項」，不得提供操作路徑或篩選提示，並在受測者表示完成時停止計時。
3. 每次 SC-003 驗收只有在 120 秒內完成，且受測者回報的兩區總筆數與以畫面可見欄位識別的事項，依重複筆數和 expected manifest 完全一致時才通過；不要求受測者辨識內部 occurrence ID。至少 10 名受測工作人員須全部通過才能宣稱 SC-003 達標。系統四區的完整 ID 集合、唯一性與分類正確率另由 integration／Playwright fixture 驗證 100%。
4. 記錄每位受測者的開始／完成時間、耗時、使用的篩選或操作、expected／actual bucket total、畫面可見比對欄位、遺漏／誤列數及是否求助；不得以後端 p95 或自動化測試時間代替真人操作時間。
5. 同一批授權工作人員可接著執行 SC-004，但 SC-003 與 SC-004 必須分別計時及判定。

## 10. Agenda 效能量測方法

1. 使用固定 seed 建立 100 隻動物及 500 筆 mixed-state occurrence；資料必須涵蓋四個 bucket、單次／週期提醒、terminal／rescheduled exceptions 與長期 daily series。
2. 使用單一服務程序及已完成 migration、seed 的本機 PostgreSQL；關閉 reload／debug。參考機器至少具備 4 個 logical CPU 與 8 GiB RAM。
3. 計時從 Agenda application service 開始處理到 response model 完成 serialization；包含資料庫查詢與 recurrence projection，不包含 migration、seed、程序啟動、網路傳輸及瀏覽器 render。
4. 每輪先執行 5 次不計分暖機，再連續執行 100 次；完整執行 3 輪，三輪皆須 p95 ≤ 1 秒且分類正確率為 100%。不得挑選最佳輪次取代失敗輪次。
5. 驗收紀錄保存實際指令、commit、固定 seed 識別、資料筆數、每輪 p50／p95／max、查詢數，以及作業系統、CPU／RAM 與 PostgreSQL 版本。低於參考硬體的結果可保留作診斷，但不能單獨宣告門檻失敗。

## 11. 完成條件

- `spec.md` 的所有 Given／When／Then 與 SC-001～SC-009 都有對應自動或人工證據。
- 依第 10 節固定方法量測的三輪 Agenda server-side projection 均為 p95 ≤ 1 秒，且分類正確率 100%。
- canonical OpenAPI、generated contracts 與 runtime response 無 drift。
- Migration 可從空資料庫 bootstrap，也可由前一 Alembic head upgrade。
- 未授權跨收容所矩陣為 0 筆資料洩漏；所有正式 mutation 可稽核。

## 12. 驗收紀錄

實作完成後在本節保留實際結果；不得只寫「通過」，需填入可重現的版本、環境、樣本與證據。2026-08-16 的完整紀錄見 [`evidence/t097-validation-2026-08-16.md`](evidence/t097-validation-2026-08-16.md)。自動化 gate 已通過；正式 10 名管理員及 10 名工作人員的人工樣本尚未執行，因此 T097 與 release gate 維持未完成。

### 執行基準

| 項目 | 實際值 |
|---|---|
| 驗收日期／執行人 | 2026-08-16／Codex 自動化與探索性操作；正式真人驗收待執行 |
| Commit／branch | `ea400d6bb5fe30beab6835bb4ba40ba126bd0e8c`／`dev/animal_record`，驗收工作樹含未提交功能變更 |
| 作業系統、CPU／RAM | macOS 15.5 arm64／Apple M4 Pro 14 cores／24 GB |
| PostgreSQL／Python／Node 版本 | PostgreSQL 16.13／Python 3.14.3／Node 22.23.1 |
| Seed profile／固定 seed 識別／資料筆數 | `agenda-e2e`／manifest SHA-256 `c0b90c3b35689bb1c766bb43059962e442a671784f3a53af3c54ffa99493a0bd`／100 隻動物、500 筆 occurrence，四區各 125 |

### 自動化與效能證據

| 證據 | 實際指令或 profile | 結果與統計 | Log／artifact |
|---|---|---|---|
| Ruff／Pytest／mypy | repo-root 完整 Ruff、pytest、mypy | Ruff 通過；pytest 431 passed；mypy 197 source files、0 issues | [`evidence/t097-validation-2026-08-16.md`](evidence/t097-validation-2026-08-16.md) |
| Vitest／Playwright／axe／visual | web Vitest、production Playwright、獨立 axe／visual | Vitest 46 files／87 tests；Playwright 123 passed／6 opt-in skipped；axe 15 passed；visual 15 passed／6 opt-in skipped；0 failed | [`evidence/t097-validation-2026-08-16.md`](evidence/t097-validation-2026-08-16.md) |
| OpenAPI drift／migration／隔離矩陣 | canonical generate/check；完整 pytest contract、migration、isolation/security | 通過；跨 tenant 測試無資料洩漏 | [`evidence/t097-validation-2026-08-16.md`](evidence/t097-validation-2026-08-16.md) |
| Agenda 三輪效能 | `scripts/measure_care_agenda.py`；每輪 5 warmups + 100 samples | p95 25.313／23.640／24.894 ms；每 sample 7 queries；三輪分類 100%、遺漏 0、誤列 0 | [`evidence/t097-agenda-performance.json`](evidence/t097-agenda-performance.json) |

### 代表性使用者證據

每位受測者各列一筆或多筆適用 SC；只使用匿名編號，不記錄不必要的個人資料。

| 匿名編號 | 角色群體 | SC | 開始／完成時間 | 耗時 | 主要步驟 | Expected／actual／遺漏／誤列 | 是否求助 | 通過 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| EXP-A01 | 管理員（agent 探索） | SC-001 | 未保留精確 wall-clock | 21.872s | 動物頁→新增醫療歷史→送出 | 建立成功；未見產品錯誤 | 否；工具 locator 修正 1 次 | 探索成功 | 非真人，不計正式通過率 |
| EXP-A01 | 管理員（agent 探索） | SC-002 | 未保留精確 wall-clock | 133.495s | 建立每三月提醒 | native datetime 未觸發 React state，沒有 API POST | 是，嘗試工具 fallback | 無法判定 | 工具限制，不判產品成敗 |
| EXP-A01 | 管理員（agent 探索） | SC-009 | 未保留精確 wall-clock | 0.752s | 查看動物今日摘要 | 正確辨識有逾期待辦 | 否 | 探索成功 | 非真人，不計正式通過率 |
| EXP-S01 | 工作人員（agent 探索） | SC-003 | 未保留精確 wall-clock | 3.980s | 查看 Agenda 四區 | 發現每區 50 筆截斷；修正後自動核對 125／125／125／125、遺漏 0、誤列 0 | 否 | 發現缺陷後已修正 | 真人 expected／actual 尚待驗收 |
| EXP-S01 | 工作人員（agent 探索） | SC-004 | 未保留精確 wall-clock | 12.991s | 2 個主要步驟完成提醒 | 完成後移入已完成區，待處理區不再顯示 | 否 | 探索成功 | 非真人，不計正式通過率 |
| FORMAL-A01～A10 | 管理員 | SC-001／002／009 | 待真人驗收 | 待真人驗收 | 依第 9 節 | 待真人驗收 | 待真人驗收 | 待真人驗收 | 正式樣本 0／10 |
| FORMAL-S01～S10 | 授權工作人員 | SC-003／004 | 待真人驗收 | 待真人驗收 | 依第 9 節 | 待真人驗收 | 待真人驗收 | 待真人驗收 | 正式樣本 0／10 |
