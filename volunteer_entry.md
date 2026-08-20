# 志工報名與 LINE LIFF 入口待完成任務

目前「志工報名」核心功能大多已有既有實作；真正待完成的工作主要集中在 **LIFF 入口整合、完整安全測試、文件與真機驗收**。

> 狀態說明：`部分完成` 代表已有程式碼，但尚未通過完整驗證；`未完成` 代表尚無足夠實作或證據。

| 優先級 | 待完成任務 | 目前狀態 | 完成條件 |
|---|---|---|---|
| P0 | 驗證 NEW → 送出報名 → PENDING 的完整入口流程 | 部分完成 | 從 `/volunteer-entry` 進入報名、送出申請、畫面轉為 PENDING，且不把 ID token 放入 URL |
| P0 | 驗證管理員核准後建立 Membership／Grant | 既有實作、待回歸驗證 | 核准後建立 exact organization 的 active `VOLUNTEER` membership 與有效 grant；重複核准不產生 duplicate |
| P0 | 驗證核准後第二次 LIFF 進入 | 部分完成 | exchange 回 ACTIVE、internal session 建立、token 先保存、導向 `/animal-confirmation`、`GET /v1/animals` 不再 401 |
| P0 | 補真實 HTTP exchange integration tests | 未完成 | 透過 FastAPI HTTP 測試 NEW、PENDING、ACTIVE、SUSPENDED 及錯誤 response contract，而不只測 service |
| P0 | 補完整 authorization failure matrix | 未完成 | malformed／revoked／expired／wrong-purpose entry、wrong audience、disabled user/org、expired membership、missing grant 全部不建立 session |
| P0 | 補 no-partial-state transaction 測試 | 未完成 | exchange 任一驗證或 DB 步驟失敗後，新增 Session、Refresh Token 及 Active Context 數量均為 0 |
| P0 | 補真實 PostgreSQL entry resolver 測試 | 未完成 | migration 後實際驗證 active、expired、revoked、wrong-purpose 與 cross-organization reference |
| P0 | 補多機構隔離 E2E | 未完成 | 同一 LINE user 在 org A 及 B 都有 membership 時，entry A 只建立 A context，entry B 只建立 B context |
| P0 | 增加志工 route/session boundary | 未完成 | `/animal-confirmation` 載入動物前先確認 server-side session、role 及 active shelter context |
| P0 | 實作 LIFF session 失效單次恢復 | 未完成 | 受保護 API 回 401 時，每個事件最多重做一次 LIFF exchange；失敗或第二次 401 立即停止 |
| P0 | 防止失效 session 顯示 stale 動物資料 | 未完成 | session/context 失效時立即卸載受保護內容，不保留前一個 organization 的動物資料 |
| P0 | 顯示目前協助的收容所 | 未完成 | `/animal-confirmation` 及 `/care-report` 顯示後端確認的 organization 名稱 |
| P0 | 補 Rich Menu 實際 dry-run 與發布驗證 | 部分完成 | 缺變數時 fail-fast；resolved URL 必須是 HTTPS 且指向 `/volunteer-entry?entry=…`，不得含 placeholder |
| P0 | 更新 LIFF／tunnel 開發文件 | 未完成 | README 或 004 quickstart 清楚記錄 Web/API tunnel、LIFF Endpoint、environment 及手機測試步驟 |
| P0 | 更新 004 契約文件 | 未完成 | `contracts/liff-exchange.openapi.yaml` 與目前 NEW／PENDING／ACTIVE／SUSPENDED response 一致 |
| P0 | 執行 Alembic migration 實測 | 未完成 | 真實 PostgreSQL 升級到新增 entry expiration migration，確認既有 reference backfill 與 resolver 正常 |
| P0 | 完整 Python 品質門檻 | 未完成 | `uv run ruff check .`、`uv run ruff format --check .`、`uv run pytest` 全部通過 |
| P0 | 完整 frontend 品質門檻 | 未完成 | frontend unit tests、typecheck、format check、production build 全部通過 |
| P0 | Playwright LIFF／onboarding E2E | 未完成 | 覆蓋 login redirect、NEW、submit→PENDING、ACTIVE redirect、SUSPENDED、network failure 與跨機構拒絕 |
| P0 | 360px、keyboard 與 axe 驗證 | 未完成 | 志工報名及各入口狀態在手機、鍵盤、螢幕閱讀器下可操作，Axe critical／serious 為 0 |
| P0 | 真機 LINE／LIFF 驗收 | 未完成，需要外部設定 | 使用真實 LIFF ID、LINE Login Channel、HTTPS tunnel 及測試 LINE 帳號完成 Case A–D |
| P1 | 志工報名 visual snapshots | 未完成 | 對 onboarding states 完成 reviewer-approved visual baseline；對應 005 T108 |
| P1 | 實際使用者計時驗收 | 未完成 | 至少 20 位首次志工及 3 位管理員批次操作留下匿名驗收證據；對應 005 T110 |
| P0 | 同步 Spec Kit task ledger | 未完成 | 依實際程式碼與測試證據更新 `specs/004-volunteer-entry-route-isolation/tasks.md`；目前 T001–T056 仍全部未勾選 |
| P0 | 最終 diff review 與 commit | 未完成 | 修正完整 gate 發現的問題、獨立 review 最終 diff；使用者完成畫面驗收後再建立 commit |

## 建議下一步順序

1. **先補後端 HTTP／transaction／PostgreSQL 安全測試**
2. **完成志工 session boundary 與 401 單次 LIFF 恢復**
3. **補 Playwright 完整報名與多機構流程**
4. **更新契約、README、quickstart 及 task ledger**
5. **執行完整 Ruff、Pytest、frontend quality、build**
6. **以真機 LINE 完成 Case A–D 驗收**
7. **畫面確認後再 commit**

## 目前工作樹狀態

目前工作樹仍有未提交修改；最近一次 `git diff --check` 沒有回報 whitespace 錯誤，但尚未完成完整測試，因此目前不應將志工報名／LIFF 功能標記為完成。

## 執行任務 Ledger

| 任務 | 狀態 | 範圍 | 驗證／證據 | Commit |
|---|---|---|---|---|
| Task 1：重整現有未提交變更與任務歸屬 | 完成 | 僅盤點與更新本文件，不修改 production code | staged boundary僅`A volunteer_entry.md`；`git diff --cached --check` exit 0；final independent review passed，無security／logic blocker | `docs: establish volunteer entry completion ledger` |
| Task 2A：同步既有 Membership generated contract drift | 完成 | 只同步canonical中既有`expected_access_version`與archive／restore request body；不包含LIFF變更 | generated SHA-256逐位元一致；`uv run pytest tests/contract/test_generated_contract_types.py -q`：2 passed；independent review passed | `chore(contracts): sync existing membership types` |
| Task 2：固定 LIFF exchange contract | 待執行（BLOCKING DRIFT） | canonical／004 spec、route-access、research、OpenAPI、Pydantic、generated types | 必須先解決200 state vs safe 403、entry minLength及ACTIVE credential discriminator | — |
| Task 3：LINE ID Token security boundary | 待執行 | verifier、Login channel config、safe errors/logging | 尚未取得完整 security suite 證據 | — |
| Task 4：Entry expiration／PostgreSQL resolver | 待執行 | model、0030 migration、production resolver | 尚未在真實 PostgreSQL 執行 | — |
| Task 5：Exact-organization exchange states | 待執行（RLS BLOCKER） | session service、auth repository、entry adapter、combined user+organization scope | 候選 fake tests無法發現organization scope被清空；必須用真實PostgreSQL驗證 | — |
| Task 6：HTTP atomicity／isolation | 待執行 | FastAPI HTTP、rollback、zero partial state | 專屬 security／isolation tests 尚未建立 | — |
| Task 7：Approval idempotency | 待執行 | application→membership→grant | 既有實作待補並行／重複核准回歸 | — |
| Task 8：LIFF bootstrap／onboarding | 待執行 | `/volunteer-entry`、session storage、NEW→PENDING | 候選 Vitest 已存在，尚未人工畫面驗收 | — |
| Task 9～12：Volunteer route/session lifecycle | 待執行 | route gate、animals handoff、401 recovery、shelter label | 尚未實作完整 boundary／single-flight recovery | — |
| Task 13：Rich Menu safe publication | 待執行 | env substitution、HTTPS、entry URL | 候選 unit test 已存在，尚未完成 dry-run gate | — |
| Task 14～15：Browser／a11y／visual | 待執行 | Playwright、多機構、360px、keyboard、Axe | 尚未建立 LIFF route matrix；snapshot 未經人工核准 | — |
| Task 16～20：Docs／full gates／controlled LINE／completion | 待執行 | tunnel、真機、完整 gate、Spec Kit、人工計時 | 需要後續技術與外部驗收證據 | — |

## 2026-08-20 Task 1 Reconciliation

### Working-tree 檔案歸屬

| 任務 | 候選檔案 |
|---|---|
| Task 1 Ledger | `volunteer_entry.md` |
| Task 2 Contract | `services/api/app/api/authentication.py`、`specs/001-volunteer-care-report/contracts/openapi.yaml`、`packages/contracts/src/openapi.ts`、`tests/contract/test_authentication_contract.py` |
| Task 3 LINE verifier/config | `.env.example`、`services/api/app/config/settings.py`、`services/api/app/infrastructure/line/identity_verification_adapter.py`、`services/api/app/api/authentication.py`、`services/api/app/api/volunteer_access.py`、`tests/unit/test_line_identity_verification.py` |
| Task 4 Entry expiration | `services/api/app/persistence/models/volunteer_access.py`、`services/api/migrations/versions/0030_volunteer_entry_reference_expiration.py`、`tests/security/test_volunteer_entry_reference_expiration.py` |
| Task 5 Exchange states | `services/api/app/application/authentication/session_service.py`、`services/api/app/persistence/repositories/authentication_repository.py`、`services/api/app/infrastructure/line/entry_reference_adapter.py`、`tests/unit/test_liff_exchange_states.py`、`tests/integration/test_authentication_session.py` |
| Task 8 Frontend bootstrap | `apps/web/package.json`、`apps/web/package-lock.json`、`apps/web/app/(volunteer)/volunteer-entry/`、`apps/web/app/(volunteer-onboarding)/volunteer-application/page.tsx` |
| Task 13 Rich Menu | `.env.example`、`scripts/sync_line_rich_menu.py`、`infra/local/line-rich-menu.yaml`、`infra/gcp-demo/line-rich-menu.yaml`、`tests/unit/test_sync_line_rich_menu.py` |

### Reconciliation 發現

1. `apps/web/package.json` 與 `apps/web/package-lock.json` 在盤點開始前已被 staged；已於 Task 1 使用 `git restore --staged apps/web/package.json apps/web/package-lock.json` 移除其 staged 狀態。
2. `specs/004-volunteer-entry-route-isolation/contracts/liff-exchange.openapi.yaml` 尚未隨 canonical response 更新，屬 Task 2 blocking contract drift。
3. 既有 E2E／visual／responsive／a11y fixtures 仍使用 `/volunteer-application?...&id_token=...`：
   - `apps/web/e2e/volunteer-access-approval.spec.ts`
   - `apps/web/e2e/p0-visual.spec.ts`
   - `apps/web/e2e/p0-responsive.spec.ts`
   - `apps/web/e2e/p0-a11y.spec.ts`
   - `docs/frontend_phase_e_summary.md`
   這些不是本次已修改檔案，但會在 Task 14～16 移除舊 token-in-URL fixture／文件契約。
4. 靜態搜尋未發現本次候選 source 新增 `console.log`／logger／`print` 輸出完整 ID token、access token 或 LINE user ID；搜尋命中的 credential字串均為測試fixture或既有local placeholder，仍需在各任務 staged diff reviewer再次確認。
5. 現有候選實作跨 Task 2、3、4、5、8、13，不可作為單一feature commit；必須依上表逐任務驗證並以精確路徑stage。
6. `.hermes/plans/2026-08-20_202122-volunteer-entry-completion.md` 是本機執行計畫；Task 1 不將 `.hermes/` 納入 staged paths。
7. Task 1 不宣稱任何 production 行為完成；其唯一交付是可重複使用的任務歸屬與commit邊界。

### Task 1 Staged Boundary Evidence

快照時間：`2026-08-20 20:31:11 CST`

```text
$ git diff --cached --name-status
A\tvolunteer_entry.md

$ git diff --cached --check
# no output; exit 0
```

第一次獨立審查因輸入只允許檢視 `git diff --cached -- volunteer_entry.md`，無法自行證明完整 staged path 集合，依 fail-closed 規則判定未通過。此結果不計為production implementation失敗；補上完整 staged name-status證據並整合候選實作審查結果後，final independent review已通過，沒有security concern或logic error。

### Candidate Implementation Reviewer Findings

下列結果來自對全部未提交候選實作的唯讀審查；它們是後續任務的阻擋條件，不影響Task 1文件commit，但不得在對應任務中忽略：

1. **Task 2 normative conflict**：004 additive contract目前只允許授權成功回`200 AuthResponse`，`route-access.md`把missing binding／pending／inactive organization／ineffective membership定義為safe `403`；候選canonical/service則回`200 NEW|PENDING|SUSPENDED`。Task 2必須同步檢查並對齊004 `spec.md`、`research.md`、`route-access.md`及兩份OpenAPI，不可只改canonical contract。
2. **Task 2 request length drift**：004要求`entry reference minLength=32`，候選Pydantic／canonical為1，tests使用短字串。正式contract採高熵opaque reference，runtime與測試必須一致使用至少32字元。
3. **Task 2 response discriminator缺口**：候選單一response schema把session credential全部設為optional，無法保證ACTIVE必須有session、NEW／PENDING／SUSPENDED禁止credential；需改為state-discriminated schema。
4. **Generated contract drift**：`packages/contracts/src/openapi.ts`除了LIFF變更，還混入membership archive／restore／version的既有generated drift。Task 2前需確認是否建立獨立前置contract-sync commit，不能誤標為LIFF變更。
5. **Task 5 RLS blocking bug**：entry resolver先設定organization scope，但`set_authentication_user_scope()`會清空`app.current_org_id`；之後才查受RLS保護的grant/application，真實PostgreSQL可能把合法ACTIVE判成SUSPENDED、PENDING判成NEW。Task 5必須建立combined exact user＋organization scope並以真實DB測試。
6. **Task 9／12 stale tenant data risk**：`/animal-confirmation`目前mount後立即讀animals，401只顯示錯誤、不清除既有candidates。route boundary完成前不得提交frontend handoff為完整可用。
7. **Task 8／13／16 entry URL exposure**：004要求entry位於URL以保留organization context，但該reference會進browser／LINE／proxy history。首次解析後應評估以`history.replaceState`移除query，並在部署文件要求edge/access log query redaction；entry仍不得被視為authorization credential。
8. **Refresh token storage trade-off**：目前沿用004既定`sessionStorage`相容方案；同源XSS可讀refresh token。此次不擴張為cookie auth migration，但後續frontend review必須確認CSP／第三方script限制並把cookie migration列為明確的安全改善，而不是宣稱風險不存在。
9. **Task 4 rollout risk**：候選migration把既有reference回填為`issued_at + 90 days`，超過90天的入口會在升級時立即失效。migration驗收前必須先盤點／輪替舊reference並同步Rich Menu，記錄fail-closed rollout步驟。
10. **跨任務hunk拆分**：`authentication.py`、`session_service.py`、`.env.example`、`test_authentication_contract.py`及generated OpenAPI跨多個任務；後續不得依整檔stage，必須以任務邊界拆分hunks或先建立明確前置commit。
