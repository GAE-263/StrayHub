# Quickstart：Implementation and Acceptance Guide

本文件是後續實作與驗收的操作順序，不代表目前已完成 production code 或 T008 人工作業。

## 1. Preconditions

1. 確認目前 branch 為 `013-remote-management-public-access`，並保存既有 unrelated dirty changes。
2. 閱讀 `spec.md`、`plan.md`、`research.md`、`data-model.md` 與 `contracts/*`。
3. 確認 012 Phase A/B/C 已合併或本 branch 可讀到其 registry、redaction、login canonicalization 與
   activation-gate contract。
4. 不要把 T008 標示完成；真實 public activation 前必須有人工 evidence。

## 2. Suggested implementation order

```text
contract tests for registry/profile/host
  -> generator + generated nginx config
  -> DB migration/models/repository abuse primitives
  -> auth service/API public-profile enforcement
  -> session origin + rollback command
  -> shared-demo production/dev launcher
  -> API/integration/security tests
  -> production-build Playwright + LINE regression
  -> manual runtime acceptance
```

所有 production change 先加 failing test。不要在實作時重新設計 tunnel topology、cookie auth、MFA、
OAuth、refresh token architecture、CDN 或全站 security headers。

## 3. Local deterministic validation

實際 command 名稱由 `/speckit-tasks` 依 repository scripts 確認；至少須覆蓋：

```bash
uv run pytest tests/contract/test_remote_management_public_boundary.py
uv run pytest tests/security/test_remote_login_abuse_control.py
uv run pytest tests/security/test_remote_management_access.py
uv run pytest tests/integration/test_remote_login_abuse_postgres.py
uv run mypy services/api
uv run ruff check .
uv run ruff format --check .
uv run pytest
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
git diff --check
```

Constitution 要求涉及 Python 的功能在完成前執行全 repository `ruff check .`、
`ruff format --check .`、`pytest`，不能只用 targeted tests 宣告完成。

## 4. Registry/config acceptance

以 temporary output directory 產生三個 profile，不能覆寫 committed template：

```text
line-only                  -> 只有 012 routes
shared-demo-dev            -> LINE + core management + HMR
shared-demo-production     -> LINE + core management - HMR - static pattern
                              + build-manifest exact assets
unknown/malformed profile  -> non-zero exit, no usable output
```

對 generated nginx config 執行 `nginx -t`，再跑正負 route matrix。至少檢查：

- Login、dashboard、animals、timeline、reports、AI review、care calendar 可達。
- 支援 API `organizations/{id}/areas`、`care-agenda` 可達且 tenant-scoped。
- Platform、volunteer governance、QR/settings、docs/openapi/metrics/debug、未列 mutation 為 404。
- Production HMR 為 404；static chunks 可讀。
- Manifest 未列的 hashed chunk、`.map`、`/_next/image`、font/favicon 維持 404 且不送 Next。
- Wrong Host、encoded path bypass、額外 suffix、wrong method 都不送 upstream。
- Sensitive management access log 不含 query/referer；ordinary local observability 未全域消失。

## 5. Authentication acceptance

使用 synthetic users，不任意修改 production-like data：

- Active `STAFF`、active `SHELTER_ADMIN`：可登入並完成各自可授權的核心 journey。
- `PLATFORM_ADMIN`、`VOLUNTEER`、disabled、expired/no membership：公開 profile 拒絕。
- 將 private/local 取得的 platform token 帶入 shared host：仍須拒絕。
- A shelter session 以 B shelter UUID 呼叫每個 resource family：不得回傳 B shelter data。
- Shared profile 的 management shell 只顯示 core navigation；report correction/archive 與 care
  reminder mutation controls 不顯示，但以直接 API 呼叫仍須得到 gateway/backend deny。

以 injectable clock 驗證：

```text
wrong #1-#4 -> 401
wrong #5    -> 429 + Retry-After
correct during 15m lock -> 429
after expiry correct -> success

IP attempt #1-#20 -> evaluated
IP attempt #21    -> 429 + Retry-After
after oldest exits rolling window -> evaluated
```

另以兩個 service/repository instance 與 concurrency test 證明 PostgreSQL 狀態跨 worker 且原子。
Sentinel raw username/password/IP/token 不得出現在 nginx、application、audit 或 command output。

## 6. Production browser acceptance

1. 建立 Next production build，以 `shared-demo-production` 啟動，不使用 `next dev`。
2. Playwright 從 public origin 驗證 login success/failure、Enter/click submit、URL 無 credential、
   shelter context 與所有 core journeys。
3. Network evidence 確認 login 是 JSON `POST /v1/auth/login`，query 無 credential。
4. Dev/HMR endpoint、out-of-scope navigation/API 與 direct platform access 必須拒絕。
5. 檢查 security headers、history canonicalization 與 access logs 維持 012 contract。

## 7. LINE regression

同一 shared host 驗證：

```text
LINE webhook signature + 200 acknowledgement
LIFF volunteer entry/application
animal confirmation and report handoff
volunteer walk/adoption photo capability
```

再切回 `line-only`，確認 management login/page/API 都拒絕而 LINE 流程仍正常。不可修改 capability
TTL、MinIO topology 或 LINE authorization 來通過本 feature。

## 8. Manual activation gate

`MANUAL ACTION REQUIRED`：T008 尚未完成時，不得把 shared profile 暴露至 ngrok。負責人必須：

1. Rotate 已曝光 demo password，確認未在其他環境重用。
2. 清理／確認 ngrok inspector、browser history 與 remote logs 的 credential URL evidence。
3. 保存操作者、UTC timestamp、執行命令／畫面、rotation verification 與 log scan 結果。
4. 讓 launcher 讀取可驗證 evidence reference；不得只用 boolean 或口頭確認。

## 9. Rollback drill

在 synthetic shared-demo session 下計時：

1. 執行 rollback，先驗證 public management route 已 deny、LINE route 仍 allow。
2. 驗證 remote session/access/refresh token 全部失效，local/LIFF session 不被誤撤銷。
3. 保存 route probes、session revoke count、start/end UTC timestamp；總時間需小於 300 秒。

## 10. Completion evidence

交付報告至少包含：profile 名稱與 generated config digest、exact public host（可遮蔽非必要部分）、
route matrix、role matrix、cross-tenant matrix、rate-limit concurrency results、production build/browser
結果、LINE regression、log sentinel scan、T008 evidence 狀態、rollback drill、全套 Ruff/Pytest 與
frontend checks、`git diff --check`、`git status --short`。
