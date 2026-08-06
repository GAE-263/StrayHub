# Object Storage 契約

## 目的

讓 Application Layer 在本機使用 MinIO、在 GCP Demo 使用 Cloud Storage，並以相同的檔案生命週期與權限規則運作。

## 共通能力

- `put`：以已驗證的 Shelter、Report、用途與 Metadata 保存物件。
- `get`：以 CRM Object Key 與 Actor Scope 取得短期檔案內容或受限存取位置。
- `delete`：依 CRM 關聯與權限刪除或撤銷物件；不得只憑前端 URL。
- `exists`：僅能在已授權範圍內判定，不得用於洩漏其他 Shelter 的存在性。
- `create_access_url`：產生短期 Signed URL 或等效存取方式，不得保存為永久識別。

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

## 契約測試

同一組 Object Storage Contract Test 必須對 `MinioStorageAdapter`、`GcsStorageAdapter` 與必要的 Fake 執行；本機門檻要求 MinIO 測試通過，Demo 門檻要求 GCS Contract Test 通過。
