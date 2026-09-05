# Credential URL Incident Runbook

本 runbook 用於 StrayHub synthetic/local demo credential 意外進入 URL 的前 30 分鐘處置。禁止把原始密碼、token 或完整敏感 URL 貼進 issue、chat、log 或 evidence。

## Safety boundary

- 僅處理已確認的 local/test synthetic database 與本次 helper 啟動的 tunnel。
- production-like account、database、remote log deletion 或第三方控制台操作都需要環境 owner 明確授權。
- Evidence 只保存 UTC timestamp、environment、surface、不可逆 account fingerprint、結果與 artifact digest。
- 已同步到瀏覽器、第三方或備份的副本可能無法證明完全刪除；只能記錄已完成的清理與殘餘風險。

## 0–5 minutes: stop propagation

1. **MANUAL** 記錄事件開始 UTC 時間、環境名稱與受影響 route；不要保存 query value。
2. **MANUAL** 停止建立該公開 URL 的 helper-owned ngrok/tunnel process，並以 process list 與 ngrok dashboard 確認 endpoint 已不可達。不要只關閉瀏覽器分頁。
3. **MANUAL** 暫停公開 management `/login`；LINE 必要 webhook 或 LIFF route 若仍需公開，必須由既有獨立 helper 管理，不得臨時擴大 allowlist。
4. **AUTOMATED** 部署或切換到 Phase A login source fix：SSR form 為 `POST /login`、hydration 前 disabled、登入頁不預填 credential、legacy credential query canonicalize 到 `/login`。

Evidence：開始時間、停止的 PID/tunnel identifier digest、endpoint probe 結果、部署 commit（不得包含 secret）。

## 5–15 minutes: rotate and revoke

1. **MANUAL** 雙重確認目標為 loopback `strayhub` synthetic database，且 account username 為預期的 `demo-*` 身分。若任一 guard 不符立即停止。
2. **AUTOMATED** 以互動式 `scripts/demo.sh` 產生新的高熵 demo password，或在受控 shell 明確設定 `STRAYHUB_DEMO_PASSWORD` 後執行 bootstrap。不得把值放在 command URL、shell argument、issue 或版本庫。
3. **AUTOMATED** Demo bootstrap 會拒絕已知曝光值與短密碼、更新五個 `demo-*` account password hash，並將其 active `SessionRecord` 設為 expired。Refresh token 因 server-side session 非 active 而失效。
4. **MANUAL** 若不允許執行完整 bootstrap，由環境 owner 使用既有 account-management 能力輪替精確 account 並撤銷全部 session；不要直接任意編輯 production-like rows。
5. **MANUAL** 驗證舊 password 登入回 `401`、舊 access token 與 refresh token 均失效；再以新 credential 驗證正常 JSON `POST /v1/auth/login`。新值不得出現在 URL 或 log。

Evidence：account username 的 SHA-256 digest、rotation/revocation UTC 時間、失效 session 數量、三項 HTTP status；不得保存 password、token 或完整 request target。

## 15–25 minutes: contain retained copies

1. **MANUAL** 清除可控制的 local nginx/Next/ngrok agent log、Playwright HAR/trace/screenshot 與暫存檔；先記錄檔案 digest 與刪除範圍，不複製敏感內容。
2. **MANUAL** 開啟 ngrok inspector/dashboard，確認 retention、request capture 與刪除能力；刪除允許刪除的 capture，保存設定頁或操作結果的去識別 evidence。
3. **MANUAL** 清除測試瀏覽器的該筆 history/autofill；若瀏覽器 history sync 已開啟，依供應商機制刪除同步紀錄並記錄無法驗證的遠端副本風險。
4. **MANUAL** 檢查 shell history、clipboard manager、screen recording、chat 與 ticket 是否含該 URL。只能刪除有權控制的副本。
5. **MANUAL** 由 credential owner 確認該值是否在其他環境、account 或服務重用；若有，逐一輪替並撤銷 session。

Evidence：每個 surface 的 `checked/cleaned/not-retained/unverifiable` 狀態、UTC 時間與 evidence digest。

## 25–30 minutes: restore and verify

1. **MANUAL** 必要時以新的 helper process/tunnel session 重啟允許的 demo surface；不得恢復舊 tunnel session。
2. **AUTOMATED** 執行 login unit、Playwright no-JS/hydration/legacy URL/network matrix 與 `git diff --check`。
3. **MANUAL** 使用不同的 synthetic sentinel 驗證 address bar、Back history、browser console、ngrok、nginx、Next 與 application log 不含原值。
4. **MANUAL** 將結果填入 `specs/012-sensitive-data-transport-hardening/runtime-incident-result.md`。有任何未完成外部步驟時，狀態必須是 `MANUAL ACTION REQUIRED` 或 `BLOCKED`。

## Evidence record format

```text
timestamp_utc:
environment:
account_fingerprint_sha256:
surface:
action: checked | rotated | revoked | cleaned | not_retained
result: PASS | FAIL | BLOCKED | UNVERIFIABLE
http_status_or_count:
evidence_digest_sha256:
operator:
notes_without_secret:
```

## Recovery limitation

完成本 runbook 不代表所有第三方、同步裝置或備份副本已被證明刪除。結案只能聲明已輪替 credential、已撤銷 session、已清理可控制副本，以及仍無法驗證的 retention surface。

## Engineering prevention checks

事件處理不取代 repository 防回歸。修正或新增 form、URL builder、LIFF/QR capability、logger
或 tunnel route 後執行：

```bash
uv run python scripts/check_sensitive_transport_policy.py
uv run python scripts/verify_sensitive_transport_runtime.py
uv run pytest tests/e2e/test_local_line_tunnel_boundary.py
```

第一個命令拒絕 unsafe login fallback、production hard-coded demo password、Class A URL、unsafe
nginx sensitive format 與 tunnel catch-all。第二個命令只輸出 synthetic sentinel digest；外部
ngrok inspector、瀏覽器同步 history 與 remote retention 仍必須保留為人工 evidence，不能用本機
PASS 取代。

## Completed incident record

2026-09-05 的 synthetic demo credential 事件已依本 runbook 完成受控 rotation、session
invalidation、browser/local artifact review 與登入驗證。去敏結果與不可回溯的 ngrok residual
risk 記錄於 [`runtime-incident-result.md`](../../specs/012-sensitive-data-transport-hardening/runtime-incident-result.md)。
該紀錄只關閉 012 T008；不代表 013 public-host smoke 或 rollback drill 已完成。
