// ============================================================
// LIFF (LINE Front-end Framework) 初始化與登入
// 這一支是整個 LINE 串接的核心，負責：
//   1. 初始化 LIFF SDK
//   2. 確認使用者是否已登入 LINE，沒登入就導去 LINE 登入頁
//   3. 登入後取得使用者的 LINE Profile (userId / displayName / pictureUrl)
// ============================================================

import { CONFIG } from "./config.js";

// 開發模式用的假資料，讓工程師在一般瀏覽器(非LINE App)也能測試畫面，
// 不用每次改個小地方就要透過手機LINE重新整理。
const MOCK_PROFILE = {
  userId: "U-mock-0000000000000000000000000",
  displayName: "測試志工小美",
  pictureUrl: "https://placehold.co/100x100?text=LINE",
};

/**
 * 初始化 LIFF 並確保使用者已登入。
 * 回傳值：LINE Profile 物件 { userId, displayName, pictureUrl }
 */
export async function initLiffAndLogin() {
  if (CONFIG.MOCK_MODE) {
    console.warn(
      "[開發模式] MOCK_MODE=true，跳過真實LIFF初始化，使用假的LINE使用者資料。"
    );
    // 模擬網路延遲，讓載入動畫的體驗跟正式環境接近
    await new Promise((resolve) => setTimeout(resolve, 500));
    return MOCK_PROFILE;
  }

  // liff 是透過 index.html 裡 <script src="https://static.line-scdn.net/liff/edge/2/sdk.js">
  // 載入的全域變數，這裡直接使用。
  await liff.init({ liffId: CONFIG.LIFF_ID });

  if (!liff.isLoggedIn()) {
    // 尚未登入：呼叫 liff.login() 會導向LINE登入頁，登入完成後LINE會把使用者
    // 導回這個網址，屆時 liff.isLoggedIn() 就會是 true，流程等於重新跑一次。
    liff.login();
    // login() 會離開頁面，這裡回傳一個永遠不 resolve 的 Promise，
    // 讓呼叫端的 await 卡住、不會誤以為登入完成繼續往下執行。
    return new Promise(() => {});
  }

  const profile = await liff.getProfile();
  return profile;
}

/**
 * 登出：清除 LIFF 的登入狀態並重新整理頁面回到登入畫面。
 */
export function liffLogout() {
  if (CONFIG.MOCK_MODE) {
    window.location.reload();
    return;
  }
  if (liff.isLoggedIn()) {
    liff.logout();
  }
  window.location.reload();
}
