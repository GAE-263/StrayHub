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
const organizationSelectEl = () =>
  document.getElementById("login-organization-select");

let pendingLineIdentity = null;

function destinationScreen() {
  const action = new URLSearchParams(window.location.search).get("action");
  if (action === "staff_create_animal") return "screen-add-animal";
  if (action === "staff_update_health") return "screen-update-animal";
  return "screen-menu";
}

export async function runLoginFlow(organizationId = null) {
  errorBoxEl().classList.add("hidden");
  organizationSelectEl().classList.add("hidden");
  statusTextEl().textContent = "正在透過 LINE 登入...";

  try {
    const lineIdentity = pendingLineIdentity || (await initLiffAndLogin());
    pendingLineIdentity = lineIdentity;

    statusTextEl().textContent = "登入成功，正在確認身分...";
    const verifiedUser = await verifyUserRole(lineIdentity, organizationId);

    if (verifiedUser.requiresOrganizationSelection) {
      const select = organizationSelectEl();
      select.replaceChildren(
        ...verifiedUser.organizations.map((organization) => {
          const option = document.createElement("option");
          option.value = organization.id;
          option.textContent = `${organization.name}（${organization.role}）`;
          return option;
        })
      );
      select.classList.remove("hidden");
      errorBoxEl().querySelector("p").textContent = "請先選擇目前要操作的收容所";
      retryBtnEl().textContent = "確認收容所";
      retryBtnEl().dataset.mode = "select";
      errorBoxEl().classList.remove("hidden");
      statusTextEl().textContent = "需要選擇收容所";
      return;
    }

    setState({ currentUser: verifiedUser });
    pendingLineIdentity = null;
    showScreen(destinationScreen());
  } catch (err) {
    console.error("登入流程發生錯誤:", err);
    statusTextEl().textContent = "登入失敗";
    errorBoxEl().classList.remove("hidden");
    errorBoxEl().querySelector("p").textContent =
      "無法完成登入，請確認網路連線後再試一次。";
  }
}

export function initLoginPage() {
  retryBtnEl().addEventListener("click", () => {
    if (retryBtnEl().dataset.mode === "select") {
      void runLoginFlow(organizationSelectEl().value);
      return;
    }
    pendingLineIdentity = null;
    void runLoginFlow();
  });
  runLoginFlow();
}
