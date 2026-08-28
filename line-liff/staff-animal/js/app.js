// ============================================================
// App 進入點
// 負責：把每個畫面的初始化函式註冊進 router，然後啟動登入流程。
// ============================================================

import { registerScreen, showScreen } from "./router.js";
import { initLoginPage } from "./pages/login.js";
import { initMenuPage, renderMenuUserInfo } from "./pages/menu.js";
import { initAddAnimalPage, onEnterAddAnimalPage } from "./pages/addAnimal.js";
import {
  initUpdateAnimalPage,
  onEnterUpdateAnimalPage,
} from "./pages/updateAnimal.js";

// 各畫面「一次性」的事件綁定(按鈕點擊等)，App啟動時執行一次就好
initMenuPage();
initAddAnimalPage();
initUpdateAnimalPage();

// 各畫面「每次進入」都要重新執行的邏輯(重置表單、產生新ID、渲染最新使用者資訊)
registerScreen("screen-menu", renderMenuUserInfo);
registerScreen("screen-add-animal", onEnterAddAnimalPage);
registerScreen("screen-update-animal", onEnterUpdateAnimalPage);

// App 啟動：從登入頁開始
showScreen("screen-login");
initLoginPage();
