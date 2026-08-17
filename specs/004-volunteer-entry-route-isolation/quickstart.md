# 快速開始：志工角色入口與管理路由隔離驗證

本指南用於實作後驗證 [spec.md](spec.md)、[LIFF exchange contract](contracts/liff-exchange.openapi.yaml) 與 [route contract](contracts/route-access.md)。P0 必須同時完成可重跑的 local fixture matrix 與共用受控 LINE／LIFF 驗收。

## 1. 前置條件

- Docker Desktop／Docker Compose
- Python 3.11+、`uv`
- Node.js、npm
- 已依 `.env.example` 建立 local-only `.env` 與 JWT keys
- 005 migrations、entry references、Membership/Grant fixtures 已可用
- 正式驗收另需一個受控 LINE OA/channel/Webhook/LIFF App，且 LIFF 啟用 `openid` scope

Local 帳號密碼均為 `local-only-password`：

| 帳號 | 用途 |
| --- | --- |
| `local-volunteer-a` | ORG-A 志工入口、draft、管理 route isolation |
| `local-volunteer-b` | ORG-B 與 cross-tenant regression |
| `local-staff-a` | 工作人員 `/` regression |
| `local-shelter-admin-a` | 收容所管理者入口與設定 regression |
| `local-platform-admin` | 多 context 與平台管理入口 regression |

Local fixture 不是正式 LINE 身分，不能取代受控 LIFF 驗收。

## 2. 啟動 local stack

```bash
docker compose -f infra/local/docker-compose.yml up -d postgres minio
uv run alembic upgrade head
uv run python -m scripts.seed_local
```

確認 `.env` 至少包含 local `LINE_CHANNEL_ID`、`LIFF_ID`、JWT keys 與 database settings。分別啟動 API 與 Web：

```bash
uv run python -m uvicorn services.api.app.main:app --reload --host 127.0.0.1 --port 8000
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3000
```

入口：

- Web：<http://127.0.0.1:3000>
- Local login：<http://127.0.0.1:3000/login>
- LIFF bootstrap（fixture）：`http://127.0.0.1:3000/volunteer-entry?entry=<local-reference>`
- API health：<http://127.0.0.1:8000/healthz>

不得把 raw ID token 或 entry reference 貼入 issue、snapshot、test report 或錄影。local seed 的 deterministic reference 只可用於非正式環境。

## 3. Contract 與純規則驗證

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/contract/test_authentication_contract.py \
  tests/contract/test_openapi_contract.py \
  tests/contract/test_generated_contract_types.py -q
npm --prefix packages/contracts run check
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
```

預期：

- canonical `LiffExchangeRequest` 必填 `id_token` + `shelter_entry_reference`，拒絕額外 client role/org 欄位。
- `packages/contracts/src/openapi.ts` 與 canonical OpenAPI 無 drift。
- `VOLUNTEER + management` → `redirect-volunteer`。
- management roles + valid context → `allow-management`。
- missing token／local 401 → `redirect-login`。
- formal LIFF 401 → `liff-recovery`；同 epoch attempt 最大 1。
- Membership/context mismatch 不 fallback 為 `STAFF`。

## 4. LIFF exchange transaction matrix

執行專屬 tests：

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/integration/test_authentication_session.py \
  tests/security/test_liff_exchange_authorization.py \
  tests/isolation/test_liff_entry_isolation.py -q
```

必要矩陣：

| Entry／identity／access | HTTP/結果 | 新 Session/Refresh/context |
| --- | --- | --- |
| valid ORG-A entry + matching active-unexpired access | 200 | 各 1；context=ORG-A |
| valid ORG-B entry + matching active-unexpired access | 200 | 各 1；context=ORG-B |
| malformed／unknown／revoked／cross-purpose entry | safe deny | 各 0 |
| invalid/expired/wrong-audience LINE token | safe deny | 各 0 |
| missing/disabled Binding、disabled User/Org | safe deny | 各 0 |
| no application、pending、rejected | safe deny | 各 0 |
| future、expired、revoked、disabled、missing Grant | safe deny | 各 0 |
| ORG-A entry + ORG-B-only Membership | safe deny | ORG-A/ORG-B 都為 0 |
| database failure after Session flush | 503/rollback | 各 0 |

另外驗證 concurrent exchange vs revoke/expiry：結果必須有明確 commit ordering；revoke commit 後 protected request 成功率為 0，且不得建立新的有效 context。

## 5. Local role-directed login

```bash
npm --prefix apps/web exec -- playwright test e2e/login-home.spec.ts
```

手動確認：

1. `local-volunteer-a` context 成功後進入 `/animal-confirmation`，不經過 `/`。
2. `local-staff-a`、`local-shelter-admin-a` 進入 `/`。
3. `local-platform-admin` 先選擇 context，成功後進入 `/`。
4. context 建立失敗不宣稱已進入工作台，也不顯示 protected data。
5. Login/context action 文案對志工不寫成「進入管理工作台」。

## 6. 管理 route isolation

實作後執行：

```bash
npm --prefix apps/web exec -- playwright test e2e/liff-route-isolation.spec.ts
npm --prefix apps/web run test:e2e:p0:list
npm --prefix apps/web run test:e2e:p0
```

以志工對下列代表 routes 驗證 deep link、query、尾端斜線、dynamic id、reload 與 back：

```text
/
/animals
/animals/<animal-id>
/animals/<animal-id>/timeline
/reports
/reports/<report-id>
/ai-review
/care-calendar
/settings/observation-options
/settings/reportable-scope
/settings/qr-codes
/settings/audit
/settings/volunteer-access
/volunteers/applications
/volunteers/access
/volunteers/notifications
/shelters
```

每條 route 預期：

- first visible state 只有安全 checking/redirect status。
- 最終為 `/animal-confirmation`。
- Management Shell、Sidebar、Breadcrumb、metrics、count、detail 與 permission-denied management view 都不可見。
- `/v1/organizations`（在 management gate 階段）、Dashboard 與 page-specific management request count 都為 0。
- back/reload 不顯示 stale management content，也不形成 loop。

再以 management roles 確認 `/` 與既有 route 不被誤導到 volunteer flow。

## 7. Volunteer context、shelter label 與 draft

| 狀態 | 預期 |
| --- | --- |
| context 尚未驗證 | 不發 animals/draft request；不顯示舊 shelter |
| ORG-A 成功 | `/animal-confirmation`、`/care-report` 顯示 ORG-A 名稱且只讀 ORG-A data |
| recovery 後變成 ORG-B | 先卸載 ORG-A view；完整驗證後只顯示 ORG-B |
| no current draft | 直接顯示今日 animals/QR/search；無空 prompt |
| active、未過期、same context、animal allowed | 顯示 name/number/progress +「繼續／稍後」 |
| continue | 前往 `/care-report` 並重讀 current draft |
| later | 留在 confirmation；Draft 無 mutation |
| expired/non-active/cross-context/animal unavailable | 不顯示 answers/detail；安全 unavailable |
| save failure | 保留既有輸入、可明確重試；不自動重播 mutation |

Cross-context 測試必須同時觀察 response body、visible UI 與 network request；交叉顯示率為 0%。

## 8. Formal LIFF 401 recovery

Playwright 使用可控 LIFF adapter 模擬：

1. first protected request 回 401，另外兩個並行 request 同時回 401。
2. assert `/v1/auth/liff/exchange` request count 為 1。
3. success：重新驗證 context，回到原 volunteer route；原 management deep link 不恢復。
4. failed exchange：進入 terminal「重新進入／回到 LINE」，count 維持 1。
5. exchange 成功後 protected request 再 401：terminal，count 不增加。
6. 401 發生在 save mutation：不自動重播；form input 仍可恢復，要求使用者重試。

Local credential Session 遇 401 必須直接 `/login`，不得呼叫 LIFF exchange。

## 9. LINE Bot regression

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/e2e/test_local_line_bot_vertical_flow.py \
  tests/integration/test_line_webhook*.py \
  tests/security/test_line*.py -q
```

預期：

- 已確認且有效 context 先提供該 shelter 可回報狗狗。
- 多 context、無 context 或 Membership 無效時先 requires-LIFF/context verification。
- 不以狗名、shelter number 或 client state 推測 organization。
- Webhook signature、event idempotency、Draft/Report flow 無回歸。

若 shell glob 在環境中無匹配，改以 `rg --files tests` 取得實際檔案後明確列出，不可靜默略過。

## 10. Responsive、keyboard、axe、visual

```bash
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:axe
npm --prefix apps/web run test:visual
```

P0 matrix：360x800、768x1024、1024x768、1440x900。

必須涵蓋 initializing、logging-in、exchanging、checking、redirecting、recovering、context-required、error、terminal、draft prompt。Axe critical/serious 為 0；所有主要 action 可鍵盤操作且有可見 focus；長 shelter name／中文錯誤不截斷或重疊。

Visual baseline 只在 reviewer 確認預期變更後更新：

```bash
npm --prefix apps/web run test:visual:update
```

## 11. 共用受控 LINE／LIFF 驗收

### 準備

1. 一個受控 LINE Official Account、Messaging API channel、Webhook、LIFF App；記錄其非敏感識別與配置版本。
2. LIFF App `openid` scope、Endpoint URL 與允許的 redirect URL 正確。
3. 受控 ORG-A／ORG-B active organizations，各自發行 entry reference：

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/issue_volunteer_entry_reference.py <organization-uuid>
```

raw reference 只顯示一次；立刻放入受控 URL/QR 管理流程，不寫入 evidence。

4. 至少準備：ORG-A-only active volunteer、ORG-B-only active volunteer、跨兩 org volunteer，以及 pending/expired/revoked 對照 identity。

### 實機 matrix

| 情境 | 預期 |
| --- | --- |
| ORG-A identity + ORG-A URL | 無帳密、context=ORG-A、只見 ORG-A dogs/draft |
| ORG-B identity + ORG-B URL | 無帳密、context=ORG-B、只見 ORG-B dogs/draft |
| ORG-B-only identity + ORG-A URL | 安全拒絕；任何 context/data 為 0 |
| 同一 identity 依序開 A/B URL | 每次後端重驗 exact Membership；無 stale data |
| pending/revoked/expired URL flow | 不建 context；顯示適用下一步 |
| Session 失效 | 每事件自動 exchange <=1；成功回原 flow，失敗 terminal |

至少在約 360px 實機完成 dog selection 與 report entry。Evidence 只記錄時間、app/channel configuration reference、測試 case、結果與遮罩後截圖；不得保存 raw token/reference、LINE user id、個人名稱或 protected animal/report content。

## 12. 後端安全與完整 gate

```bash
env UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
env UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .
env UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
npm --prefix packages/contracts run check
npm --prefix apps/web run quality
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e:p0
npm --prefix apps/web run test:a11y:browser
npm --prefix apps/web run test:visual
./scripts/verify_local.sh
```

完成條件：

- exchange 全矩陣與 partial-state=0 通過。
- ORG-A/ORG-B cross-entry/cross-data 成功率為 0%。
- local 4-role destination 與全部 management route isolation 通過。
- 正式 401 recovery 每 epoch exchange<=1、mutation replay=0、loop=0。
- shelter label、draft、animals/report 無 stale/cross-context data。
- LINE Bot、CRM、原始資料、AI、OpenAPI 與 management regression 全通過。
- 共用受控 LINE／LIFF 實機證據完成，且不含 secret/PII。
