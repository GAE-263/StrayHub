# AI 非同步 Job 契約

## 建立 Job

人工 Daily Care Report 成功保存後，CRM 可建立 AI Processing Job。Job 必須指向已保存的 Report、Shelter 與來源 Photo／Volunteer Note；LINE Image Message 必須先完成 EXIF 清理與重新編碼，AI 不得讀取 LINE 原始圖片。不能由 AI 產生 Animal 或 Shelter 識別。Job 建立時必須保存非空的 AI Provider、Model Name、Model Version／Snapshot、Prompt Template ID、Prompt Version 與 Output Schema Version；若呼叫失敗也不得遺失這些版本資訊。

## 狀態

```text
pending -> running -> succeeded
                   -> failed
                   -> invalid
```

重試可由 `failed` 回到 `pending`，但不得覆蓋既有原始輸出或人工確認結果。

## 輸出規則

- 所有輸出都標示為 AI 輔助擷取。
- AI Observation 必須可追溯至已完成 EXIF 清理的 Photo 或 Note。
- `raw_ai_output`、`validated_ai_observation` 與 `human_review_result` 必須分開保存。
- AI 原始輸出、模型版本與 Prompt 版本不得被人工修正覆蓋。
- 輸出需經結構驗證、白名單比對與禁用詞檢查。
- 診斷、健康正常、就醫決策、關注分數、等級、排序、正式狀態與正式識別碼不得成為正式結果。
- Job 失敗、逾時、無效或服務中斷不得改變人工 Report 成功狀態。

## Worker 契約

Worker 只能處理 CRM 指定的 Job，依 Job 的 Shelter 與來源關係讀取已清理的 Photo／Note；不得依前端傳入的 Shelter 或 Object Key 擴大範圍。Worker 每次處理都必須驗證 Job `org_id`、關聯資源 `org_id`、Organization 狀態、Job 狀態與 Care Report 存在。完成、失敗、無效、重試與人工覆核都要留下可追溯狀態。

## 驗證重點

- AI 服務關閉時人工回報與 Timeline 仍可用。
- AI 回傳診斷語意時不會寫入正式 Observation。
- AI 不能變更志工選擇的 Animal、Shelter 或正式識別。
