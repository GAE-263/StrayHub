# 志工照護回報：從 LINE 選單到 PostgreSQL

這份文件走一遍「志工在 LINE 上按下按鈕 → 一筆照護紀錄存進資料庫」的完整路徑，
對照實際程式碼與行號。寫給想接手或修改這條流程的人。

對應分支：`practice/line-flex-ui`。第 10 節說明這個分支相對 `main` 改了什麼。

---

## 1. 全景

```
志工手機 LINE
    │  按下 Rich Menu 按鈕
    ▼
LINE 平台  ──POST──▶  /v1/line/webhook
                          │
                          │ ① 驗簽章      verify_line_signature
                          │ ② 事件去重    claim_event
                          │ ③ 解析身分    _resolve_context
                          ▼
                   _handle_postback
                          │
                          ▼
              LineDraftConversationService
                          │  操作狀態機
                          ▼
                  DraftStateMachine  ◀──▶  care_report_drafts（暫存）
                          │
                          │  13 題答完 + 確認送出
                          ▼
                 ReportSubmissionService
                          │
                          ▼
                    care_reports（正式紀錄）
                          │
                          ▼
                 ai_processing_jobs（背景分析）
```

回覆訊息由 `line_message_presenter.py` 組成 Flex Message，經
`LineMessagingApiAdapter` 送回 LINE。

---

## 2. 進入點：Rich Menu

選單定義在 `infra/local/line-rich-menu.yaml`，五個按鈕：

| 按鈕 | 送出的 postback data |
|---|---|
| 開始照護回報 | `action=start_care_report` |
| 掃描 QR Code | （URI，開啟 LIFF） |
| 今日照護毛孩 | `action=list_reportable_animals` |
| 繼續未完成回報 | `action=resume_draft` |
| 聯絡工作人員 | `action=contact_staff` |

`scripts/sync_line_rich_menu.py` 把這份 YAML 轉成 LINE 要的 `areas` 座標陣列
並上傳。底圖尺寸固定 2500×1686。

---

## 3. Webhook 的三道關卡

進入點：`services/api/app/api/line_webhook.py:613`

### ① 驗簽章 — 確認訊息真的來自 LINE

`services/api/app/domain/line_webhook_security.py:11`

```python
expected = base64.b64encode(
    hmac.new(channel_secret.encode(), raw_body, hashlib.sha256).digest()
).decode()
if not hmac.compare_digest(expected, signature):
    raise DomainError("invalid_line_signature", ..., 401)
```

用**原始 bytes** 算 HMAC-SHA256，不是解析後的 JSON——所以 `line_webhook.py:614`
先 `await request.body()` 拿 raw body，之後才 `json.loads`。順序反了簽章就對不起來。

比對用 `hmac.compare_digest` 而非 `==`，避免時序攻擊。

### ② 事件去重 — LINE 會重送

`services/api/app/persistence/repositories/line_identity_repository.py:54`

LINE 在沒收到 200 時會重送同一個事件。每個事件有唯一的 `webhookEventId`，
`claim_event()` 拿它當鎖：

- `SELECT ... FOR UPDATE` 查 `line_webhook_events`，已存在就回 `(existing, False)`
- 不存在則在 **savepoint 內**插入；撞到 unique key 代表另一個交易搶先，
  退回去重讀（`line_identity_repository.py:76-89`）

用 savepoint 是關鍵：若不包 savepoint，`IntegrityError` 會讓外層交易整個不可用，
後續處理全部失敗。

回傳 `claimed=False` 時，`line_webhook.py` 直接記 `duplicate_ignored` 跳過。

### ③ 解析身分 — LINE userId 換成系統內的人

`line_webhook.py:65` `_resolve_context()`

`event.source.userId` → `LineWebhookSessionService.resolve()` → 拿到
`(user_id, organization_id, membership_id)`。

沒綁定會拋 `line_binding_required`，webhook 回覆一段 LIFF 連結請志工先綁定
（`line_webhook.py:85`）。**`organization_id` 從這裡開始貫穿全程**，是多租戶隔離的根據。

---

## 4. 狀態機：13 題怎麼問完

`services/api/app/domain/line_care_report_state.py`

### 必答的 13 題

`line_care_report_state.py:30`

| 代碼 | 中文 | 代碼 | 中文 |
|---|---|---|---|
| `care_completion` | 照護完成 | `walk_completion` | 散步完成 |
| `feeding` | 餵食 | `water` | 飲水 |
| `activity` | 活動力 | `urination` | 排尿 |
| `defecation` | 排便 | `resource_guarding` | 護食 |
| `human_interaction` | 對人互動 | `animal_interaction` | 對動物互動 |
| `emotion` | 情緒 | `walk_reaction` | 散步反應 |
| `appearance_special_status` | 外觀特殊狀況 | | |

散步佔兩題：`walk_completion`（有沒有散成）和 `walk_reaction`（散步時的反應）。
兩者的代碼空間不可混用，`line_care_report_state.py:160` 有專門的 `mixed_walk_code`
檢查——選項字典裡 `walk_completion.not_done` 和 `walk.not_done` 長得很像，這個檢查
防止塞錯欄位。

### 狀態順序

`line_care_report_state.py:61` `_NEXT_STATES`

```
selecting_animal → confirming_animal
  → answering_completion    （care_completion, walk_completion）
  → answering_feeding       （feeding）
  → answering_water         （water）
  → answering_activity      （activity）
  → answering_elimination   （urination, defecation）
  → answering_behavior      （resource_guarding, human_interaction,
                              animal_interaction, emotion, walk_reaction）
  → answering_special_status（appearance_special_status）
  → awaiting_media → awaiting_note → reviewing → submitting → submitted
```

一個狀態可以掛多題（`_STATE_QUESTIONS`，`line_care_report_state.py:77`）。
`next_answer_key()`（`:189`）決定現在該問哪一題，該狀態的題目全部答完才往下一個狀態走。

### 為什麼不信任前端送來的 step

`LineDraftConversationService` 的 docstring 說得很直接：

> 在 CRM Draft 上執行 Bot 對話，不信任 Postback 的 step 或權限欄位。

postback data 是使用者可以偽造的。所以 `answer_question()`
（`line_care_report_state.py:208`）會檢查送來的答案 key 是否等於**伺服器端算出的**
`next_answer_key()`，不符就拋 `unexpected_answer`。權限同理——每次送出前重查一次
可回報範圍（`line_draft_conversation.py:108`）。

### 上一步

`back()`（`line_care_report_state.py:222`）不只是退回狀態，還會**清掉該步驟以後的
所有答案**。因為前面的答案可能影響後面的題目，留著會產生矛盾的組合。

### 更換動物

`action=reselect_animal`：答案保留但全部標進 `reconfirmation_keys` 待重新確認，
**照片不沿用**（`clear_media`）。理由是照片綁定特定動物，換了動物就不再有效。

---

## 5. 每一步怎麼變成畫面

`services/api/app/application/line_message_presenter.py`

| 函式 | 行號 | 用途 |
|---|---|---|
| `question_bubble()` | `:185` | 一題一張卡片，含分類標題、進度條、選項 |
| `prompt_bubble()` | `:239` | 照片／心得這類非選擇題的提示卡 |
| `summary_bubble()` | `:289` | 送出前的答案摘要 |
| `celebration_bubble()` | `:366` | 送出成功的完成畫面 |
| `_progress_bar()` | `:72` | 第幾題／共幾題的視覺化 |
| `_choice_box()` | `:41` | 單一選項的卡片，可帶圖示 |

配色集中在檔案開頭 `:7-21`（`INK`、`CREAM`、`LEAF`、`GREEN_DEEP`、`WOOD`、
`PROGRESS`…），改主題只要動這一區。

選項文字受 `_LABEL_LIMIT = 20`（`:23`）限制——這不是設計選擇，是 **LINE 平台的硬限制**：
postback action 的 `label` 上限 20 字元，超過 LINE 會直接退回整則訊息。

`line_webhook.py:280` 的 `_reply_next_step()` 依當前狀態挑對應的 bubble，
是畫面與狀態機的接縫。

---

## 6. 送出：草稿 → 正式紀錄

`services/api/app/application/report_submission.py:39` `submit()`

送出前依序檢查，任一不過就中止，不會留下半筆資料：

1. **冪等** — 先用 `idempotency_key` 查有沒有送過，有就回傳原本那筆
2. 草稿存在且 `status == "active"`
3. `current_step` 必須是 `reviewing` 或 `submitting`——**不能跳過摘要確認**
4. **跨租戶檢查** — 草稿、動物、報告三者的 `organization_id` 必須一致，
   不一致回 404（不是 403，避免洩漏「這筆資料存在」）
5. 草稿綁定的志工與動物要和當下操作一致
6. `CareReportAnswers(...)` 建構時驗證 13 題到齊且完成代碼合法
7. 逐欄驗證選項代碼有效、需要備註的選項有填備註
8. 動物仍是 `active` 且仍在今日可回報範圍

那個 `idempotency_key` 就是 **LINE 的 `webhookEventId`**
（`line_draft_conversation.py:126`）。所以志工連按兩次送出、或 LINE 重送事件，
都只會產生一筆紀錄。唯一鍵定義在 `care_report.py` 的 `ReportIdempotencyKey`：
`(organization_id, volunteer_user_id, key)`。


### 已知問題：補充說明的檢查時機

13 題裡有 6 題帶「其他」選項（護食、人際互動、動物互動、情緒、散步反應、
外觀／特殊狀態）。這些選項的 `requires_note` 為真，選了就必須填文字。

但 `note_validator` 只傳給 `ReportSubmissionService`，**只有送出那一刻才檢查**
（`line_draft_conversation.py` 的 submit 分支）。中間沒有任何提示，而
`awaiting_media`／`awaiting_note` 兩步還照常顯示「略過照片」「略過心得」。

實測（2026-08-21）走出來的結果：

```
05:13:11  第 8 題選「其他」      ← 義務在此產生，無提示
05:13:14 ~ 05:13:37  又走 5 題、略過照片、略過心得、看摘要
05:13:41  送出 → failed: observation_note_required
```

**系統先邀請志工略過，再因為他略過而拒絕他。** 錯誤訊息「此選項需要補充說明」
也沒有指出是 13 個答案裡的哪一個。草稿會停在 `reviewing`，答案不會遺失——
在摘要按「修改」可退回心得補填（`back()` 在這兩個狀態不清除任何答案）。

規格只要求「選『其他』或需補充的選項時要求文字」（FR-023），**沒有規定檢查
時機**，所以修正不需要偏離規格。可行的最小修法有兩個，尚未實作：

1. `_reply_next_step` 在 `AWAITING_NOTE` 時檢查答案裡有無需補充的選項，
   有的話換掉文案並拿掉「略過心得」按鈕
2. `observation_note_required` 的訊息帶上分類與選項名稱

還有一層模型上的粗糙：`requires_note` 是**每個選項**的屬性，`note` 卻是
**整份回報共用一個欄位**。所以在心得欄打任何文字都能通過，即使內容與該選項
無關。要真正解決得引入每題補充欄位，那會動到領域模型與規格。

---

## 7. 資料落在哪些表

`services/api/app/persistence/models/`

### 暫存 — `care_report_drafts`（`care_report_draft.py:9`）

| 欄位 | 說明 |
|---|---|
| `opaque_token_digest` | 草稿 token 只存**雜湊**，原始 token 只出現在 postback data |
| `current_step` | 狀態機當前狀態 |
| `answers` | JSON，逐題累積 |
| `reconfirmation_keys` | JSON 陣列，換動物後待重新確認的題目 |
| `expires_at` | 過期時間，TTL 預設 86400 秒（24 小時，`settings.py:35`） |
| `status` | `active` / `submitted` / `cancelled` / `expired` |

### 正式 — `care_reports`（`care_report.py:22`）

| 欄位 | 說明 |
|---|---|
| `answers` | 13 題的最終答案 |
| `answer_snapshots` | 送出當下的選項顯示名稱快照 |
| `animal_name_snapshot`、`shelter_number_snapshot` | 動物資訊快照 |
| `draft_id` | unique，一份草稿只能產生一筆紀錄 |
| `ai_job_status` | 預設 `pending_enqueue` |
| `status` | 預設 `saved` |

**為什麼要快照**：選項字典和動物資料日後會被管理端改動。若不留快照，半年前的
紀錄會隨著字典更新而改變意思，歷史就不可信了。

### 其他

- `care_report_media` — 紀錄與照片的關聯
- `media_assets` — 照片本體的中繼資料（`exif_removed` 預設 `True`）
- `report_idempotency_keys` — 送出去重
- `care_report_corrections` — 事後更正的前後值與理由

---

## 8. 照片

志工在 `awaiting_media` 步驟傳圖時：

1. `LineImageService.attach_to_draft()` 用 message id 向 LINE 取原圖
2. 存進 MinIO，object key 為 `drafts/{draft.id}/{event_id}.media`
3. 建立 `media_assets` 並掛到 `draft_media_assets`

抓圖走的是 **`api-data.line.me`**，不是 `api.line.me`——LINE 的二進位內容在不同
主機上。這正是本分支修掉的 bug，見第 10 節。

失敗處理值得注意：照片處理失敗會把事件標成 `processed` 並回覆「照片處理失敗，
請重新傳送或略過照片。」，**而不是讓整個事件失敗**。因為讓 LINE 重送不會讓一張
壞掉的圖變好，只會讓志工卡住。

---

## 9. 送出之後：AI 背景分析

`ReportJobDispatchService.dispatch()` 在**交易提交之後**才呼叫，插一筆
`ai_processing_jobs`（狀態 `pending_enqueue`）。

回報本身不等 AI。志工收到的是「原始照護回報已保存。AI 分析將於背景處理，
不會阻擋本次回報。」這是刻意的降級設計——AI 掛掉不影響回報。

> **原本的缺陷（`main` 上仍存在，本分支已修）**
>
> `services/worker/app/handlers/ai_handler.py` 的 `AIJobHandler` 完整實作且有約
> 9 個測試檔覆蓋，但 `services/worker/worker.py` 的 `run()` 迴圈只呼叫
> `run_volunteer_iteration()`，從未載入或呼叫 `AIJobHandler`。結果是每一筆
> `ai_processing_jobs` 永遠停在 `pending_enqueue`。2026-08-20 實測確認。
>
> 那些測試全部用 `SimpleNamespace` 直接實例化 handler，從不碰資料庫，所以 CI
> 全綠卻掩蓋了缺失的生產接線。這是「單元測試覆蓋率高，接線卻沒人測」的典型。

### Worker 怎麼把 Job 跑完

`services/worker/app/handlers/ai_job_runner.py`

`AIJobHandler` 只做「呼叫供應商、判讀結果」，它拿到的是備妥的 job、report、
圖片位元組與允許的選項代碼。`AIJobRunner` 補上兩者之間的搬運：

1. **交還逾時工作** — `reclaim_stale(timeout_seconds=300)`，Worker 中途死掉的
   Job 不會永遠停在 `running`
2. **認領** — `claim_next()` 用 `FOR UPDATE SKIP LOCKED` 取一筆，寫入
   `claim_token` 後**立刻提交**。供應商呼叫可能耗時 30 秒，不該一直持有資料列鎖
3. **組裝上下文** — 讀 `care_reports`、經 `care_report_media` 取出照片並從
   MinIO 下載位元組、由 `ObservationRepository.effective_options()` 取得
   `allowed_codes`
4. **執行** — 交給 `AIJobHandler.handle()`
5. **保存與釋放** — 寫入 `ai_observations`，再用 `finish()` 釋放 Claim；
   `finish()` 會比對 `claim_token` 與 `claimed_by`，別人的 Claim 動不了

### 失敗怎麼分類

| Handler 結果 | Job 最終狀態 | 理由 |
|---|---|---|
| `succeeded` | `succeeded` | — |
| `invalid`（驗證失敗） | `failed` | 決定性錯誤，同樣的輸入重跑一次仍然不會通過 |
| `failed`（供應商錯誤／逾時） | `retry_wait`，超過 3 次才 `failed` | 暫時性錯誤，值得再試 |

重試帶指數退避（60 秒起跳，上限 15 分鐘）。**沒有退避的話重試等於沒有重試**：
`finish()` 原本把 `available_at` 設成 `now`，同一輪迴圈會立刻重新認領，三次
重試在幾毫秒內燒完。本分支讓 `finish()` 接受 `available_at`，由呼叫端決定退避。

`retry_wait` 時會把 `report.ai_job_status` 改回 `enqueued`——這筆還會再試，
對工作人員來說它仍在排隊，顯示「失敗」是誤導。

### 兩條迴圈

`run()` 現在用 `asyncio.gather` 同時跑志工權限迴圈（60 秒）與 AI 迴圈（15 秒）。
分開的理由有二：志工作業卡住時 AI 佇列仍要消化；而志工送出回報後，不該等上
一分鐘才開始分析。

本機預設 `ai_provider=mock`（`settings.py:36`），`build_ai_client()` 會回傳
`MockAIAdapter`，所以展示流程不需要任何外部 AI 服務。要接真實供應商就設定
`AI_PROVIDER`、`AI_ENDPOINT`、`AI_API_KEY`。

---

## 10. 本分支改了什麼

相對 `origin/main`（`8d300cc`）：

### `483cbbf` — bug 修復

- **`messaging_api_adapter.py:107`** Rich Menu 底圖上傳原本送往 `api.line.me`，
  改為 `api-data.line.me`。LINE 的二進位上傳必須走 data host，原本底圖永遠上傳
  失敗，選單建了卻沒有圖、也無法綁定。**這是 `main` 上的既有 bug。**
- 同檔補上 LINE API 拒絕時的錯誤紀錄。呼叫端一律只看到通用 503，沒有這段就
  無法分辨是訊息格式錯誤還是 LINE 服務中斷。
- **`sync_line_rich_menu.py`** 新增 `columns` 支援網格排版；未指定時維持原本
  單列全高的行為。

### `c595397` — Flex Message 改造

問答介面從純文字加 Quick Reply 改為 Flex Message 卡片：分類標題、進度條、
圖示化選項、退回上一題的頁尾、送出後的完成畫面。配色集中為具名常數。
`line_message_presenter.py` +411 行，`line_webhook.py` +275 行，四個測試檔同步更新。


### `46c5120` — 格式

`ruff format --check` 對前一個 commit 的手寫換行失敗，套用 formatter 的輸出。

### `71cebe0` — 把 AI Job 接進 Worker

修好第 9 節描述的缺陷。新增 `services/worker/app/handlers/ai_job_runner.py`
承擔 Handler 與資料表之間的搬運，`run()` 改以 `asyncio.gather` 同時執行志工
權限迴圈與 AI 迴圈，`WorkerJobRepository.finish()` 改為接受 `available_at`
以支援重試退避。新增 `tests/integration/test_ai_worker_wiring.py`，四個測試
直接對資料庫驗證整條接線。


### `73874c3` — 修正本機種子語彙的顯示名稱

`scripts/seed_local.py` 的 `OPTION_NAMES` 以代碼後綴為 key，同一個後綴只能有
一個名稱。結果 `walk_completion.not_done` 與 `walk.not_done` 都顯示「未完成」，
而規格第 434 行明確說這兩者是不同的觀察類別；照護完成與散步完成更是五個選項
有四個字面相同，連續問兩題時看起來像同一題。

新增以完整 Code 為 key 的 `OPTION_NAME_OVERRIDES`，名稱取自 spec.md 的 FR-016
與「情緒與散步反應平台預設選項」表：`care_completion.completed` →「已完成照護」、
`walk_completion.not_done` →「未進行散步」等。`walk` 分類改名為「散步反應」，
共用後綴 `not_observed`／`uncertain` 統一為規格用語「未觀察」／「無法判斷」。

只改顯示名稱，不動 Code、狀態機或領域模型——規格明訂「Code 不依顯示名稱」。

---

## 11. 在這台 Windows 機器上跑

專案在 macOS 開發，Windows 需要三個環境修正，都不改動 repo：

```bash
# 依賴服務
docker compose -f infra/local/docker-compose.yml up -d postgres minio

# 測試
PYTHONUTF8=1 PYTHONPATH=<repo 根目錄> uv run --with tzdata pytest -q
```

| 修正 | 原因 |
|---|---|
| `PYTHONUTF8=1` | 測試用 `Path.read_text()` 未指定編碼，Windows 套 cp950，讀到原始碼裡的中文註解就爆掉 |
| `uv run --with tzdata` | Windows 沒有系統時區資料庫，`ZoneInfo("Asia/Taipei")` 會拋 `ZoneInfoNotFoundError`。**執行中的 API 也需要**（`animal_timeline.py` 少了它回 500），不只測試。`tzdata` 不在 `pyproject.toml` 裡 |
| `PYTHONPATH=<repo 根目錄>` | `pytest` 由 `pythonpath=["."]` 取得，但 `python services/worker/worker.py` 沒有，worker 會死在 `ModuleNotFoundError: No module named 'services'`。README 的 worker 指令在所有平台都失敗 |

本機測試帳號密碼都是 `local-only-password`。`local-staff-a` 對醫療歷史回 403 是
設計如此（`medical_care_access=false`），要看該面板用 `local-shelter-admin-a`。

---

## 12. 測試結果

2026-08-21 於本分支（`71cebe0`）執行完整套件：

```
1 failed, 481 passed, 1 warning in 131.05s
```

唯一失敗是 `tests/contract/test_gcp_iac_contract.py::test_terraform_format_and_validate`，
原因是這台機器沒有安裝 `terraform` CLI，該測試第一行就 assert 它存在
（`test_gcp_iac_contract.py:80`）。**與本分支的改動無關**——它檢查的是 Terraform
IaC 的格式，不碰 LINE 流程。裝了 `terraform` 或設定 `TERRAFORM_BIN` 就會通過。

LINE 相關測試全數通過，包含：

- `tests/integration/test_line_webhook_idempotency.py` — 事件去重
- `tests/integration/test_line_postback_flow.py` — postback 流程
- `tests/integration/test_line_draft_resume.py` — 草稿恢復
- `tests/integration/test_line_duplicate_submit.py` — 重複送出
- `tests/integration/test_line_unbound_user.py` — 未綁定使用者
- `tests/integration/test_line_image_message.py` — 照片訊息
- `tests/e2e/test_local_line_bot_vertical_flow.py` — LINE Bot 到 PostgreSQL 全鏈路
- `tests/integration/test_ai_worker_wiring.py` — AI Job 從資料表到供應商再回到
  `ai_observations` 的接線，含重試退避與 `run()` 必須啟動 AI 迴圈

---

## 13. 想改東西的話，改哪裡

| 想做的事 | 動這裡 |
|---|---|
| 加一題新問題 | `line_care_report_state.py` 的 `REQUIRED_ANSWER_KEYS`、`_STATE_QUESTIONS`、`_NEXT_STATES`、`_PREVIOUS_STATE`，加上 `line_webhook.py:209` `_answer_options()` 的 prefix 對照 |
| 改選項內容 | 管理端的觀察選項設定，或 `scripts/seed_observation_vocabulary.py` |
| 改卡片外觀 | `line_message_presenter.py:7-21` 的配色常數，或各 bubble 函式 |
| 改題目順序 | `_NEXT_STATES` 與 `_PREVIOUS_STATE` **要一起改**，兩張表必須對稱 |
| 改 Rich Menu | `infra/local/line-rich-menu.yaml`，再跑 `scripts/sync_line_rich_menu.py` |
| 改草稿保留時間 | `settings.py:35` 的 `draft_ttl_seconds` |
