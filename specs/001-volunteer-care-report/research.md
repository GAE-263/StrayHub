# 研究與設計決策：志工日常照護回報與動物近期歷程

**日期**：2026-08-06

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

**Decision**：每個非公開資料實體都帶有 Shelter 歸屬；所有 read、create、update、delete、search、export 與圖片存取都必須接收已驗證的 Actor Scope。Repository／資料存取邊界拒絕缺少或不一致的 Shelter Scope；前端篩選只作呈現，不作安全控制。未授權情況使用一致的無權限或無法存取結果。

**Rationale**：滿足多收容所資料隔離，避免 A／B 資料因網址、識別碼、收容編號或搜尋條件外洩。隔離測試必須涵蓋正常查詢、直接識別、QR、圖片、匯出與修改。

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

**Decision**：採以下已確認的規劃決策：收容所名稱、機構代碼、啟用狀態與初始管理員為建立收容所的必要資訊；地址／服務區域與聯絡資訊可先為非必要欄位；志工可被授權服務多個 Shelter，但同一時間只有一個目前服務中的 Shelter，發現不同 Shelter 或不同地點同時操作時顯示警示；QR Code 使用非祕密 QR Token 或系統深層連結；每日可回報範圍由收容所管理員或被授權工作人員設定，支援個別 Animal、籠舍／區域與指定 Volunteer，不包含完整班次排班；志工可在 24 小時內修改自己的回報內容、照片與心得，但不能修改動物綁定。

**Rationale**：這些決策保留資料隔離與 P1／P2 的最小可驗收流程，允許跨 Shelter 授權但避免同時操作造成回報歸屬不明，也不把功能擴大成完整班次排班、強制照片或同步 AI。照片是否必填、草稿保存期限與跨裝置恢復等低優先細節留到 tasks 階段。

**Alternatives considered**：志工永久只能隸屬單一 Shelter；拒絕，因不支援實際跨地點志願服務。由 QR 或搜尋結果自動切換目前 Shelter；拒絕，因可能造成跨租戶誤綁。等待低優先照片／草稿政策確認才產生設計；拒絕，因不阻擋核心回報與隔離驗收。

## 決策 9：SQLAlchemy 2.x、AsyncSession 與 Alembic

**Decision**：FastAPI API 與 Background Worker 使用 SQLAlchemy 2.x 的 `AsyncSession`，PostgreSQL 非同步 Driver 使用 `asyncpg`；Pydantic Model、SQLAlchemy Model 與 Domain／Application Layer 分離；資料表與 Schema 變更全部使用 Alembic Migration。Repository 是唯一允許業務查詢租戶資料的資料存取邊界，所有查詢強制帶入 `Organization Scope`。

**Rationale**：SQLAlchemy 2.x 能提供明確的 ORM／資料存取邊界，`AsyncSession` 與 FastAPI／Worker 的非同步流程一致；Pydantic 與 SQLAlchemy 分離可避免 API 驗證模型與複雜多租戶資料關係耦合；Alembic 讓空資料庫建立、Cloud SQL Demo 與 migration 審查可重現。受控 Repository、Composite Constraint、PostgreSQL Row-Level Security／交易層防護與跨租戶測試形成 Defense in Depth。

**Alternatives considered**：使用 SQLModel；拒絕，因 API Schema、Database Model 與多租戶關係會過度耦合。使用同步 SQLAlchemy Session；拒絕，因 API 與 Worker 的 I/O 流程需要一致的非同步存取。以手動資料庫操作建置 Schema；拒絕，因無法保證空資料庫、CI、Demo 與環境遷移的一致性。只依賴 Repository；拒絕，因 Constitution XI 要求資料存取層強制隔離，必須加上資料庫層防護與自動化測試。

## 研究完成檢查

- 本機與 GCP 的儲存差異已由 Object Storage Interface 隔離。
- LINE／LIFF、QR Code、AI 與後台的正式資料來源均回到 CRM。
- A／B Shelter 隔離、相同 Shelter Number、圖片存取、匯出與停用狀態均有驗證路徑。
- GCP 專屬 IAM、Signed URL、Cloud SQL、Service Account 與 HTTPS LIFF 行為列為 Demo 另行驗證，不假設本機通過即等於 GCP 通過。
- SQLAlchemy `AsyncSession`、`asyncpg`、受控 Repository、Composite Constraint、PostgreSQL 防護與 Alembic 空資料庫 migration 已納入 Phase 1 設計與 quickstart 驗證路徑。
- 規格原有的五項高影響待釐清事項已完成確認並同步至本計畫；照片必填、草稿保存與刪除／封存等低優先細節列為 tasks 階段決策。
