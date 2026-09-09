# 013 Remote Management Public Access — 計畫與實作彙整報告

**日期**：2026-09-05
**Feature**：`013-remote-management-public-access`
**Feature status**：`READY_FOR_CONTROLLED_ACTIVATION`（已完成受控啟用前驗收）
**整體結果**：Phase A～E、T055～T057 已完成；目前可進行另行授權的 controlled activation，但不代表 tunnel 正在運行
**目前 runtime**：Public tunnel 未運行
**資料範圍**：Runtime 驗收只使用 isolated `strayhub_test` synthetic fixtures

## 1. 背景與目標

本計畫源自 demo 管理帳密曾出現在 `/login` URL 的事件。Feature 012 先完成 credential URL、
logging/redaction 與 LINE tunnel default-deny hardening；Feature 013 再建立單一 shared tunnel 上的
遠端管理能力，同時維持：

- 未明確 opt-in 時只公開既有 LINE／LIFF routes。
- Public management 僅允許 active `STAFF` 與 `SHELTER_ADMIN`。
- `PLATFORM_ADMIN`、`VOLUNTEER`、PII、平台治理與未列 routes 維持拒絕。
- FastAPI、membership、active shelter context 與 PostgreSQL RLS 仍是 authorization／tenant
  isolation 的最終邊界。
- Production profile 使用 Next production build，不公開 HMR、source map、任意 Next/API
  namespace。
- 能在五分鐘內先封閉 public management，再精準撤銷 remote sessions，而不影響 LINE、local、
  LIFF 或 legacy sessions。

本計畫沒有導入 OAuth、MFA、SSO、cookie migration、Redis、WAF、VPN、Zero Trust、CDN 或 CSP
redesign。

## 2. 計畫分期與交付結果

| Phase | Tasks | 主要交付 | 結果 | Git baseline |
|---|---|---|---|---|
| A — Auth Protection | T001～T013 | PostgreSQL account/IP abuse control、trusted client-IP、generic deny、dummy Argon2 verify | PASS | `ee051f9` |
| B — Shared Profile Contracts | T014～T022 | LINE／management registry composition、Host contract、Next manifest exact assets | PASS | `9600975` |
| C — Gateway/Helper Integration | T023～T036 | Generated nginx/ngrok policy、explicit helper opt-in、backend role enforcement、Core-only UI | PASS | `7a65a1e` |
| D — Session/Rollback | T037～T044 | Session origin/profile、refresh binding、selective revoke、ordered rollback CLI | PASS | `65e406f` |
| E — Runtime Acceptance | T045～T060 | Activation gate、browser/tenant/LINE/log acceptance、quality gates | PASS | `3edc414` 等 |
| Manual/Public runtime subset of Phase E | T055～T057 | Incident containment、真實 public smoke、真實 rollback drill | PASS | 已納入本次 commit |

> T055～T057 是 Phase E 中需要真實 public／manual runtime 驗收的子集合，不是獨立於 Phase E 之外的 phase。

相關前置 security commits：

- `f55dabc`：避免 login credential 進入 URL。
- `c400b8f`：建立 sensitive URL 與 centralized logging policies。
- `9015166`：LINE tunnel default-deny boundary。
- `10c703c`：記錄 credential incident containment evidence。

## 3. 最終架構與安全邊界

### 3.1 Public profile

```text
line-only
  = 既有 LINE／LIFF registry

shared-demo-production
  = LINE／LIFF registry
  + 明確列舉的 Core Management routes
  + build manifest 證明的 exact Next assets
  - HMR / source maps / arbitrary Next internals
```

`line-only` 是預設值。Shared profile 必須同時提供明確 profile、reserved HTTPS origin 與通過
schema 驗證的 manual-external activation evidence；缺少任一項即 fail closed。

### 3.2 Request chain

```text
Browser / LINE
→ reserved HTTPS endpoint
→ ngrok Traffic Policy
→ default-deny nginx gateway
→ Next.js 或 FastAPI exact upstream
→ server-side role / membership / tenant / RLS enforcement
```

Gateway 只決定 route 是否可達，不授予 application 權限。Client 不能用 body、query、Host、
`X-Forwarded-For` 或自訂 profile header 提升角色或改變 shelter scope。

### 3.3 Authentication protection

- Login 維持 JSON `POST /v1/auth/login`，credential 不進 URL。
- Account 第 1～4 次失敗回 generic 401，第 5 次起鎖定 15 分鐘並回 429。
- 同一 trusted source 15 分鐘內最多接受 20 次 login evaluation，第 21 次回 429。
- Counter 使用 PostgreSQL transaction/advisory lock，可跨 process/worker。
- Username 與 IP 只以 domain-separated HMAC digest 保存。
- Unknown／不可登入 identity 仍執行 dummy Argon2 verify，降低 enumeration timing 差異。

### 3.4 Session 與 rollback

Session 由 server 標記為：

- `legacy`
- `local_web`
- `liff`
- `remote_management_demo`，並保存 shared public profile

Rollback 固定依序執行：

1. 產生並驗證 `line-only` config。
2. Atomic replace／reload nginx gateway。
3. 確認 public management page/API 全部拒絕。
4. 確認 LINE route 仍可達且簽章驗證仍 fail closed。
5. 在同一 DB transaction 撤銷所有 active remote sessions 與 refresh families。

Rollback session cleanup 固定使用 application runtime `DATABASE_URL`，不再被 migration connection
導向另一個資料庫。

## 4. Runtime 驗收摘要

### 4.1 T055 Incident containment

- 舊 demo password：401。
- 新 demo password：200，使用 query-free JSON POST。
- Rotation 後 active session／refresh session：0。
- Browser local history、autofill 與 Back navigation：PASS。
- Browser sync：`NOT_ENABLED`。
- Credential reuse：`NOT_REUSED`。
- Local artifact、static policy 與 runtime sentinel scan：PASS。
- 原 ngrok Inspector session 已不存在，因此歷史 capture／third-party retention 維持
  `UNVERIFIABLE` residual risk；報告未假稱外部資料已刪除。

### 4.2 T056 Real public smoke

- 使用真實 reserved HTTPS host、`shared-demo-production`、Next production build 與 synthetic DB。
- Synthetic STAFF 與 SHELTER_ADMIN 各完成五次 Core journey：10/10 PASS，單次 2.4～4.8 秒。
- PLATFORM_ADMIN 與 VOLUNTEER：server-side deny PASS。
- Cross-shelter animal、timeline、report：404，未暴露資料。
- Platform、settings、PII、docs、debug、internal、任意 API／management、HMR 與 unknown Next
  internals：404。
- LINE／LIFF public entry：200；unsigned webhook：401。
- Login request 維持 query-free JSON POST。

首次 smoke 發現 ngrok Local Inspector 預設保存 request body 與 Authorization。該次證據作廢，
synthetic credential 立即旋轉，相關 session／refresh 全數撤銷。Production helper 現在對
`shared-demo-production` 使用 `--inspect=false`；重跑後 Inspector request count 與 runtime artifact
敏感命中均為 0。

### 4.3 T057 Real rollback drill

Rollback 前：

- Public STAFF／SHELTER_ADMIN login、context switch、dashboard：200。
- Active remote session：2。
- Active remote refresh：2。
- Preservation controls：`legacy=1`、`local_web=1`、`liff=1`。

Rollback 後：

- Public management success：0/7；所有目標 route 回 404。
- LINE／LIFF availability：4/4 符合預期，100%。
- 舊 remote access／refresh token：4/4 回 401。
- Active remote session／refresh：0／0。
- Legacy、local_web、LIFF preservation counts：不變。
- Runtime／Inspector sensitive findings：0。
- 從首次 gateway deny 到正確 session revoke：38.141 秒，小於 300 秒。

第一次 CLI 執行雖已正確封閉 gateway，但因 migration/runtime DB URL precedence 而回報 0 revoke；
此結果未被接受為 PASS。修正後以 runtime `DATABASE_URL` 重跑並成功撤銷 2+2，另以 1+1
synthetic fixture 完成 post-fix runtime regression。

## 5. 品質門檻

- Full Pytest：1707 passed，2 個 documented opt-in skips。
- Full Ruff check：PASS。
- Full Ruff format：841 files PASS。
- Mypy：PASS。
- Frontend Vitest：91 files／467 tests PASS（先前完整 Phase E gate）。
- TypeScript typecheck：PASS。
- Prettier：PASS。
- Next production build：PASS，25 pages。
- nginx syntax／generated gateway config：PASS。
- Sensitive transport static policy：PASS。
- `git diff --check`：PASS。

## 6. 實測中發現並修正的問題

| 問題 | 風險 | 修正 |
|---|---|---|
| Shared gateway readiness probe 未帶 reserved Host | 正確 Host boundary 會讓 helper 啟動失敗 | Shared probe 明確使用 reserved Host；不放寬 gateway |
| ngrok Local Inspector 保存 body／Authorization | 短效 credential 與 token 被本機 capture | Production shared profile 使用 `--inspect=false` |
| Public Playwright 遇到 ngrok warning interstitial | 真實 browser acceptance 無法進入 application | 測試請求加入 ngrok warning bypass header |
| 重複 deny-role login 第五次回 429 | Abuse lockout 與角色 deny assertion 混在同一 repetition | Core journey 重複測試與 deny-role 單次測試分離；不放寬 security policy |
| Rollback 優先使用 migration DB URL | Gateway 已封閉但 remote sessions 可能留在 runtime DB | Session revoke 固定使用 runtime `DATABASE_URL` 並新增 regression test |

## 7. Residual risk 與操作限制

- 2026-09-05 之前原 ngrok session 的第三方歷史 retention 無法回溯驗證，維持
  `UNVERIFIABLE`；已曝光 credential 已旋轉且未重用。
- `READY_FOR_CONTROLLED_ACTIVATION` 不代表 tunnel 正在運作，也不代表允許永久公開。
- 每次啟用仍需獨立 operator authorization、有效 activation evidence、synthetic/demo data guard、
  reserved Host 驗證與 explicit `shared-demo-production` profile。
- 真實 public hostname、password、Authorization、access/refresh token 與 capability 不得寫入
  repository、issue、commit message 或驗收報告。

## 8. Git 與交付狀態

目前 branch：`main`，相對 `origin/main` ahead 12。T055 已在 `10c703c`；T056／T057 runtime
corrections、tests 與 validation evidence 已納入本次 commit。

本輪 working tree 包含：

- Production/runtime：`scripts/demo-line.sh`、`scripts/rollback_remote_management.py`
- Browser tests：兩個 remote-management Playwright specs
- Python tests：helper contract、rollback E2E
- Docs/spec：remote-management runbook、`tasks.md`、`validation-result.md`、本報告

建議在 diff review 後建立一個獨立 commit：

```text
fix(remote-access): complete public smoke and rollback validation
```

不要將 hostname、一次性 evidence file、terminal capture 或 `/tmp` artifacts 納入 commit。Public
tunnel、API、Next、nginx 與 Inspector ports 已關閉；一次性 credential/token 暫存檔已永久刪除。

## 9. 最終結論

**Feature status: `READY_FOR_CONTROLLED_ACTIVATION`.**

Feature 013 已完成從 policy、gateway、server authorization、tenant isolation、session lifecycle、
incident containment 到真實 public smoke／rollback 的閉環驗證。已實證 rollback 從首次 gateway deny
到正確 remote session revoke 為 38.141 秒，低於 300 秒操作目標；流程先封閉 public management，
再撤銷 remote sessions，同時保留 LINE 與非 remote sessions。

系統目前不是公開運行狀態，也不代表允許永久公開。每次啟用仍需獨立 operator authorization、
有效 activation evidence、synthetic/demo data guard、reserved Host 驗證，以及明確指定
`shared-demo-production` profile；public tunnel 在本輪驗收後已停止。
