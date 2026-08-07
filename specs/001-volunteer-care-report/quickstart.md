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
uv run fastapi dev services/api/app/main.py
npm --prefix apps/web run dev
uv run python services/worker/worker.py
```

三個入口必須分別對應 `services/api/app/main.py`、`apps/web` 與 `services/worker/worker.py`，並保留三個獨立的可觀察程序與本機 Hot Reload 能力。

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
- Database Scope Setter 在 transaction 內使用 `set_config(..., true)`，未設定 scope 時預設拒絕；transaction 結束與 connection pool 重用後不保留上一個 Organization。
- 同一 Organization 內重複 Shelter Number 被拒絕；不同 Organization 的相同 Shelter Number 可以存在。
- Composite Constraint 與 PostgreSQL 防護阻止跨 Organization 關聯。
- 空資料庫可由 migration 建立所有必要 Schema、Constraint、Index 與租戶防護。

執行資料存取與 migration 測試：

```bash
uv run pytest tests/integration/test_migrations.py tests/integration/test_database_scope_setter.py tests/isolation -q
```

若需要驗證回復策略，依實作任務提供的明確 migration 測試執行 downgrade 或替代遷移驗證；不得以手動資料庫介面操作取代 migration。

## 4. 驗證 Authentication API 與 Contract Types

執行 Authentication Contract 與 Session lifecycle 測試：

```bash
uv run pytest tests/contract/test_openapi_contract.py tests/contract/test_authentication_adapters.py tests/security/test_authentication_adapters.py tests/integration/test_authentication_session.py tests/isolation/test_active_shelter_context.py -q
npm --prefix packages/contracts run generate
npm --prefix packages/contracts run check
```

驗證：

- Login、Refresh、Logout、Current User、LIFF Identity Exchange 與 Active Shelter Context Read／Switch 都符合 OpenAPI。
- Refresh Token rotation、replay 防護、Session 撤銷及 User／Membership／Organization 停用立即生效。
- `PasswordHasherPort`、`AccessTokenPort` 與 `LineIdentityVerifierPort` 的正式 Adapter 通過共同契約與安全測試；Application Service 不直接依賴密碼、Token 或 LINE SDK。
- Password Hash 使用 `Argon2id`（`m=19456 KiB`、`t=2`、`p=1）；Access Token 使用 `RS256` JWT，檢查 `kid`、issuer、audience、type、時間與必要 Claims；Refresh Token 只在 CRM 保存 `SHA-256` digest。
- Access Token 不含 `org_id`、角色或 Membership；即使 JWT 尚未過期，Session／User／Membership／Organization 撤銷後仍立即拒絕。
- Request 不能以自行傳入的 `org_id` 覆寫 Session Active Shelter Context。
- `packages/contracts/src/openapi.ts` 由 `openapi.yaml` 產生且無漂移；生成檔沒有手動業務規則。

## 5. 建立虛構 Seed Data

建立兩個互相隔離的 Shelter：

- Shelter A：`ORG-A`
- Shelter B：`ORG-B`
- 兩者各建立一個工作人員、一個志工與一隻收容編號 `VAAAG114080610` 的 Animal。
- 產生各自的 QR Token、Cage／Area 與今日可回報範圍。
- 載入平台預設 Observation Category／Option 與 Effective Option 測試資料。
- 不使用真實姓名、電話、地址、照片或正式收容所資料。

預期結果：相同 Shelter Number 可同時存在；每筆使用者、Animal、QR、Scope 與回報都可辨識其 Shelter。

## 6. 驗證多收容所隔離

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

另以 `PLATFORM_ADMIN` 驗證平台級 Scope：

1. 建立沒有任何 Shelter Membership 的 `PLATFORM_ADMIN`。
2. 以該帳號查看、建立、修改或封存 A／B Shelter 的非公開業務資料。
3. 確認不需逐次額外授權，且每項跨 Shelter 操作都有完整 Audit Record。
4. 確認正式 Care Report 與正式 Media 仍不得 Hard Delete。

## 7. 驗證 LINE Webhook Session 解析

使用 Mock LINE Webhook Payload 驗證下列分支：

1. LINE Binding 無效時，回覆 LIFF 驗證連結，且不建立 Draft、Care Report 或其他正式業務資料。
2. Binding 有效且只有一個可用 Webhook Session 時，重新驗證 Shelter Membership 與權限；權限有效才允許開始回報。
3. 沒有可用 Webhook Session 且只有一個有效 Shelter Context 時，建立綁定該 Context 的 Webhook Session 後開始回報。
4. 有多個可用 Webhook Session，或沒有 Session 但有多個有效 Shelter Context 時，不自動選擇，回覆 LIFF 連結要求明確選擇。
5. 修改 Postback、QR Token 或 Request 中的 Organization／Animal 識別不能改變 Webhook Session、Active Shelter Context 或 Draft 的正式歸屬。

## 8. 驗證 LINE Bot 回報與近期歷程

在 Mock LINE User、Mock Webhook Payload 與 Mock LIFF Context 中以 A 志工：

1. 從 Rich Menu 的「今日照護毛孩」選擇 A Animal，或解析 A QR Token。
2. 顯示照片、名稱、完整 Shelter Number 與 Cage／Area，明確確認 Animal。
3. 以 Quick Reply／Postback 依序完成照護完成狀態、散步完成狀態、進食、飲水、活動、排尿、排便、護食或資源防衛、對人的互動、對其他動物的互動、情緒、散步反應及外觀／特殊狀態；各題可選擇有效的「未觀察」、「無法判斷」或「未進行散步」，但不可略過必要題目。
4. 以 Image Message 附加一張虛構照片，測試 EXIF 清理後才建立 Draft Media；心得可略過。
5. 顯示完整摘要，確認前驗證 Signature、`webhookEventId`、Draft、Animal、Membership 與 Active Shelter Context。
6. 送出後立即確認人工 Report 先獨立保存，再由另一個 transaction 冪等建立 AI Job；Job 建立失敗不得回滾 Report。
7. 重送同一 Webhook Event，確認不重複建立答案、照片關聯、Report 或 AI Job。
8. 中斷後從 Rich Menu 繼續有效 Draft，或取消 Draft；取消不得建立正式 Report。
9. 重複建立同一 Animal 同日第二筆回報。
10. 在 Timeline 查看近 14 日每日摘要、同日多筆、原始照片、心得與「當日無回報」。
11. 在建立後 24 小時內修改自己的回報內容、照片與心得；正式 Report 不得 Hard Delete，只能依權限 Correction 或 Archive。

預期結果：兩筆 Report 都保留；沒有回報日期不顯示為正常；24 小時內的內容修改保留前後版本；動物綁定修改交由授權人員處理；所有資料可追溯至 A Shelter。

重新選擇動物的驗證必須另外確認：原結構化答案與心得顯示為待重新確認、原照片不自動沿用、新 Animal 重新通過確認與 Reportable Scope，且跨 Organization 候選被拒絕。

## 9. 驗證 Object Storage

在本機以 MinIO 執行：

```bash
uv run pytest tests/integration/test_storage_adapters.py tests/integration/test_media_validation.py -q
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

## 10. 驗證 AI 非同步與失敗降級

以 Mock AI Service 或測試用 AI Adapter 執行：

```bash
uv run pytest tests/integration/test_ai_job_version_trace.py tests/integration/test_ai_worker_lifecycle.py tests/integration/test_ai_failure_timeline_status.py -q
```

驗證：

- Report 先以獨立 transaction 保存，Job 以另一個 transaction 冪等建立。
- Job 建立失敗時 Report 保持成功，並呈現 `pending_enqueue`／`enqueue_failed`；reconciliation 可補建且不重複。
- Worker 可將 Job 從 `pending` 處理至 `succeeded`。
- 每一筆 Job 都保存非空的 Provider、Model Name／Version、Prompt Template／Version、Output Schema Version 與處理時間；失敗時仍保存預定版本資訊。
- AI 逾時、服務中斷、無效內容或診斷語意會產生 `failed`／`invalid`，不覆蓋原始 Report。
- `raw_ai_output`、`validated_ai_observation` 與 `human_review_result` 分開保存；人工修正不覆蓋原始輸出。
- 人工回報與 Timeline 在 AI 失敗時仍可用。
- AI Observation 可追溯至已移除 EXIF 的 Photo 或 Volunteer Note。

## 11. 驗證正式 LINE Adapter Contract

一般測試使用 `MockLineAdapter`，不得呼叫真實 LINE API：

```bash
uv run pytest tests/contract/test_line_adapter_contract.py tests/integration/test_line_webhook_idempotency.py tests/e2e/test_line_bot_mvp.py -q
```

驗證 Mock 與正式 Adapter 的共同契約包含 Reply Message、受控 Push Message、Image Content 取得及 Rich Menu 管理；Quick Reply／Postback 由 Effective Observation Options 產生。真正 LINE API 只在受控 HTTPS／Demo 環境執行 smoke test，並由 `scripts/sync_line_rich_menu.py` 依環境設定發布 Rich Menu。

## 12. 真人 Usability Validation

依 `validation/usability-test-plan.md` 執行固定腳本：

1. 使用至少 10 名未受本系統專門訓練的志工測試者驗證 SC-001／SC-002，將去識別化結果寫入 `validation/volunteer-usability-evidence.md`。
2. 使用至少 10 名未參與設計或實作的工作人員測試者驗證 SC-006／SC-014，將去識別化結果寫入 `validation/staff-usability-evidence.md`。
3. SC-001：至少 8 名志工能獨立完成標準回報；SC-002：至少 8 名志工能在 90 秒內完成標準回報；SC-006／SC-014：至少 9 名工作人員能在三次主要操作內進入 Timeline 並正確區分四種狀態。
4. 不得保存 LINE User ID、真實姓名或正式收容所資料；不得排除失敗樣本；自動化測試不得代替真人結果。

## 13. 本機品質門檻

```bash
ruff check .
ruff format --check .
pytest
npm --prefix apps/web test
npm --prefix packages/contracts run check
```

以上命令與 Frontend 測試必須通過，且空資料庫 migration、關鍵本機流程、Shelter A／B 隔離與 MinIO Adapter 測試都必須有成功結果，才可進入 GCP Demo。

## 14. GCP Demo 部署後驗證

部署前先驗證唯一 Terraform 來源：

```bash
terraform fmt -check -recursive infra/gcp-demo/terraform
terraform -chdir=infra/gcp-demo/terraform validate
```

Cloud Run、Cloud SQL、Cloud Storage、IAM、Service Account、Artifact Registry 與 Cloud Logging 均必須由 `infra/gcp-demo/terraform/` 建立；不得直接套用 `cloud-run-*.yaml`。接著重新執行空 Cloud SQL 的 migration 驗證；部署後重新執行：

1. Database Migration 驗證。
2. Cloud Storage 權限與 Signed URL 驗證。
3. LINE Webhook HTTPS、Signature、Event Idempotency 與 Rich Menu 驗證。
4. LIFF HTTPS 與真正 LINE 身分受控驗證。
5. QR Code 流程驗證。
6. Shelter A／B 資料隔離驗證。
7. AI 失敗降級驗證。
8. Cloud SQL 連線、IAM、Service Account 與 Cloud Logging 可追溯性驗證。
9. 正式 `LineMessagingApiAdapter` 的 Reply Message、Image Content 與 Rich Menu 發布／綁定驗證。

本機通過只代表本機流程可用，不代表 GCP 專屬整合完成。任何 Demo 失敗都必須保留失敗證據與環境資訊，不能以本機結果代替。

本 Feature 不實作自然語言自由對話、語音辨識或 AI Agent；LINE Messaging API Webhook、Message／Image／Postback Event 均屬本 Feature 的受控輸入流程。
