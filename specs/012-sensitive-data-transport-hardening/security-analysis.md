# 敏感資訊傳輸與登入安全：現況分析與修改策略

**分析日期**：2026-09-04  
**分析基準**：`main` @ `b20210a`  
**狀態**：規劃完成，尚未實作

## 1. Executive Summary

目前已確認一個 P1 credential exposure：`/login` 的 SSR HTML form 沒有明確
`method`，兩個具 `name` 的 input 又預填固定帳密；在 React hydration 前、JavaScript
失效或 handler 尚未掛載時，瀏覽器會用原生 GET 提交，形成
`/login?username=...&password=...`。敏感資料第一次進入 URL 的位置是瀏覽器，不是
Next proxy 或 FastAPI。

正常登入 API 本身使用 JSON `POST /v1/auth/login`，後端沒有 GET login route，也沒有
從 login query 讀回帳密。問題可在不重建 authentication architecture 的前提下，以
form 原生安全語意、hydration gate、legacy URL canonicalization、password 空值及測試修正
封堵。

目前第二個主要風險是「保存與暴露面不一致」：Uvicorn 已有敏感值 filter，animal photo
route 的 nginx log 也已省略 query／Referer；但其他 nginx request 使用 `$request` 與
`$http_referer`，而兩套 ngrok helper 都是 catch-all。公開 LINE／LIFF tunnel 因此同時
公開 `/login`、全部管理頁及 `/v1/**`。Next proxy 亦會原樣轉送 query。

本期應分三階段：Phase A 立即封堵 login 與處理已曝光 demo credential；Phase B 建立
Sensitive URL Registry 及跨層 logging policy；Phase C 將 tunnel 改為 route allowlist，並
加入 no-JS、sentinel log 與 CI 防回歸。完成本文件更新後，適合執行 `speckit-tasks`；尚不
建議略過 task 拆解直接開始 implementation。

## 2. Confirmed Findings

### 2.1 confirmed

| ID | 位置 | 現況與風險 | 發生條件／影響 |
|---|---|---|---|
| CF-01 | `apps/web/app/login/page.tsx:39-40, 65-70, 136-176` | Login form 無 `method`／`action`，只靠 `preventDefault()`；username/password 具 `name` 且 SSR 初值為固定 demo 帳密。 | hydration 前、JS disabled／failed 或 Enter 提交時，原生 GET 可把帳密寫入 URL。影響 address bar、history、log、tunnel inspector、分享與同源 Referer。|
| CF-02 | `services/api/app/api/authentication.py:216-225` | 真正登入 API 是 JSON `POST /v1/auth/login`。Router 中沒有 GET login route。 | 正常 hydrated flow 不把 credential 放入 URL；原生 fallback 打到 Next `/login`，不是 API。|
| CF-03 | `apps/web/app/login/page.tsx` 與 repository query consumer 搜尋 | Login page 沒有讀取 `searchParams`、username 或 password query。 | Legacy URL 不會直接登入，但也不會主動清除；秘密仍停留在 URL／history。|
| CF-04 | `apps/web/e2e/login-home.spec.ts:13-24` | Login E2E 依賴預填 username/password，沒有 assertion request method/body 或 URL safety。 | 移除預填後既有測試需明確填 synthetic credential；目前不能阻止此回歸。|
| CF-05 | 其他 Web forms | 多個 form 也只用 `onSubmit`；但已檢查到的管理 temporary-password inputs 沒有 `name`，不會被原生成功控制項序列化。 | 目前未發現第二個可重現的 password-in-query 點；仍應由 static contract 防止未來加 `name` 後重現。|
| CF-06 | `services/api/app/observability/logging.py:8-67`、`services/api/app/main.py:41-43` | `SensitiveLogFilter` 能遮罩 token/secret/password/authorization 等，啟動時只明確掛到 `uvicorn.access`。 | Uvicorn request target 已受保護；一般 `logging.getLogger(__name__)` 與 handler 層的全域 coverage 未被證明。|
| CF-07 | `tests/security/test_observability_logging.py` | 已測 photo capability Uvicorn redaction，並刻意保留 ordinary query。 | 目前沒有 `/login` query、Referer、application logger、exception 或 Next log 的跨層 sentinel test。|
| CF-08 | `infra/local/nginx/line-local.conf.template:16-25`、`infra/edge-nginx/strayhub.enadv.quest.conf:10-19` | Standard format 記 `$request` 及 `$http_referer`；只有 public animal photo route 使用 query-free、Referer-free format。 | Login、LIFF entry、QR deep link 等若帶敏感 query，會進 standard access log。|
| CF-09 | `infra/edge-nginx/strayhub.enadv.quest.conf:33`、`infra/gce/nginx/strayhub.conf:17` | HTTP→HTTPS redirect 保留 `$request_uri`。 | 若 client 已送達帶秘密 HTTP URL，第一個 HTTP request 已可被 access log／edge 看見，redirect 也會繼續攜帶 query。源頭禁止仍是主控制。|
| CF-10 | `apps/web/app/v1/[...path]/route.ts:137-142` | Next proxy 將 `request.nextUrl.search` 原樣複製到 upstream。 | 合法 query 可運作，但任何已進 `/v1` URL 的秘密會再穿過 Next／Uvicorn；proxy 不是安全清理邊界。|
| CF-11 | `scripts/test_line_local.sh`、`infra/local/nginx/line-local.conf.template` | 單一 ngrok 指向 local nginx；nginx 使用 `/v1/` 與 `/` catch-all。 | Internet 可到所有 Next route、所有 `/v1/**` API（仍受各 endpoint auth），不只 webhook／LIFF。|
| CF-12 | `scripts/demo-line.sh:118, 209-242` | ngrok 直接指向 Next dev server，而 Next 再代理 `/v1`；同樣是 catch-all。 | `/login`、management pages、Next proxy APIs 全部暴露。|
| CF-13 | Web route tree、FastAPI router registration | 公開 tunnel 可達 `/login`、`/`、`/animals/**`、`/reports/**`、`/settings/**`、`/shelters/**`、`/platform-admins`、`/volunteers/**`、volunteer pages、Next assets，以及所有 `/v1/**`。 | Authorization 仍在後端執行，但 attack surface 與 credential-stuffing 面被不必要擴大。|
| CF-14 | `services/api/app/application/media_access.py:109-185, 217-296` | Animal photo capability 預設 300 秒，簽名且綁 purpose、organization、animal、object key digest；resolve 重新做 tenant/resource policy。 | Class B，可保留在 URL；必須 query-free logging，不應因本期任意改 TTL。|
| CF-15 | `services/api/app/api/media.py:89-109` | Staff signed download URL 經 authenticated POST 取得，300 秒，storage adapter 生成。 | Class B；完整回傳 URL 不得進 app/audit log，storage host 的 log policy需納入 runtime 驗證。|
| CF-16 | `services/api/app/application/qr_token_service.py:15-117`、`services/api/app/api/qr_codes.py:58-75` | QR token 是 HMAC opaque bearer，綁 QR id；DB 只存 digest，可 regenerate/revoke，但 token 本身沒有固定 TTL。Deep link 含 `organization_id` + `qr_token`。 | Class B；可重放至撤銷，初次頁面載入前仍可能進 edge/tunnel logs。|
| CF-17 | `apps/web/app/(volunteer)/animal-confirmation/page.tsx:284-291` | QR payload 讀取後用 `history.replaceState` 清掉 query，API resolve 以 POST body 傳 token。 | 已有 browser-side scrub，但不能回收首次 HTTP request 已留下的 log。|
| CF-18 | `ShelterVolunteerEntryReference` model／migration 0030、entry adapter | `entry` 為 32-byte random opaque reference，DB 存 digest，purpose/organization-bound，預設 90 天，可 revoke/rotate，resolver 檢查 expiry。 | Class B；不是短效值，需全程省略／遮罩及在 LIFF recovery 完成後清理。|
| CF-19 | `VolunteerEntryClient.tsx`、`liffUrl.ts` | `entry` 會跨 LIFF redirect/recovery 保留；legacy `id_token` 會用 replace 清除，id token 後續以 POST body exchange。 | 現有 legacy scrub 是良好控制；`entry` 仍可能進 initial request、ngrok/nginx log。|
| CF-20 | volunteer application frontend/API | Application status 使用 `POST /v1/volunteer-applications/status` 或 `/self-status`，LINE `id_token` 在 JSON body。 | repository 中沒有「application status short-lived URL token」；不得在 registry 虛構。|
| CF-21 | GCE/edge nginx headers | 正式 nginx 使用 `Referrer-Policy: strict-origin-when-cross-origin`。 | 跨 origin 通常只送 origin；同 origin 導航/request 仍可能帶完整 path/query。Local LINE nginx 未設定此 header。|
| CF-22 | `AuditService` 與 `model_dump_for_audit` | Audit persistence 會直接序列化 caller 提供的 before/after/reason，沒有中央敏感欄位 mask。 | 目前抽查的 account/QR audit 只存安全摘要，未找到 raw password/token；但未來 caller 誤傳時沒有最後防線。|
| CF-23 | tracked env/deployment files | 真實 production secrets 由 Secret Manager/runtime file 注入；tracked `.env.example` 與 verification example 使用 fake/synthetic values。 | 未發現 tracked 真實 secret；這不代表本機 `.env` 或外部 log 未含秘密。|
| CF-24 | README、seed/demo scripts、login UI | `local-only-password` 大量存在於 seed、文件、E2E、demo output；login UI 同時硬編碼帳號與密碼。 | Synthetic credential 本身可存在本機 fixture，但曾透過 public tunnel 可用且已進 URL，該實例須視為曝光、輪替並撤銷 session。|
| CF-25 | frontend diagnostics search | LIFF diagnostics 只記 presence／state，不輸出 raw id token/entry；未找到 Sentry/PostHog/gtag 等自建 analytics。LIFF package 自帶 analytics dependency。 | 自建 analytics exposure：not found；第三方 LIFF/ngrok 行為仍需 runtime/供應商設定確認。|

### 2.2 likely（需 runtime 驗證）

- Next development request log 很可能看得到完整 `/login?...` request target；需 sentinel runtime test。
- ngrok inspector 很可能保存完整 request URL；保留時間、刪除能力取決於帳戶與 agent 設定。
- `strict-origin-when-cross-origin` 下，同源 asset/API request 可能帶完整敏感 Referer；需 browser network test。
- Uvicorn filter 可處理 `password=...` 字串，但目前未驗證 percent-encoding、重複 key、巢狀 URL 與 malformed query。
- Object-storage access logs 是否永久保存 staff signed URL query，repository 無法證明，需環境盤點。

### 2.3 not found

- 沒有 FastAPI GET login endpoint。
- 沒有程式從 `/login` query 讀回 username/password。
- 沒有 application-status URL bearer token；狀態 identity token 在 POST body。
- 沒有 tracked production secret 值或額外 app analytics SDK 初始化。
- 沒有在抽查的 account/QR audit call site 發現 raw password、id token、QR token 或 signed URL。

## 3. Root Cause

### 正常流程

```text
Browser /login
  → hydrated React onSubmit + preventDefault
  → POST /v1/auth/login (application/json body)
  → Next /v1 proxy（local direct-Web 模式）或 nginx API route
  → FastAPI SessionService.login
  → password hash verification + server-side session issuance
```

### 異常 fallback

```text
Browser receives SSR <form> with no method/action
  + named username/password controls already contain values
  → user clicks submit / presses Enter before handler is active
  → HTML default: GET current document
  → /login?username=...&password=...
  → browser history + tunnel/edge/Web request logs
```

根因不是 API method 錯誤，而是 HTML 本身沒有安全 fallback，安全行為只存在於 client-side
event handler。hydration 前按鈕也是 enabled。敏感資料首次進入 URL 的精確邊界是「瀏覽器
原生 form serialization」。後續 nginx、Next、ngrok、history 與 Referer 是擴散／保存層。

## 4. Attack / Exposure Paths

1. **Pre-hydration submit**：慢網路、bundle failure、React error、使用者快速點擊或 Enter。
2. **Browser persistence**：address bar、history sync、bookmark、autocomplete、copy/share、screen recording。
3. **Tunnel persistence**：公開 ngrok 先看到完整 URL，應用程式後續 canonicalize 無法回收。
4. **Reverse proxy**：standard nginx `$request` 及 `$http_referer` 保存 query。
5. **Next runtime**：catch-all Web tunnel 收到 `/login?...`；dev request logging 是否完整保留需 runtime 證明。
6. **Referer propagation**：同源 request 在現行 policy 下可能帶完整 query；跨 origin 通常只剩 origin。
7. **Human redistribution**：使用者複製或傳送含 credential 的 URL。
8. **Capability replay**：QR、entry、photo、signed URL 被截圖／轉傳後，在 expiry/revocation 前重放。
9. **Audit/application regression**：目前 audit serializer 無 central mask；新 caller 若傳入 raw payload 可持久化秘密。
10. **CLI/terminal artifact**：entry issuance CLI 一次輸出 raw reference，terminal scrollback/CI capture 可形成副本。

## 5. Sensitive URL Inventory

| URL / parameter | 實際存在 | 現行傳輸 | 現行控制 | 主要缺口 |
|---|---:|---|---|---|
| `/login?username&password` | 是，異常 fallback | Browser native GET | API 不採信 query | source prevention、canonicalization、logs、tests |
| `access_token`, `refresh_token` | 有 token，未發現 URL 使用 | JSON response、sessionStorage、Authorization/body | server-side session check | 非本期 session redesign；static URL ban |
| LIFF `id_token` | 有；legacy URL 相容碼存在 | SDK→POST body | URL scrub、server verification | 首次 legacy request log policy |
| `/volunteer-entry?entry=` | 是 | LIFF URL/recovery | opaque、digest-only DB、90d、purpose/org scope、revoke | nginx/ngrok log、scrub timing |
| `/volunteer-application?...` | 是 | `view`, `organization_id`, legacy entry/liff.state | server verifies identity/target | distinguish public hint from capability; safe log |
| `/animal-confirmation?organization_id&qr_token=` | 是 | QR deep link | HMAC opaque、digest DB、revoke、POST resolve、URL scrub | no fixed TTL；initial request log |
| `/v1/public/.../photo?token=` | 是 | LINE/browser image URL | 300s、signed、purpose/org/resource bound、special logs | retain registry/runtime checks |
| staff signed media URL | 是，response value | authenticated POST returns storage URL | 300s、tenant/role check | storage/tunnel logging not proven |
| animal confirmation token | 是，但不在 URL | JSON response then POST body | user/org/membership/session/animal bound | register as body-only credential, not URL exception |
| care-report handoff id | path/body workflow identifier | authenticated route/body | expiry and tenant authorization | Class C identifier; never sufficient alone |
| `organization_id`, `animal_id`, resource UUID path | 是 | URL path/query | server-side tenant checks | Class C; do not treat as authorization proof |
| search/page/date/status/cursor/`v` | 是 | ordinary query | normal endpoint auth | Class D; keep observability |

## 6. Sensitive URL Registry

Registry 應為單一 machine-readable source（建議放既有 security/contract 邊界，而非新 service），
欄位：`route_pattern`, `parameter`, `classification`, `purpose`, `owner`, `ttl_seconds`,
`reusable`, `revocation`, `tenant_binding`, `resource_binding`, `logging_policy`,
`referer_policy`, `exposure_scope`, `scrub_event`, `mitigation`, `tests`。

| Parameter / path | Class | Purpose / owner | TTL | Reusable / revoke | Log / Referer policy | Exposure / mitigation |
|---|---|---|---:|---|---|---|
| `password`, `temporary_password` | A Forbidden | authentication/account management | n/a | no | never log; no Referer | body only; static ban + form contract |
| `access_token`, `refresh_token`, JWT, Authorization, provider/API secrets | A Forbidden | auth/provider | token-defined | bearer | never log | header/body only; never redirect/QR/hash |
| LIFF `id_token` | A Forbidden | LINE identity exchange | provider-defined | bearer | never log | SDK→POST body; legacy query immediately replace |
| public photo `token` | B Restricted Capability | `media_access` | 300s | bounded replay; expiry | omit query and Referer | public LINE/image route; purpose/org/animal/object bound |
| `qr_token` | B Restricted Capability | `qr_token_service` | no fixed TTL | reusable until revoke/regenerate | omit/redact query and Referer | QR/deep link only; digest DB; scrub after capture |
| `entry` / `shelter_entry_reference` | B Restricted Capability | volunteer access | 90d | reusable; revoke/rotate | omit/redact query and Referer | LIFF entry/recovery; purpose/org bound; scrub after exchange/recovery |
| storage signed URL query | B Restricted Capability | media/storage | 300s | bounded replay; expiry | never app-log full URL | authorized response only; inspect storage access log |
| standard OAuth/LIFF `code`/`state` if introduced | B Restricted Capability | provider callback | provider/session bound | protocol-defined | query-free callback log | only registered callback; scrub after exchange |
| `organization_id` | C Public Identifier / hint | LIFF target, filters | n/a | yes | standard unless paired with B | never authorizes; server verifies membership/entry |
| animal/media/report/handoff UUID path identifiers | C Public Identifier | resource addressing | n/a | yes | standard | authorization + tenant scope required |
| search/page/date/sort/status/cursor/`v` | D Ordinary Query | UI/filter/cache | n/a | yes | standard log allowed | no credential semantics |

Class A/B/C 是需求要求的最低分類；Class D 明確保留一般 query，避免把正常識別與查詢誤判
為 credential。所謂「application status short-lived URL token」標記為 not found，不加入例外。

## 7. Login Remediation Strategy

| 項目 | 決策 | 策略 |
|---|---|---|
| 明確 POST fallback | 必做 | form 設定 `method="post"`，使任何 native fallback 不可能形成 credential query。|
| hydration 前 submit | 必做 | SSR 初始狀態 disable submit；client effect 完成後才 enable。測試 keyboard/Enter。|
| action / no-action | 必做 | 採明確 `method="post" action="/login"` 作 fail-closed native fallback；SSR submit維持disabled，因此正常不會送出document POST，即使被強制提交也只會得到不支援的POST而不形成URL query。React handler仍攔截正常流程。不可只靠省略action。|
| 正常 API contract | 必做 | 保持 JSON `POST /v1/auth/login`（不是背景文字中的 `/auth/login`），不改 response/session contract。|
| password 預填 | 必做 | state 初值改空字串；E2E 明確填 synthetic password。|
| username 預填 | 建議 | production UI 預設空值，保留 `autocomplete="username"`；若要 demo convenience，改由 local-only helper/fixture 明確提供，不進 URL。|
| frontend hard-coded demo credential | 必做 | 從 login bundle 移除 username/password；seed/docs 可保留 synthetic fixture，但不得被 public tunnel 預設暴露。|
| legacy sensitive query | 必做 | server/earliest render 不採信；以 replace semantics canonicalize `/login`，確保 history 不新增含秘密 entry。|
| replace vs push | 必做 | 使用 replace；push 會留下舊 URL 在 back history。|
| 清除時機 | 必做 | edge/server 最早可行位置優先，client effect 作補強；即使清除仍需 safe access log，因首個 request 已到 edge。|
| Referrer-Policy | 必做 | `/login` 使用 `no-referrer`；不要依賴全站 `strict-origin-when-cross-origin` 保護同源 query。|
| autocomplete | 必做 | username=`username`、password=`current-password` 保留；不要用 `autocomplete=off` 假裝修復。|
| login error | 必做 | 保持泛化「帳號或密碼錯誤」；測試 response/UI/log 不反射 submitted values。|
| frontend logging | 必做 | 禁止 console/error context 帶 form state、request body 或 sensitive URL；用 sentinel test。|
| HttpOnly cookie/MFA/OAuth rewrite | 本期不做 | 與 password-in-URL 封堵無必要依賴，列 Deferred。|

## 8. Logging Hardening Strategy

採「共同分類、各層最小 hook」，不關閉整站 observability。

| Route / surface | 現況 | 目標策略 |
|---|---|---|
| `/login` | nginx standard `$request` + Referer | query-free、Referer-free safe format；保留 method/path/status/bytes/latency/correlation。|
| `/v1/auth/login`, refresh, LIFF exchange | POST body；access target通常無秘密 | safe-format；禁止 body/header/Referer，application errors 不記 credential。|
| `/volunteer-entry`, `/volunteer-application` 含 entry | standard log | safe-format 或 route+classified keys redaction；不保存 raw entry/legacy id token。|
| `/animal-confirmation` 含 qr_token | standard log | query-free、Referer-free。|
| public photo capability | 已 special format | 保持並納入 registry contract。|
| staff signed URL issue endpoint | standard path，URL 在 response | access log可保留 path；禁止 response body/app/audit log，另查 storage provider logs。|
| ordinary management filters | standard log | 保留一般 query，不做全站 query shutdown。|
| Uvicorn | root logger filter只掛 access logger | 擴充測試到 encoding/repeated/nested values；確認 filter 於所有 startup mode 生效。|
| application/exception logs | logger 使用不一致 | 使用既有 `get_logger` 或 handler-level existing hook；不要大改 logging architecture。|
| audit DB | serializer無 mask | 在 audit persistence boundary 加 fail-safe mask/reject，並保留 caller 僅傳摘要的原則。|
| Next dev/proxy | runtime behavior未證明 | 避免自訂 log request URL/body；以 sentinel runtime test決定是否需最小 existing hook。|
| CLI | entry raw value一次輸出 | 僅 interactive terminal 明示、CI capture guard、stderr 不回顯；不要把 raw value寫檔。|

nginx `map` 應由 `$uri` 判斷敏感 route；safe format 不使用 `$request`、`$request_uri`、`$args`
或 `$http_referer`。如無法可靠逐 key redact，整條 query 省略。HTTP redirect server 也必須套用相同
route map，不能只保護 HTTPS server。

## 9. Tunnel Exposure Strategy

### 現況

兩個 helper 均為 catch-all：

- `test_line_local.sh`：Internet → ngrok → local nginx → `/v1/**` FastAPI、`/**` Next。
- `demo-line.sh`：Internet → ngrok → Next dev → `/v1/**` proxy → FastAPI。

預設可達 route 因而等同整個 Web route tree與整個 API router tree。這不代表未授權請求會成功，
但違反 demo 最小暴露原則。

### 目標 allowlist（由 contract test 從實際 route constants 驗證）

預設 ALLOW：

- `POST /v1/line/webhook`（保留 `X-Line-Signature` 驗證）。
- `GET /v1/public/animals/{id}/photo` 及 adoption variant（LINE Flex image）。
- `GET /volunteer-application`、`GET /volunteer-entry`、`GET /animal-confirmation`、
  必要時 `GET /care-report` 與 `/assigned-care/{id}`。
- LIFF flow 實際使用的 API：public organization directory、LIFF exchange、application
  status/submit/withdraw、自身 status、active shelter context、animal search/QR resolve/confirm、
  handoff與 care-report draft endpoints。
- `/_next/static/**` 與實際 runtime 必要的 Next asset；development HMR 只在明確 local-dev mode。
- `/healthz` 是否公開由 helper health check 需要決定；若允許只回最小狀態。

預設 DENY：

- `/login`、`/` management home、全部 management pages。
- `/v1/management/**`、`/v1/platform/**`、organization/membership governance API。
- debug、OpenAPI/docs、非必要 storage/internal endpoints。
- 未列入 allowlist 的任何 `/v1/**` 或 Web route；不得保留 catch-all pass-through。

`demo-line.sh` 與 `test_line_local.sh` 應共享同一 route policy，避免一套修好另一套仍暴露。若需要
遠端管理展示，另開 explicit opt-in mode：synthetic DB guard、短效隨機 credential、醒目 banner、
固定 expiry、停止時 revoke；不得當成 LINE demo 預設行為。

## 10. Credential Rotation / Incident Actions

已觀察到 URL 中的 `demo-furkids-admin / local-only-password` 視為曝光，最低處置順序：

1. 停止 helper-owned tunnel；確認不是只關瀏覽器分頁。
2. 在 synthetic demo database 旋轉該帳號 password；public-demo可用值改為每次啟動產生或由明確
   environment輸入，不可只是把舊常數換成另一個共同常數。同步seed/E2E/docs；isolated test fixture
   可保留不具外部權限的synthetic literal，但frontend bundle不得預填或持有可登入runtime的值。
3. 將該 user 的所有 active `SessionRecord` 標為 expired/revoked，使 access token 的 server-side
   session check失效；refresh token 隨 session 一併不可用。現有 platform repository 有
   `invalidate_sessions` pattern，但實作應放在安全、通用且 tenant-aware 的既有邊界。
4. 重新啟動 tunnel 以取得新的 agent/session 狀態；先完成 allowlist 或暫時不公開 management。
5. 清理可控制的 local nginx/Next/ngrok log、Playwright trace/HAR/screenshot及 shell history；瀏覽器
   history由使用者清理並關閉跨裝置 history sync 副本（如適用）。
6. 檢查 ngrok dashboard/inspector retention與可刪除項；記錄「已請求/已清除」而非宣稱所有副本
   可證明消失。
7. 若同一 password 在任何非 synthetic account、其他環境或服務重用，立即全部輪替；目前 repo
   無法證明外部重用情況。
8. Incident evidence 只保存時間、帳號不可逆 fingerprint、受影響 surface、輪替/撤銷結果，不保存
   原始 password 或完整 URL。

本規劃階段沒有執行停止 tunnel、輪替、刪 log或 session invalidation。

## 11. Testing Strategy

### Login browser / network

- Playwright 正常登入、錯誤密碼、click、Enter、多 organization、platform-only：每次都 assertion
  URL/history 不含 username/password，request 為 JSON `POST /v1/auth/login` 且 credential 只在 body。
- Legacy `/login?username=SENTINEL&password=SENTINEL`：不登入，最終 URL 為 `/login`，使用 replace。
- `javaScriptEnabled: false` context：SSR submit button不可提交或 safe POST不含 query；檢查 document URL。
- Hydration race：route/block `/_next/**` scripts 或以專用 test fixture延遲 hydration，在此期間 click/Enter。
  若 Playwright 對 race 不穩定，以 SSR HTML contract（method/action/disabled）作 deterministic gate，
  Playwright no-JS 作 runtime complement。
- Password manager/autofill語意：保留 autocomplete token並驗證 password initial value為空。

### Logging / URL registry

- 每個 scenario 使用不同 synthetic sentinel；掃 browser URL/history/network、ngrok inspector、local nginx、
  Next stdout、Uvicorn、application/error/audit及 test artifact。
- Assertion message只顯示 digest與 surface，不回顯 sentinel。
- 測 percent-encoded、大小寫、重複 key、fragment、nested signed URL與 sensitive Referer。
- Registry completeness test掃描 URL builders/query readers/FastAPI Query fields/nginx maps；未知 sensitive key
  fail closed，但 ordinary query fixtures必須 pass。

### Capability / tenant isolation

- Photo：valid/expired/wrong purpose/changed object/cross-org；不改 300s TTL。
- QR：valid/revoked/regenerated/cross-org/replay；確認 URL capture後 scrub。
- Entry：valid/expired(90d)/revoked/rotated/forged/cross-org及 LIFF recovery。
- Signed media：authorized role/current tenant；foreign tenant/unauthorized拒絕；response URL不進 logs。
- Application status：確認 id token只在 POST body，沒有 URL token。

### Tunnel

- nginx syntax/contract + runtime allow/deny matrix；必要 route逐一 smoke，login/management/API/docs逐一 deny。
- webhook smoke不得停用 signature verification。
- 兩個 helper都要通過相同 policy test；停止後確認只終止 helper-owned process並清理 temporary files。

## 12. Phase A / B / C Implementation Plan

### Phase A — Immediate containment

#### SEC-A01 — 封堵 login native GET

- **目的**：使 hydration 前、no-JS、Enter與 handler failure都不產生 credential URL。
- **修改範圍**：login form SSR/native behavior；不改 auth API/session contract。
- **相關檔案**：`apps/web/app/login/page.tsx`、其 component/unit tests。
- **依賴**：無。
- **具體修改**：`method="post" action="/login"` fail-closed fallback、SSR disabled hydration gate、password空值、username不硬編碼、
  保留正確 autocomplete；normal handler仍 JSON POST `/v1/auth/login`。
- **驗收**：normal/no-JS/pre-hydration/click/Enter/error 均無 credential query；登入主流程不變。
- **Regression risk**：hydration gate未解除造成無法登入；password manager與 keyboard可用性。
- **獨立 commit**：是。

#### SEC-A02 — Legacy login URL canonicalization與頁面 policy

- **目的**：不採信並盡早清除既有 sensitive login URL，阻止後續 history/Referer擴散。
- **修改範圍**：`/login` 最早可行 routing/render boundary及 response headers。
- **相關檔案**：login page/layout或既有 Next middleware/config邊界（實作前選最小既有 pattern）、E2E。
- **依賴**：SEC-A01。
- **具體修改**：偵測 forbidden keys、replace/canonical redirect至 `/login`、`no-store`、`Referrer-Policy: no-referrer`；
  不讀取或反射值。
- **驗收**：legacy URL不登入、back history無 sensitive entry、同源 request無 sensitive Referer。
- **Regression risk**：錯誤清除合法 login return-state；redirect loop。
- **獨立 commit**：是。

#### SEC-A03 — Login tests與fixture去預填依賴

- **目的**：讓 regression suite真實輸入 synthetic credential並驗證 transport。
- **修改範圍**：Playwright/login tests及 mock fixtures。
- **相關檔案**：`apps/web/e2e/login-home.spec.ts`、`apps/web/e2e/fixtures.ts`、login unit test。
- **依賴**：SEC-A01、SEC-A02。
- **具體修改**：fill username/password；assert POST/content-type/body、clean URL、錯誤/Enter/no-JS/hydration。
- **驗收**：測試在恢復 GET fallback或預填 password時會失敗。
- **Regression risk**：hydration race test flaky；以 deterministic SSR contract補強。
- **獨立 commit**：是（可與 A01 同 PR，但保留獨立 commit）。

#### SEC-A04 — 已曝光 demo credential incident處置

- **目的**：降低已知 URL credential的後續可利用性。
- **修改範圍**：synthetic demo account、seed/docs/test fixture、session invalidation runbook；不碰正式資料。
- **相關檔案**：`scripts/seed_*`、`scripts/demo.sh`、README/demo docs、既有 authentication repository/service或一次性安全維運指令、incident runbook。
- **依賴**：A01完成後再重新公開 tunnel。
- **具體修改**：public-demo runtime改用啟動時生成或明確environment提供的短效值，不以新hard-coded共同密碼取代舊值；frontend不再持有；撤銷該 user全部 sessions；清理可控 artifact並記錄不可回收風險。
- **驗收**：舊 password與舊 session均失效；新值不出現在 URL/log/source bundle；只作用於 synthetic target。
- **Regression risk**：seed/E2E/docs不同步；誤操作 production-like data。需要 environment與target guard。
- **獨立 commit**：程式/文件可 commit；實際輪替與清理是受控維運動作，不應把 secret寫進 commit。

### Phase B — Transport & logging hardening

#### SEC-B01 — 建立 machine-readable Sensitive URL Registry

- **目的**：集中 A/B/C/D分類與所有 URL例外。
- **修改範圍**：security contract/fixture及validator；不建立通用 token service。
- **相關檔案**：建議沿用 `tests/security/`、`specs/012.../contracts/security-boundary.md`，registry放可被 Python test讀取的既有 config/test fixture位置。
- **依賴**：A01。
- **具體修改**：登錄 photo、QR、entry、signed URL、provider callback；application-status URL token明確 not-found；普通 query allowlist/category。
- **驗收**：每個 Class B具 purpose/owner/TTL/reuse/revoke/scope/log/referer/scrub/tests；未知敏感例外使CI失敗。
- **Regression risk**：static scan false positive/negative；需 route+key而非只看名稱。
- **獨立 commit**：是。

#### SEC-B02 — nginx sensitive route safe logging

- **目的**：阻止 query/Referer在 local、edge與GCE access log持久化。
- **修改範圍**：現有 nginx maps/formats，不改 topology。
- **相關檔案**：`infra/local/nginx/line-local.conf.template`、`infra/edge-nginx/strayhub.enadv.quest.conf`、`infra/gce/nginx/strayhub.conf`、nginx contract tests。
- **依賴**：B01 route registry。
- **具體修改**：將 login/auth callback/LIFF entry/QR加入 sensitive map；safe format只留 method `$uri` protocol status bytes latency/correlation；HTTP redirect server同 policy。
- **驗收**：sentinel不出現在 query/Referer log；ordinary query仍保留；nginx syntax/tests pass。
- **Regression risk**：route regex漏配/過配、失去一般診斷資料。
- **獨立 commit**：是。

#### SEC-B03 — Uvicorn/application/exception/audit defense-in-depth

- **目的**：讓非access logger與audit persistence也有最後遮罩邊界。
- **修改範圍**：既有 observability與audit boundary的最小hook。
- **相關檔案**：`services/api/app/observability/logging.py`、app startup、使用 raw logger的少數模組、`AuditService`/audit serialization、security tests。
- **依賴**：B01。
- **具體修改**：handler/startup coverage、encoding-aware URL redaction、structured extra/exception test；audit對Class A/B key mask/reject，保留安全摘要。
- **驗收**：各 logger/audit sentinel為0；合法 event/status/correlation可診斷；沒有raw body logging。
- **Regression risk**：過度遮罩業務欄位、破壞Uvicorn formatter args或audit搜尋。
- **獨立 commit**：是。

#### SEC-B04 — LIFF/QR/signed URL lifecycle收斂

- **目的**：使Class B在必要期間存在，消費後清理且全程不被log。
- **修改範圍**：既有 URL lifecycle與tests；不改TTL或授權模型。
- **相關檔案**：`VolunteerEntryClient.tsx`、`VolunteerApplicationClient.tsx`、`liffUrl.ts`、animal confirmation、media/QR/entry tests。
- **依賴**：B01、B02、B03。
- **具體修改**：entry只保留至LIFF recovery/exchange必要點；QR維持capture即replace；signed URL不進log/audit；document callback rules。
- **驗收**：LIFF redirect/retry正常；legacy id token、entry/QR在規定事件後消失；tenant/revoke/expiry tests pass。
- **Regression risk**：過早清除entry導致LIFF loop或無法恢復；必須用state matrix驗證。
- **獨立 commit**：是。

#### SEC-B05 — CLI與開發輸出安全

- **目的**：降低一次性entry與demo credential進terminal/CI artifact的機率。
- **修改範圍**：既有 issuance/demo scripts與docs。
- **相關檔案**：`scripts/issue_volunteer_entry_reference.py`、`scripts/demo.sh`、`scripts/demo-line.sh`、contract tests。
- **依賴**：B01。
- **具體修改**：interactive/explicit reveal、禁止CI implicit capture、只印安全metadata與警告；raw值仍只發一次且不持久化。
- **驗收**：default output不含credential；需要raw reference時明確opt-in且stderr/error不回顯。
- **Regression risk**：破壞既有人工設定流程；需清楚 migration instruction。
- **獨立 commit**：是。

### Phase C — Regression prevention and exposure boundary

#### SEC-C01 — 統一本機 LINE tunnel route allowlist

- **目的**：預設公開必要 LINE/LIFF surface，不公開 management/login/internal API。
- **修改範圍**：兩個helper及local nginx；不改GCP topology。
- **相關檔案**：`scripts/test_line_local.sh`、`scripts/demo-line.sh`、`infra/local/nginx/line-local.conf.template`、contract tests。
- **依賴**：B01、B02、必要route runtime inventory。
- **具體修改**：共享/生成allowlist；移除pass-through catch-all；Web/API/assets逐route；deny為404或最小403；保留signature verification。
- **驗收**：必要LINE/LIFF vertical flow全通；`/login`、management、platform、docs、unknown routes全拒絕。
- **Regression risk**：漏掉Next asset、LIFF redirect或care-report API；需真实vertical smoke。
- **獨立 commit**：是。

#### SEC-C02 — 遠端 management demo明確opt-in（若產品決定保留）

- **目的**：將管理展示與LINE demo分離。
- **修改範圍**：demo helper mode、synthetic guard、ephemeral credential lifecycle。
- **相關檔案**：demo scripts、seed/bootstrap、docs/tests。
- **依賴**：C01；產品決策。
- **具體修改**：explicit flag、synthetic DB proof、random short-lived credential、expiry/banner、stop-time revoke。
- **驗收**：default mode永不開management；opt-in結束後credential/session失效。
- **Regression risk**：credential lifecycle與cleanup失敗；此task可延後，不阻塞C01。
- **獨立 commit**：是。

#### SEC-C03 — Static URL policy與cross-layer sentinel CI

- **目的**：阻止新表單/query builder/logger重現同類漏洞。
- **修改範圍**：security tests/CI；不掃描或輸出真實env值。
- **相關檔案**：`tests/security/**`、`tests/contract/**`、Playwright config/spec、CI/verify scripts。
- **依賴**：A03、B01-B05、C01。
- **具體修改**：form contract、URL candidate scan、registry completeness、encoded sentinel、多層log/tunnel matrix、artifact cleanup。
- **驗收**：刻意新增named password GET form/未登錄token/raw logger會fail；合法query與核准capability pass。
- **Regression risk**：掃描規則脆弱、CI runtime增加；分static fast gate與runtime focused suite。
- **獨立 commit**：是。

#### SEC-C04 — Security runbook與review checklist

- **目的**：讓維運與reviewer能重複執行rotation、log檢查、tunnel驗收。
- **修改範圍**：documentation only。
- **相關檔案**：本feature quickstart、README/demo/deployment security docs。
- **依賴**：A04、B/C最終行為。
- **具體修改**：分類、owner、incident 30-minute checklist、不可回收副本聲明、review questions、command index。
- **驗收**：新操作員可只依runbook完成synthetic演練，報告不含raw sentinel。
- **Regression risk**：文件與script drift；contract test檢查關鍵route/command引用。
- **獨立 commit**：是。

## 13. Deferred Security Improvements

- Authentication全面改為HttpOnly/SameSite cookie。
- MFA、OAuth/provider migration、passwordless登入。
- Refresh token architecture重新設計（現有refresh family rotation不因本期修改）。
- 全站CSP、Permissions-Policy與完整security-header program。
- 全面zero-trust/network segmentation或GCP/nginx topology重建。
- CDN/cache/signed URL供應商架構變更。
- QR token固定TTL或single-use重新設計；需要獨立產品/現場流程評估。
- 第三方SIEM/DLP導入與歷史log forensic program。

## 14. Open Questions

以下不阻塞A01-A03/B01規格化，但會影響後續實作細節：

1. ngrok目前帳戶/方案的inspector與edge log retention、刪除能力為何？repository無法回答。
2. Object storage是否啟用access logging，是否保存signed URL query？需逐環境查證。
3. 遠端management demo是否仍是實際需求？若否，SEC-C02可不實作，只保留local management。
4. `/care-report`與`/assigned-care/{id}`是否必須由本次public LINE tunnel直接使用，或只需LINE聊天流程？
   C01實作前應用一次真實vertical smoke確定最小清單。
5. 已曝光demo password是否曾在其他環境/帳號重用？若有，incident scope需擴大；repo內無法證明。

## 15. Recommended next Spec Kit command

Spec、plan、research、data model、security boundary、quickstart與本現況分析已可支撐task generation。
下一步建議：

```text
/speckit-tasks
```

結論：**不應直接跳入 implementation**；應先以 `speckit-tasks` 將上述Task ID轉成依賴排序的
`tasks.md`並review。現有spec/plan已在本輪更新完成，無需再開另一輪specify；完成tasks review後，
先做Phase A，再進B/C。
