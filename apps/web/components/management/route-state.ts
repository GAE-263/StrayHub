export const LOGIN_STATE_COPY = {
  idle: {
    label: "尚未登入",
    nextStep: "輸入帳號與密碼後登入。",
  },
  saving: {
    label: "正在登入",
    nextStep: "請稍候，正在建立登入與收容所情境。",
  },
  success: {
    label: "登入成功",
    nextStep: "正在進入管理工作台。",
  },
  invalidCredentials: {
    label: "帳號或密碼錯誤",
    nextStep: "請確認帳號與密碼後重試。",
  },
  noShelterAccess: {
    label: "沒有收容所授權",
    nextStep: "請聯絡收容所管理者開通授權。",
  },
  contextFailure: {
    label: "收容所情境設定失敗",
    nextStep: "請重新選擇收容所或稍後重試。",
  },
} as const;

export const MANAGEMENT_HOME_STATE_COPY = {
  loading: {
    label: "載入中",
    nextStep: "請稍候，正在載入目前收容所摘要。",
  },
  emptyRecentReports: {
    label: "目前沒有最近回報",
    nextStep: "新回報會在這裡出現，也可以先查看動物清單。",
  },
  error: {
    label: "Dashboard 載入失敗",
    nextStep: "請重試；目前收容所與權限不會被改變。",
  },
  permissionDenied: {
    label: "沒有查看權限",
    nextStep: "請切換到已授權收容所，或聯絡收容所管理者。",
  },
  success: {
    label: "摘要已載入",
    nextStep: "可從快速入口前往動物、回報或 AI Review。",
  },
} as const;

export type LoginState = keyof typeof LOGIN_STATE_COPY;
export type ManagementHomeState = keyof typeof MANAGEMENT_HOME_STATE_COPY;
