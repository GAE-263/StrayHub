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

**Decision**：人工回報以獨立 transaction 成功保存後，才以另一個受控 transaction 冪等建立可追蹤的 AI Job。Worker 依 Job 狀態處理照片與心得，狀態至少包含 pending、running、succeeded、failed、invalid；重試與失敗結果都可稽核。Job 建立失敗不得回滾已保存 Report；Report 保存 `pending_enqueue`／`enqueue_failed` 狀態，並由 reconciliation 找出已保存但尚無有效 Job 的 Report。AI Observation 是衍生資料，不覆蓋原始回報。

**Rationale**：本機不需新增訊息佇列即可測試完整流程；GCP Demo 可用 Background Worker／Job 執行相同契約。Report 與 Job 使用分離 transaction，能讓外部 AI 或 enqueue 失敗不影響人工回報；Job 的唯一冪等關係與 reconciliation 則處理兩次 transaction 之間的中斷。

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

**Rationale**：SQLAlchemy 2.x 能提供明確的 ORM／資料存取邊界，`AsyncSession` 與 FastAPI／Worker 的非同步流程一致；Pydantic 與 SQLAlchemy 分離可避免 API 驗證模型與複雜多租戶資料關係耦合；Alembic 讓空資料庫建立、Cloud SQL Demo 與 migration 審查可重現。受控 Repository、Composite Constraint、PostgreSQL Row-Level Security（RLS）、交易內租戶 Scope 與跨租戶測試形成 Defense in Depth。

**Alternatives considered**：使用 SQLModel；拒絕，因 API Schema、Database Model 與多租戶關係會過度耦合。使用同步 SQLAlchemy Session；拒絕，因 API 與 Worker 的 I/O 流程需要一致的非同步存取。以手動資料庫操作建置 Schema；拒絕，因無法保證空資料庫、CI、Demo 與環境遷移的一致性。只依賴 Repository；拒絕，因 Constitution XI 要求資料存取層強制隔離，必須加上資料庫層防護與自動化測試。

## 決策 10：Authentication、Session 與 LIFF 身分邊界

**Decision**：FastAPI 是唯一的 Authentication／Authorization 執行邊界。`PLATFORM_ADMIN`、`SHELTER_ADMIN` 與 `STAFF` 使用帳號密碼登入；Volunteer 使用 LIFF 完成 LINE 身分驗證，再由 FastAPI 對應既有 User 與 `organization_membership`。系統採短效 Access Token、可輪替 Refresh Token 與 Server-side Session Record；Access Token 不包含可直接授權的 `org_id` 或角色。

每一個受保護 Request 都重新驗證 Session、User、Organization、Membership、角色與 Session 綁定的 Active Shelter Context。停用 User、Membership、Organization 或撤銷 Session／Refresh Token 後，必須立即拒絕後續存取。Worker 不使用一般 User Session，改用受限 Database Credential／Service Account，但每次處理 Job 仍驗證 Job、Report、Organization 與狀態一致。

Authentication API 固定包含 Login、Refresh、Logout、Current User、LIFF Identity Exchange、Active Shelter Context Read 與 Switch；HTTP router 位於 `services/api/app/api/authentication.py`，Session／Token rotation／replay 防護與 Context 切換由 `services/api/app/application/authentication/` 協調。這組 API 與測試是所有受保護 User Story 的 Foundational dependency，不得延後到 US1 或由 Next.js 自行補足。

Authentication 外部與密碼學能力以 `services/api/app/application/ports/authentication.py` 定義 `PasswordHasherPort`、`AccessTokenPort` 與 `LineIdentityVerifierPort`。正式實作分別固定於 `services/api/app/infrastructure/auth/password_hasher.py`、`services/api/app/infrastructure/auth/access_token_adapter.py` 與 `services/api/app/infrastructure/line/identity_verification_adapter.py`；Application Service 只能依賴 Port，不得直接呼叫密碼雜湊套件、Token 套件或 LINE 驗證 API。Adapter Contract Test 與 Security Test 必須涵蓋錯誤密碼、過期／格式錯誤 Token、Refresh replay、錯誤 issuer／audience、無效 LINE 身分資料、撤銷後立即拒絕及 Secret 不進 Log。

**Decision**：Password Hash 固定使用 `argon2-cffi` 的 `Argon2id`，採 PHC encoded hash，基準參數為 `m=19456 KiB`、`t=2`、`p=1`，salt 由函式庫逐筆產生；本期不使用 pepper。低於目前基準的舊 hash 在成功登入後重新雜湊。Access Token 固定使用 `PyJWT[crypto]`／`cryptography` 的 `RS256` JWT，RSA key 至少 2048-bit，TTL 15 分鐘，Header 使用 `typ=JWT`、`alg=RS256`、`kid`，Claims 使用 `sub`、`sid`、`jti`、`iat`、`exp`、`iss`、`aud` 與固定 access-token type，不放入 `org_id`、角色或 Membership。`AUTH_JWT_ISSUER`、`AUTH_JWT_AUDIENCE` 與 current／previous key set 由受控設定提供；驗證固定 allowlist `RS256`，並檢查 key、issuer、audience、type、時間與必要 Claims。Refresh Token 是至少 256-bit 的 opaque random value，只保存 `SHA-256` digest，rotation 與 family replay detection 仍由 Server-side Session 執行。

**Rationale**：OWASP 建議新系統使用 Argon2id，且提供 `m=19456`、`t=2`、`p=1` 的最低設定。JWT 使用非對稱簽章可避免把同一個 shared secret 散布至驗證元件；RS256 與 `PyJWT[crypto]` 可明確固定演算法、issuer、audience 與 key id。即使 JWT 尚未過期，每次 Request 仍查詢 Server-side Session，因此 User、Membership、Organization 或 Session 撤銷可以立即生效。Refresh Token 使用高熵 opaque value 並只保存 digest，可避免將可重放憑證寫入資料庫。

**Alternatives considered**：使用 bcrypt；拒絕，因新系統優先採用 memory-hard 的 Argon2id。使用 HS256；拒絕，因需要在簽發與驗證端共享高敏感 symmetric key，且本系統已有多個驗證邊界。使用 opaque Access Token；拒絕，因本 Feature 已定義短效 Access Token Claims、OpenAPI Bearer 介面與 issuer／audience 驗證，採受控 JWT 並以 Server-side Session 作最終授權判定。使用 pepper；暫不採用，避免第一階段增加全量密碼失效與 Secret rotation 的耦合。

**Official references**：[OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、[RFC 8725 JSON Web Token Best Current Practices](https://datatracker.ietf.org/doc/rfc8725/)、[RFC 9068 JWT Profile for OAuth 2.0 Access Tokens](https://datatracker.ietf.org/doc/html/rfc9068)、[PyJWT Usage Examples](https://pyjwt.readthedocs.io/en/latest/usage.html) 與 [PyJWT API Reference](https://pyjwt.readthedocs.io/en/stable/api.html)。

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

**Decision**：Draft 固定歸屬 `org_id`、志工、Membership 與 Animal，保存 opaque token、current step、答案、媒體、時間與狀態。狀態至少包含 `selecting_animal`、`confirming_animal`、`answering_completion`、`answering_feeding`、`answering_water`、`answering_activity`、`answering_elimination`、`answering_behavior`、`answering_special_status`、`awaiting_media`、`awaiting_note`、`reviewing`、`submitting`、`submitted`、`cancelled`、`expired`。`answering_completion` 依序取得照護完成狀態與散步完成狀態；`answering_behavior` 依序取得護食或資源防衛、對人的互動、對其他動物的互動、情緒與散步反應；`answering_special_status` 取得外觀／特殊狀態。標準回報必要答案包含 `care_completion`、`walk_completion`、`feeding`、`water`、`activity`、`urination`、`defecation`、`resource_guarding`、`human_interaction`、`animal_interaction`、`emotion`、`walk_reaction` 與 `appearance_special_status`；`not_observed`、`uncertain` 與 `walk_completion.not_done` 是有效答案，不是略過。尚有必要答案未完成時不得進入 `reviewing` 或 `submitting`。同一志工在單一 Organization 同時間只保留一筆 active Draft；有效期限由設定控制。無效轉移、跨 Organization、重送事件與修改 Postback 不得改綁 Draft。

## 補充決策 E：Mock LINE Adapter、正式 Adapter 與本機 HTTPS

**Decision**：Application Layer 以 `LineMessagingPort` 隔離 LINE Messaging API。本機使用 Mock LINE Webhook、Signature Helper、Mock User、Postback／Image／Redelivery Fixture 與 `MockLineAdapter`，不呼叫真實 LINE API；正式 `LineMessagingApiAdapter` 負責 Reply Message、必要的受控 Push Message、依 Message ID 取得圖片，以及 Rich Menu 驗證、建立、圖片上傳與環境綁定。Quick Reply／Postback payload 由後端依有效 Observation Vocabulary 組合。需要驗證真正 Webhook、Rich Menu、Reply、Image Content、LIFF URL 或 Browser 行為時，使用官方建議的 HTTPS 本機開發方式或受控 Demo 入口。Rich Menu 採版本化環境設定與可重複執行的同步腳本，避免本機、Demo 與正式設定互相覆蓋。

**Rationale**：正式 Adapter 與 Mock 共用 Port，可讓單元／整合測試不依賴 LINE，又能讓 Demo 驗證真正 HTTP、Reply Token、媒體下載與 Rich Menu 行為。LINE 官方要求 Webhook 在事件解析前驗證簽章，且使用者傳送的內容只保留有限期間，因此簽章與媒體取得不能只存在測試 Fake。參考：[Webhook Signature](https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/)、[Receive messages](https://developers.line.biz/en/docs/messaging-api/receiving-messages/)、[Rich menus](https://developers.line.biz/en/docs/messaging-api/rich-menus-overview/) 與 [Messaging API reference](https://developers.line.biz/en/reference/messaging-api/nojs/)。

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

## 決策 18：GCP Demo Infrastructure as Code

**Decision**：使用 Terraform 管理 `infra/gcp-demo/terraform/` 下的全部 GCP Demo 基礎設施，涵蓋 Next.js／FastAPI／Worker 的 Cloud Run 執行單元、Cloud SQL、Cloud Storage、Secret Manager、Artifact Registry、Cloud Logging、Service Account 與 IAM。`cloud-run-*.yaml` 不作為正式部署來源；如有診斷用 YAML，僅能是 Terraform 可重建的衍生產物。Terraform 設定只服務虛構 Demo 環境，不把正式環境部署納入本 Feature。

**Rationale**：Terraform 已與本計畫的 GCP Demo 元件及部署門檻對齊，可讓資源宣告、審查與重建流程可重現，並避免把本機開發綁定 GCP Console 的手動操作。

**Alternatives considered**：OpenTofu；暫不採用，避免在同一 Feature 保留兩套 IaC 工具語意。GCP Console 手動建立；拒絕，因無法提供可重現的 Demo 資源定義與審查軌跡。

## 決策 19：PostgreSQL 租戶隔離防護

**Decision**：租戶隔離採受控 Repository、交易內設定的 `Organization Scope`、Composite Constraint、PostgreSQL Row-Level Security（RLS）與跨租戶自動化測試的 Defense in Depth。Runtime Role 不擁有資料表且沒有 `BYPASSRLS`，租戶資料表啟用 `FORCE ROW LEVEL SECURITY`。一般 Request 與 Worker 由後端的 Database Scope Setter 在 transaction 內執行參數化 `set_config('app.current_org_id', :org_id, true)`；只有經 FastAPI 重新驗證的 `PLATFORM_ADMIN` 交易可執行 `set_config('app.platform_scope', 'true', true)`，並在同一 transaction 留下 Audit Record。`is_local=true` 讓 scope 在 transaction 結束時自動清除，避免 connection pool 重用時洩漏。Migration Role 與 Runtime Role 分離，Worker 不取得平台級 Scope。RLS Policy 與 Scope 設定由 Alembic Migration 管理，並以真實 PostgreSQL Integration Test 驗證一般 Scope、平台 Scope、缺少 Scope、偽造輸入、transaction 清除、pooled connection 重用與直接資料存取。

**Rationale**：Repository 可集中業務授權，Composite Constraint 可阻擋錯誤關聯，RLS 可降低繞過 Application Layer 的資料外洩風險；多層防護共同符合 Constitution 的後端與資料存取層隔離要求。

**Alternatives considered**：只依賴交易層 Scope；拒絕，因繞過 Repository 時缺少資料庫層防護。只依賴 Repository；拒絕，因無法形成足夠的 Defense in Depth。

**Official reference**：[PostgreSQL `set_config`](https://www.postgresql.org/docs/current/functions-admin.html) 的第三個參數為 `true` 時只套用於目前 transaction；本計畫因此不使用 session-level scope。

## 決策 20：本機 Python 命令與環境管理

**Decision**：本機與 CI 的 Python 命令使用 `uv` 執行；依賴與鎖定檔由專案工具鏈管理，標準驗證命令以 `uv run` 開頭。FastAPI、Worker、Alembic 與 Pytest 的入口路徑依 `plan.md` 的 `services/api/app/main.py`、`services/worker/worker.py` 與既定測試目錄執行。

**Rationale**：統一本機、CI 與 Demo 前驗證的 Python 執行方式，避免不同開發者以不同虛擬環境或入口造成結果不一致。

**Alternatives considered**：直接使用系統 `pip`／`python`；拒絕，因依賴解析與執行環境不易重現。

## 決策 21：Canonical Source Layout

**Decision**：FastAPI 程式碼統一放在 `services/api/app/`，依 `api/`、`application/`、`domain/`、`infrastructure/` 與 `persistence/` 分層；Alembic 統一放在 `services/api/migrations/`。Worker 以 `services/worker/worker.py` 啟動，所有 Worker Session、Repository、Adapter 與 Handler 統一放在 `services/worker/app/`。後續 Tasks 與 Quickstart 必須使用這組路徑，不建立平行目錄。

**Rationale**：Alembic Migration 與 Runtime Package 分離，API 與 Worker 的內部邊界則各自集中於單一 `app/`，可以消除 Migration 與 Worker Persistence 的平行程式碼根目錄。

**Alternatives considered**：將 Alembic 放入 `services/api/app/`；拒絕，因 Migration 是部署與 Schema 管理資產，不是 Runtime Package。將 Worker Repository 放在 `services/worker/persistence/`；拒絕，因會形成第二個 Worker 程式碼根目錄。

## 決策 22：Observation Vocabulary 與 AI Job Persistence 前移至 Foundational

**Decision**：`ObservationCategory`、`ObservationOption`、平台預設 Seed、穩定 Code、停用後歷史顯示與 Effective Options 唯讀查詢在 Foundational 完成，供 US1／US2 的 Quick Reply 與回報驗證使用；US4 只負責管理操作與 UI。`AIProcessingJob` 的持久化模型、Migration、版本欄位、冪等關係、Repository 與 reconciliation 契約同樣在 Foundational 完成；US5 才加入 Worker claim／retry、正式 AI 呼叫、`AIObservation` 與人工覆核。

**Rationale**：US2 的結構化答案不能依賴尚未存在的語彙模型，Report 保存後的非同步意圖也不能依賴 US5 才建立的 Job schema。前移基礎資料與持久化不會讓 MVP 依賴 AI 成功，反而消除跨階段倒置。

**Alternatives considered**：將 Observation 全部留在 US4、Job 全部留在 US5；拒絕，因 US2 已直接依賴兩者。把選項硬編碼在 Bot；拒絕，因會形成第二套業務語彙。

平台預設 Observation Seed 的最低內容直接依 FR-017～FR-022：進食、飲水、活動、排泄、護食／資源防衛、人際互動、動物互動、外觀與特殊狀態各自具有穩定 Code，並包含規格要求的「未觀察」、「無法判斷」及適用的「其他」選項。Seed Test 必須逐一驗證最低 Code 集合，不得只檢查資料列存在。

## 決策 23：OpenAPI 產生 TypeScript Contract Types

**Decision**：`contracts/openapi.yaml` 是唯一 HTTP Contract；使用 `openapi-typescript` 產生 `packages/contracts/src/openapi.ts`，只供 TypeScript consumer 使用。生成檔禁止手動修改；`generate` 負責更新，`check` 重新產生並比較差異。FastAPI Pydantic Schema 保持獨立，透過 OpenAPI contract tests 驗證一致性。

**Rationale**：Next.js 不需手動重寫 Request／Response 型別，又不把 TypeScript 生成物誤當成後端或業務規則來源。官方 CLI 支援直接從 OpenAPI schema 產生型別，適合納入可重現的 package script 與 CI drift check。參考：[openapi-typescript CLI](https://openapi-ts.dev/cli)。

**Alternatives considered**：前後端各自手寫型別；拒絕，因容易漂移。從 FastAPI runtime OpenAPI 反向覆蓋 Feature Contract；拒絕，因會讓實作取代已核准契約。生成 Python ORM／Pydantic；拒絕，因會破壞既定分層。

## 決策 24：測試目錄依驗證邊界分工

**Decision**：`tests/contract` 驗證 OpenAPI、Contract Types 與外部 Adapter；`tests/unit` 驗證純 Domain／Application 規則；`tests/integration` 驗證 PostgreSQL、MinIO、Session、Worker 與 transaction；`tests/security` 驗證簽章、Authentication、Tampering 與單一資源越權；`tests/isolation` 使用真實 PostgreSQL 驗證完整 A／B Organization 隔離矩陣；`tests/frontend` 驗證 Next.js 元件與畫面；`tests/e2e` 執行 Mock LINE／LIFF 到 FastAPI、PostgreSQL、MinIO、Worker 的跨程序垂直流程；`tests/fixtures` 只保存虛構 Webhook、Postback、Image、Redelivery 與 Seed 輸入。

**Rationale**：明確區分 test scope 後，Tasks 不會把 E2E 放進不存在的目錄，也不會用 Mock-only 測試取代真實 PostgreSQL 隔離驗證。

## 決策 25：真人 Usability Validation 與自動化效能測試分工

**Decision**：SC-001／SC-002 使用至少 10 名未受本系統專門訓練且未參與設計／實作的志工，SC-006／SC-014 使用至少 10 名未參與設計／實作的工作人員；固定腳本與去識別化證據置於 `specs/001-volunteer-care-report/validation/`。自動化測試只量測計時埋點、固定路徑、Timeline latency 與 Query Count，不得取代真人完成率、操作次數或狀態辨識率。

**Rationale**：Integration／E2E Test 可以證明系統行為與效能，但不能證明未受訓使用者能獨立完成或理解狀態。固定樣本下限、腳本、計數方式與失敗樣本保留規則，可避免以少量或篩選後樣本宣稱達成成功條件。

**Alternatives considered**：只以自動化測試模擬真人操作；拒絕，因無法驗證學習成本與語意辨識。只記錄百分比而不保存去識別化證據；拒絕，因無法重現或稽核驗收結果。

## 研究完成檢查

- 本機與 GCP 的儲存差異已由 Object Storage Interface 隔離。
- LINE Bot／LIFF、QR Code、AI 與後台的正式資料來源均回到 CRM；Bot Webhook、Signature、Event Idempotency 與圖片清理已有明確邊界。
- A／B Shelter 隔離、相同 Shelter Number、圖片存取、匯出與停用狀態均有驗證路徑。
- Authentication、Active Shelter Context、AI 版本追溯、EXIF 清理、Draft／Media 刪除與 Care Report Archive 均已記錄驗證邊界；公開頁面、Notification 與 Export 明確排除。
- GCP 專屬 IAM、Signed URL、Cloud SQL、Service Account 與 HTTPS LIFF 行為列為 Demo 另行驗證，不假設本機通過即等於 GCP 通過。
- SQLAlchemy `AsyncSession`、`asyncpg`、受控 Repository、Composite Constraint、PostgreSQL 防護與 Alembic 空資料庫 migration 已納入 Phase 1 設計與 quickstart 驗證路徑。
- Terraform、`uv`、Canonical Source Layout、PostgreSQL RLS／Database Scope Setter、Authentication API／Ports／Adapters、正式 LINE Adapter、OpenAPI Contract Types、測試目錄與真人 Usability Validation Protocol 已定案，並與 `plan.md`、`data-model.md`、`quickstart.md` 及相關契約一致；沒有未決的主要技術選型阻擋任務產生。
- 規格原有的高影響待釐清事項，以及 `PLATFORM_ADMIN` 平台級 Scope 與 LINE Webhook Session／Active Shelter Context 解析流程，均已完成確認並同步至本計畫；照片必填、草稿保存與刪除／封存等低優先細節列為 tasks 階段決策。
