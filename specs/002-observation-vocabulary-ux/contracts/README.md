# 介面契約索引

本目錄定義觀察詞彙管理頁面與 CRM HTTP 邊界的 Phase 1 設計契約。它描述授權、資料來源、狀態、失敗處理與可觀察結果，不取代專案既有的正式 OpenAPI source-of-truth。

- [Observation Vocabulary HTTP Contract](observation-vocabulary.yaml)：本功能新增／修改的讀取、建立、編輯、排序、停用、恢復、封存與收容所自訂選項變更紀錄查詢契約。
- [UI Behavior Contract](ui-behavior.md)：頁面 IA、角色能力、狀態、篩選、響應式與可及性行為。

實作時需將本契約同步至專案既有的 `specs/001-volunteer-care-report/contracts/openapi.yaml`，再由 `packages/contracts` 重新產生 `src/openapi.ts`。生成型別不得直接編輯；契約測試必須檢查 canonical source、FastAPI response 與生成型別一致。

## 共通安全規則

- 所有操作都需要有效登入與已驗證的 Active Shelter Context。
- Staff 可讀取啟用中的詞彙，但不可建立、修改、排序、停用、恢復或封存。
- `SHELTER_ADMIN` 與有效 Shelter Context 下的 `PLATFORM_ADMIN` 才可管理收容所自訂選項；Volunteer 無法存取此管理範圍。
- 任何 path id、搜尋條件、source 或 organization 輸入都不能擴大使用者的 Organization scope。
- 平台預設 option 在收容所頁面為唯讀；不存在 DELETE operation。
- 變更紀錄沿用既有 `/v1/management/audit` 路徑；對 `resource_type=ObservationOption` 的本頁查詢使用 `resource_id`，只允許設定管理權限並維持目前收容所 scope；既有稽核入口對其他 resource type 的原有權限不因本功能改變。
- 成功 mutation 的稽核 `result` 固定為 `success`，畫面顯示「成功」；驗證失敗、取消或拒絕不得建立成功 mutation 紀錄。
- `ObservationOption` 稽核回應必須提供不可為空的 `organization_id`、`actor_user_id`、`operation_id` 與 `resource_id`；同一次多選項排序以共同 `operation_id` 關聯各選項紀錄。
- 重要失敗回應不得洩漏其他收容所的資源是否存在。
