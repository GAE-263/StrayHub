// ============================================================
// 主選單頁邏輯
// 顯示目前登入者資訊，並提供「新增收容動物」「更新現有動物紀錄」兩個入口。
// ============================================================

import { getState, resetAddAnimalDraft, resetUpdateAnimalDraft } from "../state.js";
import { showScreen } from "../router.js";
import { liffLogout } from "../liff-init.js";

const ROLE_LABEL = {
  volunteer: "志工",
  staff: "工作人員",
};

export function initMenuPage() {
  document
    .getElementById("btn-goto-add-animal")
    .addEventListener("click", () => {
      resetAddAnimalDraft();
      showScreen("screen-add-animal");
    });

  document
    .getElementById("btn-goto-update-animal")
    .addEventListener("click", () => {
      resetUpdateAnimalDraft();
      showScreen("screen-update-animal");
    });

  document.getElementById("btn-logout").addEventListener("click", () => {
    if (confirm("確定要登出嗎？")) {
      liffLogout();
    }
  });
}

// 每次「進入」主選單畫面都重新渲染一次使用者資訊
// (從其他頁面按返回鍵回到主選單時，也會確保資料是最新的)
export function renderMenuUserInfo() {
  const { currentUser } = getState();
  if (!currentUser) return;

  document.getElementById("menu-user-name").textContent = currentUser.displayName;
  document.getElementById("menu-user-role").textContent =
    ROLE_LABEL[currentUser.role] || currentUser.role;
  const avatarEl = document.getElementById("menu-user-avatar");
  if (currentUser.pictureUrl) {
    avatarEl.src = currentUser.pictureUrl;
  }
}
