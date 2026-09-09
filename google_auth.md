# Google 註冊與登入修改策略

> UI/UX 更新：Google 使用者使用 `/access`「我的收容所」；`/account` 改為舊帳密帳號專用「登入設定」。頁面入口整理至右上姓名選單，詳見 [UX 設計](specs/014-google-auth/ux-design.md)。

> 最新流程調整：已改為固定收容所申請連結、管理員審核當下選角色；否決移出待審清單但保留結果與稽核。下方邀請碼設計是歷史方案，現行規格見 [加入申請調整](specs/014-google-auth/application-review.md) 及 [操作方式](specs/014-google-auth/quickstart.md)。

- 文件日期：2026-09-06
- 分析基準：`0d80494d3d3cf8eb4faeec72c4150c98b2b43425`
- 文件建立時分支：`dev/google_auth`
- 狀態：2026-09-07 經使用者授權開始實作，程式與本機自動化驗證已完成；真實 Google 登入與發布驗收尚待環境設定。
- 原始範圍為唯讀分析；後續已授權程式修改。僅專用測試資料庫套用 migration，未修改一般開發資料庫或雲端設定，未建立 commit、PR 或部署。
- 實作差異、啟用方式與驗證限制見 [實作計畫](specs/014-google-auth/plan.md)、[開發操作](specs/014-google-auth/quickstart.md) 與 [驗證紀錄](specs/014-google-auth/validation.md)。

## 1. 建議決策

第一版採用「Google 登入＋本人帳號頁＋管理者邀請加入」。

使用 Google Identity Services（GIS）官方按鈕取得 ID token，由 FastAPI 驗證後映射至 StrayHub User，再簽發既有 session、JWT 與 refresh token。Google 只負責驗證身分；收容所 membership、角色與權限仍由 StrayHub 後端判定。

推薦新增 Google 專用 binding，保留 LINE 模型；允許新使用者取得無收容所業務權限的受限 session，並以管理者邀請、使用者認領、管理者確認的流程取得 membership。

以下保留原始分析與建議，文中的「目前」「未實作」「本次僅文件」均指原始分析時點；實際端點與欄位以 `specs/014-google-auth/contracts/openapi.yaml` 及程式碼為準。

## 2. 第一性原則：目標、事實、必要條件與假設

### 2.1 目標

- `/login` 支援 Google 首次註冊與後續登入，不要求另外設定 StrayHub 密碼。
- 舊帳號可安全綁定 Google，保留原 user_id、membership 與歷史資料。
- 一個 User 可隸屬多間收容所，各收容所角色、有效期間與權限獨立。
- 保留原帳密登入、LINE／LIFF 志工流程與現有授權限制。

### 2.2 必要條件

- 驗證 Google 身分成功不等於取得收容所權限。
- 同一 Google 身分必須穩定映射至同一 User，不能以 email 或姓名作永久鍵。
- session 可以在沒有 membership 時存在，但不能因此取得租戶資料。
- 收容所 context 必須由後端檢查有效 membership／grant 後建立。
- 註冊、綁定、session 簽發及成功稽核必須有清楚的交易原子性。
- 所有新公開認證端點都必須處理 CSRF、重放、限流與敏感資訊遮罩。

### 2.3 第一版假設與邊界

- 接受一般 Google 帳號，不限制 Workspace 網域。
- 不存取 Gmail、Drive 等 Google API，不索取 Google access／refresh token。
- 不導入 Firebase Auth、NextAuth 或第二套 session 系統。
- 不自動授予 STAFF、SHELTER_ADMIN 或 PLATFORM_ADMIN。
- 不提供公開管理人員加入申請、Google／LINE 帳號整併或不同 User 的資料合併。
- 不放寬 LINE tunnel、shared-demo profile、資料庫隔離或平台管理權限。

## 3. 程式碼已確認

本次分析開始時分支為 `main`，後續工作區切換為 `dev/google_auth`；兩者 HEAD 都是上述 commit。文件建立前工作目錄與暫存區乾淨。未查詢遠端最新版本或實際雲端設定。

已讀取 [AGENTS.md](AGENTS.md)、[專案憲章](.specify/memory/constitution.md)，以及認證、公開入口、平台治理和個資處理相關程式與文件。

| 項目 | 已確認事實與依據 |
| --- | --- |
| 前端架構 | [apps/web/package.json](apps/web/package.json) 使用 Next.js、React、TypeScript。登入頁為 [LoginClient.tsx](apps/web/app/login/LoginClient.tsx)，主要流程是 `submit()`、`activateContext()`。 |
| User | [identity.py](services/api/app/persistence/models/identity.py) 的 `User.username`、`password_hash` 允許 NULL；`display_name` 仍需提供。User 與多筆 OrganizationMembership 分離。 |
| 外部身分 | 已有 `LineUserBinding`；認證程式與 migrations 未發現 Google 登入 binding 或通用登入 ExternalIdentity。其他 Google 雲端整合不屬於使用者登入。 |
| 登入與續期 | [SessionService](services/api/app/application/authentication/session_service.py) 的 `login()`、`refresh()` 拒絕沒有有效收容所權限的一般使用者，平台管理員另有分支。 |
| 零收容所畫面 | `LoginClient.submit()` 對一般使用者零個可用收容所拋錯，catch 會 `clearAuth()`。 |
| 本人與登出 API | [authentication.py](services/api/app/api/authentication.py) 的 `current_user()` 與 `logout()` 使用要求收容所 context 的 `current_request_context`。 |
| 身分依賴 | [dependencies.py](services/api/app/api/dependencies.py) 的 `authenticated_request_context()` 允許尚未選定收容所；但 session 已選的收容所或 membership 失效時，仍會拒絕請求。 |
| dependency cache | 兩種 context dependency 共用 `request.state.auth_context`。擴充時須保證較弱的驗證結果不能跳過較強的租戶檢查。 |
| session 來源 | `SessionRecord.session_origin` 為 `legacy`、`local_web`、`liff`、`remote_management_demo`，並有與 `public_profile` 搭配的資料庫 CHECK。 |
| 前端 token | [auth.ts](apps/web/lib/auth.ts) 的 `storeSession()` 使用 sessionStorage；`authFetch()` 附帶 token。[api.ts](apps/web/lib/api.ts) 的 `apiFetch()` 才包含 refresh 處理。 |
| 帳號建立 | [OrganizationManagementService](services/api/app/application/organization_management.py) 的 `create_account()`、`create_initial_admin()` 需要 username、temporary_password；`create_membership()` 可對既有 User 建立資格。 |
| 成員授權 | [成員 API](services/api/app/api/organization_management.py) 的 `_require_membership_admin()` 限平台管理員或同收容所管理員。service 有兩名啟用收容所管理員上限，一般 membership 建立流程禁止授予 VOLUNTEER。 |
| context 切換 | [ActiveShelterContextService.switch()](services/api/app/application/authentication/context_service.py) 重新驗證目標組織與 membership，包含 audit 及既有 LINE webhook context 副作用。 |
| 本人 discovery | [0030 migration](services/api/migrations/versions/0030_volunteer_entry_reference_expiration.py) 的 `_replace_authentication_policies()` 在未指定 exact organization scope 時，只讓本人看到 active membership。不能直接拿來當完整待授權狀態清單。 |
| 帳號稽核缺口 | [AuditService.record()](services/api/app/application/audit_service.py) 對無 organization 的事件限制 resource type，Google binding 不能直接套用或假借 platform 類型。 |
| 公開入口 | [LINE allowlist](specs/012-sensitive-data-transport-hardening/contracts/line-tunnel-allowlist.yaml) 拒絕 `/login`、帳密 login API 與 management；[public profiles](specs/013-remote-management-public-access/contracts/public-tunnel-profiles.yaml) 另定義 shared-demo 邊界。 |

### 3.1 規範語意需要釐清

憲章 XI 將使用者帳號列入單一租戶歸屬，但現有資料模型以全域 User 搭配多個 OrganizationMembership 實現跨收容所身分。後續正式規格應明訂「全域登入身分、租戶內角色與業務資料」的界線，不可把這個語意差異當作放寬租戶存取的理由。

## 4. 建議方案：Google 登入整合

### 4.1 選用流程

採 GIS JavaScript API 的官方 `renderButton()`、popup callback。第一版不主動顯示 One Tap，關閉自動選取。

這個流程符合目前前端向 FastAPI POST 憑證、由後端簽發 session 的架構，不需引入 authorization-code exchange 或第二套 token lifecycle。GIS callback、nonce 與 login_uri 的差異見 [GIS JavaScript API](https://developers.google.com/identity/gsi/web/reference/js-reference)。

### 4.2 前後端步驟

1. 前端向同源 API 建立 Google 登入交易。
2. 後端產生高熵 nonce、交易識別、瀏覽器綁定秘密及 CSRF 證明；保存用途、可信 client ID、摘要、到期時間與單次消耗狀態。
3. 瀏覽器綁定秘密放入 Secure、HttpOnly、SameSite cookie；正式 HTTPS 環境使用 host-only cookie，避免子網域覆寫。開發環境 cookie 設定須另外驗證。
4. 前端將 nonce 傳給 GIS 初始化，顯示官方按鈕。
5. callback 收到 credential，僅以 POST body 傳送 Google ID token、交易 ID，並帶上應用自己的 CSRF header／瀏覽器 cookie。
6. 後端檢查交易、token 與 User 狀態。已有 binding 時登入原 User；首次使用時依註冊意圖建立無密碼 User，或引導使用原帳號完成綁定。
7. 同一資料庫交易完成 binding、必要 User、session、refresh record、成功 audit 與交易消耗。commit 成功後才回傳 StrayHub token。
8. 前端沿用 session 儲存流程，依帳號狀態與有效收容所清單導頁。

### 4.3 登入 CSRF、重放及瀏覽器綁定

- 交易建立與交換 endpoint 檢查精確 Origin，限制同源 JSON 與 CSRF header，不開放寬鬆 credentialed CORS。
- 同時驗證交易 ID、瀏覽器秘密、CSRF 證明，以及已驗簽 token 內的 nonce。
- 交易建議五分鐘有效，以資料庫原子條件更新或鎖定保證一次成功交換。
- 交易用途固定為 `login` 或 `link`。`link` 另綁既有 user_id、session_id 與重新驗證證明，不能由交換 payload 任選 user_id。
- 交易可採共享瀏覽器秘密搭配每筆交易獨立 nonce，避免多分頁共用單一 nonce；前端仍須處理交易到期、取消與重新初始化。
- 成功交換後重播一律拒絕。若成功回應遺失，重新啟動 Google 交易，透過既有 binding 登入，不重建 User。
- GIS callback 後自行 fetch 的 POST 不可假設已有 GIS 自動提供的 `g_csrf_token`。直接 POST 接收模式與本方案不能混用。
- CORS、SameSite、驗章各自都不足以單獨替代上述交易綁定。

### 4.4 Token 驗證與金鑰管理

在既有 authentication ports／infrastructure adapter 架構新增 Google verifier，建議使用官方 `google-auth` 的 `verify_oauth2_token()`。

驗證至少包含：

- Google 簽章、允許的演算法與有效金鑰。
- `aud` 精確符合後端設定的可信 Web client ID，不能信任 request 傳入的 client ID。
- `iss` 為 `accounts.google.com` 或 `https://accounts.google.com`。
- `exp`、`iat`、claim 型別、非空 `sub`，及本次交易 nonce。
- 第一版每個環境使用單一 audience。若未來擴充多 client，須另訂並測試 audience／authorized party 規則。

Google 的簽章、audience、issuer、有效期與 `sub` 要求見 [後端驗證指引](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)。

驗證器的建議操作參數與失敗策略：

- 同步 verifier 放入有併發上限的 worker thread，不阻塞 FastAPI event loop。
- HTTP transport 設連線／讀取 timeout，例如 2 秒／3 秒，並有整體請求期限。
- 共用金鑰 HTTP 快取，依 Google Cache-Control 過期；不為每次登入重新抓取憑證。
- 未知 kid 最多觸發一次受控刷新，合併併發抓取並限流。固定 Google 金鑰來源，不能依 token 內 URL 任意發送請求。
- 有效快取可繼續使用；過期且刷新失敗時回 503，不略過驗證或無限使用過期金鑰。
- 不使用 tokeninfo 作為正式環境逐筆驗證路徑。
- 外部驗證在持有 User／membership 鎖之前完成；進入資料庫交易後重新確認登入交易仍有效且未消耗。

官方 Python verifier 預設抓取憑證與快取配置見 [google-auth 文件](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.id_token.html)。上述 timeout、TTL、限流及併發策略是 StrayHub 建議值，不是 Google 強制值。

### 4.5 錯誤、限流與敏感資料

- 無效 token 回一般化 401；交易／CSRF 不符回固定錯誤；綁定衝突回 409；限流回 429；Google 金鑰或資料服務不可用回 503。
- 沿用既有可信代理來源判定，對交易建立、交換、重新驗證與邀請認領分別限流。
- Google token 未驗證前，不以其中 email／sub 作可信帳號限流鍵；驗證後可使用 provider/sub 的 HMAC 摘要。
- 不將 Google credential、StrayHub token、交易秘密或邀請秘密放入 URL、log、audit JSON、錯誤訊息、analytics 或測試 trace。
- 新端點回應使用 no-store；擴充現有 nginx 敏感路徑與應用遮罩，避免 request body 或第三方原始例外洩漏憑證。

### 4.6 設定需求

| 設定 | 需求與保存位置 |
| --- | --- |
| Web OAuth client ID | 可公開供 GIS 使用；後端獨立設定可信值。開發與正式環境分離。 |
| Authorized JavaScript origins | 精確設定實際 scheme、host、port，不使用任意動態來源。 |
| OAuth branding／對外使用設定 | 應用資訊、支援信箱、隱私政策與適用網域，部署前確認。 |
| Google client secret | 本方案不需要，不新增前端或後端 secret 設定。 |
| Redirect URI、code exchange、PKCE | 本方案不使用，不混入 authorization-code 流程需求。 |
| Google access／refresh token | 不索取、不保存。 |
| 後端專用設定 | 交易秘密／摘要、限流 HMAC secret、JWT 私鑰；不得進 NEXT_PUBLIC 變數。 |
| 功能開關 | 後端決定是否允許本環境及入口註冊；前端按鈕顯示不能取代後端限制。 |

Origin、branding 與 callback／redirect 設定差異見 [Google Setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)。

[next.config.ts](apps/web/next.config.ts) 目前對 `/login` 設 no-referrer。後續須驗證 GIS script、popup／FedCM、CSP、COOP 與 referrer policy 的組合；若需調整，限縮至必要資源或入口，不全站放寬，也不允許 credential 經 URL 傳遞。

## 5. 建議方案：身分模型與舊帳號綁定

### 5.1 模型選擇

| 選項 | 評估 |
| --- | --- |
| GoogleUserBinding | 最接近現有 LINE 模式，修改面小，不必搬動 LINE flow／webhook 語意。推薦第一版採用。 |
| ExternalIdentity | 適合未來確定增加多個供應商時評估；本次引入並遷移 LINE 會增加不必要範圍。 |

GoogleUserBinding 至少包含 user_id、google_sub、status、建立／更新時間。provider 在表語意固定為 `google`，邏輯鍵為 `(google, sub)`。

- google_sub 全域唯一，不依 shelter_id 分裂成多個登入身分。
- 第一版一個 User 最多綁一個 Google 身分。
- 若保留撤銷紀錄，重新啟用與重新綁定規則須明確；不能因部分唯一約束意外允許身分轉移。
- 新 User 的 username、password_hash、platform_role 為 NULL，不建立 membership。
- display_name 使用本人確認的顯示名稱，不強制保存 Google 真實姓名。

### 5.2 併發與交易

唯一約束作為併發註冊最後防線。兩筆首次註冊同時競爭時，失敗交易須 rollback 包含新 User 的全部變更，再重新查詢已提交 binding；不能留下孤立 User。

登入交易消耗、binding、User、session、refresh record 與成功 audit 的 commit 邊界須一致。不要照搬帳密 router 遇 DomainError 就 commit 的處理方式，否則可能保存部分註冊結果。失敗限流紀錄與成功帳號交易應有明確的獨立保存策略。

### 5.3 舊帳號綁定

1. 使用者先以原帳密登入。
2. 在本人頁選擇綁定 Google，重新輸入原密碼。
3. 後端簽發短效、單次、綁定目前 User／session 的重新驗證證明。
4. 啟動 link 用途 Google 交易，驗證 Google 身分未屬於其他 User。
5. 在原 user_id 上新增 binding，保留原密碼、membership 與歷史紀錄。

登入頁在建立新 User 前提供「已有 StrayHub 帳號，先綁定」選項，降低重複帳號發生率。不能僅憑舊 session、同名或相同 email 自動綁定。

### 5.4 衝突、整併與解除綁定

- Google 已屬於另一 User：拒絕轉移，回一般化衝突，不回傳對方資料。
- 已形成兩個 User：第一版不提供自動合併、歷史重掛或權限聯集，需另立雙方驗證與資料遷移規格。
- LINE-only 帳號：現有 LINE bind／exchange 不能直接當作通用重新驗證 API。第一版不處理 Google／LINE 帳號整併。
- 解除 Google：重新驗證保留的登入方式，鎖定 User 後再次確認至少一種可用方式；Google-only 帳號不得解除。
- 不能只因存在 LINE binding 就認定有可用替代登入方式；現有 LINE 流程還受入口、membership 與 grant 限制。
- 解除時撤銷相關 session／refresh；若第一版沒有精確驗證方法追蹤，採撤銷該 User 所有 session，要求以保留方式重新登入。

### 5.5 個資

必要保存是 sub 與 internal user_id 關係。第一版不保存 Google email、頭像、完整 claims 或 ID token，也不在每次登入時覆蓋 display_name。

[VolunteerPiiService](services/api/app/application/volunteer_pii_service.py) 已有加密、同意與保存期限，但用途屬志工資料，不能直接把其 180 天期限套用至登入身分。Google binding、註冊告知、安全 audit 與未加入收容所帳號的保存／刪除政策需明訂。

## 6. 建議方案：無 membership 的完整流程

### 6.1 推薦管理者邀請

目前管理入口已有管理者建立帳號、管理 membership 的能力。第一版以邀請銜接最符合現有模式；公開加入申請會另增收容所搜尋、反垃圾、申請個資與審核流程。

推薦「管理者建立邀請碼 → 使用者登入後認領 → 管理者確認 → 建立 membership」。

- 邀請碼高熵、短效、單次，後端保存摘要，限制認領嘗試。
- 邀請的 organization 與候選 role 由授權管理者決定，認領者不可改寫。
- 透過既有人工管道交付邀請碼，第一版不新增寄信服務或 email 身分比對。
- 使用者在本人頁以 POST 輸入碼，認領綁定目前 user_id。
- 認領本身不授權；管理者核對對象後確認，降低轉寄邀請直接取得管理權限的風險。
- 最終確認時重驗操作者、組織、對象、重複 membership 與管理員名額；以一致鎖定策略處理同收容所並行變更。
- 建立 membership、更新邀請與租戶 audit 同一交易完成。
- 邀請不得授予 PLATFORM_ADMIN；VOLUNTEER 維持既有申請與限時 grant 流程。
- 已撤銷／停用的 membership 不因認領新邀請自動復原，須走明確授權恢復流程。

### 6.2 使用者狀態

| 狀態 | 畫面 | 後端允許行為 |
| --- | --- | --- |
| 未登入 | `/login` | 建立登入交易與驗證身分。 |
| 已註冊、無 membership | 獨立 `/account` 本人頁，顯示尚未加入收容所 | 本人資料、登入方式、認領邀請、refresh、登出。 |
| 已認領邀請 | 顯示等待管理者確認 | 查看本人邀請狀態，不能讀租戶業務資料。 |
| 有有效 membership、未選 context | 可用收容所選擇 | 透過既有 context switch 重新授權。 |
| 有有效 context | 原管理／志工入口 | 依該收容所 role、membership、grant 操作。 |
| membership 到期、撤銷或組織停用 | 回本人頁，提示權限變更 | 身分層功能仍可用，租戶操作立即拒絕。 |

### 6.3 受限 session

沿用 SessionRecord，建議新增伺服器端帳號存取模式 `account_only`／`standard`，舊 session 預設 standard。

- Google 無 membership 新帳號使用 account_only，active_organization_id 為 NULL。
- `/me`、logout、登入方式管理與本人邀請狀態使用真正的身分層 dependency。
- 身分層檢查 User/session 有效性及來源限制，即使舊 context 失效也能回本人頁與登出；不得因此設定租戶 scope。
- current_request_context 繼續驗證組織、membership、角色與 grant，明確拒絕受限 session 的租戶業務存取。
- 核准後經 context switch 重新驗證有效權限，才轉入 standard；前端狀態不是授權依據。
- account_only refresh 保留到期、停用、rotation、family 重放與來源檢查，但不要求 membership。
- Google 所建立的可回本人頁 session 在失去最後有效 membership 時，應清除失效 active context、回到 account_only。須保存足以判定這項政策的伺服器端標記，例如獨立 session policy，不能僅由前端宣告。
- 不直接刪除既有全部 `not available_access` 判斷；帳密、LINE／LIFF 及 remote-demo admission policy 分別保留。
- 檢查 dependency cache，較弱的 context 不得讓較強的 dependency 略過 organization 驗證。

session_origin 繼續描述入口，不加入 google origin；Google 是驗證方法。若需紀錄驗證方法或 session policy，使用獨立欄位，不混用 origin。

### 6.4 RLS 與本人狀態

不為顯示 pending 狀態而直接擴大既有 membership／organization discovery RLS。

- 邀請資料由新邀請表承載，租戶管理操作與本人已認領狀態分別限制。
- 未認領秘密的查找必須封裝為受限的認領操作，不提供全站邀請或使用者搜尋 API。
- 本人只看到自己的狀態與必要欄位，不能指定任意 user_id 查詢。
- 既有非 active membership 若需顯示，另設狹窄的本人狀態投影／查詢政策；不能把任意 tenant scope 當查詢捷徑。
- 新帳號頁不套用必須有 shelter context 的 management layout，也不顯示全站收容所清單。

## 7. 建議修改範圍與契約

### 7.1 API 草案

| 建議 endpoint | 用途與主要限制 |
| --- | --- |
| `POST /v1/auth/google/transactions` | 建立 login 交易；link 用途另外要求目前帳號與重新驗證證明。 |
| `POST /v1/auth/google/exchange` | 單次交換 token；依伺服器交易用途註冊／登入／綁定，不接受任意角色。 |
| `POST /v1/auth/reauthenticate` | 原帳密重新驗證，發出限用途的單次證明；有獨立限流。 |
| `GET /v1/auth/me` | 保留既有 profile 欄位，補明確帳號狀態／有效存取資訊；改用身分層驗證。 |
| `GET /v1/auth/login-methods` | 本人可用登入方式摘要，不回傳 sub 或憑證。 |
| `DELETE /v1/auth/google/binding` | 重新驗證保留方式，禁止移除最後登入方式。 |
| `GET /v1/auth/invitations` | 本人已認領邀請狀態。 |
| `POST /v1/auth/invitations/claim` | 驗證邀請秘密、綁定本人；不建立權限。 |
| 組織內 invitations API | 在既有 organization management 路由增加建立、確認、撤銷操作，具 tenant 與 role 驗證。 |

refresh、logout、active-shelter-context 沿用既有 endpoint，調整狀態契約與 dependency，不另造 session API。

### 7.2 檔案與責任

| 區域 | 修改策略 |
| --- | --- |
| `apps/web/app/login/LoginClient.tsx` | GIS、註冊／舊帳號分流、零收容所導向本人頁。 |
| 新本人帳號頁 | 獨立於 management layout，顯示登入方式、邀請及待授權狀態。 |
| `apps/web/lib/auth.ts`、`api.ts` | 帳號狀態型別、儲存與續期；區分憑證失效和業務 context 失效。 |
| `route-access.ts`、`AuthenticatedRouteBoundary.tsx`、`ManagementLayout.tsx` | 本人頁與租戶頁分流，避免重導迴圈，保留原角色限制。 |
| `services/api/app/api/authentication.py` | 新交易／exchange／綁定契約及錯誤處理。 |
| `application/authentication/`、`application/ports/authentication.py` | Google 驗證協作、session 共用簽發、入口政策與受限狀態。 |
| `infrastructure/auth/` | Google verifier adapter，逾時、快取與固定金鑰來源。 |
| `api/dependencies.py`、`context_service.py` | 身分與租戶驗證分離、cache 保證、context promotion，保留既有 LINE 副作用。 |
| `identity.py`、`authentication_repository.py`、新 migration | Google binding、單次交易、session 政策及原子性。 |
| 既有 organization management | 邀請 lifecycle 與 membership 授權，沿用角色和名額規則。 |
| `audit_service.py` 與 audit policy | 明確支援 account resource 的窄範圍事件；不能冒用 platform scope 或放寬全部無租戶 audit。 |
| `scripts/configure_runtime_role.py`、migration grants | 檢查新表最小權限及預設 grants，不使用 owner／BYPASSRLS。 |
| OpenAPI、`packages/contracts/src/openapi.ts` | 同步 schema、安全需求、HTTP status 與前端消費者。 |
| settings、nginx、環境範例 | 功能開關、可信 client／origin、敏感路徑與後續部署需求；不修改公開 profile 邊界。 |

### 7.3 公開入口、遷移與回滾

- 第一版只在明確允許的一般 web 環境啟用，shared-demo profile 預設不提供 Google 註冊。
- LINE-only tunnel 仍拒絕 login／account／新 Google 入口；不能為功能可達性擴大 allowlist。
- migration 採增加式設計，不重建既有 User 或搬移 LINE binding。舊 session 的預設值保留既有政策。
- 新表須評估登入前 global identity lookup 與 tenant-owned invitation 的不同存取模型，不能對所有表套相同 RLS。
- 關閉功能開關可停止新 Google 登入／註冊，不刪除 binding、User 或歷史資料。
- Google-only 使用者在停用 Google 登入後可能無法重新登入，因此營運回滾須明訂處置；不得暗中建立密碼或刪除帳號當作回復手段。
- 雲端設定與實際 migration 執行屬未來實作／發布工作，本文件不授權執行。

## 8. 實作順序與驗收

### 8.1 建議順序

1. 將本策略轉成既有 Spec Kit 結構內的正式規格、資料模型、API 契約與任務。本文件依本次要求放於根目錄，作為設計輸入。
2. 先完成身分層 dependency、受限 session、本人頁、refresh／logout 與失效 context 處理。
3. 完成 Google verifier、登入交易、binding 與舊帳號重新驗證。
4. 完成邀請建立、認領、確認、狀態查詢與 membership 原子授權。
5. 完成 runtime-role PostgreSQL 測試、前端流程、契約與既有認證回歸。
6. 全部驗收後才於獲准環境開啟首次註冊，避免只上線按鈕而留下無法前進的新帳號。

### 8.2 必要驗收情境

- 正確／錯誤 audience、issuer、簽章、nonce、到期 token、未知 kid、金鑰輪替與逾時。
- 攻擊者 token 注入其他瀏覽器、交易互換、login 冒充 link、並行重播與回應遺失。
- 並行首次註冊僅一個 User；中途失敗不留下孤立 User、binding 或部分 session。
- 舊帳號綁定後 user_id、membership、歷史資料不變；同 email／姓名不合併。
- Google-only 不可解除最後登入方式；綁定衝突不洩漏另一帳號資訊。
- 無 membership 可重新整理本人頁、refresh、登出；直接呼叫租戶 API 仍拒絕。
- 邀請到期、撤銷、重複認領、跨租戶查改、role 篡改與管理員名額並行限制。
- 同一 User 在 A／B 收容所角色獨立，切換後舊請求不能污染新 context。
- 權限撤銷／到期後停止業務操作，但可回本人頁與登出。
- 帳密、LINE／LIFF、refresh family 重放撤銷、remote-demo rollback 及 tunnel boundary 回歸。
- sentinel credential 不出現在 URL、access log、application log、audit、analytics 或測試產物。

### 8.3 驗證方式

現有 [test_authentication_session.py](tests/integration/test_authentication_session.py) 部分使用 fake repository。service 測試不能證明真實 RLS／ACL 與併發安全，必須增加使用 PostgreSQL runtime role 的隔離及交易測試。

未來實作先以相關 pytest、Ruff、Vitest 與 TypeScript 檢查，再執行必要完整品質門檻。前端使用 package.json 已有的 `test`、`typecheck`、`build`、`test:e2e` 等 scripts，不假設有 lint script。

本次僅文件整理，未執行應用測試、資料庫驗證或雲端驗證；不宣稱上述功能或驗收已完成。

### 8.4 開發測試入口

日常 Google 開發使用 `http://localhost:3001/login`，由 Next.js `/v1/*` proxy 轉送本機 FastAPI `127.0.0.1:8001`。Google popup 把 credential 交回瀏覽器，再由瀏覽器 POST 本機 API，不需要 Google 伺服器連入本機。

- 開發專用 Google Web client 的 Authorized JavaScript origins 加入 `http://localhost` 與 `http://localhost:3001`；popup callback 不設定 redirect URI。
- 使用 `./scripts/dev.sh`；同時測 LINE 時使用 `./scripts/dev.sh --line`，Google 仍走 localhost，LINE／LIFF 走原 HTTPS tunnel。
- 瀏覽器統一使用 localhost，不與 127.0.0.1 混用，避免 origin、cookie、sessionStorage 不一致。
- 驗證 proxy 的 Cookie、Set-Cookie、Origin、CSRF header，以及 localhost cookie／referrer policy。
- 手機、遠端協作與正式 Secure cookie／安全標頭驗收使用另行授權的 staging 或專用 HTTPS 測試入口；不擴大 LINE tunnel allowlist。
- 自動化測試使用可注入 verifier 與測試金鑰；正式 verifier 不接受 mock token。真實 Google E2E 需開發 client 設定與使用者在瀏覽器操作，不將真實 credential 保存為 fixture。

## 9. 待確認事項

| 事項 | 需要確認的內容 |
| --- | --- |
| 啟用環境 | 實際登入網域、origin、適用 Google Web client、OAuth 對外使用設定，以及既有 gateway profile。未讀取 Console，不能宣稱已配置。 |
| 個資與帳號保存 | 未加入收容所帳號、Google binding、註冊告知及安全 audit 的保存期限、刪除流程與責任人。 |
| 規範語意 | 正式規格釐清全域 User 與租戶 membership／業務資料的歸屬，與憲章文字一致。 |

一般實作選擇依本文件建議推進；上述事項屬產品政策或實際環境資訊，不能僅從現有程式碼推定。

## 10. 官方技術來源

以下官方文件已於本次分析查閱；日後實作時仍須核對選用套件版本與當時文件。

- [GIS JavaScript API reference](https://developers.google.com/identity/gsi/web/reference/js-reference)：官方按鈕、callback、nonce、popup 與 redirect 差異。
- [Verify the Google ID token on your server side](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)：token 驗證、Google sub 與身分關聯。
- [Google Sign in with Google Setup](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)：Web client、origins、branding、瀏覽器安全標頭。
- [google.oauth2.id_token](https://google-auth.readthedocs.io/en/latest/reference/google.oauth2.id_token.html)：Python verifier、audience 與憑證快取。
