# Data Model：毛孩日記管理頁

## GrowthDiaryEntry（既有，擴充）

代表領養人針對一筆領養詢問與一隻動物提交的單次原始更新。

### 既有欄位

| 欄位 | 型別 | 規則 |
|---|---|---|
| `id` | UUID | 主鍵 |
| `organization_id` | UUID | 必填；管理查詢 tenant boundary |
| `inquiry_id` | UUID | 必填；關聯領養詢問 |
| `animal_id` | UUID | 必填；關聯動物 |
| `adopter_user_id` | UUID | 必填；management list 不暴露不必要個資 |
| `photo_key` | string nullable | private object key；不得直接回前端 |
| `note` | string nullable | 領養人原始文字，最長 2,000 字，不得被 AI 覆寫 |
| `ai_mood` | string nullable | `positive/neutral/concern` 描述性建議 |
| `ai_reply` | string nullable | 已推送給領養人的 AI 回覆 |
| `ai_staff_summary` | string nullable | 工作人員參考摘要，非診斷 |
| `created_at/updated_at` | aware datetime | 原始提交與更新時間 |

### 新增欄位

| 欄位 | 型別 | 規則 |
|---|---|---|
| `photo_content_type` | string nullable | 新照片固定 `image/webp`；legacy 可 null，不可信時 photo endpoint fail closed |
| `ai_analysis_status` | string nullable | `pending/succeeded/failed/unconfigured/not_applicable`；null 表示 legacy |
| `ai_provider` | string nullable | 成功呼叫時保存，例如 `google_gemini` |
| `ai_model_name` | string nullable | 呼叫時使用的模型識別 |
| `ai_model_version` | string nullable | 可追溯模型版本／識別 |
| `ai_prompt_version` | string nullable | 毛孩日記 prompt 版本 |
| `ai_output_schema_version` | string nullable | 結構化輸出 schema 版本 |
| `ai_raw_output` | JSON nullable | 原始模型文字／JSON；只在授權 detail 提供 |
| `ai_analyzed_at` | aware datetime nullable | 分析完成或終止時間 |

### Invariants

- entry、inquiry、animal 的 `organization_id` 必須彼此一致且等於 active organization；建立、count、list、detail、photo 與 join 均由 server explicit scope，client 不提供 organization id。
- 新資料 `photo_key` 有值時 `photo_content_type` 必須為 `image/webp`；legacy 缺少或不是可信 `image/webp` 時照片 endpoint fail closed，不以現行設定推測歷史 MIME。
- `note` 與 `photo_key` 至少一個應存在；管理頁仍安全呈現異常 legacy 資料。
- AI 背景更新不得修改 `note`、`photo_key`、正式動物狀態或醫療資料。
- `ai_mood=concern` 只能呈現「AI 建議人工查看」，不得用於診斷、自動排序或正式等級。

### AI transitions

```text
entry with analyzable note + configured client → pending → succeeded | failed
entry with note + no configured client          → unconfigured
photo-only entry                                → not_applicable
pre-migration entry                             → null → response derives legacy/unavailable
```

## GrowthDiaryListItem（read model）

由 entry 與同 organization Animal 投影，不是新資料表。

- IDs：`id/inquiry_id/animal_id`
- Animal snapshot：`animal_name/shelter_number` nullable
- 原始內容：`note`、`has_photo`、same-origin `photo_endpoint`
- `ai_analysis`：status、mood、reply、staff summary、provenance summary，不含 raw output
- `created_at`：ISO 8601 aware datetime

List response 是 `items/page/page_size/total`；排序固定 `created_at DESC, id DESC`，避免相同 timestamp 的分頁重複或遺漏。

## GrowthDiaryDetail（read model）

延伸 list item，僅在展開「查看 AI 來源」時取得：

- `ai_raw_output`
- provider/model/model version/prompt/output schema/analyzed time
- `provenance_status = available | legacy_missing | unavailable`

detail 受 active organization、role 與 RLS 限制；不存在與跨 tenant 使用相同 404。

## FilterPageQuery（transient）

| 欄位 | 規則 |
|---|---|
| `query` | trim 後搜尋同 organization Animal.name/shelter_number；空字串視為未設定 |
| `mood` | `all/concern/positive/neutral/unanalyzed`；預設 all |
| `page` | >= 1；預設 1 |
| `page_size` | 1..100；預設 50 |

filter 必須在 count、排序與 pagination 前套用。`unanalyzed` 包含沒有有效 mood 的紀錄；UI 再依 status 誠實顯示等待、失敗、未設定、photo-only 或 legacy。

## Private storage relationship

```text
GrowthDiaryEntry (organization_id, photo_key, photo_content_type)
  → ObjectStoragePort.get(ObjectScope(organization_id), photo_key)
  → buffered bytes (final size <= 2 MB)
  → authenticated same-origin image/webp response
  → authFetch Blob URL (revoked on unmount/context switch)
```

成功 response 固定包含：

- `Content-Type: image/webp`
- `Cache-Control: private, no-store`
- `X-Content-Type-Options: nosniff`

以上 `Content-Type` 是 runtime HTTP requirement；OpenAPI 由 `content.image/webp` 表達 media type，不在 `headers` 重複宣告。

## FinalSanitizedPhoto（暫態 value，不新增資料表）

由既有 media sanitization pipeline 在記憶體中產生，只有最終成功結果會交給 object storage。

| 屬性 | 規則 |
|---|---|
| accepted input | JPEG／PNG／WebP，實際格式必須與 declared MIME 相符 |
| input size | compressed bytes `<= 10 MB` |
| pixel limit | `width * height <= 25,000,000`，在完整 decode 前檢查 |
| frame | animated input 只使用第一 frame |
| orientation | resize 前套用 EXIF orientation |
| metadata | final output 不保留 EXIF 或其他來源 metadata |
| alpha | 透明來源保留 alpha channel |
| upscale | 禁止；小於 target 的圖片保持原尺寸 |
| attempt 1 | long edge `<= 1600 px`、WebP quality `82` |
| attempt 2 | attempt 1 超過 2 MB 時，long edge `<= 1600 px`、quality `72` |
| attempt 3 | attempt 2 仍超過 2 MB 時，long edge `<= 1280 px`、quality `68` |
| final size | `<= 2 MB`，否則拒絕 |
| content type | 固定 `image/webp` |
| checksum/size | 只依 final WebP bytes 計算 |

原始 JPEG／PNG／WebP、EXIF 版本及每次 fallback intermediate bytes 只存在 request memory，不寫入 object storage 或資料庫。

## Photo persistence state and compensation

這是 request 內的暫態 ownership，不新增 saga、job 或狀態資料表：

```text
received
  → sanitized_in_memory
  → object_stored (compensation token active)
  → entry_flushed
  → transaction_committed (token cleared; durable)
  → success reply / AI task registration
```

Failure rules：

- input/sanitization failure：沒有 object、沒有 GrowthDiaryEntry。
- storage put failure：沒有 GrowthDiaryEntry；adapter 不應回報成功 object。
- DB insert/flush/commit failure after storage success：DB rollback，使用 token 的 organization scope + object key 呼叫 `ObjectStoragePort.delete()`。
- compensation delete failure：記錄 `growth_diary_orphan_cleanup_failed` structured exception log 並保留原始 DB root cause；不向 LINE 或 management response 暴露 object key。
- compensation ownership 位於擁有 `async with session.begin()` 的 webhook per-event orchestration，因 commit 發生在 Growth Diary handler 返回之後；只在 handler 內 cleanup 不足以涵蓋 commit failure。
- success reply 與 AI task registration 在 commit 後執行；post-commit LINE／task failure 不回滾或刪除已 durable 的 entry/object，只記錄外部 side-effect failure，原始日記保持可用。

## Migration

新增 additive Alembic revision，擴充 `growth_diary_entries` 的 photo metadata、analysis status 與 provenance。既有資料允許 null，不做不可信 MIME/provenance backfill；downgrade 只移除新增欄位，不改原始日記。新圖片的 final bytes 只存在 object storage，資料表不新增 original/intermediate media 欄位。
