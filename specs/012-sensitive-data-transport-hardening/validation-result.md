# Sensitive Data Transport Hardening — Phase C Validation Result

Recorded at: `2026-09-04T12:30:39Z`

Phase B baseline commit: `c400b8f fix(security): harden sensitive URL and logging policies`

Overall code status: **READY FOR PHASE C REVIEW**
External runtime status: **MANUAL ACTION REQUIRED**

本文件不保存 raw credential、capability、sentinel 或完整敏感 URL。Phase C 僅處理 T023～T034；
T008 的實際 credential rotation、browser history、ngrok inspector 與 remote retention 仍未假裝完成。

## 1. T023 route decision

`contracts/line-tunnel-allowlist.yaml` 是 authoritative method/path allowlist。每一條 route 都有 owner、
reason、consumer evidence 與 test。

- `/care-report`: `ALLOW`。LIFF session recovery、volunteer route boundary、draft read/update consumer
  與 E2E evidence 均存在。
- `/assigned-care/{occurrenceId}`: `DENY`。只有直接 page/E2E，沒有 LINE/LIFF link producer。
- Remote management demo: `NOT IMPLEMENTED — local-only management`。沒有產品 owner 提出的公開需求，
  不建立 LINE tunnel 例外。
- `/login`、management、platform governance、organization administration、docs/debug、unknown route:
  default deny。

## 2. Default-deny gateway

Local LINE helpers 現在都只把 ngrok 指向同一個 nginx gateway。FastAPI 與 Next.js 保持 loopback
upstream；gateway 只轉送 registry 內的 method/path。`/_next/static/` 限制為靜態 asset pattern，
沒有 `/`、`/v1/**` 或 `/_next/**` catch-all。

Synthetic nginx runtime result:

- allow matrix: PASS
- deny matrix: PASS
- wrong-method matrix: PASS
- query preservation on approved Class B / ordinary query: PASS
- denied request reaching API/Web upstream: 0
- webhook missing/invalid signature boundary: `401`
- existing real signature verification tests: PASS

## 3. Static policy and CI

`scripts/check_sensitive_transport_policy.py` 檢查：

- unsafe credential form / hydration contract
- production hard-coded password
- Class A 或未登錄 sensitive URL candidate
- sensitive nginx log variables
- public tunnel catch-all / direct Next tunnel
- allowlist 與 nginx route marker drift

Negative fixtures 各自只觸發預期 rule；positive Class B/C/D 與 ordinary query 不誤報。Checker 已接入
`scripts/verify_local.sh` 與現有 CI Python job，且在 migration/test 前執行。CI 明確安裝 nginx，runtime
gateway test 不允許 silent skip。

## 4. Cross-layer synthetic sentinel

Command:

```bash
uv run python scripts/verify_sensitive_transport_runtime.py
```

Result: `PASS_WITH_MANUAL_EXTERNAL`

| Surface                     | Result | Raw/encoded occurrence |
| --------------------------- | ------ | ---------------------: |
| Browser request artifact    | PASS   |                      0 |
| Public gateway artifact     | PASS   |                      0 |
| nginx artifact              | PASS   |                      0 |
| Next artifact               | PASS   |                      0 |
| Uvicorn/application logging | PASS   |                      0 |
| Audit before/after JSON     | PASS   |                      0 |
| Test artifact               | PASS   |                      0 |

Temporary artifacts were deleted (`cleanup_status=cleaned`). Class B forwarding and ordinary-query
observability negative controls both passed. The runner's leak-injection test fails as expected without echoing
the sentinel.

`ngrok inspector and remote retention` remains `MANUAL_ACTION_REQUIRED`; no network-dependent CI claim was
made.

## 5. Automated validation

| Command / suite                                                              | Result                                                                         |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Phase C static/registry/log/audit/nginx/capability/isolation targeted pytest | PASS; 92 cases after the nginx assertion fix and Class A query-reader fixture  |
| nginx runtime + webhook signature targeted pytest                            | PASS; 17/17                                                                    |
| repository quality contract after removing silent nginx skip                 | PASS; 3/3                                                                      |
| full Python `uv run pytest`                                                  | PASS; 1523 passed, 2 documented opt-in skips                                   |
| targeted login/animal/LIFF Vitest                                            | PASS; 48/48                                                                    |
| full Web Vitest                                                              | PASS; 463/463                                                                  |
| Web TypeScript                                                               | PASS                                                                           |
| Web Prettier                                                                 | PASS                                                                           |
| Web production build                                                         | PASS                                                                           |
| generated API contracts                                                      | PASS                                                                           |
| login + animal-confirmation + LIFF Playwright                                | PASS; 24 unaffected cases plus corrected deterministic invalid-target case 1/1 |
| targeted Ruff check/format for Phase C Python                                | PASS                                                                           |
| full `ruff check .`                                                          | PASS                                                                           |
| full `ruff format --check .`                                                 | BASELINE FAIL; three pre-existing animal-photo files listed below              |
| sensitive transport CLI against repository                                   | PASS                                                                           |
| shell syntax for both helpers and local verifier                             | PASS                                                                           |
| `git diff --check`                                                           | PASS                                                                           |

The full Ruff format baseline failures are outside Phase C and were not modified:

- `services/api/app/application/management_animal_service.py`
- `tests/integration/test_management_animal_photo.py`
- `tests/unit/test_line_message_presenter.py`

The first Playwright attempt reused an unrelated stale process on port 3001 and encountered a missing Next
chunk. Final verification used the repository's isolated LIFF E2E dist directory on port 3002, left the existing
process untouched, and removed generated test artifacts afterward.

## 6. Manual smoke / external boundaries

| Item                                                | Status                 | Reason / required evidence                                                                             |
| --------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------ |
| Local real nginx routing                            | PASS                   | Actual temporary nginx process and upstream recorders were used.                                       |
| Real LINE client / LIFF app                         | BLOCKED                | Requires operator-controlled LINE account and tunnel. Preserve timestamp and route/status matrix only. |
| Real ngrok allow/deny probes                        | BLOCKED                | Requires authorized tunnel. Verify login/management/docs/unknown deny and approved LINE paths only.    |
| ngrok inspector / remote retention scan             | MANUAL ACTION REQUIRED | Confirm raw synthetic sentinel count and retention/deletion status without storing the value.          |
| T008 credential rotation/revocation/history cleanup | MANUAL ACTION REQUIRED | Follow `runtime-incident-result.md` and incident runbook.                                              |

## 7. Scope and deferred review

- No tunnel allowlist was added for management, platform, docs/debug or `/assigned-care/{id}`.
- No MFA, OAuth/cookie migration, refresh-token redesign, global CSP, zero-trust, CDN/storage redesign,
  QR/LIFF TTL redesign or capability-lifecycle redesign was implemented.
- Phase B remains the independent commit `c400b8f`; Phase C changes are currently uncommitted.
- No production behavior was changed to satisfy the LIFF Playwright fixture. The test now mocks the public
  organization directory and distinguishes it from protected APIs.

## 8. Conclusion

Phase C repository implementation and automated validation are complete. The public LINE/LIFF boundary is
default-deny, ordinary query observability remains available, registered Class B capabilities still traverse
approved routes, and tenant/signature tests remain enforced.

The change is ready for review as a separate Phase C commit. It must not be described as fully incident-closed
until T008 and the external LINE/ngrok checks are completed by an authorized operator. The pre-existing Ruff
format baseline should be resolved in its owning animal-photo change, not folded silently into Phase C.
