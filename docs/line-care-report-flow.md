# 志工照護回報：從 LINE 選單到 PostgreSQL

這份文件走一遍「志工在 LINE 上按下按鈕 → 一筆照護紀錄存進資料庫」的完整路徑，
對照實際程式碼與行號。寫給想接手或修改這條流程的人。

對應分支：`practice/line-flex-ui`。第 11 節說明這個分支相對 `main` 改了什麼。

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

| 按鈕 | 送出的 postback data | 做什麼 |
|---|---|---|
| 開始照護回報 | `action=start_care_report` | 列出今天可回報的動物供選擇 |
| 掃描 QR Code | （URI，開啟 LIFF） | — |
| 今日照護毛孩 | `action=list_reportable_animals` | 今日總覽：誰照顧過了、誰還沒 |
| 繼續未完成回報 | `action=resume_draft` | 回到未送出的草稿 |
| 聯絡工作人員 | `action=contact_staff` | 回一句引導文字 |

前兩者的分頁另有 `action=more_animals`／`action=today_overview` 兩個 postback，
只帶 `offset`，不是選單按鈕。

> 到 `7b3d515` 為止，前兩顆按鈕跑的是同一個 `if` 分支，回覆逐字相同——四格選單裡
> 有兩格做同一件事。見第 11 節。

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


### 新志工怎麼取得綁定

上面那句「請志工先綁定」講得太輕鬆了。實際上綁定**不是志工自己能完成的動作**，
而且本機環境的預設值讓它完全走不通。

陌生人加好友、按下選單，目前只會得到一個點了跳「系統錯誤」的連結，然後沒有下文。

四道關卡，本機環境一道都沒開：

| # | 關卡 | 現況 |
|---|---|---|
| 1 | LIFF App | `.env` 的 `LIFF_ID=fake-liff-id`，連結指向不存在的 App |
| 2 | 身分驗證器 | `APP_ENV=local` 且 `LINE_CHANNEL_ID` 以 `fake-` 開頭時，`configured_line_identity_verifier()` 回傳 `MockLineIdentityVerifier`，只接受 `local-id-token:` 開頭的假 token，真實 LIFF 的 id_token 一定被拒 |
| 3 | `/v1/line/bind` | `exchange_line_identity()`（`session_service.py:176-178`）查不到既有綁定就直接 403。**它是登入，不是註冊** |
| 4 | 綁定建立點 | 真正建立 `User` 與 `LineUserBinding` 的地方在 `volunteer_access_service.py:193-201`，由收容所處理志工申請時觸發 |

第 3、4 點是**刻意的設計，不是缺陷**。收容所不會讓任何人加個 LINE 就能回報動物
狀況，所以正規路徑是：

```
加好友 → 填志工申請（POST /v1/volunteer-applications）
      → 工作人員在管理端審核
      → 核准時建立 User + membership + LineUserBinding
      → 之後 LINE 才認得他
```

**未綁定的人什麼都做不了。** 檢查在伺服器端的 `_resolve_context()`，postback 帶
任何參數都繞不過去，`organization_id` 一律來自驗證過的 context。他看不到任何動物、
任何回報。缺的是體驗，不是安全。

要開放自助綁定需要三件事：在 LINE Developers 建 LIFF App 並把真實 LIFF ID 填進
`.env`；把 `LINE_CHANNEL_ID` 換成真實 Channel ID（否則驗證器還是走 mock）；確認
`APP_ENV` 與 channel_id 的組合不會落回 mock 分支。

由於 LIFF 端點必須是固定網址，而開發期間用的是會變動的 ngrok 隧道，這件事適合
等部署到有固定網域之後再做。


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


### 補充說明的檢查時機（`3d11d45`／`76ea523` 已修）

13 題裡有 6 題帶「其他」選項（護食、人際互動、動物互動、情緒、散步反應、
外觀／特殊狀態）。這些選項的 `requires_note` 為真，選了就必須填文字。

原本 `note_validator` 只傳給 `ReportSubmissionService`，**只有送出那一刻才檢查**。
中間沒有任何提示，而 `awaiting_media`／`awaiting_note` 兩步還照常顯示「略過照片」
「略過心得」。2026-08-21 實測走出來的結果：

```
05:13:11  第 8 題選「其他」      ← 義務在此產生，無提示
05:13:14 ~ 05:13:37  又走 5 題、略過照片、略過心得、看摘要
05:13:41  送出 → failed: observation_note_required
```

**系統先邀請志工略過，再因為他略過而拒絕他。** 志工的反應是放棄整筆回報，不是
回頭修改——在收容所現場那就是一筆丟掉的照護紀錄。

規格只要求「選『其他』或需補充的選項時要求文字」（FR-023），**沒有規定檢查
時機**，所以修正不需要偏離規格。`_reply_next_step` 現在在 `AWAITING_NOTE` 先呼叫
`_options_requiring_note()`：答案裡有需補充的選項時換掉文案、逐項列出是哪個分類
的哪個選項，並拿掉「略過心得」。失敗因此不再發生，而不是延後發生。

同一個 commit 也修掉文字訊息一律被當成心得的行為。志工在其他步驟隨口打一句話會
收到「目前步驟不接受心得」，讀起來像系統壞了；現在只有心得那一步把文字當心得。

**後續修正 `76ea523`：** 上面那張卡片列出項目時，分類名稱原本是從選項代碼的前綴
推出來的。「外觀／特殊狀態」的分類代碼是 `appearance_special_status`，它的選項卻
以 `appearance.` 開頭，推出來的鍵查不到標題，於是掉回印出原始代碼——志工在卡片上
看到的是「appearance：其他」。13 題裡只有這一題代碼與前綴不一致，其餘 12 題恰好
一致，所以原本的測試怎麼寫都不會發現。現在改走 `category_id` 外鍵認分類，與
`line_draft_conversation.py:54` 既有的作法一致，不再依賴代碼字串的巧合。

問題卡片的標題不受影響，它走的是 `_ANSWER_CATEGORY_CODES` 的答案鍵對應——這也是
為什麼只有必填卡片露餡。

還有一層模型上的粗糙**尚未處理**：`requires_note` 是**每個選項**的屬性，`note`
卻是**整份回報共用一個欄位**。所以在心得欄打任何文字都能通過，即使內容與該選項
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

動物名稱與收容編號的快照確實有寫入。`answer_snapshots`（選項顯示名稱的快照）
兩條送出路徑現在都會填；`1d8082f` 之前只有 LIFF／API 會填，見第 10 節。

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
主機上。這正是本分支修掉的 bug，見第 11 節。

失敗處理值得注意：照片處理失敗會把事件標成 `processed` 並回覆「照片處理失敗，
請重新傳送或略過照片。」，**而不是讓整個事件失敗**。因為讓 LINE 重送不會讓一張
壞掉的圖變好，只會讓志工卡住。

**2026-08-21 手機實測驗證**（在此之前這條路只有測試碰過，而測試是直接塞資料列、
不放真的檔案）：

| 檢查 | 結果 |
|---|---|
| MinIO 物件存在 | 234,142 bytes |
| 真的是 JPEG | 開頭 `ffd8ffe0` |
| EXIF 已剝除 | 前 4KB 無 `Exif` 標記，`exif_removed=True` 名副其實 |
| `media_assets` | `status=attached`、`content_type=image/jpeg` |
| Worker 取得圖片 | 無 `NoSuchKey`，Job 12 秒內 `succeeded` |

順帶澄清一件容易誤判的事：資料庫裡曾出現 3 筆 `failure_reason=NoSuchKey` 的失敗
Job，時間落在跑完整測試套件的當下。那是 e2e 測試直接寫入資料列、MinIO 裡沒有對應
物件，而當時剛好有 worker 在跑就把它們撿走了。**不是這條路的缺陷**，但它會讓人
以為是。測試與常駐 worker 共用同一個本機資料庫時要留意這點。

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

注意 `MockAIAdapter` 不管收到什麼都回 `{"observations": []}`
（`mock_ai_adapter.py:8`）。本機看到空的分析結果是它的定義，不是失敗——圖片與
心得都有送進去，只是 mock 不看。

### 待決定：同時有照片與心得時，來源標成哪一個

`ai_observations.source_type` 只有一個欄位，但一筆回報可以同時有心得與照片。
`ai_handler.py:141` 的判斷順序是心得優先：

```python
if current_source == "care_report" and note and report is not None:
    observation.source_type = "note"      # ← 有心得就在這裡結束
    observation.source_id = report.id
    return
if media_assets and ...:
    observation.source_type = "photo"     # ← 同時有心得時永遠走不到
    observation.source_id = media_assets[0].id
```

**只要同時有心得和照片，照片就不會被記為來源**，`source_id` 指向回報本身而不是
那張圖。2026-08-21 手機實測確認過：一筆有照片的回報，`source_type` 是 `note`。

目前影響是零，因為 mock 不產生任何 observation。接上真實供應商後才有影響：一個
主要靠影像判讀的模型，產出的觀察會被標成「來自心得」，工作人員覆核時循
`source_id` 找不到那張圖。而志工同時打字又拍照是最常見的情況，不是邊緣案例。

**現在不動，是因為現在無法驗證哪種標法才對。** mock 不產生 observation，也還沒
接真實模型，改了沒有東西能證明改對了。而真實模型很可能逐項標示來源（這一項來自
影像、那一項來自文字），那樣的話「整筆挑一個來源」這個模型本身就要換掉，先改
判斷順序等於白做。等接上真實供應商、看得到它實際回什麼，再決定：

1. 改判斷順序，有照片優先——一行的事，但反過來變成心得被吃掉
2. 改成陣列，或讓每一項 observation 各自帶來源——真正解掉，但動 schema 與領域模型

---

## 10. 管理端怎麼讀到這些資料

志工在 LINE 送出之後，工作人員從 Next.js 管理端看到同一筆資料。讀取路徑：

```
POST /v1/auth/login                     回傳 organizations 清單
    ↓
PUT  /v1/auth/active-shelter-context    必須先選定目前收容所
    ↑ 沒選的話所有管理端 API 回 409 shelter_context_required
    ↓
GET  /v1/management/reports             回報收件匣（列表）
GET  /v1/management/reports/{id}        明細，另含 media_ids 與 ai_observations
GET  /v1/animals/{id}/timeline          動物歷程，需 start_date／end_date
```

**多租戶隔離的入口就是那個 409**。`organization_id` 一律來自驗證過的 request
context，端點路徑與查詢參數都不接受——`animal_timeline.py:104` 的註解說得很直接：

> The organization scope comes from the verified request context, never
> from a query parameter or path segment.

角色也擋：Timeline 只有 `PLATFORM_ADMIN`／`SHELTER_ADMIN`／`STAFF` 能看
（`animal_timeline.py:109`）。

明細端點把結果包在 `{"report": ...}` 裡（`report_inbox.py:65`），列表則直接回陣列；
列表不計算 `media_ids`，只有明細會查 `care_report_media`。

### LINE 送出的回報沒有顯示快照（`1d8082f` 已修）

| 送出路徑 | `answer_snapshots` | `usage_service` |
|---|---|---|
| LIFF／API（`care_reports.py:297-329`） | 建立完整快照 | 有傳 |
| LINE Bot（`line_draft_conversation.py`） | 修正前**沒傳**，現已補上 | 同上 |

LIFF 路徑會為每一題組出 `category_code`、`code`、`display_name`、`description`
與 `source` 再交給 `ReportSubmissionService`；LINE 路徑建構同一個服務時兩個參數
都省略了。結果是 `care_reports.answer_snapshots` 存進 JSON `null`，Timeline 的
`observation_snapshots` 也是 `null`，消費端只能用**當前**語彙解讀裸代碼。

`plan.md:161` 要求「歷史回報保存當時的 Code 與顯示快照」。LINE Bot 是志工的
主要管道，卻曾是唯一不留快照的路徑。

**2026-08-21 實際發生過一次**：本分支把 `walk.exploring` 從「探索」改成
「願意探索環境」、`walk.not_done` 從「未完成」改成「未進行散步」。8/20 的回報
是用舊名稱記錄的，但因為沒有快照，那筆歷史紀錄在管理端的顯示文字就被當天的
改動一併改掉了。這正是快照機制存在的理由。

`line_draft_conversation.py` 現在比照 `care_reports.py` 組出 `answer_snapshots`
再傳進 `ReportSubmissionService`——該參數本來就存在，服務本身沒有改。分類同樣
走 `category_id` 外鍵認（`line_draft_conversation.py:54`），代碼前綴只當退路。

**2026-08-21 手機實測驗證**：一筆 Bot 送出的回報寫進 13 筆 `answer_snapshots`
與 13 筆 `observation_option_usages`，`animal_name_snapshot` 與
`shelter_number_snapshot` 皆有值。

> 注意：修正前的舊回報，欄位存的是 JSON `null` 而非 SQL NULL，所以
> `WHERE answer_snapshots IS NULL` 查不到它們。同樣的序列化行為也出現在
> `ai_observations.validated_ai_observation`。要回填舊資料得留意這點。

`usage_service` 補上的影響目前仍是零，因為使用次數只對組織自訂選項計算
（`observation_options.py:190`），現階段沒有自訂選項。等收容所開始自訂，
「這個選項被 N 筆回報使用」的計數才會需要它——但屆時 LINE 來的回報已經有紀錄，
不必回頭補。

---

## 11. 本分支改了什麼

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


### `b6e932c` — Rich Menu 底圖上傳依實際格式宣告 Content-Type

`upload_rich_menu_image` 把 Content-Type 寫死成 `image/png`。LINE 同時接受 PNG 與
JPEG，但在宣告型別與實際位元組不符時拒收，所以 JPEG 底圖永遠傳不上去。轉檔繞不過去：
實際使用的 2500×1686 底圖 JPEG 只有 371 KB，轉成 PNG 會膨脹到 1642 KB，超過 LINE 的
1 MB 上限。

新增 `content_type` 參數（預設仍為 `image/png`），由 sync 腳本依副檔名帶入。Port 介面
與 Mock Adapter 一併同步，並新增 `infra/local/line-rich-menu-2x2.yaml` 對應實際版面。

這個 bug 與 `483cbbf` 的主機錯誤**疊在同一個二十行的函式上**。覆蓋它的測試寫的是
`assert len(client.calls) == 3`——數對了呼叫次數，主機錯的、標頭錯的全都放行。
本次補上兩個斷言，分別守住 data host 與 Content-Type。

### `3d11d45` — 心得步驟不再邀請志工略過必填的補充說明

見第 6 節。修正前的失敗不是延後發生，而是先邀請再拒絕。

### `1d8082f` — Bot 送出的回報補上顯示快照與選項使用索引

見第 10 節。LINE Bot 曾是唯一不留快照的送出路徑。

### `4fe780b` — 測試清理時先刪除選項使用索引

`1d8082f` 讓 Bot 路徑開始寫入 `observation_option_usages`，那張表以
`care_report_id` 為外鍵，而兩個 e2e 測試的清理程序在刪 `care_reports` 之前沒有先
刪它，於是撞上 `ForeignKeyViolationError`。不是生產缺陷，是測試清理的順序問題。

值得記一筆的是**這次測試發揮了作用**。前面幾個缺陷都是測試沒抓到才藏住的；這一次
測試立刻擋下新引入的問題。差別在於那兩個 e2e 測試真的碰資料庫、真的走完整條路徑。

### `76ea523` — 必填補充說明的卡片不再顯示英文分類代碼

見第 6 節。2026-08-21 手機實測撞到，志工在卡片上看到「appearance：其他」。

### `3ee3c41` — 可回報動物清單不再靜默丟掉超過六隻的部分

清單以 `[:6]` 截斷且沒有任何提示。志工今天若被派了 8 隻，他只會看到 6 隻，剩下兩隻
在介面上完全不存在——沒有「更多」、沒有總數、沒有任何線索，他會以為今天就是這 6 隻。
在收容所現場，那是靜默漏掉的照護紀錄。

LINE 的 quick reply 上限是 13，6 是自己加的。改成一頁 12 筆，最後一格放「更多
（還有 N 隻）」帶 `offset` 往下翻。`offset` 來自 postback，當作不可信輸入處理。

取資料的方式一併改掉。原本用 `AnimalRepository.search("")` 撈出全組織所有動物，再用
Python 的 `in allowed` 過濾，最後才切前 6 筆——**切到哪幾隻取決於一個不相干查詢回傳
的順序**。改用新增的 `ReportableScopeRepository.active_animals()`，範圍直接下推到
SQL，並以收容編號、名字、id 排序。該查詢與 `active_animal_ids` 共用同一段 join，避免
兩份條件各自漂移；動物可能同時經由自身與所在區域命中，所以加上 `DISTINCT`。

### `7b3d515` — 今日照護毛孩改成真的今日總覽

「開始照護回報」與「今日照護毛孩」原本被寫進**同一個 `if` 分支**，回覆的訊息、動物
清單、後續流程逐字相同。四格選單裡有兩格做同一件事，而名字建立的預期是錯的——
「今日照護毛孩」聽起來會告訴你今天還剩哪幾隻沒照護，實際上只是再問一次要回報哪一隻。

現在它回一張總覽卡：今天範圍內的每一隻動物、各自今天回報了沒、已回報的顯示時間，
標頭給出「共 N 隻 · 已回報 M 隻」與進度條。點任何一隻就進回報流程。

兩個判斷值得記下：

- **「已回報」以整個收容所為準**，不是「這位志工回報過」。志工需要知道的是這隻今天
  有沒有人照顧，不是有沒有他自己照顧——否則兩個人重複做同一隻，真正沒人管的繼續沒
  人管。已封存的回報不算數。
- **一天的界線走收容所時區**（`local_day_range`），不是 UTC 午夜。台北的一天從
  UTC 16:00 起算，用 UTC 午夜切會把傍晚的回報算到隔天。

總覽一頁 8 隻，超過同樣用 `offset` 翻頁；計數描述的是一整天而不是當頁，否則分頁會讓
志工誤以為工作快做完了。

---

## 12. 在這台 Windows 機器上跑

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

## 13. 測試結果

2026-08-21 於本分支（`7b3d515`）執行完整套件：

```
1 failed, 508 passed, 1 warning in 110.11s
```

唯一失敗是 `tests/contract/test_gcp_iac_contract.py::test_terraform_format_and_validate`，
原因是這台機器沒有安裝 `terraform` CLI，該測試第一行就 assert 它存在
（`test_gcp_iac_contract.py:80`）。**與本分支的改動無關**——它檢查的是 Terraform
IaC 的格式，不碰 LINE 流程。裝了 `terraform` 或設定 `TERRAFORM_BIN` 就會通過。

> 用 `-k` 篩選子集執行時，`tests/integration/test_line_answer_snapshots.py` 可能因
> 執行順序改變而失敗（`ProactorEventLoop` 已關閉，共用連線池握著上一個測試的迴圈）。
> 這在乾淨的 `HEAD` 上同樣重現，是 pytest-asyncio 與共用 engine 的既有問題，跑完整
> 套件不會發生。

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
- `tests/unit/test_line_note_requirement_ux.py` — 必填補充說明的提示時機，含分類
  代碼與選項前綴不一致的案例
- `tests/unit/test_line_animal_paging.py` — 動物清單分頁，含「走完所有分頁應該剛好
  看到全部 30 隻」
- `tests/unit/test_line_daily_care_overview.py` — 今日總覽，含計數必須描述一整天而
  非當頁、一天的界線走收容所時區

---

## 14. 想改東西的話，改哪裡

| 想做的事 | 動這裡 |
|---|---|
| 加一題新問題 | `line_care_report_state.py` 的 `REQUIRED_ANSWER_KEYS`、`_STATE_QUESTIONS`、`_NEXT_STATES`、`_PREVIOUS_STATE`，加上 `line_webhook.py:209` `_answer_options()` 的 prefix 對照 |
| 改選項內容 | 管理端的觀察選項設定，或 `scripts/seed_observation_vocabulary.py` |
| 改卡片外觀 | `line_message_presenter.py:7-21` 的配色常數，或各 bubble 函式 |
| 改題目順序 | `_NEXT_STATES` 與 `_PREVIOUS_STATE` **要一起改**，兩張表必須對稱 |
| 改 Rich Menu | `infra/local/line-rich-menu.yaml`，再跑 `scripts/sync_line_rich_menu.py` |
| 改草稿保留時間 | `settings.py:35` 的 `draft_ttl_seconds` |
