# Tasks: 敏感資料傳輸與紀錄防護

**Input**: `/specs/012-sensitive-data-transport-hardening/` 下的 `spec.md`、`plan.md`、
`security-analysis.md`、`contracts/security-boundary.md`、`quickstart.md`

**Tests**: 本功能明確要求 TDD、Playwright、contract、security、isolation 與 runtime smoke；每個
production change 都先有會失敗的 regression test，且不得用真實 credential。

**Organization**: 保留既定 Phase A/B/C；在每個 phase 內依 spec User Story 分組，使每個故事可
獨立驗收。Checklist ID 使用 Spec Kit 的 `Txxx`，標題保留原分析的 `SEC-A01`～`SEC-C04`
追溯碼；拆分是為了讓 test、implementation 與人工 incident action 可分派及單獨驗證。

## Checklist format

`- [ ] Txxx [P?] [USx] 動作與精確檔案路徑`

- `[P]` 僅表示不會與未完成 dependency 寫同一檔案，可由不同工程師平行處理。
- 「獨立 commit：否」的 test-first task 應與其 implementation task形成同一可通過commit，不得把
  failing test單獨合入。
- 所有路徑均相對repository root。

---

## Phase 1: Setup

**Purpose**: 本專案、測試框架與feature artifacts皆已存在，不新增package、資料表或service layer。

本phase無implementation task；執行者先確認 `.specify/feature.json` 指向本feature，並從乾淨的
synthetic/test環境開始。不得讀取或輸出production secret。

---

## Phase 2: Foundational

**Purpose**: Phase A的login source containment不依賴registry或logging重構，沒有共同blocking
implementation。這是刻意設計：P1封堵可以立即開始。

**Checkpoint**: 可直接執行Phase A；Phase B registry工作也可由另一位工程師平行開始。

---

## Phase 3: Phase A — Immediate containment / User Story 1 (Priority: P1) 🎯 MVP

**Goal**: 正常、失敗、Enter、no-JS及pre-hydration登入都不把username/password放進URL；舊
credential URL不被採信並以replace semantics清理；已曝光demo credential完成受控處置。

**Independent Test**: 只完成本phase後，依`quickstart.md` login matrix使用synthetic sentinel驗證
address bar、history、network target及login response均無credential；正常流程仍為JSON
`POST /v1/auth/login`。Incident演練另以人工checklist記錄，不依賴Phase B/C。

### SEC-A01 / SEC-A03 — Login native fallback與基礎回歸

- [x] T001 [P] [US1] 先在 `apps/web/app/login/page.test.tsx` 新增SSR/form contract failing tests，驗證form明確為`method="post" action="/login"`、初始submit disabled、username/password初值為空且autocomplete語意保留
  - **Goal**: deterministic捕捉native GET與hard-coded prefill回歸。
  - **Files**: 新增`apps/web/app/login/page.test.tsx`；必要時只讀`apps/web/components/ui/input.tsx`與`button.tsx`。
  - **Dependencies**: 無；test first。
  - **Implementation notes**: 測rendered DOM/SSR-visible attributes，不以字串grep取代DOM assertion；不得把可登入runtime的demo password寫入fixture。
  - **Verification**: `npm --prefix apps/web test -- app/login/page.test.tsx`應先因現況失敗。
  - **Acceptance**: 測試能分別指出missing method/action、enabled pre-hydration submit及prefilled credential。
  - **Regression risks**: jsdom不等同真正browser；後續T005/T006補runtime coverage。
  - **Parallel**: 可與T003、T009平行。
  - **Independent commit**: 否；與T002一起形成passing commit。

- [x] T002 [US1] 在 `apps/web/app/login/page.tsx` 實作SEC-A01 fail-closed form與hydration gate，移除hard-coded username/password但保持JSON `POST /v1/auth/login`
  - **Goal**: browser native fallback永不形成credential query，hydrated登入行為不變。
  - **Files**: `apps/web/app/login/page.tsx`。
  - **Dependencies**: T001。
  - **Implementation notes**: 加`method="post" action="/login"`；SSR/client初始`hydrated=false`並disable submit，effect後才開啟；username/password state為空；保留`name`與autocomplete供password manager；`onSubmit`仍`preventDefault()`後JSON POST，不改API/session/context selection。
  - **Verification**: T001測試、`npm --prefix apps/web run typecheck`。
  - **Acceptance**: rendered form符合contract；bundle無`demo-furkids-admin`或`local-only-password`；成功/失敗請求仍只打`/v1/auth/login` JSON POST。
  - **Regression risks**: hydration flag未解除、Enter或password manager失效、多organization flow改變。
  - **Parallel**: 否，寫login component。
  - **Independent commit**: 是，與T001組成`SEC-A01` commit。

### SEC-A02 — Legacy credential URL canonicalization

- [x] T003 [P] [US1] 先在 `apps/web/app/login/page.test.tsx` 與 `apps/web/e2e/login-url-safety.spec.ts` 新增legacy Class A query failing tests
  - **Goal**: 定義SSR/client清理時機、replace history、error handling與不反射credential的契約。
  - **Files**: `apps/web/app/login/page.test.tsx`、新增`apps/web/e2e/login-url-safety.spec.ts`。
  - **Dependencies**: 無；可先以現況頁面建立失敗證據。
  - **Implementation notes**: 測`username`、`password`、`temporary_password`、`access_token`、`refresh_token`、`id_token`與`authorization`的大小寫/重複/percent-encoded query；合法非credential query不可被任意採信為登入資料；assert沒有UI/error/console reflection。
  - **Verification**: targeted Vitest與`npm --prefix apps/web run test:e2e -- e2e/login-url-safety.spec.ts`應先失敗。
  - **Acceptance**: 每個Class A case都有clean final URL與history assertion，failure message不印sentinel原值。
  - **Regression risks**: Playwright history assertion跨browser差異；deterministic component/server contract為主、runtime為輔。
  - **Parallel**: 可與T001、T009平行。
  - **Independent commit**: 否；與T004一起形成passing commit。

- [x] T004 [US1] 將login server/client邊界拆至 `apps/web/app/login/page.tsx` 與 `apps/web/app/login/LoginClient.tsx`，在最早可行時點canonicalize Class A query並套用login-specific no-store/no-referrer policy
  - **Goal**: 舊`/login?...credential...`不被採信，最終只留下`/login`且不新增敏感history entry。
  - **Files**: `apps/web/app/login/page.tsx`、新增`apps/web/app/login/LoginClient.tsx`；若現有Next header pattern可重用，限縮修改`apps/web/next.config.ts`，否則以login route response/page metadata完成。
  - **Dependencies**: T002、T003。
  - **Implementation notes**: server最早辨識forbidden key並導向clean URL，client以`history.replaceState`作fallback；不得把query值傳入client props、error或log；使用replace而非push；避免redirect loop；normal login component由T002移入client檔且契約不變。
  - **Verification**: T001/T003、frontend typecheck、manual inspect response headers。
  - **Acceptance**: direct legacy URL不觸發login request、不反射值、最終URL乾淨、Back不回到credential URL；`Referrer-Policy: no-referrer`與`Cache-Control: no-store`有contract test。
  - **Regression risks**: server redirect history語意、合法route state誤刪、Next client/server import錯誤。
  - **Parallel**: 否，依賴login component拆分。
  - **Independent commit**: 是，與T003組成`SEC-A02` commit。

### SEC-A03 — 完整browser/network matrix

- [x] T005 [US1] 更新 `apps/web/e2e/login-home.spec.ts` 並完成 `apps/web/e2e/login-url-safety.spec.ts` 的成功、失敗、click、Enter與network assertions
  - **Goal**: E2E不再依賴預填帳密，並證明credential只在request body。
  - **Files**: `apps/web/e2e/login-home.spec.ts`、`apps/web/e2e/login-url-safety.spec.ts`、必要時`apps/web/e2e/fixtures.ts`。
  - **Dependencies**: T002、T004。
  - **Implementation notes**: 每次明確fill synthetic username/password；攔截request並assert method=`POST`、`Content-Type=application/json`、body欄位、URL無credential；涵蓋401/API timeout、多organization與platform-only redirect。
  - **Verification**: `npm --prefix apps/web run test:e2e -- e2e/login-home.spec.ts e2e/login-url-safety.spec.ts`。
  - **Acceptance**: 所列情境全部pass，任何恢復prefill、GET或credential query都會fail。
  - **Regression risks**: 過度耦合mock payload；不得降低既有viewport與context coverage。
  - **Parallel**: 否，與T006共用新spec，序列執行避免衝突。
  - **Independent commit**: 是，可作`SEC-A03 browser matrix` commit。

- [x] T006 [US1] 在 `apps/web/e2e/login-url-safety.spec.ts` 與 `apps/web/playwright.config.ts`（僅如必要）加入no-JS/native fallback及deterministic hydration-race驗證
  - **Goal**: 覆蓋真正造成事件的JS disabled與handler尚未掛載視窗。
  - **Files**: `apps/web/e2e/login-url-safety.spec.ts`；只有需獨立project時才改`apps/web/playwright.config.ts`。
  - **Dependencies**: T005。
  - **Implementation notes**: 使用`browser.newContext({javaScriptEnabled:false})`驗證disabled/safe POST；hydration race以route阻擋`/_next/**` script或受控fixture，禁止使用不穩定sleep；若browser無法穩定觸發，以T001的SSR contract為release gate並在測試註明runtime限制。
  - **Verification**: Chromium targeted E2E至少連跑3次；`git diff --check`。
  - **Acceptance**: no-JS與pre-hydration click/Enter均無credential URL；測試無flaky timeout依賴。
  - **Regression risks**: Next asset interception誤擋document、跨browser差異。
  - **Parallel**: 否，依賴T005測試結構。
  - **Independent commit**: 是，可與T005同PR但獨立commit。

### SEC-A04 — Incident containment（文件與人工操作分離）

- [x] T007 [P] [US1] 在 `docs/security/credential-url-incident-runbook.md` 建立30分鐘incident runbook並由 `specs/012-sensitive-data-transport-hardening/quickstart.md` 連結
  - **Goal**: 將stop、rotation、session invalidation、log cleanup與不可回收副本風險變成可重複流程。
  - **Files**: 新增`docs/security/credential-url-incident-runbook.md`、`specs/012-sensitive-data-transport-hardening/quickstart.md`。
  - **Dependencies**: 無；內容依security-analysis既定範圍。
  - **Implementation notes**: 每一步標`AUTOMATED`或`MANUAL`；禁止runbook要求把raw credential貼進issue/log；含ngrok inspector、browser/history sync、credential reuse check、tunnel restart及evidence digest格式。
  - **Verification**: 文件review、連結檢查、`git diff --check`。
  - **Acceptance**: 操作者可辨識target/environment、回復與不可回收限制；不含真實secret。
  - **Regression risks**: 文件命令與實際helper drift；T033最終同步。
  - **Parallel**: 可與T001-T006及T009平行。
  - **Independent commit**: 是，documentation-only commit。

- [x] T008 [US1] 依 `docs/security/credential-url-incident-runbook.md` 對已曝光synthetic demo credential執行受控人工處置，並將去識別結果記於 `specs/012-sensitive-data-transport-hardening/runtime-incident-result.md`（2026-09-05 完成 rotation、session invalidation、browser/local artifact review；ngrok historical capture/retention 如實保留為 `UNVERIFIABLE` residual risk）
  - **Goal**: 讓已曝光credential與active sessions實際失效，而非只修UI。
  - **Files**: 新增`specs/012-sensitive-data-transport-hardening/runtime-incident-result.md`；runtime database/tunnel/log是人工外部狀態，不得把新secret寫入repo。
  - **Dependencies**: T002、T004、T007已ready/deployed至該demo環境後執行。
  - **Implementation notes**: **MANUAL** stop helper-owned tunnel、確認精確synthetic user、生成/輸入非共用新值、撤銷其全部SessionRecord、檢查refresh不可用、清理可控local logs/HAR/trace、review ngrok retention、清browser/history sync、確認無其他環境重用、再啟動必要tunnel；production-like data一律禁止。
  - **Verification**: 舊password login=401、舊access/refresh session失效、新credential不出現在URL/log；結果只記timestamp、surface、digest與PASS/FAIL。
  - **Acceptance**: checklist全完成或明確BLOCKED，無法回收的第三方副本如實記錄；不宣稱完全刪除。
  - **Regression risks**: 誤選帳號/DB、seed重跑恢復舊值、漏撤銷session；必須雙重environment/username guard。
  - **Parallel**: 否，需等待source fix ready；可與Phase B code work平行但不得在舊UI下重開management tunnel。
  - **Independent commit**: 否；operational action不commit secret，僅結果文件可另commit。

**Phase A Checkpoint**: US1可獨立驗收；credential不再由login source進URL，legacy URL會清理，incident
狀態有明確證據。Phase B/C未完成前仍不得把management route放回public tunnel。

---

## Phase 4: Phase B — Transport policy / User Story 2 (Priority: P1)

**Goal**: 以A/B/C/D registry區分禁止秘密、受限capability、公開identifier及一般query；保留
LIFF/QR/photo/signed URL合法功能與原TTL/tenant policy。

**Independent Test**: Registry validator能拒絕未知sensitive route+key，接受已登錄Class B與Class
C/D；photo、QR、entry、signed URL各自通過expiry/revocation/replay/tenant/resource matrix。

### SEC-B01 — Machine-readable Sensitive URL Registry

- [x] T009 [P] [US2] 建立 `specs/012-sensitive-data-transport-hardening/contracts/sensitive-url-registry.yaml` 作唯一Sensitive URL Registry source of truth
  - **Goal**: 完整登錄A/B/C/D與例外owner/review規則，不建立通用token service。
  - **Files**: 新增`specs/012-sensitive-data-transport-hardening/contracts/sensitive-url-registry.yaml`、更新`contracts/security-boundary.md`指向它。
  - **Dependencies**: 無；可與Phase A平行。
  - **Implementation notes**: schema至少含route pattern、parameter/class、purpose、owner module、TTL、reuse/revoke、tenant/resource binding、logging、Referer、exposure、scrub、mitigation、tests、review trigger；登錄photo 300s、entry 90d、QR無固定TTL但可撤銷、signed URL 300s；application-status URL token標`not_found`而非例外。
  - **Verification**: YAML parser可讀、人工對照security-analysis inventory。
  - **Acceptance**: 每個Class B欄位完整；Class C明示不授權；Class D保留observability；沒有「所有token禁用」規則。
  - **Regression risks**: 文件與code drift、route regex過寬。
  - **Parallel**: 可與T001-T007平行。
  - **Independent commit**: 是，policy-only commit。

- [x] T010 [US2] 先在 `tests/security/test_sensitive_url_registry.py` 建立registry schema/completeness failing tests與精準ignore機制
  - **Goal**: CI可部分驗證新增route/query，且避免文件/fixture中的`password`字樣造成naive grep false positive。
  - **Files**: 新增`tests/security/test_sensitive_url_registry.py`、必要時新增`tests/security/fixtures/sensitive_url_scan_ignores.yaml`。
  - **Dependencies**: T009。
  - **Implementation notes**: 解析YAML後掃限定production source boundaries的URL construction/query readers；ignore必含exact path+rule+reason+owner，不允許global wildcard；failure顯示route/key/file與修復說明，不印值。
  - **Verification**: `uv run pytest tests/security/test_sensitive_url_registry.py`；用temporary mutation證明未知Class A/B pattern會fail、合法fixture會pass。
  - **Acceptance**: schema、duplicate route/key、缺owner/TTL/revocation/log policy與unregistered candidate均被捕捉；ordinary query不誤報。
  - **Regression risks**: TypeScript/Python語法掃描不完整；明確標示partial static guarantee並由runtime tests補足。
  - **Parallel**: 否，依賴registry shape。
  - **Independent commit**: 是，可與T009同PR但獨立passing commit。

### SEC-B04 — Capability lifecycle證據與最小修正

- [x] T011 [P] [US2] 補強photo與staff signed URL tests於 `tests/integration/test_public_adoption_photo.py`、`tests/isolation/test_timeline_and_media_isolation.py`、`tests/security/test_observability_logging.py`
  - **Goal**: 鎖定既有300秒TTL、purpose/org/animal/object scope及response URL不被log。
  - **Files**: 上述三個既有test files；不改TTL。
  - **Dependencies**: T009。
  - **Implementation notes**: photo測valid/expired/wrong purpose/changed object/cross-org/replay window；signed URL測role/current tenant/foreign tenant/300s metadata及sentinel log；若現有測試已覆蓋，以缺口增量為限。
  - **Verification**: 三個targeted pytest files。
  - **Acceptance**: registry宣告與runtime contract一致；任何TTL或binding意外變動會fail。
  - **Regression risks**: 時間測試flaky；使用clock/monkeypatch，不sleep 300秒。
  - **Parallel**: 可與T012、T014、T016平行。
  - **Independent commit**: 是，test-only passing commit可獨立提交。

- [x] T012 [P] [US2] 補強QR與LIFF entry lifecycle tests於 `tests/unit/test_qr_management.py`、`tests/isolation/test_liff_entry_isolation.py`、`apps/web/e2e/animal-confirmation-qr.spec.ts`、`apps/web/app/(volunteer)/volunteer-entry/page.test.tsx`
  - **Goal**: 證明QR可撤銷/重生/重放至撤銷、entry 90天/可撤銷/可rotate且兩者tenant-bound，並驗證URL scrub不破壞LIFF recovery。
  - **Files**: 指定四個test files；必要時`tests/unit/test_qr_deep_link.py`。
  - **Dependencies**: T009。
  - **Implementation notes**: 不新增QR TTL；entry expiry以migration/model既有90天；測cross-org 404/fail-closed、legacy id_token scrub、entry必要recovery後清除時點與Referer contract。
  - **Verification**: targeted pytest、Vitest、Playwright specs。
  - **Acceptance**: registry與現行行為一致；若發現discrepancy先記入`security-analysis.md`，不得自行改lifetime。
  - **Regression risks**: 過早清entry造成redirect loop；此task先寫證據，不直接改流程。
  - **Parallel**: 可與T011、T014、T016平行。
  - **Independent commit**: 是，test-only passing commit可獨立提交。

- [x] T013 [US2] 僅在T011/T012證明scrub/log lifecycle與spec不一致時，於 `apps/web/app/(volunteer)/volunteer-entry/VolunteerEntryClient.tsx`、`liffUrl.ts`、`VolunteerApplicationClient.tsx`、`apps/web/app/(volunteer)/animal-confirmation/page.tsx` 做最小修正（N/A：既有capture/recovery後replace生命週期符合contract；route-specific Referrer-Policy缺口已記錄為discrepancy，未在本task重設計）
  - **Goal**: Class B只在必要流程階段存在於URL，且不改TTL/授權模型。
  - **Files**: 列出的四個frontend lifecycle files及T012 tests；未發現差異時以N/A evidence關閉task、不製造無效code change。
  - **Dependencies**: T011、T012。
  - **Implementation notes**: QR維持capture即replace；entry保留至exchange/recovery完成再replace；`organization_id`只作hint；不得把token移到另一個URL/hash或local persistent storage。
  - **Verification**: T012 suite與existing LIFF state matrix。
  - **Acceptance**: retry/redirect仍正常，消費後URL乾淨，cross-tenant policy不降低；TTL完全不變。
  - **Regression risks**: LIFF登入循環、失去target、跨tab recovery race。
  - **Parallel**: 否，依賴lifecycle evidence。
  - **Independent commit**: 是，若有production change必須連同tests提交；N/A則不commit。

### SEC-B05 — CLI與demo credential輸出安全

- [x] T014 [P] [US2] 先在 `tests/contract/test_volunteer_entry_reference_cli.py` 與 `tests/contract/test_local_product_quality_contract.py` 建立CLI/default-output failing tests
  - **Goal**: raw entry reference與runtime login credential不會因default/CI output被保存。
  - **Files**: 新增`tests/contract/test_volunteer_entry_reference_cli.py`、更新`tests/contract/test_local_product_quality_contract.py`。
  - **Dependencies**: T009。
  - **Implementation notes**: 測non-TTY/default mode不輸出raw value、explicit reveal才允許一次、error/stderr不回顯；文件/isolated tests中的synthetic字串用精確ignore，不全域禁止`password`。
  - **Verification**: targeted pytest；sentinel只在in-memory assertion，不寫artifact。
  - **Acceptance**: 現有一次性CLI default raw JSON行為會先使測試失敗，且failure不印sentinel。
  - **Regression risks**: subprocess/TTY模擬跨平台差異。
  - **Parallel**: 可與T011/T012/T016平行。
  - **Independent commit**: 否；與T015一起形成passing commit。

- [x] T015 [US2] 在 `scripts/issue_volunteer_entry_reference.py`、`scripts/demo.sh`、`scripts/demo-line.sh` 移除default raw credential輸出並提供明確interactive/explicit reveal流程
  - **Goal**: 保留必要一次性發行能力，降低terminal/CI capture。
  - **Files**: 三個scripts、`README.md`與`docs/demo/data-workflows.md`中對應操作段落、T014 tests。
  - **Dependencies**: T014。
  - **Implementation notes**: raw reference只在explicit flag+interactive確認輸出一次；metadata走safe output；public demo password由environment/ephemeral bootstrap提供，不能換成另一個共同hard-coded值；不得source `.env`或echo LINE secrets。
  - **Verification**: T014 tests、shell syntax、existinglocal helper contracts。
  - **Acceptance**: default output無raw entry/password/token；人工流程仍能取得一次性reference；error path安全。
  - **Regression risks**: 現有操作文件失效、automation依賴JSON shape；需migration note。
  - **Parallel**: 否，依賴T014。
  - **Independent commit**: 是，`SEC-B05` commit。

**US2 Checkpoint**: Registry為唯一policy source；Class B功能與現行TTL保持，Class C/D不被誤封鎖。

---

## Phase 5: Phase B — Logging hardening / User Story 3 (Priority: P1)

**Goal**: nginx、Uvicorn、application/error與audit層不保存Class A/B原值，同時保留method、path、
status、bytes、latency與一般query診斷能力。

**Independent Test**: 使用不同synthetic sentinel注入query、Referer、Authorization、nested/repeated/
encoded structured data與exception，各受檢log/audit raw sentinel次數為0，ordinary query仍可見。

### SEC-B02 — nginx sensitive-route safe logging

- [x] T016 [P] [US3] 先擴充 `tests/contract/test_line_local_helper.py`、`tests/contract/test_gce_production_nginx_contract.py`、`tests/contract/test_gce_tls_edge_contract.py` 定義三套nginx sensitive-route log contract
  - **Goal**: 在修改config前鎖定safe variables、實際route group及ordinary query例外。
  - **Files**: 三個指定contract test files。
  - **Dependencies**: T009提供route classification。
  - **Implementation notes**: sensitive group至少`/login`、`/v1/auth/login|refresh|liff/exchange`、`/volunteer-entry`、`/volunteer-application`、`/animal-confirmation`、兩個public photo routes；assert safe format只有method `$uri` protocol/status/bytes/request_time及既有request ID（若有），禁止`$request`/`$request_uri`/`$args`/`$http_referer`；standard format仍可服務search/page/date。
  - **Verification**: 三個targeted pytest files先對現況失敗。
  - **Acceptance**: local template、edge與GCE production config缺任一route或出現unsafe variable都fail；HTTP redirect server也受檢。
  - **Regression risks**: regex matching順序與nginx map語意被test過度簡化。
  - **Parallel**: 可與T011/T012/T014/T018平行。
  - **Independent commit**: 否；與T017形成passing commit。

- [x] T017 [US3] 在 `infra/local/nginx/line-local.conf.template`、`infra/edge-nginx/strayhub.enadv.quest.conf`、`infra/gce/nginx/strayhub.conf` 實作query-free/Referer-free sensitive route log map
  - **Goal**: 所有部署/本機入口對相同敏感route產生最小但可診斷的access log。
  - **Files**: 三個nginx configs、T016 tests。
  - **Dependencies**: T016。
  - **Implementation notes**: 沿用現有photo capability map/format擴充，不全域關閉access log；HTTP與HTTPS server一致；若無現成request ID不在本task新增logging architecture，只保留現有欄位。
  - **Verification**: T016、可用環境下`nginx -t`、synthetic query/Referer local smoke。
  - **Acceptance**: sensitive log無query/Referer/body，普通`/v1/animals/search?query=...`仍由standard format記錄；status/bytes/latency保留。
  - **Regression risks**: path map漏斜線/動態segment、redirect server仍記完整request。
  - **Parallel**: 否，三config需由同一owner保持一致。
  - **Independent commit**: 是，`SEC-B02` commit。

### SEC-B03 — Application、exception與audit defense-in-depth

- [x] T018 [P] [US3] 先擴充 `tests/security/test_observability_logging.py` 覆蓋application logger、exception、Authorization、nested/repeated/encoded URL與key variants
  - **Goal**: 證明不只`uvicorn.access`有redaction，並防止formatter結構被破壞。
  - **Files**: `tests/security/test_observability_logging.py`。
  - **Dependencies**: T009。
  - **Implementation notes**: cases含`password`/`temporary-password`/mixed case、Bearer、`id_token`/entry/signed_url、dict/list/repeated key、percent-encoded query與nested URL；ordinary message/query必須保留；assert failure不回顯raw sentinel。
  - **Verification**: targeted pytest先對未受保護raw logger/encoding case失敗。
  - **Acceptance**: access與application formatter皆有positive/negative assertions。
  - **Regression risks**: regex-based測試誤把安全一般文字遮罩。
  - **Parallel**: 可與T016、T020平行。
  - **Independent commit**: 否；與T019形成passing commit。

- [x] T019 [US3] 在 `services/api/app/observability/logging.py`、`services/api/app/main.py` 及直接使用raw logger的API module套用既有最小redaction hook
  - **Goal**: Uvicorn、application與exception log共享敏感結果，不重建logging architecture。
  - **Files**: `services/api/app/observability/logging.py`、`services/api/app/main.py`、確認需要時限縮修改`services/api/app/api/line_webhook.py`與`management_animals.py`改用`get_logger`。
  - **Dependencies**: T018。
  - **Implementation notes**: 保留Uvicorn AccessFormatter tuple；對URL query做key-aware decode/redact後安全重建或整query省略；structured `extra`遞迴處理；不得log raw body/header；避免root logger全域副作用。
  - **Verification**: T018、existing LINE/photo logging tests、`uv run ruff check`/format check相關files。
  - **Acceptance**: 所有sentinel raw值為0、`[REDACTED]`可辨識、ordinary query/event/status保留。
  - **Regression risks**: double-format、exception stack消失、過度遮罩、logger filter未掛至worker startup。
  - **Parallel**: 否，依賴T018。
  - **Independent commit**: 是，application logging commit。

- [x] T020 [P] [US3] 先在 `tests/security/test_audit_sensitive_data.py` 建立AuditService defense-in-depth failing tests
  - **Goal**: 將audit視為最後防線，但不把現況誤報成已存在資料外洩。
  - **Files**: 新增`tests/security/test_audit_sensitive_data.py`。
  - **Dependencies**: T009。
  - **Implementation notes**: 對before/after/reason測nested dict/list、repeated keys、Authorization、encoded/nested URL、password/token variants；safe action/result/resource/fingerprint保留；測不修改caller object。
  - **Verification**: targeted pytest先對現有直接serializer失敗。
  - **Acceptance**: 測試明確描述preventive control，不聲稱既有rows已污染。
  - **Regression risks**: 使用fake session時未覆蓋實際JSON serialization；至少一個DB-backed test。
  - **Parallel**: 可與T018平行。
  - **Independent commit**: 否；與T021形成passing commit。

- [x] T021 [US3] 在 `services/api/app/application/audit_service.py` 與必要的 `services/api/app/persistence/database/base.py` 加入central sensitive-field redaction/rejection
  - **Goal**: caller誤傳credential時audit DB不持久化Class A/B原值。
  - **Files**: 兩個指定files、T020 tests；優先重用`services/api/app/observability/logging.py`中無logging side effect的mask helper，若產生循環依賴則抽至既有security utility boundary而非新service。
  - **Dependencies**: T020；若重用T019 helper則亦依賴T019。
  - **Implementation notes**: mask keys與URL value、遞迴copy；安全事件只存type/result/time/tenant與不可逆fingerprint；禁止raw request body/full Authorization；不修改audit schema/migration。
  - **Verification**: T020、既有audit contract/integration tests、Ruff/Pytest gate。
  - **Acceptance**: raw sentinel不在persisted JSON/reason；既有audit查詢與tenant scope保持。
  - **Regression risks**: 合法欄位名稱含token被過遮罩、循環import、audit diff可讀性下降。
  - **Parallel**: 否，依賴T020/T019選型。
  - **Independent commit**: 是，audit hardening commit。

- [x] T022 [US3] 在 `tests/security/test_next_proxy_sensitive_logging.py` 與 `apps/web/app/v1/[...path]/route.ts` 驗證Next proxy不自訂輸出raw URL/body，僅在runtime證明有自訂leak時加入最小safe diagnostic hook（以等價 `apps/web/app/v1/[...path]/route.test.ts` 驗證；repository proxy無custom leak，production route不需修改）
  - **Goal**: 關閉Next application-layer缺口但不破壞合法query forwarding。
  - **Files**: 新增`tests/security/test_next_proxy_sensitive_logging.py`或等價Web test；production change僅限`apps/web/app/v1/[...path]/route.ts`且須有實證。
  - **Dependencies**: T009、T018；nginx protection不作為Next安全假設。
  - **Implementation notes**: query forwarding本身保留，Class A由source/registry阻止；capture stdout/stderr與error path sentinel；若Next framework內建dev log不可hook，記錄runtime limitation並以tunnel/nginx source prevention補償，不大改logger。
  - **Verification**: targeted Node/Pytest harness、frontend typecheck。
  - **Acceptance**: repository自訂Next code不印raw target/body；ordinary query仍傳upstream；任何N/A有evidence。
  - **Regression risks**: 測到framework外部行為卻用脆弱monkeypatch、意外停止query forwarding。
  - **Parallel**: 否，需沿用T018 classification behavior。
  - **Independent commit**: 是（若有production change）；N/A evidence可併入US3驗收commit。

**US3 Checkpoint**: 每一logging layer都有可執行sentinel證據，nginx未全域關閉，一般query仍可診斷。

---

## Phase 6: Phase C — Exposure boundary / User Story 4 (Priority: P2)

**Goal**: `test_line_local.sh`與`demo-line.sh`預設透過同一default-deny policy只公開必要LINE/LIFF
route；login、management、platform、docs/debug/internal及未知route均不可由Internet到達。

**Independent Test**: 啟動synthetic local stack/tunnel，allow matrix全部成功、deny matrix全部拒絕且不
洩漏resource存在性；LINE webhook仍要求有效signature。

### SEC-C01 — Route evidence與default-deny tunnel

- [x] T023 [P] [US4] 從實際Web/API consumers產生並review `specs/012-sensitive-data-transport-hardening/contracts/line-tunnel-allowlist.yaml`，以vertical-flow證據決定`/care-report`與`/assigned-care/{id}`
  - **Goal**: 在改routing前取得最小且可追溯allowlist，不猜測open question。
  - **Files**: 新增`specs/012-sensitive-data-transport-hardening/contracts/line-tunnel-allowlist.yaml`、更新`contracts/security-boundary.md`。
  - **Dependencies**: T009 registry；可在Phase B logging implementation期間進行。
  - **Implementation notes**: 列method+exact/pattern path+consumer+reason+test；候選含webhook、LIFF pages/exchange/application、QR resolve/candidate-org、active context、animal search/confirm、handoff/report、photo與`/_next` assets；對care-report/assigned-care先跑現有LINE/LIFF tests與source trace，沒有證據即保持deny並記decision。
  - **Verification**: reviewer逐route對照frontend fetch/router與FastAPI decorator；禁止`/**`或`/v1/**` allow。
  - **Acceptance**: 每條route有owner/evidence；兩個open routes都有ALLOW/DENY結論或明確BLOCKED，不留implicit catch-all。
  - **Regression risks**: dynamic Next asset/runtime endpoint遺漏、method未限制。
  - **Parallel**: 可與T016-T022平行。
  - **Independent commit**: 是，route-policy commit。

- [x] T024 [US4] 先擴充 `tests/contract/test_line_local_helper.py` 建立default-deny config failing tests與完整allow/deny matrix
  - **Goal**: 保證local gateway不再把`/`與`/v1/` catch-all pass至app。
  - **Files**: `tests/contract/test_line_local_helper.py`；fixture讀T023 YAML。
  - **Dependencies**: T023。
  - **Implementation notes**: assert webhook method/path、LIFF/API/photo/assets allow；assert`/login`、management pages、`/v1/management/**`、platform governance、`/docs`、`/openapi.json`、unknown deny；拒絕response不揭露帳號/tenant/resource。
  - **Verification**: targeted pytest先對現有catch-all失敗。
  - **Acceptance**: 任一重新加入catch-all或漏deny route會fail；signature verification source contract保留。
  - **Regression risks**: 純字串測試無法證明nginx location precedence；T027補runtime。
  - **Parallel**: 否，依賴route policy。
  - **Independent commit**: 否；與T025形成passing commit。

- [x] T025 [US4] 在 `infra/local/nginx/line-local.conf.template` 實作method/path default-deny allowlist並保留必要Next assets與WebSocket只在local dev
  - **Goal**: 讓ngrok指向的單一gateway只轉送T023核准surface。
  - **Files**: local nginx template、T024 tests。
  - **Dependencies**: T017避免logging回歸、T024。
  - **Implementation notes**: 未匹配route直接404/最小403；API/Web分開exact/regex locations；不使用`location /`或`location ^~ /v1/` pass-through；webhook仍由FastAPI驗signature；HMR只在helper必要模式且不能開management route。
  - **Verification**: T024、`nginx -t`、`scripts/test_line_local.sh --no-tunnel` local matrix。
  - **Acceptance**: allowlist可用、denylist不可達、unknown default deny；safe logging仍通過T016。
  - **Regression risks**: Next RSC/static asset路徑、POST/OPTIONS method、location precedence。
  - **Parallel**: 否，與T017同檔需在其後。
  - **Independent commit**: 是，gateway allowlist commit。

- [x] T026 [US4] 修改 `scripts/demo-line.sh` 與 `scripts/test_line_local.sh` 共享T025 local nginx gateway，不再讓ngrok直接指向Next或不同catch-all路徑
  - **Goal**: 防止修好一個helper、另一個仍公開整站。
  - **Files**: 兩個scripts、`tests/contract/test_line_local_helper.py`、必要時`tests/contract/test_local_product_quality_contract.py`。
  - **Dependencies**: T025、T015避免credential output回歸。
  - **Implementation notes**: single ngrok addr必須是allowlist gateway；保持owned PID/cleanup、real LINE env guards、no wildcard CORS、no secret echo；啟動輸出只列safe public endpoints。
  - **Verification**: shell syntax、contract tests、兩helper的`--no-tunnel`/print mode。
  - **Acceptance**: 兩helper不存在direct Next tunnel或API/Web catch-all；stop只終止owned process。
  - **Regression risks**: port ownership、startup ordering、LIFF endpoint設定與Next allowed origin。
  - **Parallel**: 否，依賴gateway。
  - **Independent commit**: 是，helper convergence commit。

- [x] T027 [US4] 在 `tests/e2e/test_local_line_tunnel_boundary.py` 建立synthetic runtime allow/deny與LINE vertical smoke
  - **Goal**: 用實際nginx routing證明contract，不要求CI連真實ngrok帳戶。
  - **Files**: 新增`tests/e2e/test_local_line_tunnel_boundary.py`、必要fixture限`tests/e2e/`。
  - **Dependencies**: T026。
  - **Implementation notes**: local gateway測method/path/status；webhook無/錯signature仍401、有效synthetic signature依既有fixture；LIFF/QR/photo/report allow依T023；login/management/platform/docs/unknown deny；如可控真ngrok smoke只作人工quickstart，不成為一般CI必要網路依賴。
  - **Verification**: targeted pytest與既有`test_local_line_bot_vertical_flow.py`。
  - **Acceptance**: allow成功率100%、deny成功率100%、未弱化signature/tenant checks。
  - **Regression risks**: local services/ports造成flaky；使用existing guarded bootstrap/skip policy，不任意連production-like DB。
  - **Parallel**: 否，runtime驗收在implementation後。
  - **Independent commit**: 是，runtime boundary test commit。

### SEC-C02 — Explicit remote management demo（非預設）

- [x] T028 [US4] 僅在產品owner確認保留遠端management demo時，於 `scripts/demo.sh` 與 `docs/demo/remote-management.md` 加入獨立explicit opt-in、synthetic guard及ephemeral credential/session revoke lifecycle
  - **Goal**: 滿足spec US4第二情境，但不成為LINE demo預設例外。
  - **Files**: `scripts/demo.sh`、新增`docs/demo/remote-management.md`、`tests/contract/test_local_product_quality_contract.py`。
  - **Dependencies**: T007、T015、T026；需要owner decision。
  - **Implementation notes**: default off；只接受verified synthetic DB；啟動時random short-lived credential、明顯banner/expiry，停止時password/session失效；若owner決定不保留，記`NOT IMPLEMENTED — local-only management`並更新spec acceptance disposition。
  - **Verification**: default mode management deny；opt-in synthetic smoke；stop後old credential/session fail。
  - **Acceptance**: 無任何fixed public-demo credential；沒有silent opt-in；N/A decision有owner/date。
  - **Regression risks**: cleanup中斷、credential被stdout捕捉、誤連正式DB；需fail-closed guards。
  - **Parallel**: 否，依賴default tunnel完成。
  - **Independent commit**: 是（若實作）；decision-only文件可獨立commit。

**US4 Checkpoint**: public LINE/LIFF tunnel default deny；必要route由evidence核准，management不再意外暴露。

---

## Phase 7: Phase C — Regression prevention / User Story 5 (Priority: P2)

**Goal**: 新增form、URL builder、capability、logger或tunnel route時，CI提供精準、安全且可修復的
失敗訊息；測試不因naive grep誤報文件與synthetic fixture。

**Independent Test**: 在temporary fixture中分別加入named password GET form、Class A URL builder、
未登錄Class B、unsafe nginx variable及tunnel catch-all，guardrail逐一fail；合法Class B/C/D全部pass。

### SEC-C03 — Scoped static checks與cross-layer sentinel

- [x] T029 [P] [US5] 在 `tests/security/test_sensitive_transport_static_policy.py` 建立scoped static guard failing fixtures
  - **Goal**: 定義login/form、URL construction、hard-coded runtime demo password、nginx與tunnel drift的精準規則。
  - **Files**: 新增`tests/security/test_sensitive_transport_static_policy.py`、新增`tests/security/fixtures/static-policy/`中的positive/negative小fixture。
  - **Dependencies**: T009/T010 registry schema、T023 tunnel policy。
  - **Implementation notes**: scope只掃production source與指定configs；解析form/URL construction上下文而非全文搜尋；docs/test fixture預設不掃，例外須exact path+reason+owner；failure顯示rule/file/remediation，不顯示secret value。
  - **Verification**: targeted pytest；每個negative fixture必須只觸發預期rule。
  - **Acceptance**: 五類回歸皆fail，ordinary query、registry文字與isolated synthetic tests不誤報。
  - **Regression risks**: parser過度簡化、source formatting改變；測fixture鎖定行為而非行號。
  - **Parallel**: 可與T032/T033平行，但依賴registry/tunnel policy文件。
  - **Independent commit**: 是，static policy tests commit。

- [x] T030 [US5] 將T010/T029 validator實作整理為 `scripts/check_sensitive_transport_policy.py`，提供deterministic CLI與remediation output
  - **Goal**: 本機與CI共用同一檢查，不複製規則。
  - **Files**: 新增`scripts/check_sensitive_transport_policy.py`、更新T010/T029 tests。
  - **Dependencies**: T010、T029。
  - **Implementation notes**: standard library/YAML現有dependency優先，不新增重型parser；接受explicit root/fixture參數供test；exit code非零但不輸出matched raw value；Class B由route+key registry判斷，Class C/D不阻擋。
  - **Verification**: script對repo pass、對negative fixtures fail、Ruff/format。
  - **Acceptance**: output含rule ID、file與修復連結；ignore無global wildcard；執行結果可重複。
  - **Regression risks**: scanner與語言syntax drift、Windows path差異。
  - **Parallel**: 否，依賴測試規格。
  - **Independent commit**: 是，guard implementation commit。

- [x] T031 [US5] 將 `scripts/check_sensitive_transport_policy.py` 接入既有 `scripts/verify_local.sh` 與CI workflow的fast security gate
  - **Goal**: 讓未登錄sensitive URL與catch-all回歸在implementation前被拒絕。
  - **Files**: `scripts/verify_local.sh`、實際使用中的`.github/workflows/*.yml` security/test workflow、必要contract test；不得新增重複workflow。
  - **Dependencies**: T030。
  - **Implementation notes**: static fast gate先跑；runtime/Playwright維持focused stage；文件說明如何登錄合法Class B或修正Class A，禁止以skip解決。
  - **Verification**: local verify的skip-docker模式、workflow syntax/contract tests。
  - **Acceptance**: temporary regression使CI step fail；正常repo pass；failure不含sentinel。
  - **Regression risks**: CI時間、workflow path filter漏跑、安全gate被optional化。
  - **Parallel**: 否，依賴checker穩定。
  - **Independent commit**: 是，CI integration commit。

- [x] T032 [P] [US5] 建立 `scripts/verify_sensitive_transport_runtime.py` 與 `tests/security/test_sensitive_transport_runtime.py` 的cross-layer synthetic sentinel runner
  - **Goal**: 可重複掃browser/network/nginx/Next/Uvicorn/application/audit/test artifact，報告只存digest。
  - **Files**: 新增兩個指定files；runtime temporary artifacts只放OS temp並cleanup。
  - **Dependencies**: T017、T019、T021、T022、T026。
  - **Implementation notes**: 每surface不同sentinel；掃raw與encoded form；結果含run_id/digest/surfaces/result/cleanup_status；不得讀`.env`真實值或把sentinel寫入persistent report；ngrok/storage外部surface無法自動時標BLOCKED/MANUAL而非猜PASS。
  - **Verification**: unit test runner、local synthetic smoke、cleanup後artifact不存在。
  - **Acceptance**: 注入leak會fail且不回顯值；安全run raw occurrence=0；diagnostic fields仍存在。
  - **Regression risks**: runner自身製造secret artifact、跨程序log capture不完整。
  - **Parallel**: 可與T029/T033平行，前提是logging/tunnel implementation已完成。
  - **Independent commit**: 是，runtime sentinel tooling commit。

### SEC-C04 — 文件、review與final gate

- [x] T033 [P] [US5] 同步 `README.md`、`docs/security/credential-url-incident-runbook.md`、`specs/012-sensitive-data-transport-hardening/quickstart.md` 與 `contracts/security-boundary.md`
  - **Goal**: 讓developer知道A/B/C/D、registry更新、tunnel預設deny、incident及驗證命令。
  - **Files**: 四個指定documents。
  - **Dependencies**: T015、T017、T023、T026、T030；可在T032進行時撰寫。
  - **Implementation notes**: 加review checklist：新form/redirect/QR/LIFF/signed URL/logger/route須更新何處；保留Deferred清單，不加入MFA/OAuth/cookie/CSP/zero-trust/CDN implementation。
  - **Verification**: command/path links存在、台灣正體中文主敘事、`git diff --check`。
  - **Acceptance**: 新工程師可從docs找到分類、owner、registry remediation、runtime與incident流程；無raw secret。
  - **Regression risks**: 文件與實際command drift。
  - **Parallel**: 可與T032平行。
  - **Independent commit**: 是，documentation commit。

- [x] T034 [US5] 依 `specs/012-sensitive-data-transport-hardening/quickstart.md` 完成最終targeted、frontend、Python constitution與人工smoke驗收，記錄於 `specs/012-sensitive-data-transport-hardening/validation-result.md`
  - **Goal**: 交付可merge、無scope creep且不含secret的完整evidence。
  - **Files**: 新增`specs/012-sensitive-data-transport-hardening/validation-result.md`；只有發現本feature regression才回到對應task修正，不順手擴scope。
  - **Dependencies**: T005-T033中本期採用的全部implementation；T028若owner判N/A則以decision evidence取代。
  - **Implementation notes**: 跑login Vitest/E2E、registry/static/log/nginx/tunnel/capability/isolation suites、frontend typecheck；若有Python production change依constitution跑`uv run ruff check .`、`uv run ruff format --check .`、`uv run pytest`；人工LINE/LIFF/tunnel及ngrok/storage項明確PASS/FAIL/BLOCKED。
  - **Verification**: `git diff --check`、`git status --short`、所有命令結果摘要與timestamp；報告不保存raw sentinel/URL credential。
  - **Acceptance**: Phase A/B/C criteria全部有evidence；management tunnel deny、Class B正常、cross-tenant拒絕、raw sentinel=0、scope/deferred review PASS。
  - **Regression risks**: 以局部測試誤宣稱全綠、人工項未做卻標PASS。
  - **Parallel**: 否，critical-path final gate。
  - **Independent commit**: 是，validation evidence commit；不與未通過production change混在一起。

**US5 Checkpoint**: CI能在變更進入release前擋下credential URL/log/tunnel回歸，且合法query與Class B
capability不受破壞。

---

## Dependencies & Execution Order

### High-level dependency graph

```text
Phase A / US1:
T001 → T002 ─┐
T003 ────────┴→ T004 → T005 → T006
T007 ────────────────────────┐
T002 + T004 + T007 ──────────┴→ T008 (MANUAL)

Phase B / US2:
T009 → T010
T009 → T011 ─┐
T009 → T012 ─┴→ T013 (only if discrepancy)
T009 → T014 → T015

Phase B / US3:
T009 → T016 → T017
T009 → T018 → T019
T009 → T020 → T021 (also T019 if helper is shared)
T009 + T018 → T022

Phase C / US4:
T009 → T023 → T024 → T025 → T026 → T027
T017 ────────────────────┘
T007 + T015 + T026 → T028 (owner decision)

Phase C / US5:
T009 + T010 + T023 → T029 → T030 → T031
T017 + T019 + T021 + T022 + T026 → T032
T015 + T017 + T023 + T026 + T030 → T033
T005…T033 → T034
```

### Story dependencies

- **US1 / Phase A**: 無registry dependency，可立即交付MVP containment。
- **US2 / Phase B policy**: 可與US1平行；T009是US2、US3、US4/5 policy dependency。
- **US3 / Phase B logging**: nginx、application與audit三條支線可在T009後平行；nginx不依賴tunnel allowlist。
- **US4 / Phase C tunnel**: 必須先完成T023 route evidence；不得以open question阻塞default deny，無證據route維持deny。
- **US5 / Phase C guardrails**: registry checker依賴T009/T010；runtime runner依賴各layer implementation。
- **Incident T008**: login fix ready/deployed後執行；可與Phase B engineering平行，但屬人工critical security action。

### Parallel opportunities

- 初始可同時啟動：T001、T003、T007、T009。
- T009後可同時啟動：T011、T012、T014、T016、T018、T020、T023。
- Logging implementation可由三位工程師分工：T017 nginx、T019 application、T021 audit；注意T021若重用T019 helper則需等待。
- Phase C後段可平行：T029 static policy、T032 runtime runner、T033 docs。
- 不可平行寫同一檔案：T001/T003需協調`page.test.tsx`；T016/T024都改`test_line_local_helper.py`故按dependency序列；T017/T025都改local nginx故序列。

### Critical path

```text
T009 → T023 → T024 → T025 → T026 → T027
     → T029 → T030 → T031
T016 → T017 ───────────────┐
T018 → T019 → T020/T021 ───┼→ T032 → T034
Phase A T001…T006 ─────────┤
T007 → T008 evidence ──────┘
```

T028不阻塞default-deny交付；若owner決定不保留remote management demo，以正式N/A decision滿足依賴。

---

## Parallel execution examples

### Phase A + registry start

```text
Engineer A: T001 → T002
Engineer B: T003（完成後與A協調）→ T004
Security/Operations: T007
Engineer C: T009 → T010
```

### Phase B after registry

```text
Engineer A: T011 + T012 → T013 if needed
Engineer B: T016 → T017
Engineer C: T018 → T019
Engineer D: T020 → T021
Engineer E: T014 → T015
```

### Phase C

```text
Engineer A: T023 → T024 → T025 → T026 → T027
Engineer B: T029 → T030 → T031
Engineer C: T032
Technical writer/security reviewer: T033
All owners: T034 final gate
```

---

## Implementation Strategy

### MVP first — Phase A / US1

1. T001/T002封堵native GET與prefill。
2. T003/T004清理legacy URL及history/Referer。
3. T005/T006完成browser/network/no-JS/hydration evidence。
4. T007準備runbook，T008由人工執行incident containment。
5. **STOP AND VALIDATE**：Phase A可獨立部署；不要等待registry才封堵login。

### Incremental delivery

1. Phase A source containment。
2. T009/T010 registry與CI-readable policy。
3. US2 capability/CLI及US3三條logging支線。
4. T023先決定最小LINE/LIFF route，再實作default-deny tunnel。
5. US5 static/runtime guardrails與final validation。

### Scope guard

以下只留Deferred，不得從任一task擴大實作：MFA、OAuth migration、full cookie auth、refresh token
architecture rewrite、global CSP rollout、zero-trust、storage/CDN redesign、任意修改QR/entry/photo/signed
URL TTL。若測試發現需要其中任一變更，記discrepancy並另開spec。

---

## Final self-review

- [x] Phase A不依賴registry，可最先獨立完成。
- [x] 沒有task以HTML form POST取代正常JSON login API。
- [x] Legacy URL使用replace且禁止reflection。
- [x] Class B保留各自TTL/revoke/replay/scope；沒有全面禁止query token。
- [x] nginx safe log保留一般query observability。
- [x] application/audit是defense-in-depth，未誤稱已存在audit資料外洩。
- [x] tunnel由catch-all改default deny，care-report/assigned-care先驗證再決定。
- [x] 每個production change都有test-first或既有passing regression task。
- [x] T008是獨立人工operational incident task。
- [x] Static check有scoped parser/registry/ignore/remediation，不使用naive global grep。
- [x] Deferred項目沒有偷跑進implementation。
- [x] dependency與同檔衝突已標示，可供多人平行執行。

## Blocking open questions

- **無阻塞Phase A或default-deny實作的open question**。
- `/care-report`與`/assigned-care/{id}`由T023以實際vertical evidence決定；未證明必要就維持deny。
- Remote management demo是否保留由T028取得owner decision；不阻塞預設LINE/LIFF tunnel。
- ngrok/storage第三方retention只能在T008/T032/T034標人工PASS/FAIL/BLOCKED，不可由repository猜測。
