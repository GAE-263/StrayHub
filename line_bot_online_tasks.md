# 正式 LINE 官方帳號上線任務

## 目標與已確認決策

讓正式 LINE 官方帳號向全體使用者提供可實際操作的領養、毛孩日記與志工功能，包含真實 AI 回覆／分析。完成不等於 CI PASS 或 image 已發布，必須確認手機操作、資料落庫、背景任務及既有使用者選單均正常。

- 工作人員使用 Google 登入 Web 後台，自行申請加入收容所，由該收容所管理員核准。
- Staff LINE 延後，維持 `LINE_STAFF_MENU_ENABLED=false`；Staff LIFF、staff 選單及 staff 真人案例不作為本次發布條件。
- 使用正式環境的專用測試收容所與明確可識別的測試資料，避免影響真實業務。
- 目前只有一個真人 LINE 帳號：先測一般使用者，再經正常志工申請／核准流程測志工；不偽造 UID、不直接改資料庫角色。
- 優先自動化部署、設定、資源 readback、測試資料準備與證據整理；保留一次集中手機驗收。
- 修正證據生命週期：保留首次真人驗收及精確版本綁定，同版本日常重啟不應因短期測試名單到期而要求重測。
- 文件供維運及未來工程師交接，避免分散、重複或互相矛盾的規則。

## 執行規則與授權邊界

本文件是待辦計畫，不是 commit、push、PR 修改、merge、workflow dispatch 或任何正式環境操作的授權。核取方塊初始全部未完成；歷史測試或審查不得直接當作新版本完成證據。

- 依序完成各階段；程式／工具修正先於 candidate 凍結及真人驗收。
- 外部操作前先 readback，列出精確資源、差異、影響及恢復方式，再依既有授權或取得該組操作的明確授權。
- 授權分組：repository 整合、外部資源與部署、測試資料與 LINE 受限操作、全域啟用與使用者遷移。不要要求使用者逐條操作命令。
- 不重用失敗 workflow 的 rerun 寫入授權；使用新 dispatch，雙 actor 均為 `yawan0203`、attempt 必須為 `1`，並重新驗證 authoritative release HEAD。
- 不輸出 credential、token、raw UID、完整環境變數或私人對話。敏感證據放受保護位置，不提交 Git。
- 失敗停止依賴步驟，保存已完成狀態；不得盲目重試外部 mutation、直接改角色、偽造真人 PASS 或自行 rollback。
- 安全審核服務容量拒絕應標示服務不可用，不得繞過或誤報成程式安全缺陷。
- 不修改無關檔案，不覆蓋使用者 staging；備份及 stash 在確認不再需要前保留。

## 參考文件與起始基準

- [工作人員帳號與權限治理](docs/staff-access-governance.md)
- [LINE 資源發布與受限驗收](docs/line-rich-menu-safe-publication.md)
- [GCE release 流程](docs/deployment/gce-release-process.md)
- [Production 設定契約](docs/deployment/production-config-contract.md)
- [LINE 角色選單](docs/line-role-menu-framework.md)

以下是規劃時的基準，執行前必須重新確認，不能直接作為 mutation guard：

| 項目 | 規劃時基準 |
| --- | --- |
| Repository | `GAE-263/StrayHub` |
| 文件分支 | `codex/staff-web-docs` |
| main | `bafde674ed5ed2b44b242951cc7535459bde0ba9` |
| release | `9d58d13e5ac634af9061288305bc548ec5e0ce8e` |
| Release PR | #20，最後查證為 OPEN／Draft |
| 官方帳號設定候選 | `@356imngb`，仍需核對正式 Bot／Channel 身分 |

## Step 1 — 保存工作與盤點實際環境

相依：無。外部盤點須有唯讀授權。

狀態：盤點完成；詳見 [Step 1 實際環境盤點](docs/deployment/line-bot-online-inventory.md)。未驗證或缺少的外部項目已分列後續步驟，並非全部發布前置條件已通過。

- [x] T01 保存六份文件、目前 staging 與原始 stash 的身分；記錄 branch、HEAD、修改清單，禁止覆蓋未保存內容。
- [x] T02 Readback main、release、PR #20、正式 deployment receipt 與運行 SHA，區分 repository 與 production 的實際版本。
- [x] T03 盤點 WIF authoritative ownership／claims、publisher／deployer SA、最小 IAM、Artifact Registry、manifest bucket、固定 numeric Secret Manager version、IAP／OS Login／sudo。
- [x] T04 盤點 LINE Bot／Channel 關係、Webhook、LIFF、公開 HTTPS、現有 default／個人 Rich Menu，以及可安全取得的遷移資料來源。
- [x] T05 盤點 API／Legacy Worker／Celery Worker／Beat 的 AI provider、憑證來源、broker、模型與必要設定；不能以範本值推論正式狀態。
- [x] T06 產出「已符合／缺少／設定不符／尚未驗證」差異清單，附各項阻擋階段、精確修正與恢復方案；符合契約的資源重用。

驗收：每個發布／部署／啟用前置條件都有證據或明確待辦，不把未驗證當成不存在。

## Step 2 — 完成必要文件、程式與契約修正

相依：T01；環境相關修正參考 T06。

- [x] T07 核對 Google 登入、收容所自行申請／管理員核准的實作，統一六份文件；runbook 改為單帳號分階段驗收，Staff LINE 明確排除。
- [x] T08 修正 `scripts/production_config_sync.py` 的鎖範圍：lock 涵蓋 rollback、checksum 核對與 failure receipt 寫入，防止交錯執行造成成功 receipt 與最終設定不符。
- [x] T09 為 Quick Reply 補上通用 13 項容量防禦，保持必要流程操作與返回行為；以具體超量案例鎖定截取／保留規則。
- [x] T10 補足 Rich Menu best-effort 失敗的安全錯誤分類，不記錄 response body、token、UID 或私人資料，不回滾已提交業務交易。
- [x] T11 核對領養／日記及志工涉及的真實 AI 路徑與 image／Compose 設定，補足必要接線；保留 API／Legacy Worker／Celery 邊界與 AI 失敗降級。
- [x] T12 先重現已知缺陷，再執行 targeted regression、workflow contracts、security、lint／type checks；修改範圍不得加入 Staff LINE 或其他產品功能。

驗收：已知會迫使真人驗收後改 SHA 的工作先完成；真實 AI 成功不能由 mock／unconfigured 結果替代。

## Step 3 — 分離短期測試資格與正式版本驗收證據

相依：T07；與 Step 2 一併完成後再凍結 candidate。

- [x] T13 定義有明確版本的新 evidence schema：分離短期測試 scope 與正式版本核准；舊 schema 不自動轉成永久核准。
- [x] T14 保留 bounded scope 的帳號、Bot／Channel、期限及 fail-closed 驗證；測試資格到期仍拒絕新測試操作。
- [x] T15 正式核准綁定精確 release SHA、三個 image digests、bundle／Compose、Bot／Channel、資源 hashes、受驗功能設定與可信核准紀錄。
- [x] T16 同一已核准版本重啟不依賴已過期測試名單；保留受保護的撤銷機制，缺證據、篡改、身分不符或撤銷均 fail closed。
- [x] T17 SHA／image／Bot／Channel／選單或受驗功能設定改變時要求重新驗證；不接受等價 tree 替代 SHA。
- [x] T18 單帳號各案例記錄當時角色、scope、時間及去識別證據參照；一般使用者與志工階段不得混用權限或偽造不同使用者。
- [x] T19 保持真人與自動化來源可區別；負向案例的受控 scope 變更須被明確記錄，不能用最終 scope 假稱所有案例都在同一狀態完成。
- [x] T20 更新 validator、模板、preflight、runtime、文件及測試；功能關閉且無 evidence 的部署保持可啟動。

驗收：首次真實 LINE 驗收仍必要；同版本日常重啟無須每七天重新手機驗收；新版本不沿用舊身分證據。

## Step 4 — 補齊可重複執行的操作工具

相依：Steps 2–3 的契約。

- [x] T21 沿用既有 publication／manifest／config-sync 工具，提供一致的 dry-run、精確 apply、readback、receipt 輸出，不建立第二套發布平台。
- [x] T22 補齊受限配置、正式核准版本啟用、個人／default 選單切換及分批遷移操作；production 設定不靠手改容器或複製 env。
- [x] T23 新增 workflow 寫入 operation 沿用雙 actor、attempt=1、精確 repository／release／SHA、operation-specific confirmation；credential 前及首次 mutation 前重新讀取 release HEAD。
- [x] T24 Publication 不隱含 deploy／promotion／migration；push main、release 與 PR events 保持 zero external writes。
- [x] T25 每個具外部效果的工具記錄已完成步驟、去敏結果與恢復資料；不確定 outcome 先 readback，禁止盲目重試。
- [x] T26 工具測試覆蓋 dry-run 零寫入、拒絕路徑、部分失敗、中斷、receipt 一致性與精確恢復；公用 API／業務 schema 不因文件整理而改動。

驗收：operator 無須手填 hashes、複製 secrets 或逐一更新使用者選單；工具可產生供批准的具體差異。

## Step 5 — 整合並凍結精確 release candidate

相依：Steps 2–4 完成；需 repository 寫入／整合授權。

- [ ] T27 將核准變更經獨立 PR 整合 main，確認沒有其他未核准 commits；重新審查 PR #20 最新完整累積 diff。
- [ ] T28 依當下授權與 exact-head guard 完成 release PR 流程，保留 history 與既有 release hotfix；不可沿用規劃時舊 SHA。
- [ ] T29 只採實際 release merge SHA、branch=release、event=push 的 runs，等待全部驗證完成，確認寫入 jobs skipped／not triggered。
- [ ] T30 確認完整 Python、frontend、critical E2E、contracts、security、Terraform／Compose 與 clean-SHA image checks；引用精確 SHA CI，不無目的重跑大型 suite。
- [ ] T31 凍結 candidate，記錄 release SHA 與驗證證據。後續 publication 的實際 image／bundle digests 須獨立記錄，不把 CI build 身分等同已發布 images。

驗收：精確 release SHA 全部驗證成功；真人驗收開始後不得為小型文件整理任意改 SHA。

## Step 6 — 準備外部條件，部署尚未全域開放的版本

相依：T06、T31；需外部資源、publication 與 deployment 授權。

- [ ] T32 只補齊已核准的外部差異，核對最小 IAM、authoritative WIF claims、numeric token version、Registry／bucket 與 AI 憑證，不重建已符合契約資源。
- [ ] T33 新 dispatch 執行 application publish，保存 immutable images、bundle、run／artifact IDs、digests 與 publication receipt。
- [ ] T34 另一筆新 dispatch 執行 deploy，使用已驗證 artifact；初次載入 global=false、test=false、staff=false。
- [ ] T35 自動驗證 deployment receipt、三映像、migration、API／Web、Worker／Beat、broker、公開健康及 AI 存取前置；驗證不重新發布或部署。
- [ ] T36 另行 LINE publication 僅建立／重用 default、volunteer、adoption_hub 三角色，保存 definition／image readback、immutable manifest 與 receipt；不切 default、不 link user。

驗收：同一 candidate 在正式環境健康運行，LINE 資源備妥，尚未向全體使用者切換。

## Step 7 — 自動準備受限測試

相依：Step 6；需測試資料與受限 LINE 操作授權。

- [ ] T37 建立專用測試收容所、明確標示的測試動物及業務資料，保存精確 ID／建立者／清理方式；事先處理公開目錄可見性，避免被誤認為真實待領養資料。
- [ ] T38 經正常流程建立 Google 管理權限及測試使用者；安排稍後志工申請／核准，不直接改資料庫角色或真實使用者資格。
- [ ] T39 經正式 LINE identity 流程確認單一真人帳號與 Bot／Channel，敏感識別只存受保護位置。
- [ ] T40 準備日記所需合法關聯資料、測試照片及可操作場景；限制通知接收者為測試人員，避免通知無關 staff 或使用者。
- [ ] T41 保存原 default 與測試帳號個人綁定，區分「無綁定」與讀取失敗；啟用有期限的 bounded scope，staff 維持 false。
- [ ] T42 自動產生手機操作清單、NOT RUN evidence 模板、事件追蹤與資料核對方式；預先跑完自動化前置檢查。

驗收：使用者拿起手機即可測試，不須自己建立資料、改設定或填驗證 hashes。

## Step 8 — 一次集中手機驗收

相依：T42 全部前置檢查通過。需要手機 LINE；Rich Menu 不在桌面 LINE 顯示。

- [ ] T43 一般使用者：開啟官方帳號、default → adoption hub → 領養流程，完成專用測試申請及返回；自動核對 webhook、tenant scope、資料落庫與畫面結果。
- [ ] T44 毛孩日記：用已準備關聯資料新增日記／照片、查看歷史與真實 AI 回覆；自動核對背景任務、provider、儲存與回覆狀態。
- [ ] T45 同帳號送出專用收容所志工申請，經正常管理員核准取得 active grant；API／Web 自動化處理準備與核對，互動 Google 登入由使用者完成。
- [ ] T46 有效志工：確認兩格選單、完成測試散步回報、返回 default 並再進領養流程；自動核對授權、落庫與角色同步。
- [ ] T47 依預先安排的受限操作確認未開放／過期／跨收容所拒絕案例，保留真實操作與自動判定的不同來源。
- [ ] T48 自動整理去敏 evidence 與精確 candidate 身分；真人只確認實際看見／操作過的結果，不將 mock 或偽造 webhook 寫為真人 PASS。
- [ ] T49 失敗只重驗受影響案例；若需改 release SHA／images，返回整合與 candidate 驗證，不沿用舊身分 evidence。

驗收：一般使用者與志工兩個階段均完成，真實 AI 成功且資料正確；集中一次不等於省略必要案例。

## Step 9 — 全域開放與既有綁定遷移

相依：Step 8 通過；需全域啟用及精確遷移授權。

- [ ] T50 驗證完整核准證據，以同一 immutable candidate 載入 global=true、test=false、staff=false，確認設定、receipt 與 runtime 健康。
- [ ] T51 設定新版 API default Rich Menu 並 readback；保留舊 default 資源與恢復映射。
- [ ] T52 依已核對的資料來源、舊資源及使用者清單產生遷移 dry-run；區分有效志工、公開入口、未知或例外綁定，禁止推測角色。
- [ ] T53 對核准清單分批切換個人 Rich Menu，逐筆記錄原／新 ID、結果及 readback；不授予或修改 membership，不刪除舊資源。
- [ ] T54 核對遷移覆蓋率與剩餘例外；未知綁定單獨處理，無法證明覆蓋完整時不得宣稱所有既有使用者已看到新版。

驗收：公開入口全域可用，已知目標使用者遷移完成。個人 Rich Menu 優先於 default，不能只改 default 就認定完成。

## Step 10 — 上線觀察、清理與交接

相依：Step 9。

- [ ] T55 自動觀察至少 30 分鐘：API 錯誤、Webhook 重送、背景任務、AI timeout、LINE 回覆失敗與 receipt 一致性。
- [ ] T56 依新 evidence 契約驗證同版本正常重啟，不因短期 scope 到期而要求真人重測；正式重啟須有明確操作授權與健康檢查。
- [ ] T57 按精確清單清理或封存測試資料，保留 audit／receipt；禁止廣泛刪除正式資料，保留未完成對話所需的一致性。
- [ ] T58 交付具體恢復方案：config／menu 舊新映射、精確恢復操作、失敗停止條件；不自動 schema downgrade、廣泛 unlink 或刪除資源。
- [ ] T59 交付集中維運指南與最終證據，包含官方帳號、release SHA、images、menu IDs、驗收／遷移結果、外部資源與例外。

驗收：觀察期間無未處理重大失敗，所有目標流程有證據，維運者知道如何查證、停止及恢復。

## 自動化測試清單

- [ ] V01 Actor／triggering actor／attempt／repository／event／SHA／confirmation／freshness／duplicate JSON，以及新增 operator 路徑的拒絕測試。
- [ ] V02 Push main／release／PR events 不執行 WIF、Secret Manager、Registry push、SSH／IAP、LINE write、GCS write、config sync 或 promotion。
- [ ] V03 Config-sync 競態、rollback、receipt 一致性、安全中斷與鎖生命週期。
- [ ] V04 Evidence 篡改、撤銷、錯誤版本／資源、過期 scope；同版本重啟不受測試期限影響，舊 schema 不自動永久核准。
- [ ] V05 單帳號申請前後權限、跨 tenant、Staff 關閉、Webhook 簽章及重送冪等。
- [ ] V06 領養／日記／志工完整流程、Quick Reply 容量、terminal 返回及 intermediate 行為。
- [ ] V07 真實 AI 成功證據、失敗降級、任務重送及 runtime import boundary；mock 僅用於相應的自動化回歸測試。
- [ ] V08 選單工具 dry-run、分批遷移、部分失敗、既有綁定保留與精確恢復。
- [ ] V09 依 diff 執行 lint／format check／type check、sensitive transport、secret scan、diff check，以及精確 candidate 必要完整 CI。

## 最終完成清單

- [ ] 正式官方帳號已對全體使用者開放公開入口。
- [ ] 手機能完成領養、毛孩日記與志工流程，資料與收容所權限正確。
- [ ] 真實 AI 可用，並有受控失敗降級及背景任務證據。
- [ ] 既有目標使用者的個人選單已完成遷移，例外已結案。
- [ ] 工作人員 Google Web 流程保持可用；Staff LINE 仍關閉。
- [ ] 同一核准版本可正常重啟，不依賴每七天重新驗收。
- [ ] 測試資源處理完畢，維運指南、證據與恢復方案齊備。

## 執行紀錄格式

每完成一項，更新 checkbox 並新增：日期、task ID、精確 SHA／資源身分、結果、去敏證據位置、剩餘例外。此處只記錄不敏感參照，不放 secrets、raw UID 或私人對話。

| 日期 | Task ID | SHA／操作身分 | 結果 | 證據參照／剩餘事項 |
| --- | --- | --- | --- | --- |
| 2026-09-14 | T01–T06 | main `bafde674...`／production `9d58d13e...` | Step 1 盤點完成 | [盤點與剩餘缺口](docs/deployment/line-bot-online-inventory.md)；六份既有 staged 文件保留待 Step 2 |

## LINE 平台參考

[LINE Rich menus overview](https://developers.line.biz/en/docs/messaging-api/rich-menus-overview/)：Rich Menu 僅在手機 LINE 顯示；個人 API 綁定優先於 API default，再優先於 Manager default。平台規則與 API 限制在正式操作前重新核對。


### Step 2 local validation (2026-09-14)

- Regression before fixes: 4 failures reproduced (rollback lock, two overflow cases, API Gemini wiring).
- After fixes: 264 targeted tests passed, covering config sync, terminal navigation, Compose, role menus, Celery import, runtime settings, release/manual gates, workflow contracts and sensitive transport.
- Ruff check / format check / sensitive transport script / repository secret scan / diff check: PASS.
- Mypy: NOT PASS; four identical baseline errors reproduced with original HEAD files via `--shadow-file`. No new diagnostics. Existing issues: missing PyYAML stubs, ZoneInfo/timezone assignment in webhook, and two old test typing errors. Full clean candidate CI remains required in Step 5.
- Quick Reply policy: preserve business actions; reject more than 12 non-return actions before mutating the message. No silent truncation. Existing bounded terminal builders and idempotence verified.
- Config-sync lock now covers rollback and failure receipt. Failure regression verifies a competing lock cannot enter until both complete.
- Gemini key/model passed to API for existing synchronous adoption/diary paths. No production flag changed, no real AI call or credential modification performed.
- Staff join flow verified in `google_authentication.py`: applicant submits organization; administrator review chooses approved role. Documentation corrected accordingly.
- Existing staged six documents included in Step 2; original stash remains preserved. No push or PR update.

### Step 3 local validation (2026-09-14)

- 197 targeted tests passed: schema 2 approval, legacy expiry, bounded scope, staff gate, runtime/preflight, GCE release contracts and sensitive transport. Fixtures are synthetic; no human or live LINE PASS was generated.
- Ruff / format / Mypy (four changed Python files), sensitive transport policy, repository-native secret scan and diff check: PASS.
- Schema 2 binds the historical scope, staged single-account observations, exact release/images/resources/configuration (including AI), and protected operator approval. Pending/revoked/tampered/duplicate-key/wrong-identity evidence fails closed.
- Same approved version validates after historical scope expiry with the test list removed. Bounded test access still expires; legacy schema 1 remains time-limited and is not auto-upgraded.
- Approval remains an operator attestation protected by file ownership and the deployment boundary, not a cryptographic signature or proof of human truth. Runtime caches require an explicit disable/reload for immediate revocation.
- No remote write, config sync, restart, publication, deployment, LINE API or credential access performed in this step.

### Step 4 local validation (2026-09-14)

- 309 targeted tests passed: offline plans, bounded settings, strict approval issuance, exact switches/restoration, partial/ambiguous failure, interruption, immutable receipts, config rollback/drift, manual actors/attempts/events, stale/duplicate release JSON, existing evidence/release contracts and sensitive transport. All clients/identities are synthetic; no live operation was executed.
- Repository Ruff / format (972 files): PASS. Mypy for nine Step 4 Python/test files: PASS. This does not replace the separately documented Step 2 baseline diagnostics.
- Shell syntax / ShellCheck 0.11.0, sensitive transport policy, repository-native secret scan and diff check: PASS.
- Reused publication manifest and atomic config-sync/preflight. Added protected private plans, separate config sync/reload/menu switch/restore dispatch operations, first-attempt exact-head gates before WIF/SSH and again on the VM. No default switch from bounded scope; no identity or membership edits.
- Fixed release bundle packaging to include host operator Python dependencies. API image includes scripts, so clean-SHA images remain required in Step 5 CI; no new image build or full Python/frontend/E2E rerun claimed here.
- Remote readback: main bafde674ed5ed2b44b242951cc7535459bde0ba9; release 9d58d13e5ac634af9061288305bc548ec5e0ce8e. No remote codex/staff-web-docs branch exists.
- Operational details and remaining external prerequisites: [LINE online operations](docs/deployment/line-online-operations.md). Authoritative WIF claims/ownership must be reviewed before enabling the new workflow; no external policy was changed.
- Next boundary: Step 5 repository push/PR integration requires explicit authorization. No push, PR edit, merge, dispatch, GCP/LINE mutation, publication, deployment, config sync or restart performed.
