# Google 登入開發操作

## 啟用前

本功能預設關閉。新版 API 啟動前必須套用至 `0051_join_applications`。新 migration 建立加入申請及 RLS，把未到期已認領邀請轉為待審申請，關閉其餘未結束邀請；已核准的 membership 保留。本次僅在專用 `strayhub_test` 套用，未套用一般開發或正式資料庫。

依既有流程確認目標 `DATABASE_URL`、備份與 runtime role，再由操作者執行 `uv run alembic upgrade head`。使用 `uv run python -m scripts.configure_runtime_role` 檢查 ACL；應用不得使用 owner／bypass-RLS 帳號。

## 本機真實 Google 測試

1. 由環境管理者建立開發專用 Google Web client，設定 Authorized JavaScript origins：`http://localhost`、`http://localhost:3001`。GIS popup JavaScript callback **不需要 client secret、authorization-code exchange 或 redirect URI**。
2. 在未納入版本控制的 API 環境設定 `GOOGLE_AUTH_ENABLED=true`、`GOOGLE_AUTH_CLIENT_ID=<開發 client ID>`、`GOOGLE_AUTH_ORIGIN=http://localhost:3001`。client ID 與 origin 可公開；JWT／資料庫秘密仍僅留後端。前端從 config API 取得 client ID。
3. 執行 `./scripts/dev.sh`，開啟 `http://localhost:3001/login`。Google popup 回傳給瀏覽器，瀏覽器 POST 同源 `/v1` proxy；Google 不需連入 localhost。
4. 同時測 LINE 可用 `./scripts/dev.sh --line`；Google 仍走 localhost，LINE／LIFF 走原 HTTPS tunnel。不修改 tunnel allowlist，不公開管理入口。
5. 手機、外部協作及 Secure cookie／HTTPS 標頭需另行授權的 staging。不要混用 localhost 與 127.0.0.1；手機 localhost 也不代表開發電腦。

## 操作驗收

- 首次註冊：在登入頁選「第一次使用」、填姓名，再按「下一步：選擇 Google 帳號」及官方 Google 按鈕。註冊後進入 `/access`「我的收容所」；尚無 membership 時只顯示加入申請及狀態。
- Google 再次登入：官方按鈕會自動準備。只有一間可用收容所且沒有加入目標時，會經伺服器確認 context 後直接進工作台；多間顯示收容所卡片供選擇。單純打開「我的收容所」不會自動跳離。
- 舊帳號：展開「使用原帳號密碼登入」，登入後點右上姓名選單 →「登入設定」(`/account`)，輸入原密碼並連結 Google。此入口只替有帳密的舊帳號顯示；Google-only 直接開此路徑會轉回 `/access`。綁定保留 user_id；既有兩個 User 不自動合併。
- 加入收容所：管理員從右上姓名選單 →「加入申請」，或從「我的收容所」卡片進入。按「複製申請連結」提供給人員；使用者確認收容所後送出申請。管理員核對身分、選擇工作權限並核准。本人按「更新狀態」後即可進入工作台。
- 否決：按「否決」並在行內確認後，申請移出待審列表；顯示處理成功回饋。本人仍可看到結果，一天後可重新申請，其他收容所權限不受影響。
- 固定連結為 `/access?join=<收容所 UUID>`；舊 `/account?join=...` 仍相容轉址。網址不具授權能力。本機 localhost 連結僅適合同一電腦測試，遠端需已授權的 HTTPS 管理入口，LINE tunnel 不適用。
- 舊邀請建立／認領 API 回 410；管理頁保留原 `/account/invitations` 路徑相容舊書籤，但內容已改為申請審核。
- 解除綁定：舊帳號在「登入設定」展開「管理 Google 連結」。需原密碼重新驗證，且帳密確實能登入；成功後撤銷該 User 現有 session。Google-only 不顯示此設定。
- 驗收 Origin／CSRF／nonce 不符、交易過期／重播、綁定衝突、無權限直接呼叫 API、A／B 收容所切換、membership 撤銷、refresh 及登出。
- 不把 credential、邀請碼、密碼或 cookie 放進 URL、截圖、log、network 匯出或 fixture。

## 自動化

- 契約：`uv run python -m scripts.generate_google_auth_contract`、`npm --prefix packages/contracts run generate`、`npm --prefix packages/contracts run check`。
- 後端：指向專用 PostgreSQL 測試庫，執行 `uv run pytest tests/unit/test_google_identity_verifier.py tests/integration/test_google_authentication.py tests/contract/test_google_authentication_contract.py`。
- 前端：`npm --prefix apps/web run test -- components/auth/GoogleSignIn.test.tsx 'app/v1/[...path]/route.test.ts'`，並執行 `typecheck` 與 `build`。
- 瀏覽器：另開本機前端，設定 `PLAYWRIGHT_SKIP_WEBSERVER=1`、`PLAYWRIGHT_BASE_URL`，執行 `npm --prefix apps/web run test:e2e -- e2e/google-account.spec.ts`。

測試金鑰／注入 verifier 不等於真實 Google 驗收。停用 Google 會阻止 Google-only 使用者重新登入；回滾不可刪除 binding 或偷偷建立密碼。
