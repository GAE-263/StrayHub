// ============================================================
// 全域狀態管理
// 這個專案沒有用 React/Vue，所以用一個簡單的物件當作「全域狀態」，
// 搭配 subscribe/notify 讓畫面元件知道狀態變了、該重新渲染。
// 規模夠小，這樣做比硬塞一個前端框架更快、更好維護。
// ============================================================

const state = {
  // LINE 登入後的使用者資訊
  // Access token 由 api.js module closure 持有，不寫入 localStorage/sessionStorage/state。
  currentUser: null, // { displayName, pictureUrl, role, organizationId }

  // 目前顯示的畫面 id，對應 index.html 裡各個 <section id="screen-xxx">
  currentScreen: "screen-login",

  // 新增動物流程暫存的資料(還沒送出前，畫面切換不會遺失使用者已經填的東西)
  addAnimalDraft: {
    photoFile: null,
    animalId: null,
    name: "",
    species: "dog",
    breed: "",
    gender: "unknown",
    estimatedAge: "",
    size: "medium",
    foundLocation: "",
    notes: "",
  },

  // 更新動物流程暫存的資料
  updateAnimalDraft: {
    animalId: "",
    matchedAnimal: null, // 查到動物後，後端回傳的基本資料(名稱/照片等)顯示用
    photoFile: null,
    healthStatus: "healthy",
    healthNotes: "",
  },
};

const listeners = [];

export function getState() {
  return state;
}

// 畫面元件呼叫這個來訂閱狀態變化(目前主要拿來驅動「送出按鈕能不能按」這類判斷)
export function subscribe(fn) {
  listeners.push(fn);
}

// 統一的狀態更新入口：淺層合併(shallow merge)進 state，並通知所有訂閱者
export function setState(partial) {
  Object.assign(state, partial);
  listeners.forEach((fn) => fn(state));
}

// 重置「新增動物」草稿，送出成功或使用者返回主選單時呼叫
export function resetAddAnimalDraft() {
  setState({
    addAnimalDraft: {
      photoFile: null,
      animalId: null,
      name: "",
      species: "dog",
      breed: "",
      gender: "unknown",
      estimatedAge: "",
      size: "medium",
      foundLocation: "",
      notes: "",
    },
  });
}

// 重置「更新動物」草稿
export function resetUpdateAnimalDraft() {
  setState({
    updateAnimalDraft: {
      animalId: "",
      matchedAnimal: null,
      photoFile: null,
      healthStatus: "healthy",
      healthNotes: "",
    },
  });
}
