// ============================================================
// 極簡畫面切換邏輯
// 這個 App 只有 4 個畫面、流程單純，不需要引入完整的前端路由套件。
// 做法：每個畫面都是 index.html 裡一個 <section class="screen">，
// 切換畫面就是「隱藏其他、顯示目標」，並呼叫該畫面對應的初始化函式。
// ============================================================

import { setState } from "./state.js";

// key 是畫面 id，value 是切換到該畫面時要執行的初始化函式(由 app.js 註冊)
const screenInitializers = {};

export function registerScreen(screenId, onEnter) {
  screenInitializers[screenId] = onEnter;
}

export function showScreen(screenId) {
  document.querySelectorAll(".screen").forEach((el) => {
    el.classList.add("hidden");
  });

  const target = document.getElementById(screenId);
  if (!target) {
    console.error(`找不到畫面: ${screenId}`);
    return;
  }
  target.classList.remove("hidden");
  // 每次切換畫面都捲動回頂部，避免使用者在長表單頁往下滑過、切換後停在奇怪位置
  window.scrollTo({ top: 0, behavior: "instant" });

  setState({ currentScreen: screenId });

  // 如果這個畫面有註冊「進入時要做的事」(例如重置表單、帶入資料)，就執行它
  if (typeof screenInitializers[screenId] === "function") {
    screenInitializers[screenId]();
  }
}
