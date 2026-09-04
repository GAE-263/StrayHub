# Feature Specification: 共用公開通道的遠端管理存取

**Feature Branch**: `013-remote-management-public-access`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "在不破壞既有 LINE／LIFF default-deny security boundary 的前提下，讓 STAFF 與 SHELTER_ADMIN 可透過同一個 ngrok reserved domain 從外網登入並使用明確核准的管理後台功能。"

## Clarifications

### Session 2026-09-04

- Q: 本期是否將現有 Core Remote Management Scope 凍結為完整 P0 交付範圍？ → A: 是；凍結現有 Core scope，volunteer governance、audit UI、QR、進階設定、PII reveal 與 platform governance 全部不納入。
- Q: 013 的主要 security acceptance 應以哪一種執行模式為準？ → A: Production build 是主要驗收模式；dev mode 僅額外支援，HMR 只允許於 `shared-demo-dev`。
- Q: 第 5 次帳號失敗與第 21 次來源 IP 嘗試，應採用哪種 HTTP 回應政策？ → A: 第 1～4 次錯誤回 401；第 5 次及鎖定期間回 429；第 21 次 IP 嘗試回 429；所有 429 均附不洩漏帳號資訊的 `Retry-After`。
- Q: 核准的 ngrok reserved Host 應如何提供給 `shared-demo`？ → A: 由必要的 runtime environment variable 提供，經驗證後輸入 generated gateway config，不寫入 repository；缺少或不合法時 fail closed。
- Q: 從 `shared-demo` rollback 至 `line-only` 時，是否必須同時撤銷遠端 Demo 管理 sessions 才算完成？ → A: 是；先恢復 gateway route deny，再撤銷所有 Remote Demo management sessions，兩者都須在 5 分鐘內完成。

## User Scenarios & Testing

### User Story 1 - 工作人員從外網使用核心管理功能 (Priority: P1)

具備有效收容所工作人員資格的使用者，可以從指定的共用 Demo 網域登入，選定其獲授權的收容所，並使用總覽、動物、回報、待處理事項與照護行事曆等核心管理功能，不必接觸平台治理或其他未核准功能。

**Why this priority**: 這是本功能的主要 Demo 價值；若 STAFF 無法安全完成核心日常工作，就沒有公開管理入口的必要。

**Independent Test**: 使用只具有單一收容所 STAFF 資格的 synthetic 帳號，從外網完成登入、總覽、動物清單、動物詳情、時間軸、照片、回報、AI 人工覆核與照護行事曆流程，並確認管理員專屬、平台與其他未核准入口均不可使用。

**Acceptance Scenarios**:

1. **Given** `shared-demo` 已通過所有啟用前 gate，且 STAFF 帳號有效，**When** 使用者從指定網域登入並選定其收容所，**Then** 使用者進入該收容所的管理總覽。
2. **Given** STAFF 已登入且具有有效收容所 context，**When** 使用者瀏覽動物清單、詳情、時間軸與受保護照片，**Then** 只看見目前收容所的資料。
3. **Given** STAFF 已登入，**When** 使用者瀏覽回報、待處理事項、執行核准的 AI 人工覆核動作或查看照護行事曆，**Then** 核心流程可完成且每個請求仍接受伺服器端角色與租戶驗證。
4. **Given** STAFF 已登入，**When** 使用者要求 shelter-admin-only、PII reveal 或平台治理功能，**Then** 公開 gateway 或應用程式拒絕請求，且不洩漏其他資源是否存在。

---

### User Story 2 - 收容所管理員以相同邊界進行核心展示 (Priority: P1)

具備有效 SHELTER_ADMIN 資格的使用者，可以從相同 Demo 網域完成 Core Remote Management Scope，但其管理員名稱不會使平台治理或其他未納入 Demo 的高風險功能自動公開。

**Why this priority**: Demo 需要支援收容所管理員，同時必須維持 SHELTER_ADMIN 與 PLATFORM_ADMIN 的清楚權限邊界。

**Independent Test**: 使用 SHELTER_ADMIN synthetic 帳號完成全部 Core Remote Management Scope，再直接要求平台頁面、平台 API、志工 PII reveal、帳號生命週期與未納入 scope 的治理功能，確認前者成功且後者全部拒絕。

**Acceptance Scenarios**:

1. **Given** SHELTER_ADMIN 帳號有效，**When** 使用者登入 `shared-demo`，**Then** 可完成與其角色相符的 Core Remote Management Scope。
2. **Given** SHELTER_ADMIN 已登入，**When** 使用者直接要求 PLATFORM_ADMIN 頁面或操作，**Then** 請求被拒絕且不會因名稱同為 admin 而提升權限。
3. **Given** SHELTER_ADMIN 已登入，**When** 使用者要求尚未明確納入公開 scope 的收容所治理或 PII-heavy 功能，**Then** route 維持拒絕，即使該角色在本機環境原本可能具備業務權限。

---

### User Story 3 - 公開登入抵抗濫用且不洩漏 credential (Priority: P1)

合法使用者可以正常登入，但攻擊者無法透過大量嘗試、帳號存在性差異、URL、Referer、記錄或稽核資料取得 credential 或低成本猜測密碼。

**Why this priority**: 將密碼登入入口公開到 Internet 會新增暴力破解與 credential stuffing 風險，這些控制是啟用 shared-demo 的必要前置條件。

**Independent Test**: 對存在與不存在的使用者執行成功、失敗、重複、跨來源與鎖定測試，並以唯一 synthetic sentinel 掃描 URL、瀏覽器歷史、gateway、應用程式與稽核證據。

**Acceptance Scenarios**:

1. **Given** 使用者提交正確 credential，**When** 登入成功，**Then** credential 只出現在核准的加密請求內容，不出現在 URL、Referer、任何 log 或 audit。
2. **Given** 同一 normalized username 已連續失敗四次，**When** 第五次登入失敗，**Then** 該 counting key 自第五次失敗起鎖定 15 分鐘，回應 429 與不洩漏帳號資訊的 `Retry-After`。
3. **Given** counting key 正在鎖定，**When** 從相同或不同來源再次嘗試，**Then** 系統以相同 429 contract拒絕登入且不揭露該使用者是否存在。
4. **Given** 來源 IP 在 rolling 15 分鐘窗口已送出 20 次登入嘗試，**When** 送出第 21 次且使用任意 username，**Then** 系統回應 429 與 `Retry-After`，來源限制不因切換 username 繞過。
5. **Given** 存在與不存在的 username，**When** credential 驗證失敗，**Then** 對外狀態、訊息與可觀察驗證成本不提供明顯的帳號存在性差異。

---

### User Story 4 - 維運者明確啟用並可快速回復公開範圍 (Priority: P1)

Demo 維運者可以選擇預設的 `line-only` 或明確 opt-in 的 `shared-demo`，在啟用前得到 credential、資料與 host gate 的檢查結果，並能在不修改 LINE registry 的情況下快速回復為 `line-only`。

**Why this priority**: 遠端管理必須是可控且可撤回的臨時暴露，不能成為既有 LINE helper 的隱含預設。

**Independent Test**: 分別啟動兩種 profile，驗證 route matrix、合法 Host、runtime gates 與 rollback；切回 `line-only` 後管理入口全部拒絕而 LINE happy paths 繼續正常。

**Acceptance Scenarios**:

1. **Given** 維運者未指定管理模式，**When** 啟動 public tunnel，**Then** 使用 `line-only` 並拒絕登入與管理 routes。
2. **Given** credential rotation evidence、synthetic data 與合法 Host 任一 gate 未通過，**When** 維運者要求 `shared-demo`，**Then** 系統拒絕啟用並指出未通過的 gate，但不輸出秘密。
3. **Given** 維運者明確啟用 `shared-demo`，**When** 合法 Host 要求已登錄 route，**Then** 依 route、method、角色與驗證狀態處理；未登錄 route 維持拒絕。
4. **Given** `shared-demo` 正在運作，**When** 維運者切回 `line-only`，**Then** 先恢復 `/login` 與 management routes 的 public deny，再撤銷所有 Remote Demo management sessions；兩者在 5 分鐘內完成，且既有 LINE registry 不需修改。

---

### User Story 5 - LINE／LIFF 公開流程維持既有安全邊界 (Priority: P1)

志工使用既有 LINE、LIFF、QR、照片與照護回報流程時，不會因加入 management profile 而遇到 route regression、權限降低或更廣泛的公開入口。

**Why this priority**: 012 是本功能的 security prerequisite；013 不能以新增後台展示為理由推翻已完成的 default-deny hardening。

**Independent Test**: 在 `line-only` 與 `shared-demo` 分別執行既有 LINE happy paths 與 deny matrix，確認必要流程皆成功，未知路徑與 management/platform 邊界依 profile 保持拒絕。

**Acceptance Scenarios**:

1. **Given** `line-only` profile，**When** 外部要求 `/login`、management UI 或 management API，**Then** 全部拒絕。
2. **Given** `shared-demo` profile，**When** 執行 webhook、LIFF entry/exchange、QR resolve、animal confirmation、photo capability 與 care report，**Then** 既有流程全部成功。
3. **Given** 任一 profile，**When** 要求未知 UI、未知 API、internal、debug、文件或平台治理 route，**Then** gateway 在送達應用程式前拒絕。

### Edge Cases

- 同一使用者從多個 IP 交錯失敗，或多個 process 同時處理第五次失敗。
- 攻擊者以大小寫、前後空白或 Unicode 等價形式變化 username，試圖繞過 per-account counting key。
- NAT 後多位合法使用者共用 IP，來源限制不得永久鎖死所有人，且 retry guidance 不揭露帳號狀態。
- 第五次失敗與正確密碼請求同時抵達；鎖定判定必須原子且結果可重現。
- 鎖定期間服務重啟、切換 process 或重新啟動 tunnel；鎖定狀態不得因此消失。
- 登入成功後，舊失敗計數應重設，但來源 IP 的濫用窗口不得被單一成功登入清除。
- 過期或停用 membership、缺少 active shelter context，或使用者同時屬於多個收容所。
- 使用合法 token 猜測另一收容所的 animal、report、timeline 或 photo UUID。
- 動態 path 含非 UUID、額外 segment、encoded slash、dot segment 或 method mismatch。
- Next 頁面導覽、prefetch 或 RSC／Flight request 帶 `_rsc` query；合法頁面可運作但不能擴張 path boundary。
- 開發模式需要 HMR，而 production build 不需要；production profile 不得因共用設定而公開開發端點。
- 請求使用正確 URL 但錯誤 Host、偽造 forwarded headers 或非 HTTPS public origin。
- credential rotation 已完成但 evidence 不完整，或新 credential 被輸出到長期保存的終端／artifact。
- Rollback 發生於 active session 存在時，管理 route 必須先停止公開，再撤銷 Remote Demo management sessions；不得等待 session 自然過期才宣告 rollback 完成。

## Requirements

### Management Core Scope

Core Remote Management Scope 是本期凍結的完整 P0 交付範圍，僅包含下列使用者能力；route registry 可包含支撐這些能力的最小身分、context 與 shared resource，但不得藉此公開其他產品功能：

1. 登入、登出與 session refresh。
2. 讀取與切換使用者已獲授權的 active shelter context。
3. 讀取 dashboard。
4. 讀取 animal list、animal detail、animal timeline 與 authenticated animal photo。
5. 讀取 reports list 與 report detail。
6. 讀取 attention／AI review queue，並完成既有角色已被授權的人工覆核動作。
7. 讀取 care calendar。

本 scope 不包含 animal create/update、report correction/archive、medical mutation、care reminder mutation、QR 管理、audit UI／settings、志工治理、收容所帳號治理、PII reveal、進階設定或平台治理。上述項目在所有 013 public profiles 明確維持拒絕；新增任何項目必須以 013 之外的獨立需求與 route-level 審查處理。

### Functional Requirements

- **FR-001**: 系統 MUST 保留 `line-only` 作為 public tunnel 的預設 profile；未明確選擇 management exposure 時，`/login`、management UI 與 management API 必須拒絕。
- **FR-002**: 系統 MUST 提供明確 opt-in 的 `shared-demo-production` 與 `shared-demo-dev` named profiles，僅組合既有 LINE／LIFF 公開範圍、Core Remote Management Scope 與兩者真正共用的前端資源；既有 LINE helper 未指定 named profile 時 MUST 維持 `line-only`。
- **FR-003**: LINE／LIFF 與 management 公開範圍 MUST 各自具備獨立的 route registry，profile composition 不得要求修改既有 LINE registry 才能加入或撤回 management。
- **FR-004**: 每筆公開 route MUST 指定 path 或 bounded pattern、HTTP method、目的、caller、驗證需求、角色、query policy、敏感等級、logging policy、rate-limit expectation、owner 與驗證證據。
- **FR-005**: Public unauthenticated management surface MUST 限於 `GET/HEAD /login`、`POST /v1/auth/login` 與登入頁真正需要的 shared static resources。
- **FR-006**: 除公開登入入口外，Core Remote Management Scope 的每個資料請求 MUST 要求有效 session，並依既有服務端規則重新驗證角色、active shelter context 與資源租戶。
- **FR-007**: STAFF MUST 能完成 Core Remote Management Scope，但 MUST NOT 使用 shelter-admin-only mutation、PII reveal 或 platform governance。
- **FR-008**: SHELTER_ADMIN MUST 能完成 Core Remote Management Scope，但其角色 MUST NOT 自動公開或授權未納入 scope 的 shelter governance、PII-heavy route 或任何 PLATFORM_ADMIN route。
- **FR-009**: PLATFORM_ADMIN MUST NOT 成為本功能支援的 remote management 使用者；platform UI 與 `/v1/platform/**` 在 `shared-demo` 仍必須拒絕。
- **FR-010**: Management registry MUST 使用 exact path 或限定格式的 dynamic path pattern，dynamic resource identifier MUST 符合既有 UUID 格式，且 MUST NOT 以所有 UI、`/v1/**` 或 `/v1/management/**` catch-all 表示。
- **FR-011**: 未登錄 UI、API 與 framework route、method mismatch、額外 path segment、malformed dynamic ID、internal、debug、文件與 platform route MUST 在送達應用程式前拒絕，且回應不得揭露 upstream 或資源狀態。
- **FR-012**: `shared-demo` MUST 支援管理頁 HTML、CSS、JavaScript chunks、實際使用的 shared static assets、合法 prefetch 與 RSC／Flight request；query 的存在不得使未登錄 pathname 取得存取權。
- **FR-013**: `shared-demo-production` MUST 是本功能唯一可完成主要 security acceptance 的模式；`shared-demo-dev` MAY 作為額外開發便利。兩者 MUST 分開定義 framework resource，production profile MUST NOT 公開 HMR、開發 overlay、source map browser endpoint或其他僅開發模式需要的 route。
- **FR-014**: `/_next/image`、favicon、font 或其他 static path 只有在可證明為 Core Remote Management Scope 的 runtime dependency 時才能加入；未使用的 framework route 維持拒絕。
- **FR-015**: 使用者登出 MUST 撤銷現有 server-side session；access token 過期時，既有 refresh 行為 MUST 可在相同 public origin 運作，且不得擴張 refresh-token architecture。
- **FR-016**: 使用者切換收容所時，系統 MUST 重新驗證該使用者的有效 membership；不得接受 client 提供的 organization identifier 作為授權依據。
- **FR-017**: 跨收容所 animal、photo、timeline、report、attention 或 calendar request MUST 回應 403 或 404，且錯誤內容不得讓呼叫者判斷另一收容所資源是否存在。
- **FR-018**: Remote management Demo MUST 只使用 synthetic/demo data與 Demo 專用 credential；偵測到未獲核准的 production-like、真實個資資料來源或與正式環境共用的 credential 時，`shared-demo` MUST fail closed。
- **FR-019**: PII reveal MUST 在所有 013 public profiles 明確維持拒絕；若未來需要公開，必須以 013 之外的新需求、route decision、rate control 與驗收證據處理，不得只修改角色或 wildcard。
- **FR-020**: 從 `shared-demo` rollback 至 `line-only` MUST 不修改 LINE registry或回退 application code；維運流程 MUST 先使 `/login`、management UI 與 management API停止由 public tunnel 存取，再撤銷所有 Remote Demo management sessions，兩者 MUST 在 5 分鐘內完成，否則不得宣告 rollback 完成。
- **FR-021**: Public profile MUST 只負責組合獨立的 LINE 與 management registries；同一 path/method 出現衝突的 upstream、query、logging 或安全政策時，組合 MUST fail closed，且任何 registry 都不得包含 broad wildcard。

### Security Requirements

- **SR-001**: Username 與 password MUST 僅透過核准的 HTTPS request body 傳送，MUST NOT 進入 path、query、fragment、redirect destination、Referer、gateway raw request log、應用程式 log 或 audit。
- **SR-002**: 登入頁 MUST 保留 legacy credential URL canonicalization、禁止 hydration 前 credential GET、no-JavaScript fail-safe、無 hard-coded credential 與安全 autocomplete 行為。
- **SR-003**: `POST /v1/auth/login` MUST 同時套用 per-account 與 per-source-IP 的 shared server-side abuse control，且不得依靠 browser、process-local dictionary 或單一 worker memory state；具體共享儲存方案由規劃階段依現有基礎設施決定。
- **SR-004**: Per-account counting key MUST 由提交 username 去除前後空白、執行 Unicode NFKC normalization 與 case folding 後產生，僅用於安全計數，不得改變既有 authentication identity matching 規則；存在與不存在的 username 必須使用相同 key 規則。
- **SR-005**: 每次 credential 失敗 MUST 以原子方式增加該 account key 的連續失敗次數；第 1～4 次 MUST 回應統一的 401 wrong-credential contract，第五次連續失敗 MUST 自該次判定起鎖定 15 分鐘並回應 429，且鎖定狀態 MUST 在 process 或 tunnel 重啟後仍有效。
- **SR-006**: 成功登入 MUST 清除該 account key 的連續失敗與 account lockout 狀態；鎖定到期前不得以正確密碼提早解除；成功登入 MUST NOT 清除來源 IP 的濫用窗口。
- **SR-007**: 每個可信來源 IP 在任一 rolling 15 分鐘窗口最多接受 20 次 login attempts；第 21 次及其後的嘗試 MUST 回應 429，直到最舊嘗試移出窗口而低於上限，且切換 username 不得繞過。
- **SR-008**: Source IP MUST 只從受信任 public gateway 建立的連線資訊判定；client 自行提供或附加的 forwarded header MUST NOT 成為 rate-limit authority。
- **SR-009**: Account 與 IP 計數、鎖定及解除 MUST 在所有處理同一 Demo 環境登入流量的 worker 間一致；並發第五次失敗只能得到單一、可重現的鎖定結果。
- **SR-010**: 一般 wrong credential MUST 使用相同 401 status 與訊息；第五次 account failure、account lockout 與 IP rate-limit MUST 使用相同的 429 response shape並提供符合剩餘限制時間的 `Retry-After`。上述行為對存在與不存在的 username MUST 相同，且不得回傳失敗計數、帳號存在性、帳號狀態或 membership 狀態。
- **SR-011**: Unknown-user 驗證 MUST 執行與有效 password credential 驗證可比較的固定成本工作，避免明顯 timing enumeration；不得因此改變現有 authentication 或 session architecture。
- **SR-012**: Login、refresh、logout、identity、context 與帶有個人或內部管理資料的 routes MUST 沿用敏感 logging policy；記錄只可保留診斷所需 method、去 query path、status、size、latency 與 correlation，不得保存 Authorization、credential、token、敏感 query 或 Referer。
- **SR-013**: 既有 centralized application 與 audit redaction MUST 套用於本功能所有成功、拒絕與例外路徑；以 encoded、nested、duplicate、大小寫變化或 exception 形式出現的 raw secret 也不得保存。
- **SR-014**: `shared-demo` MUST 只接受必要 runtime environment variable 明確提供的單一 reserved public Host；該值 MUST 經 HTTPS reserved-domain hostname格式驗證後才可作為 generated gateway config input，MUST NOT 將實際 hostname寫入 repository。變數缺少、格式不合法或 Host 不符時 MUST fail closed；localhost 與 loopback Host 只可用於 local verification，且不得以 request Host 產生可信 absolute URL。
- **SR-015**: Public management journey MUST 使用 HTTPS origin；gateway MUST 將 public scheme 正確傳遞至受信任 upstream，並拒絕因偽造 forwarded scheme 而將不安全 origin 視為 HTTPS。
- **SR-016**: `shared-demo` 啟用前 MUST 驗證 012 T008 runtime evidence：old demo password rejected、new demo password accepted、old sessions revoked。任一 evidence 缺少時不得啟用，且規格不得假設人工步驟已完成。
- **SR-017**: Remote exposure MUST NOT 建立任何新 authorization；gateway route allowlist MUST NOT 取代應用程式 authorization，frontend menu visibility 亦 MUST NOT 被視為角色或租戶授權證據。
- **SR-018**: 本功能 MUST 不降低 LINE webhook signature、LIFF identity exchange、QR scope、photo capability、care report、session、role、tenant isolation、RLS 或既有 sensitive URL policy。

### Explicit Deny Scope

下列 surface 在 `line-only` 與 `shared-demo` 都必須維持拒絕，除非未來另有已核准規格：

- `/platform-admins`、`/platform-volunteer-restrictions` 與 `/v1/platform/**`。
- `/docs`、`/redoc`、`/openapi.json`。
- `/debug/**`、`/internal/**`、developer-only endpoints。
- 未登錄的 `/v1/**`、未登錄 Next route、未知 UI route。
- 對已登錄 path 使用未核准 method。
- 不符合 UUID contract、含額外 segment 或無法正規化為核准 pattern 的 dynamic route。
- PII reveal、volunteer governance、shelter account governance、QR management、audit settings、account lifecycle 與 advanced admin settings。
- Production profile 中的 HMR 與其他 dev-only resource。

### LINE Regression Requirements

- **LR-001**: `line-only` MUST 持續允許既有 webhook、LIFF entry/exchange、QR resolve、animal confirmation、photo capability 與 care report paths。
- **LR-002**: `line-only` MUST 持續拒絕 `/login`、所有 management UI 與 management API。
- **LR-003**: `shared-demo` 加入 management 後，既有 LINE happy path 驗收成功率 MUST 維持 100%。
- **LR-004**: Management registry 的新增、移除或 rollback MUST NOT 改寫既有 LINE route ownership、method、query 或 logging policy。

### Runtime Gate and Rollback Requirements

- **RG-001**: `shared-demo` 啟用前 MUST 驗證 profile、runtime Host input、synthetic data、credential rotation、session revocation、route matrix 與 sensitive-log sentinel；所有 blocking gate 通過後才能公開，且不得以 fallback Host 繼續啟動。
- **RG-002**: 啟用與驗證輸出 MUST 不顯示 password、token、完整 Authorization、敏感 capability 或可重用 credential。
- **RG-003**: 維運者 MUST 能明確辨識目前使用 `line-only` 或 `shared-demo`，且不得只從可訪問頁面反推模式。
- **RG-004**: Rollback MUST 依序先恢復 gateway management deny，再撤銷所有 Remote Demo management sessions；完成後 `/login`、Core management pages 與 Core management APIs 的 public success rate MUST 為 0%，既有 LINE／LIFF happy paths成功率 MUST 為 100%。
- **RG-005**: Rollback evidence MUST 包含 profile、時間、allow/deny matrix、Remote Demo management session revocation、LINE regression 與去敏 log 結果；不得包含真實 credential。

### Key Entities

- **Public Tunnel Profile**: 一組明確命名的公開能力組合；記錄預設狀態、包含的 registry、環境變體、合法 Host、啟用 gates 與 rollback target。
- **Management Route Entry**: 單一核准 management path/method contract，包含目的、caller、角色、驗證、query、敏感度、logging、rate expectation、owner 與 evidence。
- **Login Abuse Counter**: 針對 normalized account key 或可信來源 IP 的嘗試窗口、連續失敗數、鎖定起訖與原子更新狀態；不得保存 raw password。
- **Remote Demo Runtime Gate**: 啟用 shared-demo 前必須通過的 synthetic data、Host、credential rotation、session revocation、route policy 與 log sentinel 證據集合。
- **Rollback Evidence**: 從 shared-demo 回到 line-only 的時間、profile、deny matrix 與 LINE continuity 證據，不含 credential。

## Success Criteria

### Measurable Outcomes

- **SC-001**: 使用 synthetic STAFF 與 SHELTER_ADMIN 各執行 5 次完整 Demo，至少 9/10 次能在 3 分鐘內從登入完成 dashboard、animal detail、report detail、attention 與 care calendar 導覽。
- **SC-002**: Core Remote Management Scope 的核准 route/method 驗收成功率為 100%，未登錄 route、method mismatch、malformed ID、internal、debug、文件與 platform route 到達應用程式的次數為 0。
- **SC-003**: 對 STAFF 與 SHELTER_ADMIN 各執行跨收容所 animal、photo、timeline、report、attention 與 calendar 測試，100% 回應 403 或 404，且 response 不揭露資源存在性。
- **SC-004**: 對同一 account key 連續送出錯誤 credential 時，100% 測試的第 1～4 次回應 401，第 5 次立即回應 429 並鎖定 15 分鐘；鎖定期間正確密碼、不同 IP 與服務重啟均不能提早解除，所有 429 均帶有正確且不洩密的 `Retry-After`。
- **SC-005**: 同一可信來源 IP 在 rolling 15 分鐘窗口的前 20 次 login attempts 可進入一般登入判定，第 21 次起 100% 回應 429 與正確 `Retry-After`；切換 username 無法繞過。
- **SC-006**: 存在與不存在 username 的代表性失敗請求具有相同 public status、訊息與欄位；驗證測量未觀察到可穩定分類帳號存在性的明顯成本分支。
- **SC-007**: 以唯一 synthetic sentinel 完成登入、失敗、鎖定、refresh、logout 與管理流程後，URL、Referer、gateway log、Web/API log、audit 與測試 artifact 中的 raw credential 出現次數為 0。
- **SC-008**: `line-only` 與 `shared-demo` 中 webhook、LIFF、QR、animal confirmation、photo capability 與 care report 的既有代表性 happy paths成功率均為 100%。
- **SC-009**: 所有主要 security acceptance evidence 均來自 `shared-demo-production`；該 profile 對 HMR、dev-only resource、`/_next/image` 或其他未證實 framework dependency 的外部存取成功率為 0%，合法 HTML、CSS、JavaScript、prefetch 與 RSC 導覽成功率為 100%。
- **SC-010**: 合法 reserved Host 與 local verification Host 的 route matrix 全部通過；unexpected Host 被送達 Next 或 API 的次數為 0。
- **SC-011**: 在不修改 LINE registry或回退 application code 的條件下，維運者可於 5 分鐘內先恢復 management public deny，再撤銷所有 Remote Demo management sessions；完成後管理 public success rate為 0%，LINE happy path成功率為 100%。
- **SC-012**: `shared-demo` 每次啟用均具有 old password rejected、new password accepted、old sessions revoked 與 synthetic-data verification 四項 evidence；缺少任一 evidence 時成功啟用次數為 0。

## Assumptions

- 012 的 credential URL、central logging redaction、audit redaction、LINE default-deny 與 capability hardening是本功能不可降低的前置條件。
- 「Admin」在本功能只表示 SHELTER_ADMIN；PLATFORM_ADMIN 明確排除。
- P0 Demo 的完整交付範圍已凍結為 Core Remote Management Scope；其他現有後台能力即使已有本機角色授權，也不因此成為 public surface。
- Demo 使用 synthetic data；若無法可靠證明資料環境符合此條件，shared-demo 採 fail-closed。
- 既有 password、session、access token、refresh token、active shelter context 與 Bearer authentication 架構繼續沿用。
- 同一 reserved domain 使管理頁與 API 維持 same-origin；本功能不新增跨 origin authentication contract。
- Per-IP 20 次／15 分鐘是本規格的預設 abuse ceiling；規劃階段可根據可重現的 Demo traffic evidence提出變更，但不得在實作時無紀錄調整。
- 本功能不自動執行 012 T008 的外部或人工事件處理；013 的 specification、planning、coding與非公開驗證 MAY 先進行，但 shared-demo public activation 與 runtime acceptance MUST 等到 T008 evidence完整後才能通過。

## Dependencies

- Feature 012 的程式 hardening與 route/logging contracts已完成並可供回歸驗證。
- 維運者能取得並設定固定 reserved public domain，以及 Demo 專用 synthetic credential。
- 013 runtime acceptance 前，授權人員完成 T008 credential rotation與舊 session撤銷。
- 現有服務端角色、active shelter context 與多收容所資料隔離維持為授權事實來源。

## Out of Scope

- MFA、OAuth、SSO。
- Cookie authentication migration 或 refresh-token architecture rewrite。
- Full CSP program、WAF、VPN、Zero Trust。
- CDN、media cache 或 image delivery redesign。
- PLATFORM_ADMIN remote access。
- 未列入 Core Remote Management Scope 的完整後台公開化。

## Open Issues

1. Rate-limit authoritative storage 的具體選型；需求已固定為 shared、server-side、跨 worker一致且原子更新，規劃階段須依 repository 現有共享基礎設施選定並驗證方案。
