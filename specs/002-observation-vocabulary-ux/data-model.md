# 資料模型：觀察詞彙管理介面資訊架構與可讀性優化

本文件描述本功能需要沿用、擴充與驗證的正式資料及可重建衍生資料。CRM 的正式照護回報與歷史快照仍是唯一事實來源；衍生使用索引只能協助查詢與保護性規則。

## 實體總覽

```text
Organization／收容所
  ├── ObservationCategory（平台預設或收容所範圍）
  │     └── ObservationOption（平台預設或收容所自訂）
  │             └── ObservationOptionUsage（可重建衍生索引）
  ├── CareReport
  │     └── answer_snapshots（建立回報時的詞彙顯示快照）
  └── AuditRecord（詞彙異動與狀態轉換）
```

## ObservationCategory（觀察類別）

### 來源與用途

沿用現有類別資料；本功能只重新呈現，不提供建立、刪除、合併或改名。類別可為平台預設（沒有收容所歸屬）或收容所範圍，但本 MVP 以既有 13 個平台類別為主要資料。

### 欄位

| 欄位 | 規則 | 本功能用途 |
| --- | --- | --- |
| `id` | 穩定識別；歷史回報不以畫面顯示名稱取代 | 關聯選項與表單選擇 |
| `organization_id` | 空值代表平台預設；有值時只能屬於一個收容所 | 推導 source 與租戶範圍 |
| `code` | 既有英文 code，必須保留 | 顯示為類別中文名稱的次要資訊、關聯回報欄位 |
| `display_name` | 台灣繁體中文為主要名稱 | 顯示類別標題與篩選選項 |
| `description` | 可選的繁體中文說明 | 類別用途輔助理解 |
| `status` | 既有狀態規則；本 MVP 不由收容所頁面修改 | 決定類別是否可供新選項選擇 |
| `display_order` | 保留既有平台順序 | 決定 13 個類別的呈現順序 |
| `created_at`、`updated_at` | 沿用現有 audit timestamps | 回應與相容性檢查 |

### 類別固定清單

| 順序 | 中文名稱 | code |
| --- | --- | --- |
| 1 | 照護完成 | `care_completion` |
| 2 | 散步完成 | `walk_completion` |
| 3 | 進食 | `feeding` |
| 4 | 飲水 | `water` |
| 5 | 活動 | `activity` |
| 6 | 排尿 | `urination` |
| 7 | 排便 | `defecation` |
| 8 | 護食 | `resource_guarding` |
| 9 | 人際互動 | `human_interaction` |
| 10 | 動物互動 | `animal_interaction` |
| 11 | 情緒 | `emotion` |
| 12 | 散步 | `walk` |
| 13 | 外觀／特殊狀態 | `appearance_special_status` |

## ObservationOption（觀察選項）

### 欄位

| 欄位 | 規則 | 本功能用途 |
| --- | --- | --- |
| `id` | 穩定識別；不能因改名、停用或封存改變 | UI key、稽核 resource、使用索引關聯 |
| `category_id` | 必須指向可用的既有觀察類別；建立後不在本 MVP 跨類別移動 | 分組與後續回報欄位對應 |
| `organization_id` | 空值代表平台預設；有值時必須等於操作當下已驗證的單一收容所情境；平台管理員必須先切換有效情境 | source、權限與 RLS 邊界 |
| `code` | 小寫英文字母開頭；可含小寫英文字母、數字、底線、句點；不得有空白或大寫；目前收容所完整有效詞彙範圍唯一 | stable code 搜尋、回報值、歷史快照 |
| `display_name` | 不可為空白；以台灣繁體中文為主；保持適合手機回報的短名稱 | UI 主要文字、後續回報選項 |
| `description` | 可為空；使用簡短非診斷性繁體中文 | UI 次要說明與回報輔助 |
| `status` | `active`、`disabled`、`archived` | 控制新回報是否可選及管理篩選 |
| `display_order` | 非負整數；收容所自訂只能在同一類別的自訂集合內調整 | 自訂選項排序 |
| `requires_note` | 布林值 | 後續回報流程是否提示補充說明 |
| `created_at`、`updated_at` | 沿用既有時間欄位 | 最後修改時間、回歸與稽核對照 |

### 回應衍生欄位

這些欄位不必全部直接儲存在 `ObservationOption`，但 API 回應必須提供穩定語意：

- `source`：`platform_default` 或既有 wire value `organization_extension`；UI 顯示「平台預設」或「收容所自訂」。
- `enabled`：為相容既有 client，等於 `status == active`；不可作為唯一狀態來源。
- `editable`：只有收容所自訂且目前使用者有管理權限時為真；平台預設永遠為假。
- `has_historical_usage`：是否有至少一筆歷史回報使用該選項或該 code；查不到或使用索引不完整時採 true／鎖定策略。
- `historical_usage_count`：供管理者理解保留原因的可選數量；不在一般 Staff 唯讀畫面顯示不必要的管理細節。
- `last_modified_at`：沿用 `updated_at`。
- `updated_at`：作為編輯表單的版本條件；更新請求必須帶回表單載入時取得的值，避免過期寫入覆蓋他人修改。
- `last_modified_by`：從最新相關 AuditRecord 解析；沒有可對應 actor 時顯示「系統」或「平台預設」。

### 不變條件

1. 平台預設 option 的 `organization_id` 不可被收容所管理操作修改。
2. 收容所自訂 option 的 `organization_id` 建立後固定，不可移交給其他收容所；建立與每次 mutation 均以操作當下已驗證的單一 Shelter Context 綁定。
3. `code` 在新增、未使用自訂 option 修改時都必須通過格式與目前收容所 effective vocabulary 唯一性檢查。
4. 一旦 `has_historical_usage` 為真，`code` 不可修改；狀態仍只能使用非破壞性生命週期。
5. 不提供硬刪除；`disabled` 與 `archived` 都不會出現在新回報的有效選項集合。
6. 修改 `display_name`、`description`、`requires_note` 或 `status` 不會改寫既有 `CareReport.answer_snapshots`。

## Option lifecycle（選項生命週期）

```text
                 ┌──────────────┐
                 │   active     │
                 └──────┬───────┘
                    disable│  │archive
                          ▼  ▼
                 ┌──────────────┐
          restore│  disabled    │archive
                 └──────┬───────┘
                    restore│
                          ▼
                 ┌──────────────┐
                 │   archived   │
                 └──────┬───────┘
                    restore│
                          ▼
                       active
```

狀態規則：

- `active`：出現在新的回報表單；管理者可停用或封存自訂項目。
- `disabled`：不出現在新的回報表單；管理者可恢復或封存；歷史仍可查詢。
- `archived`：不出現在新的回報表單；管理頁可依狀態查看；本 MVP 允許具權限管理者恢復，但不刪除歷史或稽核。
- 平台預設的狀態只可由平台治理資料來源變更；收容所頁面不提供平台預設的狀態轉換。
- 每次狀態轉換必須原子地更新 option、AuditRecord 與回應結果；失敗時三者都不得對使用者宣稱成功。

## ObservationOptionUsage（觀察選項歷史使用索引）

### 定位

這是可重建的衍生資料，不是 CRM 的另一個正式事實來源。它支援：

- 判斷自訂 stable code 是否已被歷史回報使用；
- 顯示管理者需要保留選項的原因；
- 避免每次管理頁載入都逐一掃描 `care_reports` JSON；
- 支援歷史回報使用過但目前 option 已停用／封存的資料。

### 欄位

| 欄位 | 規則 |
| --- | --- |
| `id` | 索引自身的穩定識別 |
| `organization_id` | 必填；只能是該 CareReport 的收容所範圍 |
| `care_report_id` | 必填；指向正式 CareReport |
| `observation_option_id` | 可空；若目前仍可對應 option 則填入，對應不到的舊 code 保留 null |
| `category_code` | 回報當時的類別 code 快照 |
| `option_code` | 回報當時的 stable code 快照 |
| `display_name` | 回報當時的中文名稱快照 |
| `description` | 回報當時的必要說明快照，可空以相容舊資料 |
| `created_at` | 建立索引或回填索引的時間，不代表原始回報時間 |

### 建立與重建規則

- 新 CareReport 成功建立後，依同一筆回報的答案與 `answer_snapshots` 建立 usage rows。
- CareReport 觀察修正時只追加新的 code 使用記錄，不刪除原本的 usage row，保留修正前後歷史。
- migration 優先讀取 `answer_snapshots` 的 code、display name、description；沒有 snapshot 時讀取 `answers` 的 category／code，並以當時可解析的 option 資料補充顯示名稱。
- 無法對應目前 option 的舊資料不得丟棄；以 `observation_option_id = null` 保留其 code，讓任何相同 code 的新／既有 option 都採保守鎖定。
- 提供可重複執行的重建或校正入口；重建不修改 CareReport 原始答案與快照。
- 使用索引的 RLS 必須以 `organization_id` 隔離；跨收容所資料不可因 option code 相同而合併。

### 故障策略

- 建立 usage index 失敗時不得回滾已保存的人工回報；回報仍是正式 CRM 事實來源。
- 管理頁無法確認 usage 狀態時，顯示「歷史使用狀態待確認」並鎖定 stable code 編輯；不得以 false 當作未使用。
- 使用索引與 CRM 回報不一致時，以 CareReport／snapshot 重建並留下稽核或維護紀錄，不由 UI 靜默修正歷史資料。

## CareReport.answer_snapshots（歷史顯示快照）

沿用既有 `care_reports.answer_snapshots` JSON 欄位。新建立的回報應保存至少：

```json
{
  "emotion": {
    "category_code": "emotion",
    "code": "emotion.calm",
    "display_name": "平靜",
    "description": "觀察到的情緒表現",
    "source": "platform_default"
  }
}
```

相容規則：

- 既有只有 `code` 或 `display_name` 的 snapshot 原樣保留，不以現在的名稱覆寫。
- 歷史檢視若缺少新欄位，仍顯示原有 code／名稱，並清楚標示資訊不可由目前詞彙設定回推。
- option 的重新命名、停用、恢復、封存與未使用 code 修正都不能變更舊 snapshot。
- 回報修正新增的 code 使用記錄不會抹除原始 snapshot；歷史檢視依既有 correction／timeline 規則呈現前後內容。

## AuditRecord（詞彙變更稽核）

沿用既有 `audit_records` 與 `AuditService`。觀察選項異動至少使用下列 action：

| action | 觸發時機 | before／after 必要內容 |
| --- | --- | --- |
| `observation_option.created` | 新增自訂 option | category、code、name、description、order、requires_note、status、source |
| `observation_option.updated` | 編輯名稱、code、說明、排序或補充說明 | 只列出真正變更的欄位及前後值，並保留 option scope |
| `observation_option.reordered` | 重新排序 | 每個受影響 option 各自的前後 order 與 category，並帶共同 `operation_id` |
| `observation_option.disabled` | 確認停用 | 原／新 status、option code、name、歷史使用旗標 |
| `observation_option.restored` | 確認恢復 | 原／新 status、option code、name |
| `observation_option.archived` | 確認封存 | 原／新 status、option code、name、原因（若有） |

稽核 invariants：

- `organization_id`、`actor_user_id`、`resource_id`、時間與 `source_channel` 對 ObservationOption mutation 不可為空；平台預設不由一般收容所 mutation 產生。
- `operation_id` 對所有 ObservationOption mutation 不可為空；新的單次 mutation 產生新的 UUID，同一次多選項排序共用同一 UUID。既有稽核紀錄由 migration 以各自的 AuditRecord `id` 回填，不建立不存在的歷史批次關聯。
- `before` 與 `after` 欄位必須存在；新增操作可使用 `before: null`，其他成功 mutation 應保存對應的前後內容。成功 mutation 的 `result` 固定為 `success`，畫面顯示「成功」。
- 一次排序若影響多個自訂 option，必須為每個受影響 option 建立獨立 AuditRecord，使用相同 `operation_id` 關聯，且 `resource_id` 指向各自 option。
- 失敗驗證、權限拒絕或使用者取消不得產生成功 mutation action；若安全政策要求拒絕紀錄，使用既有 access-denied action。
- A 收容所管理者只能讀取 A scope 的稽核資料；不可透過 code、resource id 或筆數推測 B。

## Summary projection（摘要投影）

頁面摘要不是新的正式資料表；由同一份目前收容所資料計算：

- `category_count`：固定為平台既有的 13 個觀察類別，即使某類別暫時沒有選項也計入；Staff 的 `staff_active` scope 仍只回傳其可見的啟用數量語意；
- `active_option_count`：平台預設＋收容所自訂的 active option；
- `custom_option_count`：本收容所自訂 option 的全部狀態；
- `inactive_option_count`：disabled＋archived option；
- `matched_option_count`：由前端使用完整 API response 經搜尋／篩選後計算的畫面衍生值，不屬於 API 的未篩選摘要或 response 必填欄位。

管理者的 summary／category counts 使用 `admin_full` scope；Staff 使用 `staff_active` scope，只提供啟用中的詞彙與數量，不回傳收容所自訂或停用／封存的管理數量。

類別計數與選項來源／狀態從同一個 API response 或同一個資料快照計算，避免頁面顯示互相矛盾的數字。

## Observation option audit query（觀察選項變更紀錄查詢）

本功能不建立第二份稽核資料，也不新增另一個稽核資料表。管理頁沿用既有 `/v1/management/audit` 與 `AuditRecord`，以 `resource_type=ObservationOption`、`resource_id` 和目前已驗證的 Shelter Context 查詢目前收容所的自訂選項變更紀錄。

查詢規則：

- 只有設定管理權限可查詢；Staff、Volunteer、無有效 Context 或其他未授權角色不得取得管理稽核內容。
- 回應至少提供不可為空的 `organization_id`、`actor_user_id`、`resource_id`、`operation_id`，以及 `created_at`、`action`、`before`、`after`、`reason`、`source_channel` 與 `result`；成功 mutation 的 `result` 固定為 `success`，供頁面顯示「成功」。
- 本頁對 `resource_type=ObservationOption` 的查詢只允許設定管理權限；既有稽核入口對其他 resource type 的原有權限不因本功能改變。
- 後端必須以已驗證的 organization scope 過濾，不信任 query string 的 organization id；查詢結果不得洩漏其他收容所的存在性、筆數或內容。
- 沒有紀錄是正常空狀態；查詢失敗時不以空資料冒充成功，前端顯示錯誤與重新載入操作。
- 變更紀錄檢視不提供修改、刪除或重播稽核事件的操作。

## Migration 與回滾要求

1. 新 migration 只能向前增加 `archived` 可用語意、`audit_records.operation_id`、usage index、必要索引與 RLS policy，不把既有 `active`／`disabled` 資料改成新來源；既有 AuditRecord 的 `operation_id` 以該筆 record id 回填。
2. 回填前先備份或驗證既有 `answer_snapshots`／`answers` 可讀取；回填失敗不得清空正式回報。
3. Migration downgrade 不得刪除既有 CareReport 或 snapshots；若無法安全 downgrade derived usage index，應明確標記不可回退，而不是破壞歷史資料。
4. 空資料庫升級、既有資料升級、重複執行回填、A／B RLS 與回報提交／修正回歸都必須有測試證據。
