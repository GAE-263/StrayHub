# Quickstart: 敏感資料傳輸與紀錄防護驗收

本文件是實作完成後的驗收指南，不包含真實 credential。所有 runtime 測試使用每次執行新建的 synthetic sentinel，報告只保存摘要。

Credential URL 事件請依 [`docs/security/credential-url-incident-runbook.md`](../../docs/security/credential-url-incident-runbook.md) 執行；外部處置結果記錄於 [`runtime-incident-result.md`](runtime-incident-result.md)。

## 1. Prerequisites

- 使用 synthetic demo database，不連 production-like 或正式資料。
- 確認 `APP_ENV=local`／test、loopback database 與既有 local storage guard。
- 若使用 ngrok，先確認 tunnel 屬於本次 helper，測試後由 helper 停止。
- 準備兩個 organization 的 synthetic account／resource，供 cross-tenant replay 驗證。

## 2. Static policy validation

檢查範圍：

```text
apps/web/**/*.{ts,tsx}
services/api/**/*.py
infra/**/*.conf
infra/**/*.template
scripts/**/*.sh
scripts/**/*.py
```

預期：

- 每個 sensitive query candidate 都是 prohibited 或出現在 exception registry。
- Login form 不可能原生 GET credential。
- Password 沒有 client-side 固定預填。
- nginx sensitive logging 不含 query／Referer。
- public tunnel 不含 catch-all management exposure。

## 3. Login browser matrix

依序驗證：

1. 正常 JavaScript 登入。
2. 首次載入期間立即按 Enter。
3. 延遲或阻擋 JavaScript 後嘗試提交。
4. 錯誤 password、API 401、API timeout。
5. 直接開啟 `/login?username=SENTINEL&password=SENTINEL`。
6. 登入多 organization account 並選擇 active context。

每個情境都確認：

```text
address bar: no sentinel
history: no sentinel
network request URL: no sentinel
login API method/body: expected POST body only
nginx/Next/Uvicorn/application logs: no raw sentinel
```

## 4. Controlled URL exception matrix

逐項使用 synthetic 值驗證：

| Flow                        | Positive                                     | Negative                                                      |
| --------------------------- | -------------------------------------------- | ------------------------------------------------------------- |
| LINE/adoption photo         | valid current capability renders             | expired, wrong purpose, changed object, cross-tenant rejected |
| QR animal confirmation      | active QR resolves then URL scrubs           | revoked, malformed, duplicated, cross-tenant rejected         |
| Volunteer entry/application | valid target survives required LIFF recovery | raw `id_token`, forged entry, foreign organization rejected   |
| Staff signed download       | authorized current tenant receives short URL | foreign media and unauthorized role rejected                  |

不在本驗收修改 TTL；只記錄實際 lifetime 與 HTTP 行為。

## 5. Public tunnel matrix

啟動既有 local stack 後，以更新後 helper 建立 tunnel。驗證：

```text
ALLOW  configured LINE webhook
ALLOW  required LIFF pages and exchange/report APIs
ALLOW  required public image capability
DENY   /login
DENY   management pages
DENY   /v1/management/**
DENY   platform-admin routes
```

LINE webhook 測試必須保留有效 `X-Line-Signature`；不得為了 smoke 關閉簽章驗證。

## 6. Cross-layer log scan

對每個 exposure surface 使用不同 synthetic sentinel。檢查：

- browser console／HAR（只在安全暫存目錄）
- ngrok inspection/log
- local nginx access/error log
- Next stdout/stderr
- Uvicorn access log
- application structured/error log
- test report、screenshot 與 trace

預期原始 sentinel 次數為 0；method、path、status、latency 與 correlation 仍可辨識。掃描完成後清理暫存 artifact 並回報 `cleaned=true`。

## 7. Suggested targeted commands

依實際修改檔案選用 repository 已存在的 scripts：

```bash
npm --prefix apps/web test -- login
npm --prefix apps/web run typecheck
uv run pytest tests/security/test_observability_logging.py
uv run pytest tests/contract/test_line_local_helper.py
uv run pytest tests/contract/test_gce_production_nginx_contract.py
uv run pytest tests/unit/test_qr_deep_link.py
uv run pytest tests/unit/test_line_role_menu_actions.py
uv run pytest tests/integration/test_public_adoption_photo.py
uv run pytest tests/isolation/test_timeline_and_media_isolation.py
git diff --check
```

若修改 Python，完成 targeted tests 後仍依 constitution 執行：

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## 8. Incident response smoke

使用 synthetic credential 演練：

1. 偵測 URL exposure。
2. 停止 helper-owned tunnel。
3. 撤銷／輪替 synthetic credential。
4. 清理可控 local logs、HAR、trace 與 screenshot。
5. 記錄無法回收的第三方／瀏覽器副本風險。
6. 在 30 分鐘內完成並留下不含原值的 evidence。

## 9. Exit criteria

- Prohibited URL candidate = 0。
- Unregistered controlled exception = 0。
- Raw sentinel in checked surfaces = 0。
- Cross-tenant capability acceptance = 0。
- Legitimate query／LINE／LIFF regression = 0。
- Temporary evidence cleanup = true。
