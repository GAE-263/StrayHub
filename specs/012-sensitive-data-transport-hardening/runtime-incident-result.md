# Runtime Incident Result — Phase A

Recorded at: `2026-09-05T08:19:06Z`

Overall status: **COMPLETE WITH DOCUMENTED RESIDUAL RISK**

本文件不保存原始 credential、token 或完整敏感 URL。授權操作者 `JS-LOCAL-01` 已對 loopback
synthetic demo 環境完成 credential rotation、session invalidation、登入驗證、瀏覽器與可控本機
artifact 清查。原 ngrok agent/Inspector session 已不存在，因此 historical request capture 與第三方
retention 無法回溯證明，明確保留為 `UNVERIFIABLE`，不宣稱所有遠端副本均已刪除。

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

## Manual runtime evidence

| Action / surface | Result | Evidence |
| --- | --- | --- |
| Synthetic account scope | PASS | Five known `demo-*` identities rotated together; sorted account-scope digest `f634556b65719b4f877dbdf63c5c65504de20e4f658787cbbc81e4173318cc52` |
| Rotation | PASS | Completed `2026-09-05T07:23:29Z`; local database/storage guard and demo bootstrap passed |
| Login transport | PASS | Old password `401`; rotated password `200`; JSON `POST`; empty login query string |
| Session invalidation | PASS | Active sessions `0`; active refresh/session records `0` after rotation |
| Browser cleanup | PASS | Local history, autofill and Back navigation checked; sensitive URL absent; history sync not enabled |
| Old tunnel exposure | PASS | Helper-owned tunnel stopped and old endpoint confirmed unreachable |
| ngrok local Inspector | UNVERIFIABLE | Checked `2026-09-05T08:01:46Z`; tunnel and request APIs both returned connection status `000`; historical session cannot be recovered locally |
| ngrok remote retention | UNVERIFIABLE | Historical third-party retention cannot be proven after the original session ended |
| Controlled local artifacts | PASS | Fixed-string repository scan returned zero findings; empty-findings digest `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Logging defenses | PASS | Static policy check passed; runtime sentinel reported zero raw occurrences on all controllable local surfaces |
| Credential reuse | PASS | Credential owner attested `NOT_REUSED`; the value copied into chat is treated as unrecoverable and was superseded by rotation |

Operator-held evidence manifest SHA-256:
`ec8202b66617c11260d238a9e22665a355ce4f54729f7f25457970ebd790ac79`.
The manifest references local, secret-free evidence files; raw credentials and complete sensitive URLs are not
part of the evidence package or repository.

## Residual risk

- The original ngrok Inspector session was unavailable at review time, so request-capture absence cannot be
  proven retrospectively.
- Third-party retention and inaccessible copies remain `UNVERIFIABLE`.
- These limitations do not restore validity to the exposed credential: it was rotated, old sessions were
  invalidated, and the old password is rejected.

## Current conclusion

T008 operational containment is complete with the residual risks above. This closes the credential/session
incident action but does not constitute 013 public activation, public-host smoke evidence, or an external
rollback drill.
