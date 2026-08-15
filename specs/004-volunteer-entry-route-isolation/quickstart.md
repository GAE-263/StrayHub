# 快速開始：志工角色入口與管理路由隔離驗證

本指南用於實作後驗證 [spec.md](spec.md) 與 [route-access contract](contracts/route-access.md)。P0 先以 local Web／LIFF fixture 完成，不依賴真實 LINE channel、Rich Menu 或 LIFF production deployment。

## 前置條件

- Docker Desktop／Docker Compose
- Python 3.11+ 與 `uv`
- Node.js、npm
- 已依 `.env.example` 建立本機 `.env` 與 local-only JWT keys
- 可使用下列虛構帳號，密碼均為 `local-only-password`

| 帳號 | 角色／用途 |
| --- | --- |
| `local-volunteer-a` | ORG-A 志工入口、草稿與管理 deep-link 隔離 |
| `local-volunteer-b` | ORG-B 志工與 tenant regression |
| `local-staff-a` | 工作人員管理首頁 regression |
| `local-shelter-admin-a` | 收容所管理者入口與設定權限 regression |
| `local-platform-admin` | 多 context 選擇與平台管理入口 regression |

Local fixture 只代表 Web／LIFF 測試帳號，不是真正 LINE 身分。

## 啟動本機服務

先準備資料與基礎服務：

```bash
docker compose -f infra/local/docker-compose.yml up -d postgres minio
uv run alembic upgrade head
uv run python -m scripts.seed_local
```

分別啟動 API、Web 與 Worker：

```bash
uv run python -m uvicorn services.api.app.main:app --reload --host 127.0.0.1 --port 8000
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3000
uv run python services/worker/worker.py
```

入口：

- Web：<http://127.0.0.1:3000>
- Login：<http://127.0.0.1:3000/login>
- API health：<http://127.0.0.1:8000/healthz>

## 自動化驗證順序

### 1. 純角色／route decision

```bash
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
```

預期結果：

- `VOLUNTEER` + management area → `redirect-volunteer`。
- `STAFF`／`SHELTER_ADMIN`／`PLATFORM_ADMIN` + valid context → `allow-management`。
- 所有角色缺少 token／Session 401 → `redirect-login`。
- Context 缺少或 Membership 不一致 → `context-required`，不得 fallback 為 `STAFF`。
- Volunteer area + valid context → `allow-volunteer`；不新增管理角色反向限制。

### 2. 角色入口與管理 deep-link suite

實作後，直接執行本功能的 browser spec：

```bash
npm --prefix apps/web exec -- playwright test e2e/role-route-isolation.spec.ts
```

並確認它已納入 P0 script：

```bash
npm --prefix apps/web run test:e2e:p0:list
npm --prefix apps/web run test:e2e:p0
```

預期至少涵蓋：

- 志工登入後前往 `/animal-confirmation`。
- 工作人員、收容所管理者、平台管理員前往 `/`；平台管理員先完成 context 選擇。
- 志工直接開啟全部管理 route pattern 時導回志工入口。
- 志工情境沒有 `/v1/management/dashboard` 或 page-specific management request。
- Reload、browser back、query string、尾端斜線與 dynamic id 不能繞過 gate。
- Session 401 導向 `/login`；context 缺少與 temporary error 進入安全終止 state，沒有 redirect loop。

### 3. Responsive、keyboard、axe 與 visual

```bash
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:axe
npm --prefix apps/web run test:visual
```

P0 route matrix 必須在 360x800、768x1024、1024x768 與 1440x900 驗證。Visual baseline 只有在 reviewer 確認預期變更後才能更新：

```bash
npm --prefix apps/web run test:visual:update
```

預期結果：

- Checking／redirecting／context-required／error 與 active draft prompt 在四個 viewport 無必要水平溢出。
- 鍵盤可操作登入、context 選擇、繼續回報、稍後處理、重試與返回登入。
- Axe critical／serious violations 為 0。
- 志工 route 不顯示 Management Shell、Sidebar 或 Breadcrumb。
- 既有管理 route visual 只因合理的掛載順序調整產生 reviewer 可解釋的變化。

## 手動驗收流程

### 1. 志工登入目的地

1. 清除目前 browser session，開啟 `/login`。
2. 使用 `local-volunteer-a` 登入。
3. 確認 Active Shelter Context 成功後，最終 URL 為 `/animal-confirmation`。
4. 確認過程沒有顯示「管理工作台總覽」、Dashboard metrics、管理 Sidebar、Breadcrumb 或管理 permission denied 畫面。
5. 在 browser network panel 確認沒有 `/v1/management/dashboard` request。

### 2. 志工管理 route matrix

登入 `local-volunteer-a` 後，逐一貼上：

```text
/
/animals
/animals/<known-animal-id>
/animals/<known-animal-id>/timeline
/reports
/reports/<known-report-id>
/ai-review
/settings/observation-options
/settings/reportable-scope
/settings/qr-codes
/settings/audit
/shelters
```

每一條 route 的預期結果：

- 首次可見內容只有安全的角色／context checking 或 redirect status。
- 最終前往 `/animal-confirmation`。
- 不顯示管理資料、筆數、metrics、操作或 permission denied 管理畫面。
- Network panel 沒有該管理 page-specific request。
- Reload 與 browser back 仍重新執行 gate，不會顯示舊管理內容或形成 loop。

再以 query string、尾端斜線與不同 dynamic id 重複代表性案例，結果必須一致。

### 3. 管理使用者 regression

1. 以 `local-staff-a` 登入，確認進入 `/` 且 Dashboard、Sidebar 與既有管理 route 可用。
2. 以 `local-shelter-admin-a` 登入，確認進入 `/` 且設定／收容所操作仍依既有權限顯示。
3. 以 `local-platform-admin` 登入，確認先選擇 ORG-A／ORG-B；context 成功後才進入 `/`。
4. 切換 context 後 reload 管理 deep link，確認只顯示新 context 資料。
5. 模擬 context switch 失敗，確認保留舊 context 或安全 error，不混合兩個收容所資料。

### 4. Active draft 恢復

以 Playwright fixture 或 local API 準備下列狀態：

| 狀態 | 預期結果 |
| --- | --- |
| 沒有 current draft | 直接顯示今日動物、QR 與收容編號搜尋，不顯示空恢復提示 |
| 單一 active、未過期且 animal 可回報 | 顯示動物名稱／收容編號／進度，以及「繼續回報」「稍後處理」 |
| 選擇繼續 | 前往 `/care-report`，由後端重新取得 current draft |
| 選擇稍後 | 留在 `/animal-confirmation`，Draft 狀態與內容不變 |
| Draft 過期／非 active | 不顯示為可恢復，不載入答案 |
| Draft context 不一致或 animal 不在今日授權名單 | 不顯示受保護內容；提供安全重試／聯絡管理者下一步 |
| `/care-report` 保存失敗 | 保留既有輸入並可重試；不導向管理頁 |

P0 不建立多筆 active draft；現有單一 active draft invariant 必須保留。

### 5. Session 與 Context failure

- 移除 access token 後開啟任一受保護 route：前往 `/login`，children 不掛載。
- 將 profile 或 context response 設為 401：清除 client auth cache並前往 `/login`。
- 將 Active Context 設為缺少／409：顯示 context-required state，可返回登入／重試／聯絡管理者；不自動 loop。
- 將 profile/context 設為 network failure／5xx：顯示繁中 error 與重試，不顯示 stale protected content。
- 將 Active Context 與 Membership organization 設為不一致：不得 fallback 為管理角色，也不得顯示任一收容所資料。

## 後端安全與資料回歸

前端測試不能代替後端 authorization。至少執行：

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/security tests/isolation tests/contract -q
npm --prefix packages/contracts run check
```

預期結果：

- 志工直接呼叫 management API 仍由後端拒絕。
- ORG-A／ORG-B 不因相同 shelter number、id 輸入或錯誤訊息洩漏資料。
- Active Shelter Context、Session 撤銷與 Membership 規則不變。
- OpenAPI generated types 無漂移。
- CRM 原始回報、LINE Bot、AI 人工覆核與歷史資料不受 route 變更影響。

## 完整品質 Gate

```bash
npm --prefix apps/web run quality
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e:p0
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:visual
./scripts/verify_local.sh
```

完成條件：

- 所有角色入口與 route matrix 通過。
- 志工 management request assertion 全部為 0。
- 沒有 redirect loop、管理內容 flash 或 stale protected content。
- Active draft 的 continue／later／unavailable 流程通過。
- 360px 與 keyboard／screen reader 可完成主要下一步。
- 既有管理、後端權限、租戶隔離、OpenAPI、CRM、LINE 與 AI regression 全部通過。
- P0 不依賴真實 LINE／LIFF deployment 或 P1 多筆草稿策略。
