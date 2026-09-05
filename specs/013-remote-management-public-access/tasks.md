# Tasks: Remote Management Public Access

**Input**: `spec.md`、`plan.md`、`research.md`、`data-model.md`、`quickstart.md`、`contracts/*`

**Tests**: 本 feature 明確要求 test-first。測試 task 先建立可重現的 failing evidence；對應 production
task 完成後必須轉為 PASS，不得以 skip、放寬 assertion 或固定 sleep 取代。

**Task format**: 每個 checkbox 行遵循 `- [ ] Txxx [P?] [US?] Description with path`；其下欄位補足
Phase、Goal、files、dependencies、implementation notes、verification、acceptance、risk、parallelism
與 commit boundary。

## Phase A — Auth Protection Foundation（US3，獨立可驗收）

**Goal**: PostgreSQL 共享狀態提供 account lockout、IP rolling window、可信來源解析及 unknown-user
固定成本驗證；尚不公開 management route。

**Independent test**: 兩個 service/repository instance 共用 PostgreSQL，以 injectable clock 與並行
request 證明第 1–4 次 401、第 5 次與鎖定期間 429、15 分鐘後恢復、第 21 次 IP request 429，且
偽造 header 與 unknown username 不形成 bypass/enumeration。

- [X] T001 [P] [US3] 先建立 login abuse schema contract tests 於 `tests/contract/test_remote_login_abuse_schema.py`
  - **Phase/Goal/Files/Deps**: A；鎖定兩張 abuse table、索引、constraint 與 migration downgrade contract；修改該 test；無依賴。
  - **Notes/Test/AC**: 先對缺少 schema 失敗；驗證 account digest unique、IP `(source_digest, attempted_at)` index、UTC timestamps、無 raw username/IP 欄位；測試失敗原因單一明確。
  - **Risk/Parallel/Commit**: 避免測到 ORM 名稱而漏 DB constraint；可與 T003、T008 平行；不獨立 commit，與 T002 同一 commit。

- [X] T002 [US3] 新增 abuse persistence model 與 Alembic migration 於 `services/api/app/persistence/models/identity.py`、`services/api/migrations/versions/0045_remote_login_abuse.py`
  - **Phase/Goal/Files/Deps**: A；建立 `login_account_abuse_states`、`login_ip_attempts`；依賴 T001。
  - **Notes/Test/AC**: follow existing UUID/timestamp conventions，account failure check 0–5，upgrade/downgrade 可重複；T001 PASS 且 migration heads 單一。
  - **Risk/Parallel/Commit**: 不把平台 auth metadata 誤加 shelter RLS；不可平行於 T001；可獨立 commit（含 T001）。

- [X] T003 [P] [US3] 先建立 normalization、HMAC 與 runtime-secret tests 於 `tests/unit/test_login_abuse_keys.py`、`tests/unit/test_runtime_safety.py`
  - **Phase/Goal/Files/Deps**: A；定義 NFKC→trim→casefold 只用於 abuse key，以及 account/IP domain separation；無依賴。
  - **Notes/Test/AC**: 等價 Unicode 共用 digest、authentication lookup input 不被改寫、placeholder/missing key 在 shared profile fail closed、local/test fixture 可明確注入；先失敗。
  - **Risk/Parallel/Commit**: 避免 raw identifier 出現在 assertion artifact；可與 T001/T008 平行；不獨立 commit，與 T004 同一 commit。

- [X] T004 [US3] 實作 abuse-key utility 與設定驗證於 `services/api/app/application/authentication/login_abuse.py`、`services/api/app/config/settings.py`
  - **Phase/Goal/Files/Deps**: A；產生 HMAC-SHA256 subject 並驗證專用 SecretStr；依賴 T003。
  - **Notes/Test/AC**: 不重用 JWT/PII key、不 log secret/raw key、local fixture 明示；T003 PASS 且既有 runtime-safety tests 不退化。
  - **Risk/Parallel/Commit**: key 變更會使既有 counter 不可定位，runtime 必須穩定提供；不可平行於 T003；可獨立 commit（含 T003）。

- [X] T005 [US3] 先建立 PostgreSQL account/IP repository tests 於 `tests/integration/test_remote_login_abuse_postgres.py`
  - **Phase/Goal/Files/Deps**: A；定義 transaction、advisory lock、atomic upsert、rolling prune 與 Retry-After；依賴 T002、T004。
  - **Notes/Test/AC**: injectable clock，不用 sleep；成功清 account state但保留 IP window，以不同username送第21次仍拒絕且不新增 row，過期 row cleanup；先失敗。
  - **Risk/Parallel/Commit**: SQLite/mock 不能證明 PostgreSQL lock；不可平行於 schema/key；不獨立 commit，與 T006 同一 commit。

- [X] T006 [US3] 實作原子 abuse repository operations 於 `services/api/app/persistence/repositories/authentication_repository.py`
  - **Phase/Goal/Files/Deps**: A；以 digest-keyed transaction advisory lock 完成 account/IP 讀改寫；依賴 T005。
  - **Notes/Test/AC**: absent-row 也序列化，IP 先 prune/count 再 insert，Retry-After 最少 1 秒；T005 PASS，DB failure 不回傳可建立 session 的結果。
  - **Risk/Parallel/Commit**: lock order 固定 IP→account 避免 deadlock；不可平行；可獨立 commit（含 T005）。

- [X] T007 [US3] 增加跨 instance 與 race tests 於 `tests/integration/test_remote_login_abuse_concurrency.py`
  - **Phase/Goal/Files/Deps**: A；證明兩 repository/service instance、並行第五次與第二十一次結果可重現；依賴 T006。
  - **Notes/Test/AC**: 使用 barrier/event 協調，不用時間 sleep；只有前四次 wrong request 為 401，第五次起 429，IP 前二十次進入 evaluation；全部 PASS。
  - **Risk/Parallel/Commit**: 測試不可依 completion order 造成 flaky；可與 T010 測試撰寫平行；可獨立 commit。

- [X] T008 [P] [US3] 先建立 trusted client-IP resolution tests 於 `tests/security/test_trusted_client_ip.py`
  - **Phase/Goal/Files/Deps**: A；定義 Internet→ngrok→nginx→FastAPI 信任鏈；無依賴。
  - **Notes/Test/AC**: 覆蓋 IPv4/IPv6 canonicalization、forged/duplicate/invalid dedicated header、任意 X-Forwarded-For、direct request、明確 local-test mode；先失敗。
  - **Risk/Parallel/Commit**: 不把 localhost fallback 帶到 shared runtime；可與 T001/T003 平行；不獨立 commit，與 T009 同一 commit。

- [X] T009 [US3] 實作 exposure/client-IP resolver 於 `services/api/app/api/management_access.py`、`services/api/app/config/settings.py`
  - **Phase/Goal/Files/Deps**: A；只接受 configured loopback gateway 建立的專用 metadata；依賴 T008、T004。
  - **Notes/Test/AC**: 不信任 body/query/XFF/client X-Forwarded-Proto；shared metadata 缺漏或多值 fail closed，local validation 必須 explicit；T008 PASS。
  - **Risk/Parallel/Commit**: proxy hop 判定錯誤可讓攻擊者控制 rate key；不可平行；可獨立 commit（含 T008）。

- [X] T010 [US3] 先建立 login API/service behavior tests 於 `tests/security/test_remote_login_abuse_control.py`
  - **Phase/Goal/Files/Deps**: A；固定 401/429/503 shape、Retry-After、dummy verify 與 reset semantics；依賴 T006、T009。
  - **Notes/Test/AC**: 測第1–4次401、第5次429、換IP後鎖仍有效、鎖內正確密碼429、15m後成功、成功不清IP、known/unknown皆套用相同計數與response fields；先失敗。
  - **Risk/Parallel/Commit**: timing assertion 只驗證相同 verifier path/call，不設脆弱毫秒門檻；可與 T007 平行；不獨立 commit，與 T011 同一 commit。

- [X] T011 [US3] 將 abuse controls 與 dummy verification 接入 `services/api/app/application/authentication/session_service.py`、`services/api/app/api/authentication.py`
  - **Phase/Goal/Files/Deps**: A；保留 JSON `POST /v1/auth/login` 與既有 identity matching；依賴 T010。
  - **Notes/Test/AC**: IP gate→account lock→password verify→atomic update/session，unknown/disabled 跑 dummy Argon2；DB error 503 fail closed；T007/T010 PASS。
  - **Risk/Parallel/Commit**: transaction 持鎖順序與 password cost 必須可預測，不能建立 session 後才判 limiter；不可平行；可獨立 commit（含 T010）。

- [X] T012 [P] [US3] 建立 abuse state expiry/cleanup regression tests 於 `tests/integration/test_remote_login_abuse_cleanup.py`
  - **Phase/Goal/Files/Deps**: A；驗證15分鐘邊界、stale account reset與bounded opportunistic IP cleanup；依賴 T006。
  - **Notes/Test/AC**: 精確測 `<= now-15m`、大量不同 digest cleanup 不做 unbounded delete；先失敗且不需 scheduler。
  - **Risk/Parallel/Commit**: boundary off-by-one 會錯算 Retry-After；可與 T010 平行；不獨立 commit，與 T013 同一 commit。

- [X] T013 [US3] 完成 bounded cleanup 與 Phase A 驗收於 `services/api/app/persistence/repositories/authentication_repository.py`、`specs/013-remote-management-public-access/validation-result.md`
  - **Phase/Goal/Files/Deps**: A；讓過期狀態最小保存並記錄 targeted evidence；依賴 T007、T011、T012。
  - **Notes/Test/AC**: T001–T012 全部 PASS，process/tunnel restart 不清 DB lockout，raw username/IP sentinel 不進 log；只記 synthetic evidence。
  - **Risk/Parallel/Commit**: 不宣告 public activation；不可平行於 Phase A 尾端；可獨立 commit（含 T012）。

## Phase B — Shared Profile Contracts（US4/US5，獨立可驗收）

**Goal**: 將 management registry、profile composition、Host policy 與 production static manifest
轉為 deterministic source-of-truth compiler；不改既有 LINE registry 語意、不啟動 tunnel。

**Independent test**: 純 contract tests 對 23 筆 management routes、25 筆 LINE compatibility metadata、
三個 profiles、Host inputs、衝突與 Next manifests 產生固定結果；任何 broad/unknown/missing input fail。

- [X] T014 [P] [US4] 先建立 management registry schema tests 於 `tests/contract/test_management_tunnel_registry.py`
  - **Phase/Goal/Files/Deps**: B；驗證23 routes逐筆具 FR-004 欄位與 `demo_required`、strict UUID/method/upstream/query/log/rate/auth/role/evidence；無依賴。
  - **Notes/Test/AC**: 明確拒絕 `/v1/**`、`/v1/management/**`、catch-all UI及未 anchored pattern；目前缺 `demo_required` 時先失敗。
  - **Risk/Parallel/Commit**: 不把 explicit deny notation 當 allow pattern；可與 T016/T018/T020 平行；不獨立 commit，與 T015 同一 commit。

- [X] T015 [US4] 補齊 registry demo-required metadata 於 `specs/013-remote-management-public-access/contracts/management-tunnel-allowlist.yaml`
  - **Phase/Goal/Files/Deps**: B；使每筆 route 可由 compiler 完整驗證；依賴 T014。
  - **Notes/Test/AC**: 只補 contract metadata，不擴張 path/method/role、不修改012 LINE registry；T014 PASS且仍為23筆。
  - **Risk/Parallel/Commit**: metadata default 不可掩蓋個別 route 缺欄；不可平行；可獨立 commit（含 T014）。

- [X] T016 [P] [US4] 先建立 profile composition/conflict tests 於 `tests/contract/test_public_tunnel_profiles.py`
  - **Phase/Goal/Files/Deps**: B；定義 line-only預設、shared explicit opt-in、include/exclude、duplicate及policy conflict fail closed；無依賴。
  - **Notes/Test/AC**: 每個LINE id恰一次、unknown registry/exclusion失敗、production排除HMR/static pattern；先失敗。
  - **Risk/Parallel/Commit**: 同 method/path但不同 upstream/query/log/security 必須拒絕而非 last-write-wins；可與 T014/T018/T020 平行；不獨立 commit，與 T017 同一 commit。

- [X] T017 [US4] 實作 registry/profile compiler 於 `scripts/public_tunnel_policy.py`
  - **Phase/Goal/Files/Deps**: B；解析兩份 registry及compatibility metadata為 immutable effective routes；依賴 T015、T016。
  - **Notes/Test/AC**: deterministic sort、schema errors具route id但無秘密、default profile line-only；T016 PASS，不寫回LINE registry。
  - **Risk/Parallel/Commit**: YAML merge/default 不得讓缺欄通過；不可平行；可獨立 commit（含 T016）。

- [X] T018 [P] [US4] 先建立 Next build-manifest parser tests 於 `tests/contract/test_next_public_asset_manifest.py`、`tests/security/fixtures/next-manifests/`
  - **Phase/Goal/Files/Deps**: B；以 fixture 定義allowed pages的exact shared/page CSS/JS assets；無依賴。
  - **Notes/Test/AC**: deterministic去重排序、missing/empty/unresolved route失敗，`.map`、`/_next/image`、font/favicon及unproven chunk拒絕；先失敗。
  - **Risk/Parallel/Commit**: fixture須模擬Next 15 manifest結構但不hard-code真實ephemeral hash；可與 T014/T016/T020平行；不獨立 commit，與 T019同一commit。

- [X] T019 [US4] 實作 production exact-asset extraction 於 `scripts/public_tunnel_policy.py`
  - **Phase/Goal/Files/Deps**: B；從實際 `.next` manifests解出profile頁面依賴；依賴 T017、T018。
  - **Notes/Test/AC**: production取代`next_static_assets`，dev維持bounded pattern/HMR；T018 PASS，輸出不含source map或未證實資源。
  - **Risk/Parallel/Commit**: Next manifest版本差異須fail closed並提供非敏感診斷；不可平行；可獨立commit（含T018）。

- [X] T020 [P] [US4] 先建立 reserved-origin/Host normalization tests 於 `tests/unit/test_public_tunnel_host_policy.py`
  - **Phase/Goal/Files/Deps**: B；驗證HTTPS exact reserved host、case/IDNA/port及loopback test exception；無依賴。
  - **Notes/Test/AC**: userinfo/path/query/fragment/wildcard/http/missing/unknown host失敗，不從request Host生成可信origin；先失敗。
  - **Risk/Parallel/Commit**: port normalization不可誤接受不同authority；可與 T014/T016/T018平行；不獨立commit，與T021同一commit。

- [X] T021 [US4] 實作 runtime origin/Host policy 於 `scripts/public_tunnel_policy.py`、`services/api/app/config/settings.py`
  - **Phase/Goal/Files/Deps**: B；將合法runtime origin轉為generated config input；依賴 T020、T004。
  - **Notes/Test/AC**: repository無實際ngrok hostname，loopback僅explicit local validation；T020 PASS，缺值時shared profile non-zero exit。
  - **Risk/Parallel/Commit**: hostname canonicalization須與nginx Host比較一致；不可平行；可獨立commit（含T020）。

- [X] T022 [US5] 完成 Phase B deterministic contract acceptance 於 `tests/contract/test_public_tunnel_policy_snapshot.py`、`specs/013-remote-management-public-access/validation-result.md`
  - **Phase/Goal/Files/Deps**: B；固定三profile route/asset摘要與LINE registry digest；依賴 T017、T019、T021。
  - **Notes/Test/AC**: 相同input byte-stable，line-only route語意/digest不變，production無HMR；所有B tests PASS。
  - **Risk/Parallel/Commit**: snapshot只存結構不存host/secret/chunk環境值；不可平行；可獨立commit。

## Phase C — Gateway and Helper Integration（US1/US2/US4/US5）

**Goal**: 由 compiler 產生 default-deny nginx/ngrok policy，helper 明確 opt-in shared profile，FastAPI
對可信 public profile縮限角色，Frontend呈現core-only介面。

**Independent test**: local loopback harness 分別啟動 line-only/shared dev/shared production，逐一驗證
Host、method、path、upstream、RSC/static/HMR、header spoofing、角色與 deny matrix。

- [X] T023 [US4] 先建立 generated nginx route/logging tests 於 `tests/contract/test_remote_management_nginx.py`
  - **Phase/Goal/Files/Deps**: C；定義exact/bounded locations、wrong method/catch-all 404與sensitive path-only log；依賴 T022。
  - **Notes/Test/AC**: `$request/$request_uri/$args/$http_referer`不得進sensitive format，一般local observability保留；先失敗。
  - **Risk/Parallel/Commit**: nginx location precedence不可讓regex越過exact deny；可與T025/T027/T029/T033平行；不獨立commit，與T024同一commit。

- [X] T024 [US4] 實作 shared-demo nginx renderer 於 `scripts/generate_public_tunnel_config.py`、`infra/local/nginx/line-local.conf.template`
  - **Phase/Goal/Files/Deps**: C；只輸出runtime temp config並維持default deny；依賴 T023、T017、T019、T021。
  - **Notes/Test/AC**: exact Host guard、API/web upstream分離、query policies、production exact assets；T023與`nginx -t` fixture PASS。
  - **Risk/Parallel/Commit**: 不直接覆寫committed template或產生broad location；不可平行；可獨立commit（含T023）。

- [X] T025 [P] [US3] 先建立 ngrok trusted-metadata policy tests 於 `tests/contract/test_ngrok_shared_policy.py`
  - **Phase/Goal/Files/Deps**: C；定義remove-then-set client IP/profile/scheme及無秘密輸出；依賴 T017。
  - **Notes/Test/AC**: forged dedicated header/XFF/XFP不得成authority，缺`conn.client_ip` fail；先失敗。
  - **Risk/Parallel/Commit**: 測試需依目前agent支援語法驗證，不臆測cloud行為；可與T023/T027平行；不獨立commit，與T026同一commit。

- [X] T026 [US3] 產生並驗證 ngrok Traffic Policy 於 `scripts/generate_public_tunnel_config.py`
  - **Phase/Goal/Files/Deps**: C；以connection metadata建立可信headers；依賴 T025、T021。
  - **Notes/Test/AC**: policy輸出temp、header先remove再set、CLI config check PASS；T025與T008 trusted-IP tests PASS。
  - **Risk/Parallel/Commit**: 不允許client同名headerappend成多值；不可平行；可獨立commit（含T025）。

- [X] T027 [P] [US4] 先建立 helper opt-in/process-mode tests 於 `tests/contract/test_remote_management_helper.py`
  - **Phase/Goal/Files/Deps**: C；鎖定未帶flag=line-only、明確production/dev選擇、production先build後start；依賴 T022。
  - **Notes/Test/AC**: `--with-management`或等價明確flag，012 T008只在public activation檢查；unknown/missing host non-zero；先失敗。
  - **Risk/Parallel/Commit**: 不改`demo-line.sh`預設成shared；可與T023/T025/T029/T033平行；不獨立commit，與T028同一commit。

- [X] T028 [US4] 整合 shared profile helper 於 `scripts/demo-management.sh`、`scripts/demo-line.sh`、`scripts/test_line_local.sh`
  - **Phase/Goal/Files/Deps**: C；提供explicit opt-in並正確啟動Next production/dev、nginx、ngrok；依賴 T024、T026、T027。
  - **Notes/Test/AC**: production不啟HMR/dev overlay，line helpers無flag仍line-only；shell使用LF、cleanup child processes；T027 PASS。
  - **Risk/Parallel/Commit**: 避免將host/password/token印到terminal；不可平行；可獨立commit（含T027）。

- [X] T029 [P] [US2] 先建立 public exposure-context API tests 於 `tests/security/test_remote_management_access.py`
  - **Phase/Goal/Files/Deps**: C；定義STAFF/admin allow、volunteer/platform/expired deny與既有token deny；依賴 T009。
  - **Notes/Test/AC**: 兩層驗證platform route gateway deny及platform token呼叫management API deny；client不能提交profile；先失敗。
  - **Risk/Parallel/Commit**: 不改private/local PLATFORM_ADMIN能力；可與T023/T025/T027/T033平行；不獨立commit，與T030/T032同一commit。

- [X] T030 [US2] 將 server-derived exposure context 接入 auth/management dependencies 於 `services/api/app/api/management_access.py`、`services/api/app/api/authentication.py`
  - **Phase/Goal/Files/Deps**: C；shared request只允許active STAFF/SHELTER_ADMIN且不信frontend；依賴 T029、T009。
  - **Notes/Test/AC**: login與既有token都受限，active shelter/membership/RLS照舊，deny不揭露membership；T029 PASS。
  - **Risk/Parallel/Commit**: 不能用gateway role metadata取代DB identity；不可平行；與T032一起commit。

- [X] T031 [US1] 增加 `/v1/auth/me` exposure hint contract tests 於 `tests/contract/test_authentication_contract.py`、`tests/integration/test_authentication_session.py`
  - **Phase/Goal/Files/Deps**: C；固定nullable `public_exposure_profile` response，client不可控制；依賴 T030。
  - **Notes/Test/AC**: shared prod/dev回各自值，private/line-only固定null；refresh不接受body override；先失敗。
  - **Risk/Parallel/Commit**: additive response需同步TypeScript types；可與T033撰寫平行；不獨立commit，與T032同一commit。

- [X] T032 [US2] 實作 exposure hint 與 public role policy 於 `services/api/app/application/authentication/session_service.py`、`services/api/app/api/authentication.py`
  - **Phase/Goal/Files/Deps**: C；完成後端角色縮限與穩定response shape；依賴 T030、T031。
  - **Notes/Test/AC**: STAFF/SHELTER_ADMIN成功，PLATFORM_ADMIN/VOLUNTEER/expired拒絕；local contract不變；T029/T031 PASS。
  - **Risk/Parallel/Commit**: hint不是access-token claim或authorization來源；不可平行；可獨立commit（含T029–T031）。

- [X] T033 [P] [US1] 先建立 core-only UI tests 於 `apps/web/components/management/ManagementLayout.test.tsx`、`apps/web/app/(management)/reports/[reportId]/page.test.tsx`、`apps/web/features/medical-care/CareAgenda.test.tsx`
  - **Phase/Goal/Files/Deps**: C；shared profile隱藏out-of-scope navigation、report correction/archive與care mutation controls；依賴 T022。
  - **Notes/Test/AC**: direct API deny仍由後端測，private/local UI維持既有功能；先失敗。
  - **Risk/Parallel/Commit**: 不能把menu hidden當security assertion；可與T023/T025/T027/T029平行；不獨立commit，與T034同一commit。

- [X] T034 [US1] 實作 scope-safe frontend 於 `apps/web/components/management/ManagementLayout.tsx`、`apps/web/components/management/AppSidebar.tsx`、`apps/web/app/(management)/reports/[reportId]/page.tsx`、`apps/web/features/medical-care/CareAgenda.tsx`
  - **Phase/Goal/Files/Deps**: C；使用`/me` nullable hint提供core-only/read-only UX；依賴 T032、T033。
  - **Notes/Test/AC**: 更新TypeScript type，不從URL/localStorage決定profile；T033 PASS且local UI regression PASS。
  - **Risk/Parallel/Commit**: hydration前不得短暫顯示高風險controls；不可平行；可獨立commit（含T033）。

- [X] T035 [US4] 建立 local gateway allow/deny integration matrix 於 `tests/e2e/test_remote_management_tunnel_boundary.py`
  - **Phase/Goal/Files/Deps**: C；實際nginx驗證login/core/RSC/prefetch/static、wrong Host/method/path與所有explicit deny；依賴 T024、T028。
  - **Notes/Test/AC**: arbitrary `/v1/**`、unknown UI、platform/docs/debug/internal、PII/mutations不達upstream；production HMR 404，dev HMR allow；全部PASS。
  - **Risk/Parallel/Commit**: 使用upstream probe counter證明「未到達」而非只看404；可與T034後半平行；可獨立commit。

- [X] T036 [US5] 驗證 line-only registry semantic regression 於 `tests/e2e/test_local_line_tunnel_boundary.py`、`tests/contract/test_line_local_helper.py`
  - **Phase/Goal/Files/Deps**: C；證明無management opt-in時login/core拒絕且25筆LINE route owner/method/query/logging不變；依賴 T028、T035。
  - **Notes/Test/AC**: 比對012 registry digest/effective matrix，不要求修改LINE registry；tests PASS。
  - **Risk/Parallel/Commit**: 避免snapshot吸收未審核變動；不可平行於C尾端；可獨立commit。

## Phase D — Remote Session Origin and Rollback（US4）

**Goal**: server-side session可精準辨識remote demo，refresh保留來源，rollback先deny route再撤銷remote
session，且不影響local/LIFF session。

**Independent test**: 建立remote、local、LIFF、legacy sessions後執行rollback，驗證management先404、
remote access/refresh立即失效、其他session仍有效，synthetic clock總流程小於300秒。

- [X] T037 [P] [US4] 先建立 session-origin schema/migration tests 於 `tests/contract/test_remote_session_origin_schema.py`
  - **Phase/Goal/Files/Deps**: D；定義`session_origin`、nullable profile、constraint、index與legacy backfill；依賴 T002。
  - **Notes/Test/AC**: remote只允許兩shared profile，其他origin profile須null；upgrade/downgrade及existing row測試先失敗。
  - **Risk/Parallel/Commit**: 不依時間猜session來源；可與T039/T041平行；不獨立commit，與T038同一commit。

- [X] T038 [US4] 擴充 session model/migration 於 `services/api/app/persistence/models/identity.py`、`services/api/migrations/versions/0046_remote_session_origin.py`
  - **Phase/Goal/Files/Deps**: D；persist server-derived origin/profile並建立rollback index；依賴 T037、T002 migration head。
  - **Notes/Test/AC**: existing rows backfill legacy後non-null，migration保持single head；T037 PASS。
  - **Risk/Parallel/Commit**: 若0045尚未落地不得產生branching head；不可平行；可獨立commit（含T037）。

- [X] T039 [P] [US4] 先建立 origin lifecycle tests 於 `tests/integration/test_remote_session_origin.py`
  - **Phase/Goal/Files/Deps**: D；login來源不可由body/header偽造，LIFF/local明確標記，refresh保留，logout撤銷；依賴 T032。
  - **Notes/Test/AC**: remote refresh重驗role/membership，platform/expired session撤銷；先失敗。
  - **Risk/Parallel/Commit**: 不重設refresh architecture或建立第二種token；可與T037/T041平行；不獨立commit，與T040同一commit。

- [X] T040 [US4] 實作 session-origin lifecycle 於 `services/api/app/application/authentication/session_service.py`、`services/api/app/application/authentication/line_identity_service.py`
  - **Phase/Goal/Files/Deps**: D；所有session建立點明確寫server-derived origin，rotation沿用；依賴 T038、T039。
  - **Notes/Test/AC**: logout仍撤銷session/family，remote refresh不可升權；T039及既有LIFF/session tests PASS。
  - **Risk/Parallel/Commit**: 漏一個SessionRecord constructor會違反constraint；不可平行；可獨立commit（含T039）。

- [X] T041 [P] [US4] 先建立 selective revocation repository tests 於 `tests/integration/test_remote_session_rollback.py`
  - **Phase/Goal/Files/Deps**: D；remote active sessions與所有refresh family同transaction撤銷；依賴 T038。
  - **Notes/Test/AC**: local/LIFF/legacy不受影響，重跑idempotent並回non-sensitive counts；先失敗。
  - **Risk/Parallel/Commit**: query必須以origin+status index且tenant無關；可與T039平行；不獨立commit，與T042同一commit。

- [X] T042 [US4] 實作 selective revocation 於 `services/api/app/persistence/repositories/authentication_repository.py`、`services/api/app/application/authentication/session_service.py`
  - **Phase/Goal/Files/Deps**: D；提供rollback service operation；依賴 T040、T041。
  - **Notes/Test/AC**: access request查server session後立即失效，refresh records同transaction revoked；T041 PASS。
  - **Risk/Parallel/Commit**: 不輸出user/token/raw session id；不可平行；可獨立commit（含T041）。

- [X] T043 [US4] 先建立 ordered rollback/helper tests 於 `tests/e2e/test_remote_management_rollback.py`
  - **Phase/Goal/Files/Deps**: D；驗證gateway deny成功後才允許DB revoke，deny失敗不得宣告完成；依賴 T036、T042。
  - **Notes/Test/AC**: injectable clock證明<300秒，保存profile/timestamp/matrix/count但無secret；先失敗。
  - **Risk/Parallel/Commit**: 不以sleep或token自然過期通過；不可平行；不獨立commit，與T044同一commit。

- [X] T044 [US4] 實作 rollback command/runbook 於 `scripts/rollback_remote_management.py`、`docs/demo/remote-management.md`
  - **Phase/Goal/Files/Deps**: D；先切line-only/reload/probe，再呼叫selective revoke與LINE probe；依賴 T043。
  - **Notes/Test/AC**: idempotent、failure exit non-zero、5分鐘evidence完整且local/LIFF session保留；T043 PASS。
  - **Risk/Parallel/Commit**: 禁止顛倒步驟或印credential；不可平行；可獨立commit（含T043）。

## Phase E — Runtime Acceptance（US1/US2/US4/US5）

**Goal**: 以 `shared-demo-production` 為唯一主要 security acceptance，完成角色、租戶、LINE、log、
activation gate與rollback evidence。012 T008 未完成時，code/tests可完成，但public activation tasks保持未完成。

**Independent test**: synthetic STAFF與SHELTER_ADMIN各完成核心journey；platform/volunteer/cross-tenant/
unknown routes全部拒絕；LINE happy paths 100%；sentinel不進任何log/artifact；rollback<5分鐘。

- [X] T045 [US4] 先建立 activation-gate tests 於 `tests/security/test_remote_management_activation_gate.py`
  - **Phase/Goal/Files/Deps**: E；要求exact host、synthetic data、old password reject/new accept/old sessions revoke、route matrix及log sentinel evidence；依賴 T028、T044。
  - **Notes/Test/AC**: 缺任一evidence shared activation失敗但line-only/coding不受阻；不接受boolean口頭替代；先失敗。
  - **Risk/Parallel/Commit**: fixture evidence不可被誤當真實T008；可與T047–T051測試準備平行；不獨立commit，與T046同一commit。

- [X] T046 [US4] 將 activation gate 接入 `scripts/demo-management.sh`、`scripts/verify_sensitive_transport_runtime.py`
  - **Phase/Goal/Files/Deps**: E；public shared啟動前驗證machine-readable evidence且輸出去敏；依賴 T045。
  - **Notes/Test/AC**: 012 T008 pending時shared public non-zero exit，line-only仍啟動；T045 PASS，不自動執行外部rotation/清log。
  - **Risk/Parallel/Commit**: 不得以環境boolean繞過evidence；不可平行；可獨立commit（含T045）。

- [X] T047 [P] [US1] 建立 STAFF production-browser journey 於 `apps/web/e2e/remote-management-staff.spec.ts`
  - **Phase/Goal/Files/Deps**: E；login/context/dashboard/animals/photo/timeline/reports/AI review/care calendar完整流程；依賴 T034、T035、T040。
  - **Notes/Test/AC**: actual Next production build、5 runs納入SC-001，URL無credential，out-of-scope controls不可見/direct API deny；PASS。
  - **Risk/Parallel/Commit**: 不mock gateway/auth/tenant boundary；可與T048–T052平行；可獨立commit。

- [X] T048 [P] [US2] 建立 SHELTER_ADMIN與PLATFORM_ADMIN/VOLUNTEER deny journey 於 `apps/web/e2e/remote-management-admin-boundary.spec.ts`
  - **Phase/Goal/Files/Deps**: E；admin完成core但治理/PII/platform拒絕，既有platform token呼叫core亦拒絕；依賴 T032、T035、T040。
  - **Notes/Test/AC**: gateway platform route未達upstream，backend second layer deny；5 runs納入SC-001；PASS。
  - **Risk/Parallel/Commit**: 不能只assert menu hidden；可與T047/T049–T052平行；可獨立commit。

- [X] T049 [P] [US1] 擴充跨收容所負向矩陣於 `tests/security/test_remote_management_tenant_isolation.py`
  - **Phase/Goal/Files/Deps**: E；STAFF/admin對B shelter animal/photo/timeline/report/attention/calendar全數403/404且non-enumerating；依賴 T032。
  - **Notes/Test/AC**: client organization/resource ID不改server scope，RLS/repository predicate均覆蓋；100% PASS。
  - **Risk/Parallel/Commit**: 每個resource family需真實B tenant fixture；可與T047/T048/T050–T052平行；可獨立commit。

- [X] T050 [P] [US4] 完成 production/dev route及framework matrix 於 `tests/e2e/test_remote_management_tunnel_boundary.py`
  - **Phase/Goal/Files/Deps**: E；用actual build assets驗證HTML/CSS/JS/RSC/prefetch，production HMR/source map/image/unproven asset deny；依賴 T035。
  - **Notes/Test/AC**: unexpected Host、ports、encoded slash/dot/semicolon/duplicate slash/suffix/wrong method不達upstream；PASS。
  - **Risk/Parallel/Commit**: production acceptance不得改跑next dev；可與T047–T049/T051/T052平行；可獨立commit。

- [X] T051 [P] [US5] 執行兩profile LINE regression 於 `tests/e2e/test_remote_management_line_regression.py`
  - **Phase/Goal/Files/Deps**: E；覆蓋webhook簽章、LIFF exchange、QR、animal confirm、photo capability、care-report；依賴 T036、T044。
  - **Notes/Test/AC**: line-only/shared各100%，capability TTL/query/logging與LINE registry語意不變；PASS。
  - **Risk/Parallel/Commit**: 不為通過測試擴大route或降低signature/tenant policy；可與T047–T050/T052平行；可獨立commit。

- [X] T052 [P] [US3] 建立 cross-log synthetic sentinel acceptance 於 `tests/security/test_remote_management_log_sentinel.py`
  - **Phase/Goal/Files/Deps**: E；跑login success/fail/lock/refresh/logout/core requests後掃nginx/app/audit/helper artifacts；依賴 T011、T024、T040、T046。
  - **Notes/Test/AC**: encoded/nested/duplicate/casing/exception sentinel raw值0次，ordinary diagnostics保留；PASS。
  - **Risk/Parallel/Commit**: scanner不可把fixture source本身當runtime leak；可與T047–T051平行；可獨立commit。

- [X] T053 [US4] 驗證 synthetic-data與credential evidence helper 於 `scripts/verify_demo_data.py`、`tests/security/test_remote_management_activation_gate.py`
  - **Phase/Goal/Files/Deps**: E；確認只用demo資料/credential且evidence不含secret；依賴 T046、T049、T052。
  - **Notes/Test/AC**: production-like/未知資料來源、共用credential或缺evidence fail closed；測試synthetic evidence PASS但不標012 T008完成。
  - **Risk/Parallel/Commit**: 不任意修改production-like資料；不可平行於其依賴；可獨立commit。

- [X] T054 [US1] 執行 production profile automated acceptance 並更新 `specs/013-remote-management-public-access/validation-result.md`
  - **Phase/Goal/Files/Deps**: E；彙整STAFF/admin、tenant、route、Next、auth concurrency、LINE與sentinel結果；依賴 T047–T053。
  - **Notes/Test/AC**: SC-001～SC-010 automated evidence完整，實際host/secret去敏；若012 T008 pending明列`CODE COMPLETE / ACTIVATION BLOCKED`。
  - **Risk/Parallel/Commit**: 不以local loopback冒充public runtime；不可平行；文件可獨立commit。

- [X] T055 [US4] 完成012 T008外部事件處置並保存去敏證據於 `docs/security/credential-url-incident-runbook.md`、`specs/012-sensitive-data-transport-hardening/runtime-incident-result.md`、`specs/013-remote-management-public-access/validation-result.md`（2026-09-05；ngrok historical capture/retention 保留為 `UNVERIFIABLE` residual risk）
  - **Phase/Goal/Files/Deps**: E；授權人員證明old demo password rejected、new accepted、old sessions revoked及外部log/history檢查；依賴 T053。
  - **Notes/Test/AC**: 依runbook操作ngrok/browser/remote環境，保存操作者與UTC evidence reference但無credential；未授權或未完成時保持unchecked。
  - **Risk/Parallel/Commit**: 此為activation blocker而非coding blocker；不可由測試fixture取代；完成證據可獨立commit。

- [ ] T056 [US4] 執行真實 `shared-demo-production` public smoke 於 `specs/013-remote-management-public-access/validation-result.md`
  - **Phase/Goal/Files/Deps**: E；在reserved HTTPS host驗證public login、核心journeys、deny與log；依賴 T054、T055。
  - **Notes/Test/AC**: production build唯一主要evidence，10次journey至少9次<3分鐘，所有deny不達upstream；不記完整host credential/query。
  - **Risk/Parallel/Commit**: 012 T008未完成不得執行或宣告ready；不可平行；evidence可獨立commit。

- [ ] T057 [US4] 執行真實 rollback drill 並記錄 5-minute evidence 於 `specs/013-remote-management-public-access/validation-result.md`
  - **Phase/Goal/Files/Deps**: E；先management public success=0，再remote sessions revoke，LINE success=100%；依賴 T056。
  - **Notes/Test/AC**: <300秒，舊access/refresh失效，local/LIFF sessions保留，log sentinel仍0；PASS才可標activation-ready。
  - **Risk/Parallel/Commit**: route deny失敗時不得先撤session並宣告rollback成功；不可平行；evidence可獨立commit。

## Final Phase — Polish, Quality Gates, and Scope Review

- [X] T058 [P] 執行完整 Python quality gates 並記錄於 `specs/013-remote-management-public-access/validation-result.md`
  - **Phase/Goal/Files/Deps**: Final；執行`ruff check .`、`ruff format --check .`、`pytest`、適用mypy與Alembic single-head；依賴 T054（runtime manual不必先完成）。
  - **Notes/Test/AC**: 全部PASS，不skip/放寬；失敗保留command與摘要；符合Constitution X。
  - **Risk/Parallel/Commit**: 可與T059平行；只更新evidence，不獨立production commit。

- [X] T059 [P] 執行完整 frontend/gateway quality gates 並記錄於 `specs/013-remote-management-public-access/validation-result.md`
  - **Phase/Goal/Files/Deps**: Final；執行Vitest、typecheck、lint/format、Next production build、Playwright、`nginx -t`、shell checks；依賴 T054。
  - **Notes/Test/AC**: production manifest來自本次build，line-only/shared matrices PASS；不使用dev結果替代。
  - **Risk/Parallel/Commit**: 可與T058平行；只更新evidence，不獨立production commit。

- [X] T060 完成 final scope/self-review 於 `specs/013-remote-management-public-access/validation-result.md`、`specs/013-remote-management-public-access/tasks.md`
  - **Phase/Goal/Files/Deps**: Final；逐項確認無broad wildcard、remote platform/PII、Redis/MFA/OAuth/SSO/cookie/WAF/VPN/CDN/CSP scope creep；依賴 T058、T059，activation-ready另依T055–T057。
  - **Notes/Test/AC**: `git diff --check` PASS，列出status，LINE registry語意未變，012 T008 pending時final status明列BLOCKED而非ready。
  - **Risk/Parallel/Commit**: 不順手修Deferred；不可平行於final review；文件commit是否建立由使用者另行授權。

## Dependencies and Critical Path

```text
Phase A: T001→T002 ─┐
         T003→T004 ─┼→T005→T006→T007→T010→T011→T013
         T008→T009 ─┘                 T012───────┘

Phase B: T014→T015 ─┐
         T016→T017 ─┼→T019→T022
         T018───────┘
         T020→T021 ───────┘

Phase C: T022→T023→T024 ─┐
         T025→T026 ──────┼→T028→T035→T036
         T027────────────┘
         T009→T029→T030→T031→T032→T034
                    T033──────────────┘

Phase D: T037→T038 ─┐
         T039→T040 ─┼→T042→T043→T044
         T041───────┘

Phase E: T045→T046; T047–T052 parallel after code foundations
         T046+T049+T052→T053→T054
         T053→T055 (MANUAL) →T056→T057
         T054→T058 || T059 →T060
```

**Critical path**: T003→T004→T005→T006→T010→T011；T016→T017→T018/T019→T022→T023→T024→
T027/T028→T035→T036；T037→T038→T039/T040→T041/T042→T043→T044→T045/T046→T053→T055→
T056→T057→T060。

**Activation blocker**: 只有 T055 的真實 012 T008 evidence 阻擋 T056/T057 與 activation-ready；T001–T054、
T058、T059 的 coding/automated validation 不受阻擋。

## Parallel Execution Examples

- Phase A 起始可平行：T001、T003、T008；T007、T010、T012 在 repository primitive 完成後可平行。
- Phase B 起始可平行：T014、T016、T018、T020；compiler core、manifest、Host policy再於 T022收斂。
- Phase C 可平行撰寫：T023、T025、T027、T029、T033；renderer/helper/backend/frontend依各自測試完成。
- Phase D 可平行撰寫：T037、T039、T041；migration/lifecycle/revocation完成後才整合rollback。
- Phase E automated suites：T047、T048、T049、T050、T051、T052 可平行；T055–T057必須序列。
- Final：T058與T059可平行，T060最後執行。

## User Story Traceability

| Story | Primary tasks | Independent evidence |
|---|---|---|
| US1 STAFF core management | T029–T034、T047、T049、T054 | STAFF production journey + tenant matrix |
| US2 SHELTER_ADMIN boundary | T029–T032、T048、T049、T054 | Admin core success + platform/PII deny |
| US3 Login security | T001–T013、T025–T026、T052 | PostgreSQL concurrency + trusted IP + sentinel |
| US4 Explicit profile/rollback | T014–T024、T027–T028、T035、T037–T046、T050、T053–T057 | Profile matrices + activation gate + rollback |
| US5 LINE continuity | T016–T022、T036、T051、T057 | Both-profile LINE happy paths and unchanged registry |

## Implementation Strategy

1. **Security MVP**: 先完成 Phase A，獨立證明公開 login protection，但不公開 management。
2. **Policy before proxy**: Phase B 先把 route/profile/asset/Host contract編譯與驗證完成，再做nginx。
3. **Layered access**: Phase C 同時完成gateway default deny、FastAPI public-role縮限與scope-safe UI。
4. **Recoverability**: Phase D 完成session origin與rollback後，才允許進入public runtime acceptance。
5. **Activation last**: Phase E automated tasks先完成；012 T008真實evidence完成後才執行public smoke/rollback。

## Deferred / Explicitly Out of Scope

MFA、OAuth、SSO、cookie auth migration、Redis、WAF、VPN、Zero Trust、CSP/CDN redesign、
PLATFORM_ADMIN remote UI、PII reveal、volunteer/shelter governance及其他未列mutation均不建立本期
implementation task；若未來需要，另開feature與route-level security review。
