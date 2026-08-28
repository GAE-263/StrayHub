# StrayHub 工作人員動物輸入 LIFF

工作人員在 LINE 底部選單點「新增動物 / 更新健康紀錄」後開啟的 LIFF 輸入介面。
定位：**LINE 只是輸入介面，資料的家在 StrayHub 後端。**

## 由來
本 LIFF 由 `paw-village-liff-main` 的新增/更新表單衍生（相同的拍照、表單、驗證流程），
改為指向 StrayHub 後端合約。純前端、無 build，一台靜態伺服器即可跑。

## 兩個功能
- 新增動物：拍照 → 自動產生暫時動物ID → 填基本資料 → 送出
- 更新健康紀錄：輸入動物ID查詢 → 確認動物 → （選填照片）→ 填健康狀況 → 送出

## 設定（`js/config.js`）
- `LIFF_ID`：工作人員 LINE Login channel 的 LIFF ID
- `API_BASE_URL`：StrayHub 後端根路徑（含 `/v1`，必須 https）
- `MOCK_MODE`：true 用假資料本機測試；上線改 false
- 另一個開關在 `js/api.js` 的 `USE_MOCK_API`，上線兩個都要改 false

## 後端合約（見 `docs/staff-animal-line-input.md`）
- `POST /v1/line/bind`：綁定並回傳角色（僅 staff 可用本 LIFF）
- `GET /v1/management/animals/{id}`：查詢動物（已存在）
- `POST /v1/management/animals`：新增動物 **[後端待實作]**
- `POST /v1/management/animals/{id}/health-records`：更新健康紀錄 **[後端待實作]**

## 本機測試（不連 LINE）
```bash
cd line-liff/staff-animal
python3 -m http.server 8010
# 瀏覽器開 http://localhost:8010
```
