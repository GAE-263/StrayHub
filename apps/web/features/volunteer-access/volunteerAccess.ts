export type EffectiveStatus =
  | "none"
  | "pending"
  | "upcoming"
  | "active"
  | "expired"
  | "revoked"
  | "rejected"
  | "withdrawn";

export type VolunteerStatus = {
  organization: {
    id: string;
    name: string;
    applications_enabled: boolean;
    insurance_required: boolean;
  };
  application: {
    id: string;
    status: string;
    version: number;
    submitted_at?: string;
    decision_reason?: string | null;
  } | null;
  grant: {
    id: string;
    status: string;
    valid_from: string;
    expires_at: string;
    version: number;
  } | null;
  effective_status: EffectiveStatus | string;
  next_actions: string[];
};

export function formatTaiwanDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function formatRemainingDuration(
  expiresAt: string,
  now = new Date(),
): string {
  const milliseconds = Math.max(
    0,
    new Date(expiresAt).getTime() - now.getTime(),
  );
  const totalMinutes = Math.floor(milliseconds / 60_000);
  const days = Math.floor(totalMinutes / (24 * 60));
  const hours = Math.floor((totalMinutes % (24 * 60)) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return `${days} 天 ${hours} 小時`;
  if (hours > 0) return `${hours} 小時 ${minutes} 分鐘`;
  return `${minutes} 分鐘`;
}

export function safeVolunteerError(code?: string): string {
  const messages: Record<string, string> = {
    entry_unavailable: "此收容所志工入口目前無法使用，請回到 LINE 聯絡收容所。",
    volunteer_applications_disabled: "此收容所目前暫停接受新申請。",
    application_version_conflict: "申請狀態已更新，請重新載入。",
    dependency_unavailable: "LINE 身分服務暫時無法使用，請稍後再試。",
  };
  return messages[code ?? ""] ?? "目前無法取得報名狀態，請稍後再試。";
}
