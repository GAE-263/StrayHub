# 工作人員 LINE 動物輸入 — 後端合約

> 定位：LINE/LIFF 只是工作人員的輸入介面；資料的家在 StrayHub 後端（CRM 唯一事實來源）。
> 前端：`line-liff/staff-animal/`（由 paw-village 表單衍生）。
> 狀態：後端、OpenAPI 與前端授權接線已實作；production 預設不啟用 mock。

## 進入點
LINE 工作人員選單 → 「新增動物」/「更新健康紀錄」→ webhook 回覆 LIFF 連結
`https://liff.line.me/<LIFF_ID>/staff-animal` → 開啟本 LIFF。

## 授權
- LIFF 取得 LINE `id_token` → `POST /v1/line/bind` 建立 session，再以 Bearer access token 呼叫 `/v1/auth/me`。
- 僅目前已選定收容所的 `STAFF` / `SHELTER_ADMIN` 可進入本 LIFF；`PLATFORM_ADMIN` 不因平台角色取得 staff menu。
- 所有動物寫入必須在已驗證的 Organization Scope 下進行；前端傳入的 org/animal 不可取代後端授權。
- access token 僅存在 JS module memory，不寫入 localStorage、sessionStorage 或 payload。

## 端點

### 1. `POST /v1/line/bind`（已存在）
Request：`{ "id_token": "<LINE id_token>" }`
Response：短效 access token／refresh token；角色與 membership 由 `/v1/auth/me` 取得。

### 2. `GET /v1/management/animals/{animalId}`（已存在，`require_staff_or_admin`）
查詢動物基本資料，供更新流程「確認是不是這隻」。查無回 404。

### 3. `POST /v1/management/animals`（已實作）
新增收容動物。`multipart/form-data`：
- `payload`（JSON 字串）
- `photo`（照片檔案）

payload 結構：
```json
{
  "requestType": "CREATE_ANIMAL",
  "submittedBy": { "displayName": "王小明", "role": "STAFF" },
  "animal": {
    "tempAnimalId": "A20260826-7431",
    "name": "小黑",
    "species": "dog",
    "breed": "米克斯",
    "gender": "male",
    "estimatedAge": "約1歲",
    "size": "medium",
    "foundLocation": "台北市大安區公園",
    "notes": "個性親人"
  },
  "submittedAt": "2026-08-26T10:32:00+08:00"
}
```
回應：`{ "success": true, "animalId": "<正式 UUID>" }`。
註：`tempAnimalId` 為前端暫時編號，後端可沿用或換發正式收容編號。

### 4. `POST /v1/management/animals/{animalId}/health-records`（已實作）
更新健康紀錄。`multipart/form-data`：`payload`（JSON 字串）+ `photo`（選填）。
```json
{
  "requestType": "UPDATE_ANIMAL_HEALTH",
  "submittedBy": { "displayName": "王小明", "role": "STAFF" },
  "animalId": "A20260826-7431",
  "healthRecord": {
    "status": "needs_medical",
    "description": "右前腳輕微跛行，建議就醫"
  },
  "submittedAt": "2026-08-26T14:05:00+08:00"
}
```
回應：`{ "success": true, "recordId": "<UUID>" }`。

## 契約優先注意事項（StrayHub）
- HTTP 唯一契約是 OpenAPI；新增端點需先更新 `specs/.../openapi.yaml`，TS 型別由 `openapi-typescript` 產生、不可手改。
- 照片走 `multipart/form-data`（非 Base64）；後端可沿用既有 MinIO/媒體處理（去 EXIF）。
- server-side session 的 active organization 是唯一 shelter scope；multipart payload 不含 organization 欄位。

## 前端切換正式環境
部署時以 `window.STRAYHUB_STAFF_LIFF_CONFIG` 注入 `liffId` 與選填的 HTTPS
`apiBaseUrl`。不注入 `mockMode`（預設 false）；production preflight 另行拒絕
`mockMode=true`。
