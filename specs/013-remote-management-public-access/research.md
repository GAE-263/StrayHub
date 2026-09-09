# Phase 0 Research：Remote Management Public Access

## 研究結論

本功能可在不新增外部基礎設施的前提下完成。既有 PostgreSQL 足以提供跨 worker、跨程序的
原子化登入限制；既有 nginx gateway 與 YAML registry 模式可擴充成 profile composition；ngrok
Traffic Policy 可提供連線來源 IP 並先移除攻擊者自訂 header。公開管理入口必須同時有 gateway
白名單與 FastAPI 角色縮限，不能把路由可達性誤當授權。

## Decision 1：登入限制使用 PostgreSQL

**Decision**：新增 account abuse state 與 IP attempt event 資料結構，搭配 transaction-level
advisory lock／row lock；不新增 Redis。

**Rationale**：

- PostgreSQL 已是所有 API worker 共用且必要的 dependency，符合「shared server-side atomic
  storage」。
- account lockout 需要對「不存在的 state row」也能序列化，advisory lock 可先鎖 HMAC subject，
  再檢查／upsert。
- IP 限制要求真正 rolling 15-minute window；事件列能精確計算第 21 次與 `Retry-After`，比固定
  bucket 更符合規格。
- demo 規模低，沒有引入 Redis lifecycle、secret、health check 與部署拓撲的必要性。

**Alternatives considered**：process-local memory 跨 worker 不一致；Redis 會新增目前不存在的
服務；nginx/ngrok 單層限制無法滿足 normalized account lock，三者均不採用。

## Decision 2：以 HMAC digest 保存 account/IP abuse key

**Decision**：username 經 NFKC、trim、casefold 後，只用於以專用 runtime secret 計算
HMAC-SHA256 abuse subject；實際 authentication identity lookup 仍使用既有規則，不改成 normalized
lookup。來源 IP canonicalize 後亦以具 domain separation 的 HMAC utility 產生 digest。資料庫與一般
log 不保存 raw username/IP。

**Rationale**：一般 SHA-256 對常見帳號與 IP 空間容易字典反查；HMAC 可降低 abuse metadata
本身成為識別資訊外洩面的風險。key 必須在 shared-demo runtime 穩定、不可輸出至 log，且不能
使用 placeholder。

**Alternatives considered**：raw value 增加個資與帳號枚舉風險；unsalted hash 可離線枚舉；
每次隨機 salt 無法跨 request 聚合，均不採用。

## Decision 3：公開 profile 是縮限條件，不是新權限來源

**Decision**：gateway 產生 server-derived exposure profile；FastAPI request context 在公開
profile 下只允許有效 `STAFF`／`SHELTER_ADMIN`，並排除 `PLATFORM_ADMIN` bypass。Frontend
顯示與否不作授權依據。

**Rationale**：目前 management dependency 包含 `PLATFORM_ADMIN`，而平台角色在 active
organization context 下可呼叫部分核心 API。只在 nginx 擋 `/v1/platform/**` 無法阻止持有既有
platform token 的人呼叫 `/v1/management/**`。

**Alternatives considered**：只隱藏 sidebar 可被直接 API 呼叫繞過；只在 login 拒絕無法阻止
既有 session；第二套 management API 會重複業務規則，均不採用。

## Decision 4：使用專用、可覆寫的可信 ingress metadata

**Decision**：ngrok Traffic Policy 先移除外部傳入的 client-IP/profile header，再以
`conn.client_ip` 設置專用來源 header；nginx 對 upstream 設定固定 public profile，FastAPI 只在
已配置的 loopback gateway hop 接受。`X-Forwarded-For` 不作登入配額 source of truth。

**Rationale**：ngrok 官方 Traffic Policy 提供連線變數及 request header add/remove actions，agent
CLI 支援 traffic policy file；因此可在最接近 public edge 的位置消除同名 header spoofing，再將
可信 metadata 傳入本機 gateway。[Traffic Policy variables/actions](https://ngrok.com/docs/pricing-limits/traffic-policy-unit-pricing)、[ngrok agent CLI](https://ngrok.com/docs/agent/cli)

**Alternatives considered**：任意 `X-Forwarded-For` 可被 spoof；nginx `$remote_addr` 只會看到
本機 agent；單一 shared-secret header 不能提供 client IP，均不足。

## Decision 5：runtime reserved host 產生設定

**Decision**：launcher 接受一個完整 HTTPS origin，驗證無 userinfo/path/query/fragment/wildcard，
並與預期 reserved host 相符後產生 nginx `server_name` 與 Host guard；repository 不保存實際 tunnel
hostname。

**Rationale**：ngrok reserved domain API 回傳具體 hostname，可作部署輸入；將 hostname 寫死在
nginx template 會造成環境漂移與誤公開。[Reserved Domains API](https://ngrok.com/docs/api-reference/reserveddomains/create)

**Alternatives considered**：`server_name _` 接受任意 Host；commit 真實 hostname 綁死環境；依
request Host 反射則由攻擊者控制，均不採用。

## Decision 6：registry composition 採 include + explicit exclusion

**Decision**：保留 012 `line-tunnel-allowlist.yaml`，013 新增 management registry；profile contract
以 registry include 組合。`shared-demo-production` 明確排除既有 `next_dev_hmr` route，dev profile
才保留 HMR。

**Rationale**：不複製 LINE route 可避免兩份 allowlist 漂移；production profile 必須在組合後仍
能移除開發專用 route。產生器負責檢查重複 route ID、衝突 method/path/upstream 與 unknown
exclusion，失敗即不產生設定。

**Alternatives considered**：複製完整 allowlist 容易漂移；手寫 nginx include 無 deterministic
collision check；production 保留 HMR 擴大攻擊面，均不採用。

## Decision 7：為 server session 記錄來源以支援精準 rollback

**Decision**：`session_records` 增加 server-derived `session_origin` 與 nullable
`public_profile`。既有資料 backfill `legacy`；公開登入標為 `remote_management_demo`。rollback
只撤銷該 origin 的 active session 與 refresh family。

**Rationale**：規格要求 route deny 後撤銷所有 remote demo management sessions，現有模型無法
可靠區分；依 user、時間或 token 猜測會誤撤銷 LINE／local session。

**Alternatives considered**：撤銷全部 session 超出 scope；等待 token TTL 不符 5 分鐘；只撤銷
refresh token 仍留下有效 access token，均不採用。

## Decision 8：未知帳號執行 dummy password verify

**Decision**：以啟動時準備的有效 Argon2 dummy hash 對未知／不可登入帳號執行一次相同 verifier，
再回 generic 401；不得在 log 或 response 透露帳號是否存在。

**Rationale**：目前不存在的 username 會略過 password verification，形成可觀測 timing 差。登入
濫用控制導入後應一併封閉此 enumeration channel，且不改 authentication contract。

**Alternatives considered**：固定 sleep 不可靠；建立假 DB user 會污染身份資料，均不採用。

## Decision 9：production acceptance 使用 Next production build

**Decision**：`shared-demo-production` 必須執行 `next build` 後的 production server；Playwright
以 production host 驗證核心 journeys。`shared-demo-dev` 僅供明確開發用途。

**Rationale**：dev server 會暴露 HMR、錯誤 overlay 與不同 cache/runtime 行為，不能作 production
profile 的驗收證據。

**Alternatives considered**：`next dev` 不代表 production；另建靜態匯出會改變現有 proxy/runtime
架構，均不採用。

## Decision 10：production static allowlist 由 build manifest 收斂

**Decision**：`shared-demo-production` 組合時排除既有開發用 `next_static_assets` pattern，改由完成的
Next production build manifests 解析 allowlisted page 及其 shared runtime/CSS chunk，產生 exact
asset paths；`.map`、`/_next/image`、font/favicon 與未被 manifest 證明的 asset 保持拒絕。dev profile
保留既有 bounded static pattern。

**Rationale**：同一個 hashed chunk 可能由 LINE 與 management page 共用，無法靠 pathname 名稱
人工判定；build manifest 是該 build 的可重現依賴證據。若 production 繼承整個
`^/_next/static/...$`，雖不是 `/_next/**` catch-all，仍無法證明每個可取資源為核心流程所需。

**Alternatives considered**：手抄 hash 每次 build 都會失效；允許整個 static namespace 超出
FR-014；由執行中 404 當 deny 仍會把 request 送到 upstream，均不採用。

## 已解決的未知項目

- Rate-limit shared store：PostgreSQL。
- Trusted client IP：ngrok connection metadata，經 remove/overwrite 後傳入專用 header。
- 公開角色 enforcement：gateway exposure + FastAPI request-context subtractive policy。
- Session rollback targeting：server-derived session origin。
- Production frontend runtime：Next production build/server。
- Production static scope：依 build manifest 產生 exact asset allowlist。

沒有剩餘待釐清項目。ngrok Traffic Policy 的精確 YAML/JSON 語法須在 implementation
task 以目前安裝 agent 的 config validation 驗證，但不影響架構決策。
