# 實作計畫

沿用 FastAPI／SQLAlchemy async／PostgreSQL、Next.js 與既有 session service。官方 google-auth 驗章搭配 httpx 非同步固定憑證來源快取。無外部網路 I/O 的驗章在有限 worker thread 執行。

新增 GoogleUserBinding、GoogleAuthTransaction、OrganizationInvitation；SessionRecord 增加 account_access_enabled，表示此 session 可在無 membership 時使用本人功能。account_only 狀態由伺服器依有效存取推導，避免保存兩個互相矛盾的狀態欄位。舊 session 預設 false，Google session 為 true。

新增 identity_request_context 與本人 account API；原租戶依賴保持強驗證並分離 cache。本人頁使用專用 account endpoint，保留舊 /me response 消費者。Google service 共用 AuthenticationRepository 與 SessionService；邀請沿用 OrganizationManagementService／OrganizationRepository 的鎖與角色規則。

登入交易使用每筆獨立 HttpOnly cookie、CSRF header 與 nonce，五分鐘有效；link 交易於建立時要求原密碼驗證，省略可轉交的額外 reauth token。邀請碼只在建立回應顯示，資料庫保存摘要；RLS 認領 scope 限 exact digest，認領者只能查看自己的資料。

帳號 audit 在既有 AuditService 新增明確 account 類型及 self-only INSERT policy；不更改租戶資料的 discovery policy。邀請表 FORCE RLS；global credential 表比照既有 session credential 的後端專用查找模式。

驗證順序：安全單元測試、真實 PostgreSQL runtime-role API／併發／隔離測試、前端型別與互動測試、build、既有認證及公開入口回歸。Google Console 與真實瀏覽器登入留作需環境設定的手動驗收，不宣稱已通過。
# 加入申請流程更新

新增 0051 migration 與 OrganizationJoinApplication，設計及過渡方案見 [application-review.md](application-review.md)。Google session／binding 沿用；邀請碼改為申請審核。
