# 實作與驗證紀錄

最新 UI/UX 調整見 [ux-design.md](ux-design.md)：65 個聚焦單元測試、27 個分組 Chromium 情境通過；含手機／桌機 axe、鍵盤與 Google／舊帳號分流。TypeScript 與 production build 通過。

最新加入申請調整的驗證結果見 [application-review.md](application-review.md)：後端 13、前端 21、Chromium 3 個聚焦測試通過，build 與契約檢查通過。下方保留原邀請版驗證紀錄。

日期：2026-09-07。基準：`dev/google_auth`，HEAD `0d80494d3d3cf8eb4faeec72c4150c98b2b43425`。起始只有使用者已 staged 的 `google_auth.md`；保留該 staged 內容，補充留在 unstaged。沒有 commit、PR、部署或雲端設定異動。

## 已實作

GIS 官方 popup、固定 client ID 驗章與限時憑證快取／輪替；cookie、CSRF、nonce 與單次交易綁定瀏覽器登入。Google sub 唯一 binding 支援並行首次註冊及原子 session 簽發；舊帳號需重新驗證，不按 email／姓名合併，不保存 Google email／姓名。

沿用 JWT／refresh／登出，以 `account_access_enabled` 動態推導 account_only；本人依賴與租戶授權分離。本人頁、邀請／認領／管理者確認、邀請 FORCE RLS、原角色與管理員名額限制均已實作。LINE tunnel allowlist 未放寬。同步 migration、runtime ACL 檢查、OpenAPI／TS、proxy 多 cookie、標頭及敏感 access-log 路徑排除。

## 驗證結果

| 檢查 | 結果 |
| --- | --- |
| 聚焦後端認證、Google verifier、runtime-role PostgreSQL、併發／原子性及既有契約 | 72 passed |
| 後續契約與安全測試組合 | 17 passed；2 個既有靜態掃描失敗 |
| Google 按鈕與 proxy | 7 passed |
| 既有前端 auth／proxy／login 回歸 | 38 passed，與其他組合部分重疊 |
| Chromium 本人頁無 membership、認領、重新整理、360px、登出 | 1 passed；API mock，非真實 Google |
| TypeScript、Next.js build、contracts check、Ruff check、git diff --check | 通過 |
| 完整後端 suite | 1743 passed、24 failed、2 skipped；24 失敗皆以 HEAD archive 重現 |
| 完整前端 suite | 469 passed、1 failed；涉及未修改的 reports 靜態文案 |
| 完整 Ruff format check | 4 個未修改檔案不符合格式 |

以上為不同時間的分組結果，不是全部通過的發布宣告。僅 `127.0.0.1:65432/strayhub_test` 套用 `0050_google_auth`。隔離測試以 runtime role 執行，合成資料以 rollback／精確清理移除。

## 既有失敗

後端 HEAD 對照：LINE demo cleanup 靜態契約 1、draft interruption 時戳 15、management report 文案 1、acceptance bootstrap invalid_credentials 1、sensitive transport／URL registry 對 `scripts/dev.py:247` 的掃描 2、LINE menu bubble 數量 1、runtime safety 設定 1、worker fake job_type 2。未修改這些測試或放寬安全門檻。

前端 `components/management/management-copy.test.ts` 仍對 `reports/page.tsx` 搜尋已拆至其他元件的文案；測試與涉及頁面沒有本次差異。

格式涉及 `scripts/seed_furkids_demo.py`、`services/api/app/api/line_webhook.py`、`services/worker/app/handlers/ai_job_runner.py`、`tests/integration/test_adoption_webhook_flow.py`，未為本功能重排。

## 尚待發布驗收

- Google Console 未配置，真實 Google 登入未驗收；需依 quickstart 設定開發 client 與實際 origin。
- 一般開發／正式 DB migration、runtime ACL 與 nginx 設定未套用，功能旗標未開啟。
- 完整品質門檻仍有上述失敗；聚焦測試不代表所有攻擊排列與所有瀏覽器均已覆蓋。
- 個資／帳號與 audit 保存期限、刪除操作、正式網域及 Google-only 回滾營運方式仍待產品／環境負責人確認。
