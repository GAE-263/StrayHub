# Runtime Incident Result — Phase A

Recorded at: `2026-09-04T08:17:07Z`

Overall status: **MANUAL ACTION REQUIRED**

本文件不保存原始 credential、token 或完整敏感 URL。Repository 內可自動完成的 source containment 與 local demo provisioning guard 已實作；外部狀態尚未獲授權執行，因此 T008 不得標示 fully complete。

## Automated evidence

| Item                           | Result          | Evidence                                                                                                                                                              |
| ------------------------------ | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Login native fallback          | PASS            | SSR contract 為 `method=post`, `action=/login`, pre-hydration submit disabled                                                                                         |
| Production login prefill       | PASS            | username/password 初值為空；登入 bundle 不再含 demo credential                                                                                                        |
| Legacy credential URL          | PASS            | server early redirect + client `history.replaceState`; Playwright final URL 與 Back 均為 `/login`                                                                     |
| Login transport                | PASS            | JSON `POST /v1/auth/login`; credential 只在 request body                                                                                                              |
| no-JS / hydration race         | PASS            | JavaScript disabled 與 blocked `/_next` script 測試均未產生 credential GET                                                                                            |
| Demo provisioning              | PASS (code)     | `STRAYHUB_DEMO_PASSWORD` 必須明確提供，互動式 helper 才可產生高熵值；已知曝光值與短值被拒絕                                                                           |
| Session invalidation           | PASS (code)     | Demo bootstrap 更新 password hash 時，同 transaction 將所有 demo user active sessions 設為 expired                                                                    |
| Initial legacy request logging | RISK / DEFERRED | Runtime smoke 觀察到 Next dev 仍會先收到並記錄直接貼入的 legacy request target；依本輪 scope 不實作 T009+ logging hardening，須依 runbook 清理本次 synthetic artifact |

## MANUAL ACTION REQUIRED

| Action                                   | How to execute                                                                                            | Verification                                         | Evidence to retain                          |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | ------------------------------------------- |
| Stop exposed tunnel                      | 依 runbook 停止精確 helper-owned process，並在 ngrok dashboard 確認 endpoint 不可達                       | 外部 probe 失敗且 agent 無 active endpoint           | UTC、tunnel identifier digest、probe status |
| Rotate the actually exposed demo account | 在確認為 loopback synthetic DB 後，以受控環境變數執行 demo bootstrap；不要把新值放進 command URL/argument | 舊 password `401`，新 password 可透過 JSON POST 登入 | account digest、UTC、status only            |
| Verify access/refresh revocation         | 使用事件前測試 session 呼叫受保護 API 與 refresh endpoint                                                 | 兩者均拒絕                                           | status codes、session count，不保存 token   |
| Review ngrok inspector/retention         | 在 account dashboard 檢查 capture、retention 與 deletion control                                          | 可控 capture 已刪；不可驗證副本標為 `UNVERIFIABLE`   | 去識別 screenshot/digest、UTC               |
| Clear browser/history sync               | 刪除該筆 local history/autofill，並處理已啟用的 history sync                                              | Back/history search 找不到事件 URL                   | browser profile label、UTC、result          |
| Clear controlled local artifacts         | 盤點 nginx/Next logs、HAR、trace、screenshots、shell history、clipboard history                           | synthetic sentinel scan 為 0                         | surface list、digest、cleaned flag          |
| Check credential reuse                   | 由 credential owner 查核其他環境/account/service                                                          | 無重用，或所有重用位置均已輪替                       | owner attestation、UTC、scope               |
| Restart only necessary tunnel            | 以新 process/session 重啟必要 LINE surface                                                                | 新 tunnel 不公開 management login，smoke pass        | tunnel digest、route probe matrix           |

## Current conclusion

Code-level containment is ready for validation. The exposed runtime credential and externally retained copies are **not yet proven rotated, revoked, or removed**. T008 remains blocked on authorized manual environment operations.
