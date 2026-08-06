# Object Storage 契約

## 目的

讓 Application Layer 在本機使用 MinIO、在 GCP Demo 使用 Cloud Storage，並以相同的檔案生命週期、EXIF 清理與權限規則運作。

## 共通能力

- `put`：只接受已完成大小、MIME、實際格式、解碼、EXIF 清理、重新編碼與 Checksum 的位元資料，並以已驗證的 Shelter、Report、用途與 Metadata 保存物件。
- `get`：以 CRM Object Key 與 Actor Scope 取得短期檔案內容或受限存取位置。
- `delete`：依 CRM 關聯與權限刪除或撤銷物件；不得只憑前端 URL。
- `exists`：僅能在已授權範圍內判定，不得用於洩漏其他 Shelter 的存在性。
- `create_access_url`：產生短期 Signed URL 或等效存取方式，不得保存為永久識別。

LINE Image Message 來源的檔案必須先由 Webhook／正式 `LineMessagingApiAdapter` 取得，再交給共通 Media Sanitization Pipeline；Storage Adapter 只接受已清理、已重新編碼的位元資料，不負責判定 MIME、EXIF 或租戶政策。LINE Adapter 不得直接把原始圖片寫入正式 Storage。

## Adapter

- `MinioStorageAdapter`：本機 Docker Compose MinIO。
- `GcsStorageAdapter`：GCP Demo Cloud Storage。
- `InMemoryStorageFake`：單元測試與無檔案服務測試。

## 強制規則

1. 永久資料只保存穩定 Object Key、Metadata、Shelter、Report 與用途。
2. MinIO URL、Cloud Storage URL 與 Signed URL 不得作為業務關聯或歷史識別。
3. 物件讀取、上傳、刪除與 Signed URL 建立都要重新驗證 Actor Scope。
4. Object Key 不可讓使用者自行指定其他 Shelter 的路徑而取得資料。
5. 物件上傳成功但 CRM 關聯失敗時，必須有可重試、清理或待處理狀態，不可留下無法追蹤的正式照片。
6. 含原始 EXIF 的檔案不得進入正式 Object Storage；Temporary Media 不得簽發正式 Signed URL，成功或失敗後都必須清理。
7. AI 只能讀取已驗證、已重新編碼且已移除 EXIF 的正式或受控清理後照片。
8. LINE 原始圖片不得進入正式儲存空間或供 AI 讀取；取得失敗、解碼失敗、EXIF 清理失敗或重新編碼失敗時，不建立正式 Media，且必須清理 Temporary Object。

## 契約測試

同一組 Object Storage Contract Test 必須對 `MinioStorageAdapter`、`GcsStorageAdapter` 與必要的 Fake 執行，並驗證 EXIF 清理、Temporary Media、原始檔不保留、LINE Image Message 來源與 AI 只能讀取清理後照片；本機門檻要求 MinIO 測試通過，Demo 門檻要求 GCS Contract Test 通過。
