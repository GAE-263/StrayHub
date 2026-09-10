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
flag=false 維持非本機環境拒絕功能；true 缺 hub 會由 API settings／preflight 拒絕。
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
3. **Gate 先後**：本地 mock 不是實機 evidence。現有 production 與 acceptance gate 都要求
   `verified-YYYYMMDD-<40-char-tested-sha>`，且沒有 production 單帳號 feature flag。
   若缺該 SHA 的合法 production-like 實機 evidence，目前不能先填假值啟用再補證據。
   本機 demo smoke 可驗功能，但現有文件不允許拿它冒充 production-like evidence。
   **待決：批准獨立受控 pre-release 驗證入口／gate bootstrap 設計，或提供已合法取得且
   對應本次 SHA 的 evidence。此缺口尚未由本輪解決，不可繞過 staff gate。**
4. **單帳號階段**：取得已確認一般使用者及有效志工身份；不可猜 UID 或改角色湊測試。
   先 GET 保存原 API default 與各人綁定，404「無個人綁定」須與查詢失敗區分。
   在合法 gate 與另外批准的 runtime/config 載入後，明確批准各人 link 到待驗 ID。
   注意啟用 flag 是程序級，可能影響其他事件；需先核可這個影響範圍，不能宣稱只有兩人受影響。
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
