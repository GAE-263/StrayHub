# Quickstart：本機與 GCP Demo 驗證

本指南是本功能的驗證與執行入口，不包含完整實作程式碼、migration 內容或測試 fixture。命令名稱代表實作階段應提供的標準命令；若工具鏈命名不同，必須在任務文件與 README 同步更新。

## 1. 前置條件

- Docker 與 Docker Compose 可用。
- Node.js 與專案指定的套件管理工具可用。
- Python 與專案指定的 Python 執行工具可用。
- 不使用 GCP 正式憑證、不使用真實個資、不使用正式收容所敏感資料。
- 本 Feature 以 LINE Bot 為主要回報介面，使用 Mock LINE Webhook 與 Mock LINE Adapter；LIFF 只作為輔助介面。

## 2. 啟動本機服務

從 repository root 執行：

```bash
docker compose -f infra/local/docker-compose.yml up -d postgres minio
```

啟動 FastAPI、Next.js 與 Background Worker 的開發模式：

```bash
uv run fastapi dev services/api/app.py
npm --prefix apps/web run dev
uv run python -m services.worker
```

實際入口可在實作階段調整，但必須保留三個獨立的可觀察程序與本機 Hot Reload 能力。

## 3. 驗證 Database Access 與 Migration

在空的本機 PostgreSQL 上執行完整 Alembic Migration：

```bash
uv run alembic upgrade head
```

驗證：

- SQLAlchemy 2.x 可透過 `AsyncSession` 使用 `asyncpg` 連線。
- Pydantic Request／Response Model 不直接作為 SQLAlchemy Model。
- API 與 Worker 的資料存取都經過受控 Repository。
- Repository 每次操作都強制帶入 `Organization Scope`。
- 同一 Organization 內重複 Shelter Number 被拒絕；不同 Organization 的相同 Shelter Number 可以存在。
- Composite Constraint 與 PostgreSQL 防護阻止跨 Organization 關聯。
- 空資料庫可由 migration 建立所有必要 Schema、Constraint、Index 與租戶防護。

執行資料存取與 migration 測試：

```bash
uv run pytest tests/integration/test_migrations.py tests/isolation -q
```

若需要驗證回復策略，依實作任務提供的明確 migration 測試執行 downgrade 或替代遷移驗證；不得以手動資料庫介面操作取代 migration。

## 4. 建立虛構 Seed Data

建立兩個互相隔離的 Shelter：

- Shelter A：`ORG-A`
- Shelter B：`ORG-B`
- 兩者各建立一個工作人員、一個志工與一隻收容編號 `VAAAG114080610` 的 Animal。
- 產生各自的 QR Token、Cage／Area 與今日可回報範圍。
- 不使用真實姓名、電話、地址、照片或正式收容所資料。

預期結果：相同 Shelter Number 可同時存在；每筆使用者、Animal、QR、Scope 與回報都可辨識其 Shelter。

## 5. 驗證多收容所隔離

執行隔離測試：

```bash
uv run pytest tests/isolation -q
```

至少驗證：

1. A 使用者只能搜尋 A 的 Animal。
2. A 使用者以 B 的 Animal 識別、Shelter Number、QR Token、網址或 Object Key 查詢時，不取得 B 的資料，也不知悉資料是否存在。
3. A 與 B 可同時使用 `VAAAG114080610`，查詢結果仍各自正確。
4. A 志工掃描 B QR Token 時，不能進入回報流程。
5. 前端偽造 B 的 Shelter 識別時，CRM 仍依已驗證 Actor Scope 拒絕。
6. 停用 Shelter 或使用者後，不能登入、讀取或建立新業務資料。
7. 同一志工可被授權 A、B 兩個 Shelter；切換時必須明確更新 Active Shelter Context，Draft／Animal／QR Token／Reportable Scope 與目前 Context 不一致時阻擋送出，不以地點、裝置或時間推測志工所在 Shelter。

## 6. 驗證 LINE Bot 回報與近期歷程

在 Mock LINE User、Mock Webhook Payload 與 Mock LIFF Context 中以 A 志工：

1. 從 Rich Menu 的「今日照護毛孩」選擇 A Animal，或解析 A QR Token。
2. 顯示照片、名稱、完整 Shelter Number 與 Cage／Area，明確確認 Animal。
3. 以 Quick Reply／Postback 逐題填寫進食、飲水、活動、排泄、行為與外觀等結構化選項。
4. 以 Image Message 附加一張虛構照片，測試 EXIF 清理後才建立 Draft Media；心得可略過。
5. 顯示完整摘要，確認前驗證 Signature、`webhookEventId`、Draft、Animal、Membership 與 Active Shelter Context。
6. 送出後立即確認人工 Report 已保存，且 AI Job 另行非同步建立。
7. 重送同一 Webhook Event，確認不重複建立答案、照片關聯、Report 或 AI Job。
8. 中斷後從 Rich Menu 繼續有效 Draft，或取消 Draft；取消不得建立正式 Report。
9. 重複建立同一 Animal 同日第二筆回報。
10. 在 Timeline 查看近 14 日每日摘要、同日多筆、原始照片、心得與「當日無回報」。
11. 在建立後 24 小時內修改自己的回報內容、照片與心得；正式 Report 不得 Hard Delete，只能依權限 Correction 或 Archive。

預期結果：兩筆 Report 都保留；沒有回報日期不顯示為正常；24 小時內的內容修改保留前後版本；動物綁定修改交由授權人員處理；所有資料可追溯至 A Shelter。

## 7. 驗證 Object Storage

在本機以 MinIO 執行：

```bash
uv run pytest tests/integration/test_object_storage.py -q
```

驗證 `MinioStorageAdapter`、`InMemoryStorageFake` 與共通契約：

- 上傳、讀取、存在性、撤銷與短期存取位置。
- 正式 Media 僅接受通過大小／MIME／實際格式／解碼驗證、移除 EXIF、重新編碼並計算 Checksum 的位元資料。
- 含原始 EXIF 的檔案不得進入正式儲存；Temporary Media 不得產生 Signed URL，成功或失敗後都必須清理。
- MinIO 與 GCS 使用相同圖片安全政策；AI 只能讀取清理後圖片。
- Object Key 與 Metadata 有 Shelter、Report 與用途關聯。
- MinIO URL 不會保存為永久識別。
- A 使用者不能以 B Object Key 讀取圖片。

GCP Demo 另執行同一組 GCS Contract Test，驗證 `GcsStorageAdapter`、IAM、Signed URL、過期與權限錯誤。

## 8. 驗證 AI 非同步與失敗降級

以 Mock AI Service 或測試用 AI Adapter 執行：

```bash
uv run pytest tests/integration/test_ai_job.py -q
```

驗證：

- Report 保存後才建立 AI Job。
- Worker 可將 Job 從 `pending` 處理至 `succeeded`。
- 每一筆 Job 都保存非空的 Provider、Model Name／Version、Prompt Template／Version、Output Schema Version 與處理時間；失敗時仍保存預定版本資訊。
- AI 逾時、服務中斷、無效內容或診斷語意會產生 `failed`／`invalid`，不覆蓋原始 Report。
- `raw_ai_output`、`validated_ai_observation` 與 `human_review_result` 分開保存；人工修正不覆蓋原始輸出。
- 人工回報與 Timeline 在 AI 失敗時仍可用。
- AI Observation 可追溯至已移除 EXIF 的 Photo 或 Volunteer Note。

## 9. 本機品質門檻

```bash
ruff check .
ruff format --check .
pytest
npm --prefix apps/web test
```

以上命令與 Frontend 測試必須通過，且空資料庫 migration、關鍵本機流程、Shelter A／B 隔離與 MinIO Adapter 測試都必須有成功結果，才可進入 GCP Demo。

## 10. GCP Demo 部署後驗證

部署前必須重新執行空 Cloud SQL 的 migration 驗證；部署後重新執行：

1. Database Migration 驗證。
2. Cloud Storage 權限與 Signed URL 驗證。
3. LINE Webhook HTTPS、Signature、Event Idempotency 與 Rich Menu 驗證。
4. LIFF HTTPS 與真正 LINE 身分受控驗證。
5. QR Code 流程驗證。
6. Shelter A／B 資料隔離驗證。
7. AI 失敗降級驗證。
8. Cloud SQL 連線、IAM、Service Account 與 Cloud Logging 可追溯性驗證。

本機通過只代表本機流程可用，不代表 GCP 專屬整合完成。任何 Demo 失敗都必須保留失敗證據與環境資訊，不能以本機結果代替。

本 Feature 不實作自然語言自由對話、語音辨識或 AI Agent；LINE Messaging API Webhook、Message／Image／Postback Event 均屬本 Feature 的受控輸入流程。
