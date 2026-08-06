# 研究與設計決策：志工日常照護回報與動物近期歷程

**日期**：2026-08-07

本文件記錄 Phase 0 對技術脈絡、部署邊界、整合方式與規格待釐清事項的規劃決策。這些決策服務於實作與驗證，不改寫功能規格中的業務權限；未來若產品確認與本文的暫定決策不同，必須先更新規格、資料模型與任務。

## 決策 1：採本機優先、GCP Demo 後置

**Decision**：日常開發、單元測試與主要整合測試以本機 Docker Compose、PostgreSQL、MinIO、Mock LINE／LIFF、Mock AI 與虛構 Seed Data 完成；只有品質門檻通過後才建立 GCP Demo。

**Rationale**：符合使用者提供的開發與部署階段，避免每次開發依賴 GCP 憑證、網路與正式資源，也使 CRM、AI 失敗降級與 A／B 隔離可重複驗證。

**Alternatives considered**：所有開發直接連接 GCP；拒絕，因會增加成本、權限暴露與測試不可重現風險。只使用記憶體 Fake；拒絕，因無法驗證 PostgreSQL migration、租戶查詢與物件儲存整合。

## 決策 2：前端、CRM API 與 Worker 分離

**Decision**：使用 `apps/web`、`services/api` 與 `services/worker` 三個可獨立執行的應用邊界。Next.js 負責畫面與使用者流程；FastAPI 負責 CRM、身分、租戶授權、資料寫入與查詢；Worker 負責照片後處理與 AI Job。

**Rationale**：LINE／LIFF、網頁後台與未來通道都必須共用 CRM 業務規則；AI 不能阻塞人工回報；前端不能成為資料隔離的最終防線。

**Alternatives considered**：將所有流程放在 Next.js；拒絕，因會讓通道承載權限與核心規則。將 AI 直接放在送出流程；拒絕，因違反 AI 非同步與人工回報獨立性。

## 決策 3：共通 Object Storage Interface

**Decision**：Application Layer 只依賴共通 Object Storage Interface，至少提供 `MinioStorageAdapter`、`GcsStorageAdapter` 與 `InMemoryStorageFake`。PostgreSQL 只保存穩定 Object Key、內容 Metadata、來源回報與 Shelter 歸屬。

**Rationale**：讓本機 MinIO 與 GCP Cloud Storage 可替換，避免將 Signed URL 或供應商 URL 寫成永久業務識別，也讓單元測試不需要啟動物件儲存。

**Alternatives considered**：Application Layer 直接呼叫 MinIO／GCS SDK；拒絕，因會造成環境耦合與測試分支。把圖片二進位直接存 PostgreSQL；拒絕，因不符合本機物件儲存與 Demo Cloud Storage 目標。

## 決策 4：使用非祕密 QR Token，伺服器重新判定範圍

**Decision**：QR Code 只提供候選 Animal 查詢所需的非祕密、可撤銷參考值；解析後由 FastAPI 依已驗證使用者、目前 Shelter Scope、QR Code 所屬 Shelter 與 Animal 所屬 Shelter 重新判定。QR Token 不代表授權，不承載照護內容、個資或長效祕密。

**Rationale**：符合 Constitution XI 與功能規格，避免修改 QR 內容繞過權限，也支援不同 Shelter 使用相同 Shelter Number。沒有 Shelter Number 的 Animal 可使用 CRM 正式識別建立 QR 參考，但查詢仍必須經 Shelter 範圍驗證。

**Alternatives considered**：把 Shelter Number 直接當作全平台唯一 QR 識別；拒絕，因不同 Shelter 可重複。把 QR Code 當作登入或授權憑證；拒絕，因籠位標示可能被拍攝、複製或貼錯。

## 決策 5：租戶隔離在 CRM 邊界與資料存取層強制執行

**Decision**：每個非公開資料實體都帶有 Shelter 歸屬；所有 read、create、update、search、圖片存取，以及 Draft／Temporary Media delete、Care Report archive 都必須接收已驗證的 Actor Scope。正式 Care Report 不允許 Hard Delete；本 Feature 不提供批次 Export。Repository／資料存取邊界拒絕缺少或不一致的 Shelter Scope；前端篩選只作呈現，不作安全控制。未授權情況使用一致的無權限或無法存取結果。

**Rationale**：滿足多收容所資料隔離，避免 A／B 資料因網址、識別碼、收容編號或搜尋條件外洩。隔離測試必須涵蓋正常查詢、直接識別、QR、圖片、修改、Draft／Temporary Media 刪除與 Care Report Archive；批次 Export 不屬本 Feature。

**Alternatives considered**：只在前端隱藏其他 Shelter；拒絕，因可由網址或請求繞過。先全平台搜尋再前端過濾；拒絕，因會造成存在性與結果外洩。

## 決策 6：以資料庫保存的 AI Job 支援非同步處理

**Decision**：人工回報保存後建立可追蹤的 AI Job，Worker 依 Job 狀態處理照片與心得，狀態至少包含 pending、running、succeeded、failed、invalid；重試與失敗結果都可稽核。AI Observation 是衍生資料，不覆蓋原始回報。

**Rationale**：本機不需新增訊息佇列即可測試完整流程；GCP Demo 可用 Background Worker／Job 執行相同契約。資料庫中的 Job 狀態讓人工回報保存與 AI 服務失敗解耦。

**Alternatives considered**：同步等待 AI 完成；拒絕，因阻塞 90 秒回報與違反 AI 失敗降級。引入額外訊息服務；暫不採用，因第一階段未要求且會增加本機與 Demo 的依賴。

## 決策 7：LIFF 分為 Mock 與受控 HTTPS 真實驗證

**Decision**：一般前端開發使用 Mock LIFF Context；真正 LINE 身分、LIFF URL 與 LIFF Browser 行為使用 LINE 官方 LIFF 開發工具提供的 HTTPS 本機環境或受控測試入口。兩者都只能透過相同 CRM 邊界完成身分與 Shelter Scope 驗證。

**Rationale**：保留 Hot Reload 與離線／低依賴開發，同時把真正 LINE 行為列為明確的 Demo 前與 Demo 後驗證。

**Alternatives considered**：所有開發使用已部署 LIFF；拒絕，因增加 GCP 依賴並降低迭代速度。永遠只使用 Mock；拒絕，因無法驗證真正 LINE 身分與 HTTPS Browser 行為。

## 決策 8：本階段對規格待釐清事項採保守規劃預設

**Decision**：採以下已確認的規劃決策：收容所名稱、機構代碼、啟用狀態與初始管理員為建立收容所的必要資訊；地址／服務區域與聯絡資訊可先為非必要欄位；志工可被授權服務多個 Shelter，但同一時間只能透過 Session 明確選擇一個 Active Shelter Context；系統不以 GPS、IP、裝置、時間重疊或地理距離推測地點，只有 Draft、Animal、QR Token、Scope 與 Active Context 的 Organization 不一致時才阻擋送出；QR Code 使用非祕密、可撤銷 QR Token 或系統深層連結；每日可回報範圍由收容所管理員或被授權工作人員設定，支援個別 Animal、籠舍／區域與指定 Volunteer，不包含完整班次排班；志工可在 24 小時內修改自己的回報內容、照片與心得，但不能修改動物綁定。

**Rationale**：這些決策保留資料隔離與 P1／P2 的最小可驗收流程，允許跨 Shelter 授權但避免同時操作造成回報歸屬不明，也不把功能擴大成完整班次排班、強制照片或同步 AI。照片是否必填、草稿保存期限與跨裝置恢復等低優先細節留到 tasks 階段。

**Alternatives considered**：志工永久只能隸屬單一 Shelter；拒絕，因不支援實際跨地點志願服務。由 QR 或搜尋結果自動切換目前 Shelter；拒絕，因可能造成跨租戶誤綁。等待低優先照片／草稿政策確認才產生設計；拒絕，因不阻擋核心回報與隔離驗收。

## 決策 9：SQLAlchemy 2.x、AsyncSession 與 Alembic

**Decision**：FastAPI API 與 Background Worker 使用 SQLAlchemy 2.x 的 `AsyncSession`，PostgreSQL 非同步 Driver 使用 `asyncpg`；Pydantic Model、SQLAlchemy Model 與 Domain／Application Layer 分離；資料表與 Schema 變更全部使用 Alembic Migration。Repository 是唯一允許業務查詢租戶資料的資料存取邊界，所有查詢強制帶入 `Organization Scope`。Authentication 與 Authorization 由 FastAPI 唯一執行；一般使用者使用帳號密碼，Volunteer 透過 LIFF 身分交換後建立本系統 Session；API 使用短效 Access Token、可輪替 Refresh Token 與可立即撤銷的 Server-side Session Record。

**Rationale**：SQLAlchemy 2.x 能提供明確的 ORM／資料存取邊界，`AsyncSession` 與 FastAPI／Worker 的非同步流程一致；Pydantic 與 SQLAlchemy 分離可避免 API 驗證模型與複雜多租戶資料關係耦合；Alembic 讓空資料庫建立、Cloud SQL Demo 與 migration 審查可重現。受控 Repository、Composite Constraint、PostgreSQL Row-Level Security／交易層防護與跨租戶測試形成 Defense in Depth。

**Alternatives considered**：使用 SQLModel；拒絕，因 API Schema、Database Model 與多租戶關係會過度耦合。使用同步 SQLAlchemy Session；拒絕，因 API 與 Worker 的 I/O 流程需要一致的非同步存取。以手動資料庫操作建置 Schema；拒絕，因無法保證空資料庫、CI、Demo 與環境遷移的一致性。只依賴 Repository；拒絕，因 Constitution XI 要求資料存取層強制隔離，必須加上資料庫層防護與自動化測試。

## 決策 10：Authentication、Session 與 LIFF 身分邊界

**Decision**：FastAPI 是唯一的 Authentication／Authorization 執行邊界。`PLATFORM_ADMIN`、`SHELTER_ADMIN` 與 `STAFF` 使用帳號密碼登入；Volunteer 使用 LIFF 完成 LINE 身分驗證，再由 FastAPI 對應既有 User 與 `organization_membership`。系統採短效 Access Token、可輪替 Refresh Token 與 Server-side Session Record；Access Token 不包含可直接授權的 `org_id` 或角色。

每一個受保護 Request 都重新驗證 Session、User、Organization、Membership、角色與 Session 綁定的 Active Shelter Context。停用 User、Membership、Organization 或撤銷 Session／Refresh Token 後，必須立即拒絕後續存取。Worker 不使用一般 User Session，改用受限 Database Credential／Service Account，但每次處理 Job 仍驗證 Job、Report、Organization 與狀態一致。

## 決策 11：LINE Bot 為主要回報介面，LIFF 為輔助介面

**Decision**：本 Feature 的主要回報介面是 LINE Bot，使用 Rich Menu、Quick Reply、Postback、文字訊息、圖片訊息與 LINE Messaging API Webhook；LIFF 僅作為第一次身分綁定、QR／Deep Link 識別、完整動物確認、答案修改、長文字及 Bot 備援介面。Bot 是受控狀態機，不以自然語言自由對話取代結構化選項。FastAPI 仍是唯一 Authentication、Authorization、Organization Scope 與 CRM 業務邊界。

Webhook 事件先驗證未修改的原始 Request Body 與 `X-Line-Signature`，再解析及處理；每個 `webhookEventId` 建立冪等處理紀錄。Postback payload、Rich Menu action、LINE User ID、Message ID 與事件中的 Organization／Animal 候選值都必須回到 FastAPI 重新查詢，不得作為最終授權依據。

**Rationale**：Quick Reply 與 Postback 適合單手逐題操作，圖片訊息能保留現場照片；LIFF 適合較複雜的確認與修改。Server-side Draft 將對話狀態與 CRM 正式資料分開，只有最終確認且重新驗證後才建立 Care Report。

**Official references**：本 Feature 依 [Webhook Signature 驗證](https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/)、[Quick Reply](https://developers.line.biz/en/docs/messaging-api/using-quick-reply/)、[Actions／Postback](https://developers.line.biz/en/docs/messaging-api/actions/)、[Webhook redelivery 與 `webhookEventId`](https://developers.line.biz/en/docs/messaging-api/receiving-messages/)、[Rich Menu](https://developers.line.biz/en/docs/messaging-api/rich-menus-overview/) 與 [Messaging API Content／Reply Token](https://developers.line.biz/en/reference/messaging-api/nojs/) 的規則進行實作與測試。

## 補充決策 A：Rich Menu、Quick Reply 與 Postback

**Decision**：Rich Menu 至少提供開始照護回報、掃描 QR Code、今日照護毛孩、繼續未完成回報與聯絡工作人員。Rich Menu 只負責入口；完整照護問卷由 Bot 狀態機驅動。每次 Bot 原則上只問一題，Quick Reply 通常提供 3 至 6 個高頻選項，適用時包含未觀察、無法判斷、略過或其他。Postback 的穩定 Code 與顯示名稱分離；Option 顯示名稱可修改，Code 不變。Bot 選項由 CRM 有效 Observation Vocabulary 產生或映射，不在 Bot 內建立第二套業務詞彙。

## 補充決策 B：Webhook Signature、冪等與 Reply Token

**Decision**：FastAPI Webhook boundary 使用 LINE channel secret 驗證 `X-Line-Signature`；驗證前不得解析、重排或修改原始 Body。無效簽章不查詢 CRM、不下載圖片、不建立 Draft 或 Care Report，並留下不含敏感資料的 Security Event。事件依 `webhookEventId` 去重，保存事件類型、處理狀態、重送旗標、時間與失敗原因；第一次失敗可安全重試，但冪等鎖定與狀態檢查必須避免重複業務寫入。Reply Token 只作即時回覆通道，不能作為 Draft 或權限狀態；長時間處理使用後續受控訊息或流程狀態。Bot 回覆失敗不回滾已保存的 Draft／Care Report，後端保存失敗狀態並允許以 Rich Menu Resume／受控重試重新取得目前狀態，避免重複建立正式資料。

## 補充決策 C：LINE 圖片內容與 EXIF

**Decision**：Image Message Event 只保存 Message ID 與必要事件 Metadata，事件處理應立即透過 LINE Content API 取得內容。LINE 官方說明內容會在一段時間後刪除且保存期間不保證，因此圖片下載須優先處理。圖片必須通過大小、MIME、實際格式、解碼、EXIF 移除、重新編碼與 Checksum 後才建立 Draft Media；原始圖片不得進入正式 Storage 或 AI。取得 404／410 或清理失敗時，提示重新傳送或略過，不阻擋其他答案。

## 補充決策 D：Bot State Machine 與 Draft Expiration

**Decision**：Draft 固定歸屬 `org_id`、志工、Membership 與 Animal，保存 opaque token、current step、答案、媒體、時間與狀態。狀態至少包含 `selecting_animal`、`confirming_animal`、`answering_feeding`、`answering_water`、`answering_activity`、`answering_elimination`、`answering_behavior`、`answering_special_status`、`awaiting_media`、`awaiting_note`、`reviewing`、`submitting`、`submitted`、`cancelled`、`expired`。同一志工在單一 Organization 同時間只保留一筆 active Draft；有效期限由設定控制。無效轉移、跨 Organization、重送事件與修改 Postback 不得改綁 Draft。

## 補充決策 E：Mock LINE Adapter、正式 Adapter 與本機 HTTPS

**Decision**：本機使用 Mock LINE Webhook、Signature Helper、Mock User、Postback／Image／Redelivery Fixture 與 Mock LINE Adapter，不呼叫真實 LINE API。需要驗證真正 Webhook、Rich Menu、Reply、Image Content、LIFF URL 或 Browser 行為時，使用官方建議的 HTTPS 本機開發方式或受控 Demo 入口。Rich Menu 採環境版本管理，避免本機、Demo 與正式設定互相覆蓋。

## 決策 12：AI 版本與 Prompt 必須完整追溯

**Decision**：每一筆 AI Job 都保存非空的 Provider、Model Name、Model Version／Snapshot、Prompt Template ID、Prompt Version、Output Schema Version、時間、原始輸出、驗證結果、失敗原因與 Retry Count。若外部服務沒有獨立 Snapshot，保存實際模型識別名稱與專案內部設定版本。`raw_ai_output`、`validated_ai_observation` 與 `human_review_result` 分開保存，人工修正不得覆蓋原始 AI 輸出。

## 決策 13：照片必須在正式保存前完成 EXIF 清理

**Decision**：志工照片在成為正式 `media_asset` 前必須完成大小、MIME、實際格式、解碼、EXIF／非必要 Metadata 移除、重新編碼與 Checksum。含原始 EXIF 的檔案不得進入正式 Object Storage；若暫存，必須在隔離 Temporary Storage、不可簽發 URL、不可供 AI 讀取，成功或失敗後都必須清理。AI 只能讀取已驗證且已清理的圖片。MinIO 與 GCS 使用相同清理規則，Storage Adapter 只保存已清理的位元資料。

## 決策 14：公開資料、Notification 與 Export 不屬本 Feature

**Decision**：本 Feature 不建立公開動物頁面、公開欄位 Allowlist、Notification 或批次 Export。只驗證未登入／未授權者不能取得 Care Report、Volunteer Note、照片、AI Observation、Timeline 或 Signed URL。Notification、公開島民檔案與 Export 必須另立 Specification。

## 決策 15：Draft、Media 與 Care Report 的刪除／封存

**Decision**：正式 Care Report 不允許 Hard Delete，只能 Correction 或 Archive，且保留 Audit。尚未提交的 Draft 與 Temporary Media 可由建立者刪除或由系統過期清理；正式 Media 不 Hard Delete，如需移除只能標記不可使用或封存並保留原因與操作者。

## 決策 16：平台管理員使用平台級 Scope

**Decision**：`PLATFORM_ADMIN` 是平台內建最高權限角色，使用獨立的 `PLATFORM` Scope，不建立任何 Shelter Membership，也不需要逐次額外授權。平台管理員可管理所有 Shelter 的非公開業務資料；正式 Care Report 與正式 Media 仍不得 Hard Delete。每項平台管理員的跨機構操作都必須留下完整 Audit Record。

**Rationale**：這與最新規格釐清一致，避免把平台治理帳號錯誤建模成某一個 Shelter 的成員，也避免一般管理員取得預設跨機構能力。平台級 Scope 仍由 FastAPI 與資料存取層強制驗證，不能只依賴角色名稱或前端畫面。

**Alternatives considered**：要求平台管理員逐一建立 Shelter Membership；拒絕，因與「不需額外權限授予」衝突。將平台管理員歸屬至特殊 Shelter；拒絕，因會產生錯誤的租戶歸屬與跨機構查詢邊界。

## 決策 17：LINE Webhook 的 Session 與收容所 Context 解析

**Decision**：Webhook 收到 `line_user_id` 後，先查詢有效 LINE Binding；無效時回覆 LIFF 驗證連結，不建立正式資料。Binding 有效後取得 `system_user_id` 並查詢有效 Webhook Session。只有一個可用 Session 時重新驗證 Shelter Membership 與權限；沒有可用 Session 時查詢有效 Shelter Context，只有一個 Context 才建立 Webhook Session。多個可用 Session 或多個有效 Shelter Context 時不得自動選擇，回覆 LIFF 連結要求明確選擇。Webhook 不得因 QR Code、Postback、裝置、地理位置或時間訊號自動切換 Active Shelter Context。

**Rationale**：Webhook 輸入本身不代表使用者具有 CRM 權限，也不能安全地推測目前收容所。唯一候選可降低操作摩擦；多個候選則必須交由使用者在 LIFF 明確選擇，以避免跨租戶誤綁與草稿錯誤歸屬。

**Alternatives considered**：依 LINE Binding 永久保存的收容所自動選擇；拒絕，因無法處理多個有效收容所與 Session 撤銷。依 QR Code 或 Postback 直接切換；拒絕，因輸入值不可信。每次回報都要求重新開啟 LIFF；拒絕，因違反 LINE Bot 主要回報介面的低摩擦目標。

## 研究完成檢查

- 本機與 GCP 的儲存差異已由 Object Storage Interface 隔離。
- LINE Bot／LIFF、QR Code、AI 與後台的正式資料來源均回到 CRM；Bot Webhook、Signature、Event Idempotency 與圖片清理已有明確邊界。
- A／B Shelter 隔離、相同 Shelter Number、圖片存取、匯出與停用狀態均有驗證路徑。
- Authentication、Active Shelter Context、AI 版本追溯、EXIF 清理、Draft／Media 刪除與 Care Report Archive 均已記錄驗證邊界；公開頁面、Notification 與 Export 明確排除。
- GCP 專屬 IAM、Signed URL、Cloud SQL、Service Account 與 HTTPS LIFF 行為列為 Demo 另行驗證，不假設本機通過即等於 GCP 通過。
- SQLAlchemy `AsyncSession`、`asyncpg`、受控 Repository、Composite Constraint、PostgreSQL 防護與 Alembic 空資料庫 migration 已納入 Phase 1 設計與 quickstart 驗證路徑。
- 規格原有的高影響待釐清事項，以及 `PLATFORM_ADMIN` 平台級 Scope 與 LINE Webhook Session／Active Shelter Context 解析流程，均已完成確認並同步至本計畫；照片必填、草稿保存與刪除／封存等低優先細節列為 tasks 階段決策。
