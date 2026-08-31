// ============================================================
// 登入頁邏輯
// 流程：頁面一載入 → LIFF初始化/登入 → 拿LINE Profile → 呼叫後端驗證身分
//       → 存進全域狀態 → 自動跳轉到主選單
// 這個頁面使用者通常「不需要按任何按鈕」，全部自動完成，
// 只有 LIFF 初始化本身失敗時才會顯示錯誤訊息 + 重試按鈕。
// ============================================================

import { initLiffAndLogin } from "../liff-init.js";
import { verifyUserRole } from "../api.js";
import { setState } from "../state.js";
import { showScreen } from "../router.js";

const statusTextEl = () => document.getElementById("login-status-text");
const errorBoxEl = () => document.getElementById("login-error-box");
const retryBtnEl = () => document.getElementById("login-retry-btn");

export async function runLoginFlow() {
  errorBoxEl().classList.add("hidden");
  statusTextEl().textContent = "正在透過 LINE 登入...";

  try {
    const lineIdentity = await initLiffAndLogin();

    statusTextEl().textContent = "登入成功，正在確認身分...";
    const verifiedUser = await verifyUserRole(lineIdentity);

    setState({ currentUser: verifiedUser });
    showScreen("screen-menu");
  } catch (err) {
    console.error("登入流程發生錯誤:", err);
    statusTextEl().textContent = "登入失敗";
    errorBoxEl().classList.remove("hidden");
    errorBoxEl().querySelector("p").textContent =
      "無法完成登入，請確認網路連線後再試一次。";
  }
}

export function initLoginPage() {
  retryBtnEl().addEventListener("click", runLoginFlow);
  runLoginFlow();
}
