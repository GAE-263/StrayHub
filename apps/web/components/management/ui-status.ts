export type UIStatusKind =
  | "loading"
  | "saving"
  | "success"
  | "empty"
  | "no-results"
  | "error"
  | "permission-denied"
  | "processing"
  | "ai-failed"
  | "needs-review";

export type UIStatusState = {
  kind: UIStatusKind;
  title: string;
  description?: string;
  actionLabel?: string;
  tone?: "neutral" | "success" | "warning" | "danger";
  ariaLive?: "polite" | "assertive" | "off";
};

export const STATUS_LABELS: Record<UIStatusKind, string> = {
  loading: "載入中",
  saving: "儲存中",
  success: "已完成",
  empty: "目前沒有資料",
  "no-results": "沒有符合條件的結果",
  error: "發生錯誤",
  "permission-denied": "沒有查看權限",
  processing: "AI 處理中",
  "ai-failed": "AI 暫時無法使用",
  "needs-review": "需要人工覆核",
};

export const STATUS_TONES: Record<UIStatusKind, UIStatusState["tone"]> = {
  loading: "neutral",
  saving: "neutral",
  success: "success",
  empty: "neutral",
  "no-results": "neutral",
  error: "danger",
  "permission-denied": "warning",
  processing: "neutral",
  "ai-failed": "warning",
  "needs-review": "warning",
};

const VALUE_LABELS: Record<string, string> = {
  active: "啟用中",
  inactive: "已停用",
  archived: "已封存",
  saved: "已保存",
  amended: "已修正",
  processing: "AI 處理中",
  running: "AI 處理中",
  succeeded: "需要人工覆核",
  failed: "AI 處理失敗",
  invalid: "AI 輸出無效",
  "ai-failed": "AI 暫時無法使用",
  "needs-review": "需要人工覆核",
  pending: "等待處理",
  not_required: "無需 AI 處理",
};

export function statusLabel(value: string | null | undefined) {
  if (!value) return "未提供";
  return VALUE_LABELS[value] ?? value;
}

export function statusSummary(value: string | null | undefined) {
  if (!value) return "未提供";
  const label = statusLabel(value);
  // An unmapped value falls back to itself; repeating it as "x（x）" is noise.
  return label === value ? label : `${label}（${value}）`;
}

export function getStatusSemantics(kind: UIStatusKind) {
  return {
    label: STATUS_LABELS[kind],
    tone: STATUS_TONES[kind],
    ariaLive: kind === "error" ? "assertive" : "polite",
  } as const;
}
