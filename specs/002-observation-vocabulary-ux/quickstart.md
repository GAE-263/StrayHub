# Quickstart：觀察詞彙管理介面驗證

本指南用本機虛構資料驗證摘要、分組、搜尋／篩選、管理權限、停用／恢復／封存、歷史追溯與兩收容所隔離。它不需要正式 LINE、AI、GCP 或真實收容所資料。

## 前置條件

- Docker Desktop／Docker Compose
- Python 3.11+、`uv`
- Node.js 與 npm
- 位於專案根目錄 `/Users/js/gae_cowork_project/StrayHub`

## 啟動本機資料與服務

```bash
cp .env.example .env
docker compose -f infra/local/docker-compose.yml up -d postgres minio
uv run alembic upgrade head
uv run python -m scripts.seed_local
```

分別啟動 API 與管理前端：

```bash
uv run python -m uvicorn services.api.app.main:app --reload --host 127.0.0.1 --port 8000
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3000
```

開啟 <http://127.0.0.1:3000/login>，使用本機虛構帳號：

| 測試帳號 | 用途 |
| --- | --- |
| `local-platform-admin`／`local-only-password` | 切換至 `ORG-A`，驗證完整管理操作 |
| `local-staff-a`／`local-only-password` | 驗證 Staff 只能唯讀查看啟用詞彙 |
| `local-staff-b`／`local-only-password` | 驗證 `ORG-B` 資料隔離 |

登入後前往 `/settings/observation-options`。

## 手動驗收流程

### 1. 摘要與漸進式揭露

以 `local-platform-admin` 選擇 `ORG-A`：

1. 確認頂部顯示觀察類別、啟用中的選項、收容所自訂選項、已停用／封存選項四項摘要。
2. 確認平台預設／收容所自訂差異說明使用台灣繁體中文。
3. 確認初次進入只顯示類別摘要，未展開全部選項。
4. 展開一個類別，確認自訂區段先於平台預設；類別計數包含啟用、自訂與停用／封存。
5. 確認中文名稱是主要文字，stable code、來源、說明與最後修改資訊為次要文字。

預期結果：不需要閱讀完整長清單就能理解總量、資料來源與要管理的範圍。

### 2. 搜尋與組合篩選

1. 以中文名稱搜尋一個平台預設選項。
2. 以 stable code 的大小寫變體搜尋同一選項。
3. 以說明文字搜尋一個選項。
4. 同時選擇觀察類別、`啟用中` 與 `平台預設`。
5. 改成 `收容所自訂`，確認結果只保留同時符合的項目。
6. 輸入不存在的文字，確認顯示友善無結果說明與「清除搜尋與篩選」。
7. 清除條件，確認恢復完整列表；頂部未篩選摘要不因條件改變。

預期結果：搜尋、類別、狀態與來源採 AND；無結果不顯示空白類別或誤導性的零總量。

### 3. 新增、編輯與排序

以具備管理權限的帳號：

1. 點選「新增選項」，填入一個合法中文名稱、例如 `emotion.shelter_calm` 的 stable code、說明、排序與補充說明需求。
2. 送出後確認顯示「收容所自訂／啟用中」及成功回饋。
3. 重新編輯，修改中文名稱、說明、排序與是否需要補充說明，確認列表與新回報可用詞彙同步。
4. 輸入空白名稱、含大寫或空白的 code、重複 code、負數排序，確認欄位級繁體中文錯誤且輸入不遺失。
5. 嘗試編輯平台預設，確認沒有可修改操作。

預期結果：表單可驗證且錯誤可修正；平台預設維持唯讀；所有成功 mutation 都有明確回饋。

### 4. 停用、恢復、封存與歷史

1. 先建立一個自訂選項並建立／使用一筆測試回報，使其有歷史使用。
2. 點選「停用」，確認訊息說明「停用後不會出現在新的回報表單，但歷史回報仍會保留」。
3. 取消確認，確認狀態與稽核不變。
4. 確認停用，確認新的有效詞彙不再包含該 option，但歷史回報仍顯示當時中文名稱與 stable code。
5. 確認該 option 的 stable code 變為唯讀且沒有永久刪除。
6. 以「恢復」將其設為啟用，確認再次出現在新回報可用詞彙。
7. 以「封存」測試另一個自訂 option，確認可依狀態篩選、歷史仍可查、恢復不改變歷史快照。

預期結果：狀態轉換是可追蹤且非破壞性；停用／封存只影響新的回報表單。

### 5. 查看變更紀錄

以具設定管理權限的 `local-platform-admin` 登入 `ORG-A`：

1. 在一個收容所自訂選項上選擇「查看變更紀錄」。
2. 確認本頁以唯讀方式顯示操作者、時間、操作類型、變更前內容、變更後內容與結果「成功」。
3. 確認只顯示 `ORG-A` 的 `ObservationOption` 紀錄；查詢使用目前 Shelter Context，不接受外部 organization id 擴大範圍。
4. 若檢視排序異動，確認每個受影響 option 各有一筆紀錄、各自顯示排序前後值，且共用同一 `operation_id`。
5. 使用 `local-staff-a` 重新登入，確認看不到「查看變更紀錄」入口，也不能從 API 取得本頁觀察選項管理稽核細節；既有稽核入口對其他類型紀錄的原有權限不因本功能改變。
6. 對沒有紀錄的選項確認顯示「目前沒有變更紀錄」；模擬查詢失敗時確認顯示繁體中文錯誤與「重新載入」。

預期結果：稽核資料沿用既有 AuditRecord／Audit API，管理者可追溯本所變更，Staff 與其他收容所不可查看。

### 6. Staff 唯讀與收容所隔離

1. 使用 `local-staff-a` 登入並選擇 `ORG-A`，確認可以閱讀啟用詞彙但看不到新增、編輯、排序、停用、恢復、封存按鈕。
2. 確認 Staff response 使用 `staff_active` scope，只顯示啟用中的類別／選項數量，不顯示收容所自訂總數或停用／封存總數。
3. 使用 `local-staff-b` 選擇 `ORG-B`，確認看不到 `ORG-A` 的自訂名稱、筆數、狀態或 stable code。
4. 嘗試將 A 的 option id 或網址帶入 B 的操作，確認回應拒絕且不洩漏 A 是否存在。
5. 以 `local-platform-admin` 切換收容所後，確認摘要與自訂 option 隨目前 Context 改變。

預期結果：前端角色差異與 API／資料存取邊界一致；相同 stable code 可在不同收容所獨立存在且互不影響。

### 7. 小尺寸螢幕與鍵盤

使用瀏覽器約 320px 寬度並只使用鍵盤：

1. 確認摘要卡、搜尋、類別標題、中文名稱、狀態與主要按鈕不重疊或截斷。
2. 以 Tab 完成搜尋、篩選、展開類別、開啟表單、修正錯誤、取消與儲存。
3. 開啟停用確認後，確認焦點進入確認區；取消或關閉後焦點回到原觸發按鈕。
4. 使用螢幕閱讀器確認類別展開／收合狀態、欄位錯誤、成功回饋與狀態文字可讀取。

預期結果：狀態不只靠顏色；主要流程不要求滑鼠或英文 stable code 才能完成。

## Targeted automated validation

在服務與測試資料可用後執行：

```bash
uv run pytest \
  tests/unit/test_observation_option_service.py \
  tests/integration/test_observation_options.py \
  tests/integration/test_observation_option_usage.py \
  tests/integration/test_observation_option_audit.py \
  tests/integration/test_audit_service.py \
  tests/isolation/test_observation_option_isolation.py \
  tests/contract/test_observation_options_contract.py \
  tests/contract/test_management_workbench_contract.py \
  tests/e2e/test_us4_observation_options.py -q

npm --prefix apps/web test -- --run
npm --prefix apps/web run typecheck
npm --prefix packages/contracts run check
```

預期結果：測試涵蓋狀態轉換、stable code 驗證與使用鎖定、歷史 snapshot、Audit、A／B 隔離、前端互動、可及性與生成契約無漂移。

效能驗收：使用 13 個類別與約 500 個選項的本機 fixture，固定同一瀏覽器與本機服務條件，重複執行初次載入、搜尋／篩選與模擬請求失敗各 10 次；摘要可見、結果可見，以及錯誤或重新載入狀態可見時間的 p95 均不得超過 2 秒。篩選操作使用已完成的單次載入資料，不另發送逐字搜尋請求。

## 完整品質 Gate

Targeted validation 通過後，再依專案 README 執行：

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
npm --prefix apps/web run quality
npm --prefix apps/web run build
npm --prefix packages/contracts run check
```

若需要完整本機 migration／seed／服務驗證，執行 `./scripts/verify_local.sh`；此命令可能啟動 Docker，且仍只使用本機虛構資料。

## 完成判定

- [ ] 四項摘要與 13 類別資訊架構符合 [ui-behavior.md](contracts/ui-behavior.md)。
- [ ] HTTP response、狀態動作、錯誤與授權符合 [observation-vocabulary.yaml](contracts/observation-vocabulary.yaml)。
- [ ] 歷史 snapshot、使用索引、Audit 查詢（含 `resource_id` 與管理者授權）與 RLS 測試通過 [data-model.md](data-model.md) 的 invariants。
- [ ] Targeted tests、完整品質 Gate 與人工小尺寸螢幕／鍵盤驗收均完成。
- [ ] 管理者能在本頁查看自訂選項變更紀錄，Staff 與其他收容所無法查看或推測。
- [ ] 效能測試的初次摘要載入、搜尋／篩選結果與失敗錯誤／重新載入狀態可見時間 p95 均不超過 2 秒。
