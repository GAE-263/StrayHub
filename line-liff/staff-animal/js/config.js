// ============================================================
// 全域設定檔（StrayHub 工作人員動物輸入 LIFF）
// 本 LIFF 由 paw-village 的表單衍生，改為指向 StrayHub 後端。
// 交接給後端 / 部署正式環境前，最需要注意的就是這個檔案。
// ============================================================

export const CONFIG = {
  // 從 LINE Developers Console > LIFF 取得（工作人員用的 LINE Login channel）。
  LIFF_ID: "YOUR_STAFF_LIFF_ID",

  // StrayHub 後端 API 根路徑（含 /v1）。正式環境必須是 https。
  // 例如：https://api.your-strayhub.example.com/v1
  API_BASE_URL: "https://your-strayhub-api.example.com/v1",

  // 開發模式開關：
  // true  → 不呼叫真實 LIFF、用假的工作人員資料，可在一般瀏覽器測畫面。
  // false → 正式串接 LIFF，必須在 LINE App 內開啟。
  MOCK_MODE: true,

  // 圖片欄位在 FormData 裡的 key，前後端要對好。
  PHOTO_FIELD_NAME: "photo",
};

// ============================================================
// 切換正式環境的兩個開關（要一起改，別漏）：
//   1. 本檔 CONFIG.MOCK_MODE      → 控制「LINE 登入(LIFF)」是否用假資料
//   2. js/api.js 的 USE_MOCK_API  → 控制「後端 API」是否用假資料
// 上線時兩個都要改成 false，並填好 LIFF_ID 與 API_BASE_URL。
// ============================================================
