import { apiFetch } from "./api";

export type AccountProfile = {
  user: {
    id: string;
    display_name: string;
    username: string | null;
    platform_role: string | null;
  };
  state: "account_only" | "ready";
  organizations: Array<{
    id: string;
    code: string;
    name: string;
    role: string;
  }>;
  login_methods: { google: boolean; password: boolean };
};

export type Invitation = {
  id: string;
  organization_id: string;
  organization_name: string;
  role: "STAFF" | "SHELTER_ADMIN";
  status: "open" | "claimed" | "approved" | "revoked" | "expired";
  expires_at: string;
  claimed_by: string | null;
  display_name: string | null;
};

const messages: Record<string, string> = {
  join_target_unavailable: "此收容所無法接受申請，請確認管理者提供的連結。",
  join_retry_later: "申請未通過，請隔一天再重新申請。",
  join_already_reviewed: "此申請已處理，請重新整理。",
  invitation_replaced: "已改用加入申請，請向管理者取得固定申請連結。",
  google_registration_required:
    "尚未建立 Google 登入帳號。請選擇建立新帳號，或使用原帳密登入後綁定。",
  google_binding_conflict: "無法綁定此 Google 帳號，請確認是否已用於其他帳號。",
  invalid_transaction: "登入交易已失效，請重新開始。",
  invalid_google_token: "Google 身分驗證失敗，請重新開始。",
  invalid_credentials: "原帳號密碼驗證失敗。",
  login_rate_limited: "嘗試次數較多，請稍後再試。",
  invitation_invalid: "邀請碼無效、已認領或已到期。",
  membership_exists: "此帳號已有成員紀錄，請由管理者確認原有資格。",
  shelter_admin_limit_reached: "收容所啟用中的管理員已達兩名上限。",
};

export async function accountRequest<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    authenticated?: boolean;
    csrf?: string;
  } = {},
): Promise<T> {
  const headers = new Headers();
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    headers.set("X-StrayHub-Account", "1");
  }
  if (options.csrf) headers.set("X-CSRF-Token", options.csrf);
  const init = {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store" as const,
    credentials: "same-origin" as const,
  };
  const response = await (options.authenticated === false
    ? fetch(path, init)
    : apiFetch(path, init));
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { code?: string };
    // Never render raw server/provider messages or credentials.
    throw new Error(
      messages[body.code ?? ""] ??
        (response.status === 401
          ? "登入已到期，請重新登入或再試一次。"
          : "暫時無法完成，請稍後再試。"),
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export const invitationStatus: Record<Invitation["status"], string> = {
  open: "尚未認領",
  claimed: "等待管理者確認",
  approved: "已核准",
  revoked: "已撤銷",
  expired: "已到期",
};

export type JoinApplication = {
  id: string;
  organization_id: string;
  organization_name: string;
  user_id: string;
  display_name: string | null;
  status: "pending" | "approved" | "rejected";
  role: "STAFF" | "SHELTER_ADMIN" | null;
  created_at: string;
  reviewed_at: string | null;
};

export const applicationStatus = {
  pending: "等待管理者審核",
  approved: "已核准",
  rejected: "未通過審核（可於一天後重新申請）",
};

export function joinAccountPath(): string | null {
  if (typeof window === "undefined") return null;
  const id = new URL(window.location.href).searchParams.get("join") ?? "";
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    id,
  )
    ? `/access?join=${encodeURIComponent(id)}`
    : null;
}
