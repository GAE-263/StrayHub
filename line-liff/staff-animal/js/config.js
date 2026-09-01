// ============================================================
// 全域設定檔（StrayHub 工作人員動物輸入 LIFF）
// 本 LIFF 由 paw-village 的表單衍生，改為指向 StrayHub 後端。
// 交接給後端 / 部署正式環境前，最需要注意的就是這個檔案。
// ============================================================

const runtime = window.STRAYHUB_STAFF_LIFF_CONFIG || {};

export const CONFIG = {
  // 由 hosting/runtime 注入，不在 tracked source 寫 production LIFF ID。
  LIFF_ID: runtime.liffId || "",

  // 預設同源；若 API 分離部署，只能由 runtime config 注入 HTTPS base URL。
  API_BASE_URL: runtime.apiBaseUrl || `${window.location.origin}/v1`,

  // 必須明確注入 true 才啟用；production 未注入時永遠走真實驗證並 fail closed。
  MOCK_MODE: runtime.mockMode === true,

  // 圖片欄位在 FormData 裡的 key，前後端要對好。
  PHOTO_FIELD_NAME: "photo",
};

// ============================================================
// Local demo 可在 index.html 載入本檔前注入：
// window.STRAYHUB_STAFF_LIFF_CONFIG = { mockMode: true }。
// Production contract 禁止 mockMode=true，且必須注入有效 liffId。
// ============================================================
