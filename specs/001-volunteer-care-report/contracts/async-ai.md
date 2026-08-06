# AI 非同步 Job 契約

## 建立 Job

人工 Daily Care Report 成功保存後，CRM 可建立 AI Processing Job。Job 必須指向已保存的 Report、Shelter 與來源 Photo／Volunteer Note，不能由 AI 產生 Animal 或 Shelter 識別。

## 狀態

```text
pending -> running -> succeeded
                   -> failed
                   -> invalid
```

重試可由 `failed` 回到 `pending`，但不得覆蓋既有原始輸出或人工確認結果。

## 輸出規則

- 所有輸出都標示為 AI 輔助擷取。
- AI Observation 必須可追溯至來源 Photo 或 Note。
- 輸出需經結構驗證、白名單比對與禁用詞檢查。
- 診斷、健康正常、就醫決策、關注分數、等級、排序、正式狀態與正式識別碼不得成為正式結果。
- Job 失敗、逾時、無效或服務中斷不得改變人工 Report 成功狀態。

## Worker 契約

Worker 只能處理 CRM 指定的 Job，依 Job 的 Shelter 與來源關係讀取 Photo／Note；不得依前端傳入的 Shelter 或 Object Key 擴大範圍。完成、失敗、無效、重試與人工覆核都要留下可追溯狀態。

## 驗證重點

- AI 服務關閉時人工回報與 Timeline 仍可用。
- AI 回傳診斷語意時不會寫入正式 Observation。
- AI 不能變更志工選擇的 Animal、Shelter 或正式識別。
