# Security Boundary Contract

## 1. Login UI contract

- `/login` 不接受 query／fragment 中的 username、password、access token 或 refresh token 作為登入資料。
- 正常登入只透過既有 authenticated session API 的 request body 傳送 username／password。
- JavaScript 未掛載、載入失敗或 hydration 尚未完成時，不得產生 credential GET。
- Password 初始值為空；username 是否提示不構成授權，但不得透過 URL 預填。
- Legacy sensitive query 必須 canonicalize 到 `/login`；canonical response／page 使用 `no-store`，且不把原 query 放入錯誤訊息。
- 登入成功、失敗、無 organization、platform-only 與 context selection 行為維持現有契約。

## 2. URL policy contract

### Prohibited in URL

`password`, `temporary_password`, `access_token`, `refresh_token`, `id_token`, `authorization`, provider secret／credential，以及任何可作為長效 bearer credential 的值。

### Controlled exceptions

只有 registry 中的 route + key 組合可使用；每項必須提供 purpose、scope、lifetime／revocation、scrub、log 與 tests。Client 提供的 organization ID 只能作為候選 target，後端仍須重新驗證。

### Ordinary query

Search、pagination、date、sort、status 與非授權性 cache version 可保留。不得因安全修正改變其 API contract 或診斷能力。

## 3. Logging contract

敏感 route 的 access log 最多包含：

```text
timestamp method path protocol status bytes latency correlation_id
```

不得包含：

```text
raw query
raw Referer
Authorization value
password or session token
LINE user/id token
signed URL or capability value
raw entry/QR reference
request/response body
```

一般 route 可保留非敏感 query。無法證明 query 安全時，預設使用 query-free format。Exception traceback、structured `extra`、adapter error body 與 CLI output 必須套用相同分類。

## 4. Tunnel route contract

預設 LINE／LIFF public tunnel：

- ALLOW：實際設定的 LINE webhook、必要 public photo endpoint、LIFF public pages、其必要 exchange/report API、Next static assets與健康檢查。
- DENY：`/login`、所有 management pages、`/v1/management/**`、platform-admin routes、非必要 debug／inspection path。
- API allowlist 必須逐 route 維護，不得以 `/v1/**` catch-all 代替。
- Web allowlist 必須支援 LIFF redirect／recovery 所需頁面，但不得以 `/` catch-all 代替。
- 拒絕結果不得揭露帳號、tenant 或資源是否存在。

遠端 management demo 不是預設 tunnel 的例外條目；必須使用獨立 opt-in mode 與 synthetic-only guard。

## 5. Initial controlled-exception contract

| Route family | Value | Purpose | Current lifetime | Required logging |
|---|---|---|---:|---|
| `/v1/public/(adoption/)?animals/{id}/photo` | `token` | LINE/adoption image | 300s | omit query and Referer |
| `/animal-confirmation` | `qr_token` | resolve current animal | revocable QR lifecycle | omit/redact until scrubbed |
| `/volunteer-entry`, `/volunteer-application` | `entry` | shelter/application target | stable opaque locator, server validated | redact value; retain route |
| authenticated media download response | signed URL | direct object fetch | 300s | never log returned URL |
| approved LIFF/OAuth callback | standard callback fields | complete provider protocol | provider/session bounded | scrub after exchange; no token values |

TTL changes are outside this contract unless supported by a separate threat/runtime review.

## 6. Failure contract

- Prohibited query: do not authenticate; canonicalize or reject safely.
- Unknown sensitive key: fail CI and require classification.
- Missing/expired/replayed capability: fail closed without resource-existence leakage.
- Cross-organization capability: reject regardless of client-supplied organization.
- Redaction failure in tests: block release; do not print the failed sentinel in diagnostics.
- Tunnel allowlist drift: block helper startup or contract validation.

## 7. Required evidence

- Login browser test including delayed/disabled JavaScript behavior.
- Static URL candidate inventory and exception-registry completeness.
- nginx local/GCP syntax and log-format contracts.
- Uvicorn and application logger sentinel tests.
- LIFF legacy token scrub and recovery regression.
- QR/photo/signed URL purpose, expiry/revocation and cross-tenant tests.
- Public tunnel allow/deny matrix and log scan.
- `git diff --check`, frontend typecheck, targeted tests, then repository constitution quality gate for affected Python.
