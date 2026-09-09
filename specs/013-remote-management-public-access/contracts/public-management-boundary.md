# Contract：Public Management Boundary

## 目的

本 contract 定義 shared tunnel 上「可到達」與「可授權」的雙重邊界。Gateway allowlist 只決定
request 是否能送到 Next/FastAPI；任何 route entry 都不代表使用者已獲授權。

## Profile composition

```text
line-only
  = existing LINE registry

shared-demo-dev
  = existing LINE registry + management registry

shared-demo-production
  = existing LINE registry + management registry
    - next_dev_hmr - next_static_assets
    + exact build-manifest assets required by allowlisted pages
```

- 未選 profile 時預設 `line-only`。
- Unknown profile、registry collision、invalid pattern 或缺少 host 時，config generation/launcher
  必須 fail，不能回退成 broad proxy。
- T008 manual evidence 未完成時，兩個 shared-demo profile 都不得啟動 public tunnel；本機 synthetic
  contract test 不等於完成該 evidence。
- Production build manifest 解析失敗、出現無法對應的 required page，或 exact asset 集合為空時，
  config generation 必須 fail closed；不得回退成 `/_next/**` 或整個 static namespace。

## Public management UI surface

允許 GET/HEAD：

| Journey | Page paths |
|---|---|
| Login/logout | `/login`；logout 是 API action |
| Shelter context/dashboard | `/` |
| Animals | `/animals`、`/animals/{animalId}`、`/animals/{animalId}/timeline` |
| Reports | `/reports`、`/reports/{reportId}` |
| AI human review | `/ai-review` |
| Care calendar | `/care-calendar` |

所有 UUID segment 只接受 canonical UUID-shaped path。是否存在與是否屬於 active shelter 仍由
FastAPI/repository/RLS 決定；gateway 不解析 tenant ownership。

## API surface

精確 method/path 清單以 `management-tunnel-allowlist.yaml` 為準。既有 LINE registry 提供共用的
`POST /v1/auth/refresh`、`GET /v1/auth/me`、`GET|PUT /v1/auth/active-shelter-context` 與 Next static
assets；management registry 不重複宣告它們。

唯一新增公開的 business mutation 是既有：

```text
POST /v1/management/ai-review/{observationId}/review
```

它仍須經既有角色、tenant scope、狀態轉移與 audit 規則。下列動作不因頁面可讀而公開：animal
create/update/archive、report correction/archive、care/medical reminder mutation、QR/settings、
volunteer governance、PII reveal、platform governance。

## Method and query rules

- 未列 method 一律 404；不依賴 upstream 405 作公開邊界。
- Password login/logout、photo 與 AI review action 要求 empty query；有 query 即拒絕。
- List/filter/page 與 Next RSC request 可保留 ordinary query，但 management sensitive-route access
  log 僅記 method、normalized path、status、bytes、latency、request ID，不記 args/referer。
- `/login` 保留 legacy query 送至 Next 以執行既有 replace canonicalization，但 gateway/nginx log
  不得保存 query；response 維持 `Cache-Control: no-store` 與 `Referrer-Policy: no-referrer`。
- Class B LINE photo capability 保持既有 query 傳遞與專用 redaction，不得被 management policy
  移除或改變 TTL。

## Authorization matrix

| Identity | Login through shared profile | Existing token through shared profile | Core management API |
|---|---:|---:|---:|
| Active STAFF membership | Allow | Allow | Existing tenant policy |
| Active SHELTER_ADMIN membership | Allow | Allow | Existing tenant policy |
| VOLUNTEER only | Deny | Deny | Deny |
| PLATFORM_ADMIN | Deny | Deny | Deny |
| Disabled/expired/no membership | Generic deny | Deny/revoke as applicable | Deny |
| Anonymous | Login page/API only | N/A | 401/404 per existing contract |

「Existing token through shared profile」必須由 FastAPI request-context policy enforcement，不能只靠
login endpoint。Public profile 永遠不新增 organization membership 或 role。

## Frontend scope signal

Shared profile 的 `GET /v1/auth/me` 可在既有 response 加入：

```json
{"public_exposure_profile":"shared-demo-production"}
```

Private/line-only request 固定為 `null`，以維持 response shape 穩定。此值由可信 request context
產生，不接受 client input。Management shell 應以它提供 core-only navigation，並在
report detail、care calendar 等共用 page 隱藏 013 未公開的 correction/archive/reminder mutation
controls，避免使用者看到必然失敗的操作；直接 API request 仍必須被 gateway/backend 拒絕，故此
signal 只能改善 UX，不能作 authorization evidence。

## Cross-tenant invariants

- Active organization 只能由 server-verified membership/context switch 決定。
- A shelter credential 對 B shelter 的 animal/report/area/timeline/calendar ID 不得讀到資料；response
  應沿用既有 non-enumerating 404/403 contract。
- Search/filter/query 不得繞過 tenant predicate。
- `PLATFORM_ADMIN` 的既有 platform scope bypass 在 shared profile 必須關閉；local/private behavior
  不因本 feature 改變。

## Host, path normalization, and upstream

- Runtime origin 必須是設定的 exact HTTPS reserved host；unexpected `Host` 在 upstream 前 404。
- Public scheme 只接受 edge/gateway 覆寫後的可信值；client-supplied `X-Forwarded-Proto` 不得讓
  HTTP request 被應用程式視為 HTTPS。
- nginx 應以 parsed/normalized URI 做 anchored allowlist matching；測試 encoded slash、`..`、`;`、
  duplicate slash、case changes、trailing suffix 與 percent-encoding。
- API routes 只送 FastAPI，page/static routes 只送 Next；catch-all 不代理。
- Production profile 的 `/_next/webpack-hmr` 與其他 dev endpoint 必須 404。

## Headers and logging

- Edge 先 remove 再 set `X-StrayHub-Trusted-Client-IP`；client 不能提供有效替代值。
- nginx 對 API upstream 固定覆寫 `X-StrayHub-Public-Profile`，不得直接 pass-through。
- 應用程式沿用 012 centralized redaction；不得 log password、Authorization、refresh token、LINE
  ID token、capability query 或完整 sensitive URL。
- 一般非敏感 local route observability 不需因本 profile 全域降低。

## Required negative matrix

至少驗證：

- `/v1/platform/**`、`/docs`、`/redoc`、`/openapi.json`、`/metrics`、`/debug/**`
- animal/report/volunteer/QR/settings 的所有未列 mutation
- 任意 `/v1/...` 與 `/_next/...` broad fallback
- dynamic UUID pattern 的 malformed/extra suffix/bypass variants
- production profile 的 HMR
- spoofed Host、profile header、trusted-client-IP header、X-Forwarded-For
- platform admin、volunteer、expired membership、cross-shelter resource

拒絕結果不得把 upstream detail、route existence、帳號存在或 tenant existence 暴露給 caller。
