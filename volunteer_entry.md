# 志工報名與 LINE LIFF 入口待完成任務

目前「志工報名」核心功能大多已有既有實作；真正待完成的工作主要集中在 **LIFF 入口整合、完整安全測試、文件與真機驗收**。

> 狀態說明：`部分完成` 代表已有程式碼，但尚未通過完整驗證；`未完成` 代表尚無足夠實作或證據。

| 優先級 | 待完成任務 | 目前狀態 | 完成條件 |
|---|---|---|---|
| P0 | 驗證 NEW → 送出報名 → PENDING 的完整入口流程 | 完成 | Vitest由exchange NEW進入真實報名元件、勾選同意、送出並顯示PENDING；browser／login redirect均移除ID token；390×844標題層級與按鈕間距已人工驗收 |
| P0 | 驗證管理員核准後建立 Membership／Grant | 完成 | 真實PostgreSQL已驗證並行／重複／stale／cross-org核准只投影exact organization的一組有限期VOLUNTEER Membership與Grant；雙Reviewer通過 |
| P0 | 驗證核准後第二次 LIFF 進入 | 部分完成 | exchange 回 ACTIVE、internal session 建立、token 先保存、導向 `/animal-confirmation`、`GET /v1/animals` 不再 401；Task 10已將animals／confirm／draft handoff統一改走`authFetch`，production volunteer allow仍待T008補齊`/auth/me` validity evidence |
| P0 | 補真實 HTTP exchange integration tests | 完成 | FastAPI HTTP 已覆蓋 NEW、PENDING、ACTIVE、SUSPENDED、401／403／503與response validation／commit failure |
| P0 | 補完整 authorization failure matrix | 完成 | invalid identity、entry狀態、disabled user/org、future／expired Membership、revoked／expired／missing Grant均fail-closed且非ACTIVE不建立credential |
| P0 | 補 no-partial-state transaction 測試 | 完成 | 真實AsyncSession已驗證Session／Refresh flush後service或commit失敗均rollback，獨立連線查新增row為0 |
| P0 | 補真實 PostgreSQL entry resolver 測試 | 完成 | migration後已驗證active／expired／revoked／wrong-purpose、exact-org RLS與Entry／Organization lock contention |
| P0 | 補多機構隔離 E2E | 未完成 | 同一 LINE user 在 org A 及 B 都有 membership 時，entry A 只建立 A context，entry B 只建立 B context |
| P0 | 增加志工 route/session boundary | 完成（T005/T006/T009/T010） | `/animal-confirmation` 載入動物前由共用boundary確認server-side session、role及active shelter context；受保護children只有allowed才mount |
| P0 | 實作 LIFF session 失效單次恢復 | 完成（Task 11，P1 review修正後） | 共用`authFetch`發出401 recovery event；epoch以`recovering → recovered → terminal`限制每個failure epoch最多一次exchange，late／post-recovery 401只導向terminal re-entry，不自動重試；保留opaque entry，local session仍由boundary導向`/login` |
| P0 | 防止失效 session 顯示 stale 動物資料 | 未完成 | session/context 失效時立即卸載受保護內容，不保留前一個 organization 的動物資料 |
| P0 | 顯示目前協助的收容所 | 未完成 | `/animal-confirmation` 及 `/care-report` 顯示後端確認的 organization 名稱 |
| P0 | 補 Rich Menu 實際 dry-run 與發布驗證 | 完成 | 缺變數時 fail-fast；resolved URL為HTTPS且指向`/volunteer-entry?entry=…`，不得含placeholder；safe publication tests與dry-run gate已通過 |
| P0 | 更新 LIFF／tunnel 開發文件 | 完成 | README、004 quickstart、contract index與controlled-line evidence template清楚記錄兩條HTTPS tunnel、LIFF Endpoint／`openid`、runtime environment、Rich Menu dry-run、Case A–D與credential遮罩規則 |
| P0 | 更新 004 契約文件 | 完成 | additive與canonical contract、runtime Pydantic及generated type的四狀態與401／403／503分類一致 |
| P0 | 執行 Alembic migration 實測 | 完成 | 真實PostgreSQL已反覆完成0030→0029→0030 round-trip並執行resolver／RLS tests |
| P0 | 完整 Python 品質門檻 | 完成（Task 17） | `verify_local.sh`與正確local PostgreSQL連線的`uv run pytest`均通過；full pytest `553 passed`、Ruff、format、mypy與Docker build通過 |
| P0 | 完整 frontend 品質門檻 | 完成（Task 17） | frontend unit／mobile／a11y tests、typecheck、format check、production build與P0 browser gates通過 |
| P0 | Playwright LIFF／onboarding E2E | 完成（local evidence；Task 14／17） | local fixture覆蓋login redirect、NEW、submit→PENDING、ACTIVE redirect、SUSPENDED、network failure、cross-organization與P0 responsive／keyboard matrix |
| P0 | 真機 LINE／LIFF 驗收 | BLOCKED／UNRUN（Task 18） | preflight：API `8001/healthz`通過；Web `3001`未啟動；`LIFF_ID`、LINE channel與public Web／API origins未設定；尚無真實手機Case A–D evidence |
| P1 | 志工報名 visual snapshots | 完成 | `/volunteer-entry` NEW及相關志工流程完成四個 viewport reviewer-approved visual baseline；對應 005 T108 |
| P1 | 實際使用者計時驗收 | BLOCKED／UNRUN（Task 20） | 需要至少 20 位首次志工及 3 位管理員批次操作的匿名驗收證據；目前沒有外部受控使用者與裝置資料，不以Playwright timing替代；對應 005 T110 |
| P0 | 同步 Spec Kit task ledger | 完成（Task 19） | Task 17 full gates與Task 18外部前置阻塞已同步；真機Case A–D保持`BLOCKED／UNRUN`，未以local evidence替代 |
| P0 | 最終 diff review 與 commit | 未完成 | 需在Task 17–19候選變更完成後重做independent review；依使用者授權再建立narrow commit |

## 建議下一步順序

1. **Task 8完成後進入Task 9 route gate／management request zero**
2. **完成志工 session boundary 與 401 單次 LIFF 恢復**
3. **補 Playwright 完整報名與多機構流程**
4. **更新契約、README、quickstart 及 task ledger**
5. **執行完整 Ruff、Pytest、frontend quality、build**
6. **以真機 LINE 完成 Case A–D 驗收**
7. **畫面確認後再 commit**

## 目前工作樹狀態

Task 2–7已提交。Task 8已完成LIFF init/login、identity exchange、四狀態、NEW→PENDING、ACTIVE canonical response validation與storage-before-replace、所有非ACTIVE／錯誤結果先清舊auth/context、partial storage keyed cleanup＋clear fallback、stale response isolation、safe retry／errors、legacy token URL scrub＋location fallback與fixed destination；已補Server runtime `LIFF_ID`、移除build-time API rewrite並以`/v1/[...path]` runtime proxy轉送至Cloud Run API URI，proxy具1MiB request／10MiB response cap、stream逐chunk且整體10秒deadline、禁止redirect、HTTPS origin限制、dot-segment拒絕、path encoding及安全502／503；避免loopback與空domain URL；390×844人工確認ERROR主標題層級與按鈕間距符合預期；Task 8 commit `a127a75` 的檔案目前均未出現在working tree dirty paths，後續未提交修改僅涉及volunteer access backend／contract/test檔案及本機文件／設計產物。Fresh verification（final rerun 2026-08-23T14:42:00Z UTC）：`npm test -- --run 'app/(volunteer)/volunteer-entry/page.test.tsx'`為43 passed、`npm run typecheck`通過、`npm run build`以Next.js 15.5.23成功；既有Task 8 backend 533與frontend 178為歷史staged evidence，未在本次重跑。Local Playwright E2E與本機技術gate已完成；受控真實LINE／LIFF Case A–D、T110人工計時與其他外部志工報名／LIFF驗收仍保持BLOCKED／UNRUN。

## 執行任務 Ledger

| 任務 | 狀態 | 範圍 | 驗證／證據 | Commit |
|---|---|---|---|---|
| Task 1：重整現有未提交變更與任務歸屬 | 完成 | 僅盤點與更新本文件，不修改 production code | staged boundary僅`A volunteer_entry.md`；`git diff --cached --check` exit 0；final independent review passed，無security／logic blocker | `docs: establish volunteer entry completion ledger` |
| Task 2A：同步既有 Membership generated contract drift | 完成 | 只同步canonical中既有`expected_access_version`與archive／restore request body；不包含LIFF變更 | generated SHA-256逐位元一致；`uv run pytest tests/contract/test_generated_contract_types.py -q`：2 passed；independent review passed | `chore(contracts): sync existing membership types` |
| Task 2：LIFF contract＋server security boundary | 完成（吸收Task 3–5） | canonical／004 contract、LINE verifier、entry expiry resolver、exact-org service、RLS與全域鎖序 | 獨立Task 2 snapshot `513 passed`、28檔Ruff、generated check、migration round-trip及雙Reviewer通過 | `0dc5fe6 feat(api): secure LIFF onboarding exchange` |
| Task 3：LINE ID Token security boundary | MERGED INTO TASK 2 | verifier、Login channel config、safe errors/logging | contract-only commit被Reviewer拒絕；為避免runtime drift，與Task 2安全切片原子交付 | 同Task 2 |
| Task 4：Entry expiration／PostgreSQL resolver | MERGED INTO TASK 2 | model、0030 migration、production resolver | 真實PostgreSQL已驗證valid／expired／wrong-purpose／revoked與公開organization context | 同Task 2 |
| Task 5：Exact-organization exchange states | MERGED INTO TASK 2 | session service、auth repository、entry adapter、combined user+organization scope | 原RLS blocker已以`app.auth_exact_org_id`、policy migration與真實A/B隔離測試修正 | 同Task 2 |
| Task 6：HTTP atomicity／isolation | 完成 | FastAPI四state／401／403／503、response-before-commit、commit／rollback failure、zero partial state與runtime matrix | fake與真實AsyncSession已驗證flush／commit／rollback failure；獨立連線查User／Organization／Session／Refresh新增為0；combined staged-only `529 passed`且雙Reviewer通過 | `test(api): verify LIFF exchange atomicity` |
| Task 7：Approval idempotency | 完成 | application→finite Membership→single Grant；並行／重複／stale／cross-org與batch replay | 真實PostgreSQL以`pg_blocking_pids`證明duplicate被application row lock阻擋後409；Membership／Grant各1；stale／cross-org為0；persisted succeeded batch item由新session replay且approval呼叫0次；focused `7 passed`、working `535 passed`、staged-only `532 passed`、Ruff 2檔與雙Reviewer通過；production無修改 | `test(volunteers): enforce idempotent approval membership grants` |
| Task 8：LIFF bootstrap／onboarding | 完成 | `/volunteer-entry` LIFF init/login/exchange、四狀態、NEW→PENDING、ACTIVE canonical validation／validated storage with keyed cleanup＋clear fallback、non-ACTIVE stale-auth cleanup、stale response isolation與fixed redirect；Server Component runtime讀`LIFF_ID`，`/v1/[...path]` runtime proxy讀`API_BASE_URL`並轉送Cloud Run API URI，1MiB request／10MiB response cap、stream逐chunk且整體10秒deadline、redirect拒絕、HTTPS origin限制、dot-segment拒絕與path encoding，移除build-time rewrite | 歷史證據：Security RED修正、final staged backend `533 passed`、frontend `178 passed`、雙Reviewer通過；fresh 2026-08-23T14:37:20Z UTC：`npm test -- --run 'app/(volunteer)/volunteer-entry/page.test.tsx'`：43 passed、`npm run typecheck`通過、`npm run build`成功（Next.js 15.5.23）；Task 8 allowlist目前無dirty path。真實LINE／LIFF Case A–D仍BLOCKED／UNRUN | `a127a75 feat(web): add LINE LIFF volunteer entry bootstrap` |
| Task 9～12：Volunteer route/session lifecycle | local technical slice完成；外部驗收另計 | T005 typed `AuthenticatedRouteContext`／`SessionSource`、LIFF transient entry reference與bounded recovery epoch storage、auth terminal source＋LIFF transient cleanup；entry reference強制32～512 URL-safe格式，recovery original path為strict volunteer allowlist/ID pattern；T006純函式`EffectiveRole`／route area／context-required／redirect／recovery finite-state decision matrix；T009繁中可及`ProtectedRouteState`，只有`allowed` render children，其他state不mount protected children，live region與interactive actions分離、shared 44px Button、context/access recovery actions完整；T010共用`AuthenticatedRouteBoundary`只依server `auth/me`＋`active-shelter-context` evidence推導role/context，volunteer allow fail-closed要求active-unexpired Membership＋matching active Grant，local／formal LIFF 401 recovery source分流、transient credential保留、stale loader epoch與storage fallback preservation；Task 11共用`authFetch`在401發出LIFF unauthorized event；recovery epoch以`recovering → exchanging → recovered → terminal`限制每個failure epoch最多一次exchange，terminal failure會將URL標記`recovery=terminal`以阻止reload自動重試，manual retry先建立新recovering epoch後才進入async LIFF流程；volunteer layout保留opaque entry，post-recovery／late 401只導向terminal re-entry；ACTIVE session建立後完成recovery state；Task 10將`app/(volunteer)/layout.tsx`接入共用AuthenticatedRouteBoundary（僅`/volunteer-entry`公開），`/v1/animals`、confirm、draft及care-report load/save handoff統一走`authFetch`，使用server session context而非client org授權；animal／draft 401立即清除受保護資料；authenticated VOLUNTEER所有management deep link固定導向`/animal-confirmation`；新增`/v1/auth/me` Membership／Grant validity projection與served schema；root `/`移入`app/(management)/page.tsx`並由management route group統一包裝；管理 header改用server-returned organization name，禁止client storage code作為label | T005 focused `10 passed`、T006 focused `20 passed`、T009 focused `10 passed`、T010 boundary/auth/route focused `40 passed`、Task 10 animal／draft boundary `7 passed`、Task 11 focused `66 passed`；fresh backend authentication／contract `16 passed`、route composition／shelter label／volunteer handoff 5 files／20 tests、frontend typecheck與production build通過；真實LINE／LIFF Case A–D與T110仍BLOCKED／UNRUN | 未commit |
| Task 13：Rich Menu safe publication | 完成 | env substitution、HTTPS、entry URL | safe publication unit tests與dry-run gate已通過；既有commit `f728f32` | `f728f32 fix(line): render safe volunteer Rich Menu URLs` |
| Task 14：Browser／LIFF route matrix | 完成 | Playwright onboarding與multi-organization route evidence | LIFF route matrix與cross-organization browser scenarios已通過；既有commit `f466ac3` | `f466ac3 fix(web): isolate volunteer recovery epochs` |
| Task 15：360px／keyboard／Axe／visual | 完成 | P0 responsive、keyboard、Axe及visual baseline；測試fixture改用`/volunteer-entry`主入口 | responsive／keyboard／Axe `61 passed`；visual `77 passed`；typecheck、Task 15 spec Prettier、`git diff --check`通過；使用者已明確接受目前visual baseline | `test(web): validate volunteer entry accessibility visuals` |
| Task 16：LIFF／tunnel／真機驗收文件 | 完成 | README、004 quickstart、contract index、controlled-line evidence template | 文件commands、paths與env names已對齊current code；`PYTHONPATH=.`修正entry script入口；`git diff --check`與documentation path review通過；尚未宣稱真機Case A–D完成 | `docs: add LIFF tunnel and phone acceptance guide` |
| Task 17：Full quality gates | 完成 | 完整Python／frontend／contract／Docker／P0 browser gate | `verify_local.sh`完整通過；full pytest `553 passed`；P0 `96 passed`；browser Axe `16 passed`；visual `83 passed`；Task 17 Dockerfile與StrictMode／fixture／visual timing修正已驗證 | 未commit |
| Task 18：Controlled LINE／LIFF真機Case A–D | BLOCKED／UNRUN | 真實LIFF ID、LINE Login channel、兩條HTTPS tunnel、受控帳號與手機操作 | preflight僅確認cloudflared／ngrok已安裝、API health通過；Web未啟動且runtime／public origins未設定；沒有外部PASS evidence | — |
| Task 19：Spec Kit ledger與完成報告同步 | 完成 | 同步Task 17 evidence、Task 18 blocker與後續commit／T110 boundaries | 本ledger已更新；`git diff --check`與documentation path review須於本次變更後fresh rerun | 未commit |
| Task 20：005 T110人工計時驗收 | BLOCKED／UNRUN | 至少20位首次志工與3位管理員的匿名操作時間證據 | 需外部受控使用者、裝置與匿名計時資料；目前無證據，不以Playwright timing替代 | — |

### Fresh Task 9–12 route/session verification

2026-08-23T15:04:38Z UTC：T005、T006、T009、T010、Task 11 的 client boundary／recovery／stale-state tests 9 files／73 tests 通過；新增 `/v1/auth/me` Membership／Grant validity projection、served `CurrentUserResponse` schema與matching organization regression，backend authentication／contract suite `16 passed`、generated contract check、Ruff／format、frontend typecheck與route tests通過。另完成 root route group composition、server-confirmed shelter label與volunteer animal／care handoff regression，5 files／20 tests通過，production build成功。Local Task 9–12 route/session slice完成；真實LINE／LIFF Case A–D與T110仍保持BLOCKED／UNRUN。

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
| Task 13 Rich Menu | `.env.example`、`scripts/sync_line_rich_menu.py`、`infra/local/line-rich-menu.yaml`、`infra/gce/line-rich-menu.yaml`、`tests/unit/test_sync_line_rich_menu.py` |

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
5. 現有候選實作跨 Task 2～5、8、13；Task 8／13仍須精確分離。Task 2 contract-only staged candidate被獨立Reviewer拒絕，因其會與舊runtime形成可部署的安全drift；Task 3～5因此吸收進Task 2，組成單一可部署後端安全垂直切片。
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
10. **跨任務hunk拆分**：`authentication.py`、`session_service.py`、`.env.example`、`test_authentication_contract.py`及generated OpenAPI跨多個任務；Task 2～5依Reviewer要求形成原子後端切片，但`.env.example`只可stage Login channel hunk，Task 8／13的URL與Rich Menu設定仍不得混入。

### Task 2 Contract Resolution

1. 有效LINE token＋有效entry回state-discriminated `200 LiffExchangeResponse`：NEW、PENDING、ACTIVE、SUSPENDED。
2. 只有ACTIVE schema要求並允許`access_token`、`refresh_token`、`expires_in`、`session_id`、`user_id`；其他state的schema禁止credential欄位。
3. 無效／過期／wrong-audience LINE token維持401；無效／撤銷／過期／wrong-purpose entry維持safe 403；schema／dependency錯誤分別為422／503。
4. `shelter_entry_reference`在canonical及004 additive contract統一為32～512字元；organization／role／user仍不接受client輸入。Pydantic runtime binding不得早於Task 5 exact-org service／RLS修正單獨部署。
5. 004 `spec.md`、`research.md`、`route-access.md`與T013／T015已同步四state語意；exchange只讀取005 Application／Membership／Grant，不管理其lifecycle。
6. TDD證據：第一次可執行RED揭露minLength=1、缺state response schemas／discriminator與缺generated state types；後續RED分別揭露route-specific error schema缺口、exact authentication scope缺口與舊GET verifier contract。runtime Pydantic、service、resolver與RLS已在同一切片GREEN。
7. 第一輪contract-only獨立審查未通過：一位Reviewer指出User／Organization停用語意歧義，另一位指出canonical先於runtime落地會形成高風險contract drift，且通用ErrorResponse可洩漏內部原因。修正後採固定safe 401／403 schema、User停用→SUSPENDED、Organization停用→entry safe 403，並合併Task 3～5。
8. 真實PostgreSQL證據：resolver只接受active、正確purpose、未過期entry並回安全organization公開欄位；exact scope只可見指定user＋organization的Organization、Membership與Application，跨organization UPDATE為0。
9. 第二輪修正後focused suite為`54 passed`；最新working-tree canonical `uv run pytest -q`為`508 passed in 22.29s`；generated check通過；26個staged Python檔Ruff check／format通過；migration `0030 → 0029 → 0030`成功且current為`0030_volunteer_entry_expiry (head)`。
10. 第一個staged-only snapshot（`strayhub-task2-index`）為`498 passed`，但已被第二輪Reviewer findings與後續修正取代，不得作為最終commit證據。
11. 第二輪獨立審查仍未通過，揭露並已以RED→GREEN修正：舊`/v1/line/bind`簽名回歸；exact RLS隱藏disabled Membership；ACTIVE只鎖Membership而未鎖實際Grant；resolver／DB例外落入500；文件宣告entry-first但runtime採identity-first。修正後保留獨立legacy bind flow、exact scope可讀inactive raw Membership、固定Membership→Grant雙鎖與三方關聯、safe dependency 503，並以identity-first避免未驗證caller探測entry。
12. 上述第二輪修正後證據仍須通過新的staged-only snapshot與最新雙Reviewer，通過前Task 2維持REVIEW PENDING且不得commit。
13. 最新staged-only snapshot（`strayhub-task2-final`）以`git checkout-index --all`匯出實際index，canonical pytest結果`505 passed in 33.66s`；未staged的frontend、Rich Menu與Task 6候選未參與此綠燈。
14. 第三輪Reviewer仍fail-closed，指出Entry／Organization／User未與Membership／Grant共同線性化的TOCTOU。修正後0030 resolver為`VOLATILE`並在同一transaction鎖定Entry→Organization，service再依序設定exact scope、鎖User、Membership、Grant後才建立credential；真實PostgreSQL lock-timeout tests證明entry revoke、organization disable與user disable在授權transaction結束前無法提交。最新focused suite為`58 passed`、canonical full suite為`512 passed in 22.46s`；generated check及26個staged Python檔Ruff check／format通過。前一staged-only證據再次失效，必須重建snapshot與Reviewer。
15. 第四個staged-only snapshot（`strayhub-task2-linearized`）以實際index執行canonical pytest，結果`509 passed in 32.52s`；最新Reviewer通過前仍不得commit。
16. 第四輪Review期間唯讀盤點發現既有管理撤銷與expiration worker採Grant-first；為避免exchange的反向鎖序形成deadlock，先以RED repository test確認後，把全域順序統一為Entry→Organization→User→Grant→Membership，並同步route-access／research。第四個snapshot與其Reviewer結果因此視為stale，必須以最新index重建。
17. 最新全域鎖序staged-only snapshot（`strayhub-task2-lockorder`）為`509 passed in 33.43s`；working-tree canonical為`512 passed in 22.35s`，26個staged Python檔Ruff通過。仍須最新雙Reviewer通過才可commit。
18. Stale第四輪Reviewer另揭露三個有效阻擋：Binding撤銷TOCTOU、舊status／submit／withdraw helper仍二元素解包四元素resolver、response驗證晚於commit且commit failure落入500。已以RED→GREEN新增Binding `FOR UPDATE`與真實撤銷lock contention、四元素helper回歸、HTTP validation-before-commit與safe rollback 503；Task 6 HTTP probe／真實PostgreSQL flush後rollback目前`10 passed`，最終full gates與最新Reviewer前仍不得commit。
19. Task 6再補真實PostgreSQL future／expired Membership與revoked／expired Grant runtime matrix，四案皆SUSPENDED且Session／Refresh實表新增為0；最新canonical full suite為`529 passed in 22.86s`，generated check與0030 migration round-trip通過。格式修正後仍須fresh Ruff、staged-only snapshot及最新雙Reviewer。
20. Final staged-only snapshot（`strayhub-task6-final`）以實際index執行canonical pytest，結果`526 passed in 33.04s`；32個staged Python檔Ruff check／format通過。最新雙Reviewer通過前Task 2與Task 6皆維持REVIEW PENDING。
21. 較早全域鎖序Reviewer結果雖對response validation與四元組helper已stale，但新揭露expiration JOIN的無限定`FOR UPDATE`會額外鎖User／Organization。RED SQL regression確認後已改為`FOR UPDATE OF volunteer_access_grants SKIP LOCKED`，使worker與管理撤銷及exchange一致採Grant→Membership，不提前反向鎖User／Organization；targeted expiration／lock suite為`6 passed`。前一snapshot與Reviewer再次失效。
22. Worker lock-scope修正後staged-only snapshot（`strayhub-task6-workerlock`）為`527 passed in 33.48s`；working-tree canonical為`530 passed in 23.01s`，33個staged Python檔Ruff check／format通過。最新雙Reviewer通過前仍不得commit。
23. 較早Task 6 Reviewer新增三項有效finding：rollback自身失敗會遮蔽safe 503、真實DB尚未走route commit failure、004誤把provider無法驗證列為401。RED確認rollback failure原為500後，route已用不可遮蔽的rollback guard固定回503；真實AsyncSession test在Session／Refresh已flush後由commit拋錯，確認route呼叫rollback且獨立連線查User／Organization／Session／Refresh皆0；004已將invalid／expired／audience mismatch保留401並把provider／dependency failure歸503。最新targeted HTTP／isolation suite為`8 passed`，前一snapshot再次失效。
24. Rollback guard與真實commit-failure修正後，canonical full suite為`532 passed in 21.83s`；final staged-only snapshot（`strayhub-task6-rollbackguard`）為`529 passed in 34.35s`，33個staged Python檔Ruff、generated check與migration round-trip全綠。最新雙Reviewer通過前仍不得commit。
