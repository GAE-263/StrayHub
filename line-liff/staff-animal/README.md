# StrayHub 工作人員動物輸入 LIFF

工作人員在 LINE 底部選單點「新增動物 / 更新健康紀錄」後開啟的 LIFF 輸入介面。
定位：**LINE 只是輸入介面，資料的家在 StrayHub 後端。**

## 由來
本 LIFF 由 `paw-village-liff-main` 的新增/更新表單衍生（相同的拍照、表單、驗證流程），
改為指向 StrayHub 後端合約。純前端、無 build，一台靜態伺服器即可跑。

## 兩個功能
- 新增動物：拍照 → 自動產生暫時動物ID → 填基本資料 → 送出
- 更新健康紀錄：輸入動物ID查詢 → 確認動物 → （選填照片）→ 填健康狀況 → 送出

## 設定（runtime injection）

在載入 `js/config.js` 前注入 `window.STRAYHUB_STAFF_LIFF_CONFIG`：

- `liffId`：工作人員 LINE Login channel 的 LIFF ID
- `apiBaseUrl`：選填；預設同源 `/v1`，分離部署時 production 必須是 HTTPS
- `mockMode`：只有 local demo 可明確設為 `true`；production 禁止

tracked source 不保存 production LIFF ID、API URL 或長效 credential。

## 後端合約（見 `docs/staff-animal-line-input.md`）
- `POST /v1/line/bind`：以 LINE `id_token` 建立後端 session
- `GET /v1/auth/me`：以記憶體中的 Bearer token 驗證目前 shelter membership
- `GET /v1/management/animals/{id}`：查詢動物（已存在）
- `POST /v1/management/animals`：新增動物（已實作）
- `POST /v1/management/animals/{id}/health-records`：更新健康紀錄（已實作）

## 本機測試（不連 LINE）
```bash
cd line-liff/staff-animal
# 另以 local-only HTML 注入 mockMode=true；預設會要求真實 LIFF ID。
python3 -m http.server 8010
# 瀏覽器開 http://localhost:8010
```
