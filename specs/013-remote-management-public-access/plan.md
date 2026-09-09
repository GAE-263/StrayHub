# Implementation Plan: Remote Management Public Access

**Branch**: `013-remote-management-public-access` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: `/specs/013-remote-management-public-access/spec.md`

## Summary

在既有單一 ngrok reserved host 上新增明確命名的 `shared-demo-production` 與
`shared-demo-dev` 公開入口 profile，透過兩份可組合、預設拒絕的路由 registry，僅公開 LINE
既有流程與規格列出的核心管理唯讀／有限寫入流程。公開主機名稱由 runtime 環境輸入產生 nginx
設定，不寫死於 repository；production profile 以 Next production server 運作並拒絕 HMR。

後端仍是所有授權與租戶隔離的最終邊界。公開 profile 只接受 `STAFF` 與
`SHELTER_ADMIN`，即使既有 `PLATFORM_ADMIN` session 或其他角色能在本機使用部分管理 API，
也不得藉公開入口取得同等能力。登入濫用控制使用既有 PostgreSQL 作為跨 worker 的共享原子
狀態：帳號採 NFKC/casefold/trim 後的 HMAC subject、連續失敗鎖定；來源 IP 採精確 rolling
window 事件。ngrok 與 gateway 必須移除外部同名 header，再傳遞可信來源 IP／公開 profile；
應用程式不得信任任意 client-supplied forwarding header。

公開登入建立的 server-side session 會標示來源，讓緊急 rollback 可先封鎖公開管理路由，再撤銷
所有 remote-management session。既有 sensitive URL、logging redaction、安全 header、LINE
簽章與多收容所隔離均保持不變。

## Technical Context

**Language/Version**: Python 3.12；TypeScript 5.7；Shell／nginx config／YAML

**Primary Dependencies**: FastAPI、SQLAlchemy async、asyncpg、Alembic、Pydantic Settings、
Next.js 15、React 19、nginx、ngrok agent

**Storage**: PostgreSQL 16（既有使用者／session，加上登入濫用共享狀態）；MinIO 僅供既有
受保護媒體，無本功能新資料

**Testing**: Pytest、Ruff、Mypy、Vitest、Playwright、Next build、`nginx -t`、shell／YAML
contract tests

**Target Platform**: Linux/GCP 與 macOS local demo；瀏覽器透過單一 HTTPS ngrok reserved host

**Project Type**: FastAPI + Next.js web application，搭配本機 gateway／tunnel orchestration

**Performance Goals**: 合法登入與核心頁面在 demo 負載下維持可互動；登入限制檢查不新增外部
網路 round trip；gateway policy 判定為常數級 route match

**Constraints**: 單一 public hostname、default deny、production profile 禁止 HMR、帳號第 5 次
錯誤立即鎖定 15 分鐘、同一可信來源 IP 15 分鐘最多接受 20 次登入嘗試、429 必須含
`Retry-After`、公開入口不得授權 `PLATFORM_ADMIN`／`VOLUNTEER`、T008 人工事故處置完成前
不得啟用公開入口或做 runtime acceptance

**Scale/Scope**: 小型共享 demo；兩個公開 profile、約 8 個 UI route family、約 18 個 API
method/path pair、2 個登入濫用資料結構；不涵蓋正式 production ingress 架構重設

## Constitution Check

### Phase 0 前檢查

| 原則 | 結果 | 設計證據 |
|---|---|---|
| I. CRM 唯一事實來源 | PASS | 公開入口只代理既有 API，不建立業務資料副本。 |
| II–IV. 原始資料與 AI 邊界 | PASS | 本功能不改寫原始回報或 AI 結果；AI review 仍走既有服務與人工動作。 |
| V、VII. 志工／LINE 邊界 | PASS | 既有 LINE registry、webhook 簽章與後端規則不變。 |
| VI. 歷史可追溯 | PASS | 動物 timeline 僅透過既有 tenant-scoped API 讀取。 |
| VIII. 權限、隱私、稽核 | PASS | Gateway default deny；後端再限制公開角色；沿用 012 redaction；rollback 可撤銷遠端 session。 |
| IX. P0 獨立性 | PASS | 公開核心管理流程不依賴規格排除的 P1/P2 管理功能。 |
| X. 文件與 Python 品質 | PASS | 規劃文件以正體中文為主；實作完成前須跑全套 Ruff 與 Pytest。 |
| XI. 多收容所隔離 | PASS | 不信任 URL 中的 organization/animal ID；既有 membership、request context 與 RLS 仍是最終邊界，新增跨租戶負向測試。 |

**Gate 結果**：PASS，無需例外。

### Phase 1 後重檢

PASS。資料模型只增加平台級登入防護狀態與 session 來源，不複製 shelter-owned CRM 資料；
contracts 將 route exposure 與 application authorization 分離，且明定公開 profile 不可提升任何
既有權限。資料保存、清理、失敗模式、遷移與 rollback 均已在 `data-model.md` 與 contracts 中
定義。無憲章違規。

## Project Structure

### Documentation (this feature)

```text
specs/013-remote-management-public-access/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── management-tunnel-allowlist.yaml
│   ├── public-management-boundary.md
│   ├── public-tunnel-profiles.yaml
│   └── remote-auth-security.md
└── tasks.md                         # 後續由 /speckit-tasks 產生
```

### Source Code (repository root)

```text
apps/web/
├── app/                             # login 與核心管理 pages
├── components/                      # management shell/navigation
├── lib/                             # API client 與 auth session handling
└── e2e/                             # production-profile browser acceptance

services/api/
├── app/
│   ├── api/                         # auth、management routers/dependencies
│   ├── application/authentication/  # login/session/rate-limit orchestration
│   ├── config/                      # runtime profile與HMAC secret設定驗證
│   └── persistence/
│       ├── models/                  # abuse state與session origin
│       └── repositories/            # atomic PostgreSQL operations
├── migrations/versions/             # schema migration
└── tests/                            # unit/integration/security tests

infra/local/
├── nginx/                           # generated-config template/include
└── docker-compose.yml               # 不新增 Redis

scripts/
├── demo-line.sh                     # 保持 line-only 預設
├── test_line_local.sh               # 保持既有 LINE/HMR 行為
├── generate_public_tunnel_config.py # registry/profile/host 驗證與 config 產生
├── demo-management.sh               # 明確 shared-demo profile 啟動入口
└── rollback_remote_management.py    # route deny + session revocation

specs/012-sensitive-data-transport-hardening/contracts/
└── line-tunnel-allowlist.yaml        # 既有 registry，不重寫

specs/013-remote-management-public-access/contracts/
├── management-tunnel-allowlist.yaml
└── public-tunnel-profiles.yaml
```

**Structure Decision**: 沿用現有 FastAPI、Next.js、`infra/local` 與 `scripts` 邊界；新增的
registry 與 profile contract 放在 feature Spec Kit 目錄，產生器只讀 contracts 並輸出到 runtime
暫存目錄。登入濫用資料存取擴充既有 authentication repository/service，不建立平行 auth
架構。公開入口權限由 gateway exposure policy 與 FastAPI authorization 共同執行，前端只負責
UX，不作安全判定。

## Implementation Strategy

### 1. 可組合且 fail-closed 的公開路由

1. 保留 012 LINE registry，新增 management registry 與三個 profile：`line-only`、
   `shared-demo-production`、`shared-demo-dev`。
2. 產生器先驗證 route ID 唯一性、method、anchored path pattern、upstream、query/log policy、
   profile include/exclude，再輸出 nginx config；任何未知 profile、重複衝突或缺少 runtime host
   均失敗退出。
3. `shared-demo-production` 排除 `next_dev_hmr` 與開發用 broad static route，改由 Next production
   build manifests 產生 allowed pages 實際需要的 exact chunk/CSS paths；`shared-demo-dev` 才可
   包含 HMR 與 bounded static pattern。
4. 未列出的 management、platform、docs、openapi、metrics、debug 與 mutation route 一律在
   gateway 回 404，不送 upstream。
5. dynamic path 必須 bounded；encoded slash、dot segment、重複 slash、大小寫變形與 suffix
   bypass 納入負向 contract test。

### 2. Runtime host 與可信 ingress metadata

1. 啟動器要求完整 HTTPS reserved origin，拒絕 userinfo、path、query、fragment、wildcard 與
   未保留／不相符 hostname；僅 local validation profile 可接受 loopback。
2. ngrok Traffic Policy 移除外部提供的 profile/client-IP header，再以連線 metadata 設定專用
   header；nginx 同樣覆寫送往 FastAPI 的 public-profile 值，不轉送任意 X-Forwarded-For 作為
   rate-limit authority。
3. FastAPI 只在已配置的 loopback gateway hop 接受該 metadata；缺少、重複或未知值即不視為
   public profile，public launcher 的 health check 必須因此 fail closed。
4. `Host` 不等於 runtime reserved host 時，由 nginx 在 upstream 前拒絕。

### 3. 公開角色與多租戶授權

1. 在 request context 加入 server-derived exposure profile；不接受 body/query/client header 指定。
2. 公開 profile 的 password login 僅為具有有效 `STAFF` 或 `SHELTER_ADMIN` membership 的使用者
   建立 session；`PLATFORM_ADMIN`、`VOLUNTEER` 與無有效 membership 者拒絕。
3. 所有公開核心 API 仍執行既有 membership、active organization 與 RLS；另在 management
   dependency 中對 public profile 排除 platform bypass，阻止既有本機取得的 platform token
   被帶到公開入口使用。
4. organization、animal、report 等 client ID 仍由伺服器依 active shelter 重判；加入跨租戶
   404/403 與資料不外洩測試。
5. `/v1/auth/me` 可附加 server-derived、nullable 的 `public_exposure_profile` 作 UX hint；management
   shell 在 shared profile 只呈現核心導覽，report detail 與 care calendar 使用 read-only／scope-safe
   controls。此欄位不授權任何 API，直接呼叫被隱藏的 mutation 仍由 gateway 與 FastAPI 拒絕。

### 4. 共享且原子化的登入濫用控制

1. 使用 PostgreSQL advisory/row lock 實現 account subject 序列化；normalized username 以專用
   HMAC key 雜湊後持久化，不保存原始輸入。
2. 每次嘗試先在 transaction 中檢查 IP rolling window；第 21 次在寫入新事件前回 429，
   `Retry-After` 由最舊仍佔配額事件計算。
3. 帳號第 1–4 次失敗回 generic 401；第 5 次原子更新 `locked_until=now+15m` 並回 429；鎖定期
   內即使密碼正確仍回 generic 429。成功登入清除連續失敗狀態，但不清除來源 IP window。
4. 未知帳號執行固定 dummy Argon2 verify，避免明顯 timing enumeration。
5. 以 injectable clock 測試秒級邊界、並行第五次、跨 service instance 共享與 Retry-After；
   不用 fixed sleep。

### 5. Session lifecycle 與 rollback

1. `session_records.session_origin` 由 server 寫入；既有資料 backfill `legacy`，新建立的 LINE、
   local web、remote management session 分別使用明確值。remote session 另記 profile 名稱。
2. refresh 必須沿用 session origin 與公開角色限制，不能藉 refresh 繞過 public login policy。
3. rollback 命令第一階段原子切換成 line-only／deny management 並驗證；第二階段撤銷所有 active
   `remote_management_demo` session 及其 refresh families。兩步都有 timestamp/evidence，總時限
   5 分鐘。

### 6. 驗證與發布閘門

1. Contract tests 驗證 registries、profile composition、production build-manifest asset resolution、
   host/config generation、nginx syntax、正負路由矩陣及 log 不含敏感 query/referer。
2. API tests 驗證角色、既有 session、refresh、lockout、IP limit、跨 worker/concurrency、
   cross-tenant 與 audit/log redaction。
3. production Next build + Playwright 驗證 login、shelter context 與全部核心頁面；另驗證 HMR、
   排除 route 與 platform route 從公開 host 不可達。
4. LINE smoke/regression 必須證明 shared profile 未破壞 webhook、LIFF、photo capability；line-only
   default 行為不變。
5. T008 manual evidence 未完成時，launcher 拒絕 public activation；測試可用 synthetic evidence
   fixture 驗證 gate，但不得假稱真實事故處置完成。

## Complexity Tracking

無憲章違規，無需複雜度例外。
