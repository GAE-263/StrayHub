# 便便判讀 API 串接（組員維護的外部服務）

上游服務與完整 API 規格見組員提供的「便便判讀 API — 串接說明」文件
（Cloud Run + Gemini，端點 `/v1/analyze/base64`）。本文件只記錄 StrayHub
這一側怎麼接、為什麼這樣接。

## 資料流

```
志工送出散步回報（含 subject="stool" 的便便照片）
→ webhook 建立 AIProcessingJob（既有 ReportJobDispatchService，未改動）
→ Worker 認領 → 只下載 stool 照片 → StoolAnalysisAdapter 呼叫判讀 API
→ 完整判讀（1-7 級、評估、建議）存 raw_ai_output（授權覆核用）
→ 對應到 CRM 大便選項的描述性建議走 validate_ai_output → validated_ai_observation
→ 管理端 AI 覆核流程照舊（人工確認後才成為正式資料）
```

沒有便便照片的回報（「沒排便」或志工略過拍照）不會呼叫 API，
不消耗上游免費額度。

## 啟用與停用

`.env` 設定 `STOOL_API_URL` 與 `STOOL_API_KEY`，兩者都有值時
`build_ai_client()` 啟用 `StoolAnalysisAdapter`（優先於 mock）；
金鑰留空即停用。改完要重啟 Worker。金鑰向維護者（蕭文婷）索取，
不進版控。

## 為什麼分 raw / formal（AIAnalysisEnvelope）

`validate_ai_output` 刻意禁止 `score`、診斷與醫療建議語意進入正式
Observation——上游回應的 `score`／`assessment`／`recommendation` 全部
都在禁止範圍。信封讓完整回應原樣進 `raw_ai_output`（這個欄位本來就是
給授權人員覆核的），只有「大便選項代碼＋質地/顏色描述」通過驗證成為
正式建議。這同時符合上游文件「日常照護參考，不具醫療診斷效力」的定位。

## 分數對照

| 上游 score | 對應 CRM 選項 |
|---|---|
| 3（理想） | `defecation.normal` |
| 4-5（偏軟/軟便） | `defecation.soft` |
| 1-2（乾硬）、6-7（糊狀/水瀉） | `defecation.abnormal` |
| `has_abnormalities: true`（血絲/黏液等，蓋過分數） | `defecation.abnormal` |
| `recognized: false` | 不產生建議（空 observations），完整回應仍在 raw |

志工自己在問卷答的「大便」選項與 AI 建議並存，兩者不一致時由
管理端覆核者判斷。

## 錯誤處理

| 上游錯誤 | 處理 |
|---|---|
| 400 `invalid_image`/`no_image`、401、422、503 | 終結（DomainError→invalid），重打同一張照片無效 |
| 429 `rate_limited`、502、504、逾時 | 走既有重試退避（60s 起，最多 3 次） |

429 是每日額度，退避重試大概率仍失敗後標 failed——這是接受的行為，
額度隔天重置後新回報不受影響。

## 測試

- `tests/unit/test_stool_analysis_adapter.py`：對照表、額度保護、錯誤分類
- `tests/integration/test_ai_raw_output_preservation.py`：信封的 raw/formal 分離
