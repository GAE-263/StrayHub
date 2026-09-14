# Rich Menu：資源發布與啟用分離

本文件是本地發布準備，不是 production／LINE 操作授權。不得因部署成功而假設
LINE 資源已發布；一般部署不會呼叫本工具。

## 工具契約

```bash
# 離線：不讀 .env、不建立 HTTP client、不寫 manifest
uv run python -m scripts.sync_line_role_menus \
  --roles default volunteer adoption_hub
```

預設僅上述三角色；staff、adopter 必須明確選入 `--roles`，本次不更新。
dry-run 檢查 YAML、圖片格式／尺寸／大小並列 definition/image SHA-256。
資源名稱帶角色及完整內容 fingerprint；名稱相同不是刪除、覆蓋或重用的依據。

以下為**下輪另行批准後**才可使用的資源發布入口，不是本輪已執行的操作：

```bash
uv run python -m scripts.sync_line_role_menus --apply \
  --roles default volunteer adoption_hub \
  --expected-bot '@APPROVED_BOT_BASIC_ID' \
  --manifest /approved/operator-directory/menus.json
```

憑證僅從 process 的 `LINE_CHANNEL_ACCESS_TOKEN` 取得，不放命令參數／manifest。
GET Bot info 的 basicId 必須與人工確認的正式 Bot 一致；manifest 另固定 Bot userId
的 SHA-256。Bot info 不提供 Channel ID，因此 Channel→Bot 的 Console 關係仍由 operator
先唯讀確認，不能聲稱此 API 驗證了 Channel ID。

`--apply` 不再刪同名資源、不設定 default、不 link/unlink、不回寫 env。
保留 `--no-write-env` 作無作用相容旗標；`--env-file` 明確拒絕並要求獨立審查設定。
Python `write_env()` 僅保留為既有顯式 export helper，不由 CLI 呼叫。

## 可恢復流程

1. 驗證 Bot、取得同一 manifest 的非阻塞檔案鎖。
2. 以角色、canonical definition、圖片 SHA-256 查已發布資源；逐欄比對 definition。
3. 唯一匹配才重用；多筆匹配停止。不清理舊資源。
4. 先 durable 寫 `create_intent` 再 POST 建立；回應不明時 GET list 查證。
5. 只有唯一結果才續行；零／多筆結果停止，保留 intent。重跑也不得盲目再次 POST create。
6. 保存 ID，再 GET definition/image；圖片不存在才上傳。上傳失敗保留進度，重跑先 GET，
   已上傳成功的不重傳；既有圖片不符停止，不覆蓋。
7. GET 圖片 hash 及 definition 皆一致才記錄 `ready / verified=true`。
8. 每筆保留階段時間歷程；中途失敗不標示整批成功、不回滾／刪除。每次重跑重新驗證 ready。

manifest 以 mode 0600 暫存檔、fsync、原子 replace 保存；lock 檔保留，避免換 inode
造成鎖競爭。必須跨主機由 operator 保證單一 publisher，檔案鎖不是分散式鎖。
不要遺失／編輯 unresolved intent，也不要換空 manifest「重試」；需先人工唯讀釐清結果。
資源 ID、Bot basicId、hash 是操作識別資料，不含 token、真人 UID 或其他 PII。

## 流程與責任

| 選單 | 原始定義／圖片 | actions／返回 |
| --- | --- | --- |
| default | `line-rich-menu-default.yaml` / `default.png` | 志工服務；`open_adoption_hub` |
| volunteer | `line-rich-menu-volunteer.yaml` / `volunteer.png` | 1250／1250：`walk_report`、`back_to_default_menu`；無 checkin |
| adoption_hub | `line-rich-menu-adoption-hub.yaml` / `adoption_hub.jpg` | matching / growth diary；切換成功訊息附返回 default quick reply |

圖片位於 `infra/local/rich-menu-images`，本輪不改圖片或 bounds。
hub 由 webhook 在會員解析之前處理公開領養入口；實際領養／日記保持各自的權限與流程。
quick reply 是切換當下的返回入口，不是第三個圖片按鈕，後續訊息可能取代 quick reply。
志工入口仍須 server-side binding、membership、有效 grant、收容所 scope；選單本身不授權。

| 程序 | 必要角色設定 | 時機 |
| --- | --- | --- |
| API | default、volunteer、staff、adoption_hub、flag、HTTPS origin、staff LIFF、smoke evidence | 身分／收容所接線與 webhook 互動 |
| Legacy Worker | default、volunteer、flag | 核准後與授權到期的角色同步 |
| Celery Worker／Beat | 不新增 Rich Menu 設定 | 不是角色綁定責任程序 |

API／Legacy Worker 的 default、volunteer 來自相同 Compose 變數。
API hub 新增 production Compose 接線；acceptance 原已接線，補一致的 preflight 檢查。
settings 有快取，改值須另行批准 runtime 載入，不是發布資源後立即生效。
flag=false 且 test=false 維持非本機環境原行為；受限模式見下方新流程。
true 缺 hub 會由 API settings／preflight 拒絕。
production 共用 gate 仍要求 staff menu、staff LIFF、完整 smoke evidence，不因本輪只測兩角色而略過。

角色同步為 best effort；綁定失敗不回滾已提交的業務交易。通知已標 sent 後，menu link
沒有獨立重試機制；不得重播核准通知補綁。本次不新增批次補償系統。

## 合成 dry-run 範例（非正式證據）

```text
[PLAN] default: definition=<64-char synthetic hash> image=<64-char synthetic hash>
[PLAN] volunteer: definition=<64-char synthetic hash> image=<64-char synthetic hash>
[PLAN] adoption_hub: definition=<64-char synthetic hash> image=<64-char synthetic hash>
DRY RUN: no network, no writes; create/reuse resources only; no activation.
```

Mock manifest 的 Bot 為 `@synthetic`、ID 為 `richmenu-new-*`。這些只供測試，絕不填正式設定。

## 下輪可分別批准的操作

1. **資源階段**：確認正式 Bot/Channel 後，僅 POST 建立／上傳三角色資源並 GET 回讀。
   不改 default／綁定，保留全部舊 ID、圖片、definition。確認三筆 ready 並保存 manifest。
2. **設定階段**：審查新 default／volunteer／hub IDs、既有 staff ID、staff LIFF、HTTPS origin；
   準備 API／Legacy Worker 一致設定、正式 CI 與 immutable release，但不自動批准啟用。
3. **Gate 先後**：採下方受限模式完成真實驗收，再取得完整報告；舊字串僅保留相容標籤，
   已不具全域啟用效力。本機 mock 永遠不能替代真人 evidence。
4. **單帳號階段**：取得已確認一般使用者及有效志工身份；不可猜 UID 或改角色湊測試。
   先 GET 保存原 API default 與各人綁定，404「無個人綁定」須與查詢失敗區分。
   在合法 gate 與另外批准的 runtime/config 載入後，明確批准各人 link 到待驗 ID。
   不啟用全域 flag。受限名單之外的 webhook／背景選單同步仍維持原行為。
5. 驗一般使用者 default→hub→matching/diary→返回，以及志工散步授權／返回／再次角色同步；
   到期／未授權與跨收容所持續拒絕。不得用補發通知驗證。
6. 兩帳號通過後，才另行批准 POST 全域 default。已有個人綁定不會因此更新；其他角色／
   批次綁定必須有另案範圍、清單及批准，不由資源工具執行。
7. **恢復僅提案**：保留舊資源；原本有個人綁定則另行批准 link 舊 ID，原本無綁定則
   另行批准 unlink；全域 default 回復原 ID 也需獨立批准。工具不自動恢復。

LINE 顯示優先序為個人 API 綁定、API default、Manager default；Manager/API 資源可見性
不同。參考 [官方概覽](https://developers.line.biz/en/docs/messaging-api/rich-menus-overview/)
與 [Messaging API](https://developers.line.biz/en/reference/messaging-api/)。

本輪本地測試不能證明正式圖片已上傳、正式設定已載入或真人選單已改變。

## 受限 smoke runbook（本地機制，不是執行 production 的授權）

### 判斷與責任邊界

`LINE_ROLE_MENU_FEATURES_ENABLED=false` 與 `LINE_ROLE_MENU_TEST_ENABLED=false` 是預設。
production 受限模式需全部提供以下受保護設定；名單只放 SHA-256，不放 raw UID：

| 設定 | 必要內容 |
| --- | --- |
| `LINE_ROLE_MENU_TEST_ENABLED` | 明確 `true`；撤銷時 `false` |
| `LINE_ROLE_MENU_TEST_CHANNEL_ID` | 已核對的 Messaging Channel ID，須等於 `LINE_CHANNEL_ID` |
| `LINE_ROLE_MENU_BOT_SHA256` | GET Bot info `userId` 的 SHA-256，不是 basicId 的 hash |
| `LINE_ROLE_MENU_TEST_USER_SHA256` | 1–10 個完整小寫 SHA-256，以逗號分隔；預設空、無 wildcard、不可重複 |
| `LINE_ROLE_MENU_TEST_EXPIRES_AT` | 有 timezone 的 ISO8601，啟動時須在未來七日內 |

Operator 先核對 Console 的 Channel→Bot 關係及既有配置憑證的 Bot；不能由 basicId
推導 Channel。API 只在原始 body 通過 X-Line-Signature 後，核對 payload destination 的
Bot hash，並對單一 `source.type=user` 事件設置 request-local 上下文；結束／例外即 reset。
query、自報未簽章 body、group/room、未知 UID 都不能取得受限權限。

API 身分交換／Legacy Worker 使用已验证 token 或 repository binding 的 UID，套用同一
scope predicate；preflight 比對兩程序 Channel、token、名單、Bot、期限與角色 IDs 一致。
不將此設定傳入 Celery。選單不代表授權，membership、有效 grant、tenant/RLS 原樣保留。
期限每次判斷，非僅啟動時；撤銷設定透過正式流程載入（settings 有 cache）。
到期／撤銷不會自動 unlink 已有選單，後續新功能事件 fail closed，須另行恢復個人綁定。
背景通知流程不重播；本功能只限制原有個人 menu link，不新增排程、push 或批次任務。

### 正式操作順序

1. Review／正式 CI 後建立 immutable candidate；透過正式流程先部署 global=false、test=false。
   本輪不能執行此步。確認 receipt、SHA、API/Worker/Web digests、健康後才繼續。
2. Operator 以安全方式確認一般領養者及**既有有效志工**，取得 Channel-bound UID hashes；
   不以顯示名稱猜測，也不改角色湊測試。另核對 Bot hash、四個 menu IDs、HTTPS、志工 LIFF。
   共用 production gate 要求既有 staff ID 與已審查 staff LIFF，不因只測兩人而略過。
   Staff LIFF 的正式 ID／HTTPS endpoint 與權限設計由 LINE 管理者及安全 reviewer 提供，
   必須在啟用 test=true **之前**備妥；未備妥時仍可部署兩 flag=false 的候選。
3. 透過既有 `/etc/strayhub/production.env` 管理流程配置上述 scope、期限及資源。
   檔案需 operator/root 控制，不能 world/group writable；不手改容器。
   保持 global=false，只啟用 test=true，正式 preflight／部署載入。受限模式不要求真人報告，
   但不豁免 HTTPS、staff、角色資源或身分／tenant gate。確認 API/Legacy Worker 範圍一致。
4. **另行批准個人 LINE 寫入後**，GET 保存兩人的原綁定與平台 default；明確區分無綁定／
   查詢失敗。只 link 已核對帳號到既有新版資源，不改平台 default，不建／刪資源。
   由使用者確認畫面、按鈕與返回。matching 入口可能建立領養對話 draft，散步流程可能
   建立 care draft，須在該案例前另取得明確業務寫入授權；不得自行送出申請／回報或叫 AI。
5. Operator 保存 readback 的四角色完整定義／圖片摘要及真實案例證據。以下離線工具只產生
   **NOT RUN** 模板，不會聯絡 LINE、不會寫 PASS，也不會覆蓋既有報告：

   ```bash
   uv run python -m scripts.line_menu_smoke_evidence template \
     --config-env /etc/strayhub/production.env \
     --release-manifest /opt/strayhub/current/release-manifest.json \
     --resources /etc/strayhub/line-menu/resources.json \
     --report /etc/strayhub/line-menu/smoke.json --kind real-line
   ```

   `resources.json` 是受保護 readback 摘要，不是完整 publisher manifest；四個 key 必須為
   `default / volunteer / adoption_hub / staff`，每項為
   `{"id":"richmenu-…","definition_sha256":"<64 hex>","image_sha256":"<64 hex>"}`。
   新三角色可取既有 publisher manifest 中 `stage=ready, verified=true` 的相應三欄；
   staff 由既有 GET 定義 canonical JSON 與實際圖片 bytes 計算 hash，不重新發布 staff。
   Definition hash 必須包括 size/name/chatBarText/selected/areas/actions，不能只比名稱。
   Operator 仍須核對 hash 對應當前實際 LINE readback；離線驗證器不宣稱能自行查 LINE。

   完成的案例由受保護審核流程逐項填 result/source/reference；reference 為私有稽核紀錄
   的不透明識別，不放 UID、token、URL 或對話原文。未做項目維持 NOT RUN。
   `adopter.* / volunteer.* / staff.* / boundary.*` 需真人確認；
   `resources.readback` 需自動回讀檢查。兩角色 PASS 不替 staff PASS。
   Staff 測試需 LINE 管理者提供已確認且有既有 staff 資格的帳號並另批准加入測試名單；
   staff LIFF／tenant 案例於本階段執行，不改真人資格、不偽造結果。
6. 審核完成後，檔案保持 owner-controlled（例如 0600），將實際檔案 SHA-256 記入
   `LINE_ROLE_MENU_REPORT_SHA256`，再離線驗證：

   ```bash
   sha256sum /etc/strayhub/line-menu/smoke.json
   uv run python -m scripts.line_menu_smoke_evidence validate \
     --config-env /etc/strayhub/production.env \
     --release-manifest /opt/strayhub/current/release-manifest.json \
     --resources /etc/strayhub/line-menu/resources.json \
     --report /etc/strayhub/line-menu/smoke.json
   ```

   全域啟用前配置 `LINE_ROLE_MENU_REPORT_PATH`、`LINE_ROLE_MENU_RESOURCES_PATH` 為上述
   受保護檔案；`LINE_ROLE_MENU_RELEASE_MANIFEST` 必須是
   `/opt/strayhub/current/release-manifest.json`。Compose readonly mounts，缺檔不自動建立。
   preflight 對候選 bundle 的實際 manifest 驗證（切 pointer 前），runtime 啟動對 current
   manifest 驗證。preflight 額外比對實際 rendered API/Worker/Web image refs。
7. 所有真人案例、staff/HTTPS gate、review 與部署條件齊備後，**另行批准** global=true
   及平台 default／個人或批次切換；它們仍是不同操作。本工具不執行任何切換。
8. 失敗／期限到達：停用 test mode，保存證據；另依保存的精確原綁定恢復指定帳號，
   原無綁定者 unlink，不改其他人。不重播通知、不重建資源、不隱含 rollback。

### Evidence 契約及失效條件

Schema 1 分 `automated-fixture` 與 `real-line`。模板預設 automated-fixture/isolated-test；
即使把所有結果填 PASS，也不能通過真實類型 gate。單元測試可模擬 real-line 合約，
那只證明驗證器行為，不是真人證據。checksum 只證明內容一致，無法證明真人真的點過；
可信度來自受保護配置、稽核紀錄與 operator/reviewer 的真實確認，不能拿 hash 當簽名。

全域要求同一 git SHA、三映像 digests、Compose/bundle hashes、Channel/Bot、受限帳號 scope
fingerprint/期限、資源 hashes、
角色 IDs、公開 origin 與 LIFF 設定 fingerprint；七日內且非未來的報告、完整角色/案例。
缺報告、錯類型/身分/資源、過期、FAIL/NOT RUN 一律拒絕。未啟用兩個 flag 不讀報告。
只在 preflight／API 啟動讀報告，不在每次 webhook 讀檔；長時間運行期間的報告有效期
不是自動停機計時器，下次全域啟用/部署/啟動仍重新驗證。

**不接受等價 tree 替代 SHA**：PR head、merge SHA 或重新建置 images 改變都需重驗。
報告存外部受保護目錄，不 commit 到被測 SHA；同一 immutable release 從 test→global，
只可將 test flag 關閉；測試名單、Channel、Bot 或期限變更都會使 scope fingerprint 失效。
報告不保存 UID 或個別 UID hash，只保存整體 scope fingerprint。全域啟用時仍需保留受保護的
scope 設定供比對，且期限必須有效；到期後下一次 preflight／啟動會 fail closed。
舊 `verified-…` 標籤不再充分：現有 global=true 環境若只有舊標籤，下次啟動將 fail closed，
須先完成此受限驗收與報告管理；不得直接滾動更新。global=false/test=false 不受缺報告影響。

## 2026-09-10 本地驗證紀錄（未提交工作樹）

基底 HEAD：`b2bbf546eab3581713c916454d17b467df4cb769`。
分支：`codex/line-menu-safe-publication`。不是新 RC，沒有 commit／push。
發布測試皆使用 `httpx.MockTransport`，未使用正式 LINE 憑證或網路端點。

| 驗證 | 結果 |
| --- | --- |
| 修正前新增 regression | 2 FAIL：mock adapter 確實被呼叫 DELETE；API Compose 缺 hub key |
| 最終 targeted unit + GCE release/systemd/production/acceptance contracts | 197 PASS |
| 完整 `uv run pytest tests/unit -q --tb=short` | 921 PASS、2 FAIL；見下述基底比較 |
| 未修改 HEAD 的獨立 archive，相同 unit-only 指令／合成環境 | 900 PASS、同樣 2 FAIL |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS，932 files |
| `uv run mypy scripts/line_menu_publication.py scripts/sync_line_role_menus.py` | PASS |
| `uv run python scripts/check_sensitive_transport_policy.py` | PASS |
| 修改／新增檔案的 repository-native credential patterns scan | 無命中；不等於能偵測所有秘密 |
| `bash -n` 兩支變更 preflight | PASS |
| ShellCheck acceptance-preflight | PASS |
| ShellCheck production-preflight | FAIL：既有 line 225 SC2016；未修改基底同樣重現 |
| CLI 離線 dry-run | PASS：三角色 definition／image hashes，無 HTTP／manifest／env 寫入 |
| `git diff --check` | PASS |
| 全類型 pytest、DB isolation integration、Frontend/E2E、遠端 CI | NOT RUN；不能宣稱正式 Release Gate PASS |
| 真人 LINE／正式資源驗收 | NOT RUN；帳號與啟用 gate 尚待確認 |

Targeted 包含 `test_rich_menu_publication_safety`、`test_sync_role_menus_env_writeback`、
`test_line_role_menu_actions`、`test_settings_runtime_safety`、`test_line_volunteer_application_menu`、
`test_volunteer_worker_lifecycle`、`test_liff_exchange_states`，以及 GCE release、systemd、
production Compose、acceptance isolation 四份 contract tests。

完整 unit 比較使用合成 `LINE_CHANNEL_ID / SECRET / ACCESS_TOKEN / LIFF_ID` 及 `APP_ENV=test`。
兩個失敗都在 `tests/unit/test_volunteer_self_status_api.py` 的 line 46、169：預期 INFO
訊息但 caplog 為空；功能回傳斷言通過。基底副本在
`/tmp/strayhub-menu-baseline.tZ4thF`，不包含 `.env` 或本輪修改。
這只證明相同 unit-only 執行條件下的既有失敗，不推定完整 CI 的測試順序也必然失敗。
後續需獨立釐清 logging/caplog 測試隔離，不能刪除斷言取得綠燈。

SC2016 位於既有傳入容器的單引號 shell 程式，不在本輪變更行；未加 suppression。
目前 GCE workflow 的明列 ShellCheck 清單含 acceptance-preflight、不含 production-preflight；
本輪額外檢查 production-preflight 如實保留其失敗結果。

沒有啟動任何測試 container、consumer 或服務；沒有連入 Production／Acceptance。
原工作樹乾淨，沒有六個歷史架構檔可納入；本輪不 stage 任何檔案。

## 受限 smoke 機制本地驗證（2026-09-10）

本輪 parent `eedcf81d66fa1006ffbccd73ace0c9246ae9dc7f`；保留既有安全 publisher 與資源。
以下本機 PASS 都是合成測試，不是手機實機 evidence；正式 CI 狀態以 PR checks 為準。
本輪未操作 Production、Acceptance 或 LINE 平台。

| 驗證 | 本輪結果 |
| --- | --- |
| 最初新增兩個 regression，修改前 | 2 FAIL：缺帳號級入口；舊字串單獨仍可通過 gate |
| 同兩項修改後 | 2 PASS |
| 新真實 DB 回歸過程 | 發現 flow selector 在 gate 前建立非測試領養身分；已移到拒絕判斷之後 |
| Hub 重入 | 有既存 adoption flow 時，hub 不再誤判成 care postback；保留 draft |
| 最終 scope/evidence/preflight targeted | **103 PASS**；另加 scope fingerprint/expiry 反例後相關組 **100 PASS** |
| 實際簽章＋真實 DB＋mock LINE 新增測試 | PASS；涵蓋錯 Bot、非 scope、無效簽章、重複事件與 hub 重入 |
| 實際 preflight 內嵌 Python 以合成 render 執行 | scope/image mismatch 拒絕，正常資料通過 |
| `ruff check .` / `ruff format --check .` | PASS / 938 files formatted |
| 專案預設 mypy | PASS（26 source files） |
| Bash syntax / `git diff --check` | PASS |
| ShellCheck 0.11.0 production-preflight | 僅既有 SC2016（新版 line 250；HEAD line 225 同樣重現），未 suppression |
| 合成 `.env.production.example` 實際 Compose render | PASS，API/Legacy Worker test=false，Celery 無此設定 |
| GCE release/acceptance/Compose/systemd/platform contracts | **57 PASS** |
| sensitive transport policy | PASS |
| 完整 `uv run pytest`（最終 diff） | **2106 PASS / 2 SKIP / 2 baseline FAIL**；兩個 self-status caplog 失敗在乾淨 parent 同樣重現 |
| Frontend Vitest / typecheck / format / build | **496 PASS / PASS / PASS / PASS** |
| Generated contracts / Critical E2E | **PASS / 22 PASS** |
| 正式 CI | 提交後以 PR #16 最新 head 的 checks 更新；本段不預先宣稱 PASS |
| 真人手機／點擊／LINE 平台驗收 | NOT RUN |

最終測試命令（下述 DB 已清理；重跑時需先建立新的同等專用合成 DB，不得改指 production）：

```bash
UV_CACHE_DIR=/tmp/strayhub-uv-cache APP_ENV=test \
STRAYHUB_TEST_DATABASE_URL=postgresql://strayhub:synthetic-menu-only@127.0.0.1:55439/strayhub_test \
LINE_CHANNEL_ID=1234567890 LINE_CHANNEL_SECRET=synthetic-secret \
LINE_CHANNEL_ACCESS_TOKEN=synthetic-token LIFF_ID=1234567890-Synthetic \
uv run --no-sync pytest \
  tests/unit/test_line_menu_smoke_scope.py tests/unit/test_settings_runtime_safety.py \
  tests/unit/test_line_role_menu_actions.py tests/unit/test_line_volunteer_application_menu.py \
  tests/unit/test_volunteer_worker_lifecycle.py tests/unit/test_liff_exchange_states.py \
  tests/unit/test_rich_menu_publication_safety.py tests/unit/test_sync_role_menus_env_writeback.py \
  tests/unit/test_acceptance_line_menu_preflight.py \
  tests/contract/test_line_menu_smoke_wiring.py tests/contract/test_gce_secret_manager_contract.py \
  tests/contract/test_gce_release_contract.py tests/contract/test_gce_systemd_contract.py \
  tests/contract/test_gce_production_compose_contract.py \
  tests/contract/test_gce_acceptance_isolation_contract.py \
  tests/integration/test_line_menu_scoped_webhook.py tests/integration/test_volunteer_entry_resolver.py \
  tests/integration/test_adoption_webhook_flow.py tests/integration/test_line_webhook_runtime_rls.py \
  tests/integration/test_volunteer_access_notifications.py tests/integration/test_volunteer_access_approval.py \
  tests/integration/test_volunteer_access_expiration.py tests/integration/test_line_duplicate_submit.py \
  tests/security/test_line_webhook_signature.py tests/security/test_line_cross_tenant_postback.py \
  -q --tb=short
```

最終完整測試使用 `postgres:16-alpine`、tmpfs、localhost 55440 與專用
`strayhub-menu-final2-local-net`，沒有外部 volume 或共用服務。驗證前核對 labels、mounts
與 network 唯一使用者；完成後精確移除 container/network，名稱篩選確認無殘留。
前一輪 localhost 55439 的同等專用資源亦已精確移除。合成 DB 隨 tmpfs 移除、不可恢復；
未使用 prune，沒有刪除使用者資料或舊 LINE 資源。
