# LINE 帳號、LIFF 與 Rich Menu 設定

本文件區分本機展示、自動測試、受控實機 smoke 與 production。真實 token、secret、
ID token、LINE user ID 與個資不得提交 Git 或貼入測試證據。

## 環境分級

| 環境 | Credential／資料 | 用途 |
| --- | --- | --- |
| Normal demo | `.env.example` 的 fake LINE 值；三個 demo shelters | `./scripts/demo.sh`，不發布 menu、不建立 LINE test fixtures |
| Automated test | loopback `strayhub_test`、deterministic fake verifier | pytest／E2E／tenant isolation；不可指向 demo 或 production DB |
| Controlled smoke | 非 production LINE channels、受控帳號、公開 HTTPS tunnel | 手機驗證 webhook、LIFF、menu link 與角色切換 |
| Production | Secret Manager／部署 config、正式 HTTPS origin | 預設 gate 關閉；只有精確 release commit 通過 smoke 才可啟用 |

## LINE Developers 前置條件

在同一 Provider 準備：

1. Messaging API channel：Channel ID、Channel secret、長期 access token。
2. LINE Login channel：Channel ID、Channel secret。
3. 志工申請 LIFF app：scope 至少 `openid`，Endpoint 指向公開 origin 的
   `/volunteer-application`。
4. Staff LIFF app：Endpoint 必須是已審核、部署於同一公開 origin 的 staff artifact；其
   LIFF ID 以 `LINE_STAFF_LIFF_ID` 提供。
5. 四張 2500×1686 Rich Menu 圖片位於
   `infra/local/rich-menu-images/{default,volunteer,adopter,staff}.png`。

本機 `.env` 可由 `.env.example` 複製再填入受控測試值；production 值只能由部署平台注入。
不要在命令列輸出 secret。`LIFF_ID` 是公開志工 LIFF；`LINE_STAFF_LIFF_ID` 是 staff LIFF。

## 本機與自動測試

```bash
./scripts/demo.sh
./scripts/test_line_local.sh --print-env
./scripts/test_line_local.sh --no-tunnel
uv run python -m scripts.sync_line_role_menus
```

`--no-tunnel` 只驗證 credential presence、mock 關閉、API/Web、single-origin proxy 與 LIFF
route，不把服務暴露至 Internet。自動測試使用：

```bash
uv run python -m scripts.test_local tests/unit/test_line_role_menu_actions.py -q
```

`ORG-A` 等 fixture 僅能存在 `strayhub_test`，不是 normal demo 帳號或收容所。

## 受控實機 smoke

先確認資料無敏感內容，再明確同意公開本機測試 surface：

```bash
./scripts/test_line_local.sh
```

helper 以 nginx 將 `/v1/*` 送 FastAPI、其他路徑送 Next.js，再用一條 ngrok tunnel 提供
single HTTPS origin。它不修改 `.env`、LINE Developers 或 Rich Menu。將輸出的 webhook URL
與 LIFF Endpoint 手動填入受控 channel；結束後執行 `./scripts/test_line_local.sh stop`。

發佈測試 Rich Menu 前先 dry-run；寫入需另外批准並確認 Bot 身分：

```bash
uv run python -m scripts.sync_line_role_menus
uv run python -m scripts.sync_line_role_menus --apply \
  --image-dir infra/local/rich-menu-images \
  --expected-bot '@APPROVED_TEST_BOT' --manifest /approved/operator-directory/menus.json
```

工具只建立／驗證資源，不刪除、不切 default、不綁定、不回寫 env。
設定載入、單帳號綁定與全域切換需分別批准；詳見
[安全發布與 gate 順序](line-rich-menu-safe-publication.md)。
取得完整 ready IDs 及合法 gate 後，另行批准注入測試 process 與重新啟動。實機至少驗證：

- 公開 menu 只有志工服務與領養流程。
- 志工申請核准後切 volunteer menu；返回 default 不改權限。
- 領養兩條路徑、返回／取消／續接與 AI disabled fallback；inquiry 後不切 adopter menu。
- 單 shelter staff 可進 staff menu；多 shelter staff 必須先選 shelter。
- 未選 shelter、非 staff、跨 shelter/replay request 都被 server 拒絕。
- LINE timeout/5xx 不破壞已提交資料，duplicate event 不重複建立資料。

證據只能保留時間、遮罩後 channel/environment、完整 40-char commit SHA、case 結果與錯誤碼；
不得保留 token、secret、raw ID token、LINE UID 或受保護資料。

## 帳號綁定與收容所選擇

測試管理員可用 CLI 將受控 LINE UID 綁到既有內部帳號：

```bash
uv run python -m scripts.bind_line_account bind \
  --username <TEST_USERNAME> --line-user-id <CONTROLLED_LINE_UID>
uv run python -m scripts.bind_line_account status --username <TEST_USERNAME>
uv run python -m scripts.bind_line_account unbind --line-user-id <CONTROLLED_LINE_UID>
```

只有一個 active membership 時可建立該 shelter context。多個 active memberships 時必須由
LIFF 身分交換明確傳入要使用的 organization；後端逐一驗證 membership，不能由 client
直接指定未授權 shelter。

## Production 啟用

工作人員帳號、Google 登入及收容所內的核准責任見
[收容所工作人員帳號與權限治理](staff-access-governance.md)。Staff LINE 是獨立選配能力，
不是工作人員取得權限的必要流程。本次工作人員使用 Google 登入 Web 後台，自行申請
加入收容所，由該收容所管理員核准；Staff LINE 延後。

`LINE_ROLE_MENU_FEATURES_ENABLED=false` 是預設值。先依
[受限 smoke runbook](line-rich-menu-safe-publication.md#受限-smoke-runbook本地機制不是執行-production-的授權)
在全域關閉時驗證明確帳號；完整真人報告由 preflight 比對實際 release、映像、資源與必要案例，
再透過正常 release/approval 啟用全域功能。`verified-YYYYMMDD-<40-char-tested-git-sha>`
僅為舊版相容標籤，單獨不足以啟用。不可直接在 VM 手改 env，也不可用 local/mock evidence
代替 production-like 真人 smoke。
