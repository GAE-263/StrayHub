"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Building2,
  Check,
  Clock3,
  LogOut,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import {
  accountRequest,
  joinAccountPath,
  type AccountProfile,
  type JoinApplication,
} from "../../lib/google-auth";
import {
  clearAuth,
  getAccessToken,
  storeActiveOrganization,
} from "../../lib/auth";
import { Button } from "../../components/ui/button";
import {
  IdentityShell,
  IdentityNotice,
} from "../../components/auth/IdentityShell";
import styles from "../../components/auth/identity.module.css";

const roleLabel: Record<string, string> = {
  STAFF: "工作人員",
  SHELTER_ADMIN: "收容所管理員",
  PLATFORM_ADMIN: "平台管理員",
  VOLUNTEER: "志工",
};

export default function AccessPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [applications, setApplications] = useState<JoinApplication[]>([]);
  const [target, setTarget] = useState<{ id: string; name: string } | null>(
    null,
  );
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const enter = useCallback(
    async (organization: AccountProfile["organizations"][number]) => {
      await accountRequest("/v1/auth/active-shelter-context", {
        method: "PUT",
        body: { organization_id: organization.id },
      });
      storeActiveOrganization(organization);
      router.replace(
        organization.role === "VOLUNTEER" ? "/animal-confirmation" : "/",
      );
    },
    [router],
  );
  const load = useCallback(
    async (initial = false) => {
      const continuation = joinAccountPath();
      if (!getAccessToken()) {
        router.replace(
          continuation ? continuation.replace("/access", "/login") : "/login",
        );
        return;
      }
      const next = await accountRequest<AccountProfile>("/v1/auth/account");
      setProfile(next);
      // Only the initial post-login handoff auto-enters; manual visits stay navigable.
      if (
        initial &&
        !continuation &&
        new URL(window.location.href).searchParams.get("entry") === "1"
      ) {
        window.history.replaceState({}, "", "/access");
        if (next.organizations.length === 1) {
          await enter(next.organizations[0]);
          return;
        }
        if (
          !next.organizations.length &&
          next.user.platform_role === "PLATFORM_ADMIN"
        ) {
          router.replace("/platform-admins");
          return;
        }
      }
      setApplications(
        await accountRequest<JoinApplication[]>("/v1/auth/join-applications"),
      );
      if (continuation) {
        const id = new URL(window.location.href).searchParams.get("join");
        setTarget(await accountRequest(`/v1/auth/join-target/${id}`));
      }
    },
    [router, enter],
  );
  useEffect(() => {
    void load(true)
      .catch((cause) =>
        setError(
          cause instanceof Error
            ? cause.message
            : "無法載入收容所，請重新整理。",
        ),
      )
      .finally(() => setLoading(false));
  }, [load]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "暫時無法完成，請再試一次。",
      );
    } finally {
      setBusy(false);
    }
  };
  const logout = async () => {
    try {
      await accountRequest("/v1/auth/logout", { method: "POST" });
    } finally {
      clearAuth();
      router.replace("/login");
    }
  };
  const latest = applications.filter(
    (item, index, all) =>
      all.findIndex(
        (other) => other.organization_id === item.organization_id,
      ) === index,
  );
  const targetApplication = latest.find(
    (item) => item.organization_id === target?.id,
  );
  const targetMembership = profile?.organizations.find(
    (item) => item.id === target?.id,
  );
  const pending = latest.filter((item) => item.status === "pending");
  const history = latest.filter(
    (item) =>
      !(
        item.organization_id === target?.id &&
        item.status === "pending" &&
        !targetMembership
      ),
  );
  const inCooldown =
    targetApplication?.status === "rejected" &&
    !!targetApplication.reviewed_at &&
    Date.now() - Date.parse(targetApplication.reviewed_at) < 86400000;
  return (
    <IdentityShell
      title="我的收容所"
      eyebrow={profile ? `你好，${profile.user.display_name}` : "歡迎回來"}
      description={
        profile?.organizations.length
          ? "選擇今天工作的地方，接續牠們的日常。"
          : "你已完成登入。加入收容所後，就能和團隊一起開始工作。"
      }
      actions={
        <>
          {profile?.login_methods.password && (
            <Link href="/account">登入設定</Link>
          )}
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => void run(logout)}
          >
            <LogOut size={15} aria-hidden="true" />
            登出
          </Button>
        </>
      }
    >
      {error && (
        <IdentityNotice error>
          {error}{" "}
          <Button
            variant="link"
            disabled={busy}
            onClick={() => void run(() => load())}
          >
            重新整理
          </Button>
        </IdentityNotice>
      )}
      {notice && <IdentityNotice>{notice}</IdentityNotice>}
      {loading ? (
        <div className={styles.loading} role="status">
          正在確認你的收容所…
        </div>
      ) : (
        profile && (
          <div className={styles.grid}>
            <div className={styles.stack}>
              {target && !targetMembership && (
                <section className={styles.card} aria-label="加入收容所">
                  <div className={styles.cardTitle}>
                    <span className={styles.icon}>
                      <Building2 aria-hidden="true" />
                    </span>
                    <div>
                      <span className={styles.eyebrow}>
                        {targetApplication?.status === "pending"
                          ? "等待審核"
                          : "加入團隊"}
                      </span>
                      <h2>{target.name}</h2>
                    </div>
                  </div>
                  <ol className={styles.steps} aria-label="加入進度">
                    <li className={styles.done}>完成登入</li>
                    <li
                      aria-current={
                        targetApplication?.status === "pending"
                          ? undefined
                          : "step"
                      }
                      className={
                        targetApplication?.status === "pending"
                          ? styles.done
                          : styles.current
                      }
                    >
                      送出申請
                    </li>
                    <li
                      aria-current={
                        targetApplication?.status === "pending"
                          ? "step"
                          : undefined
                      }
                      className={
                        targetApplication?.status === "pending"
                          ? styles.current
                          : undefined
                      }
                    >
                      管理員審核
                    </li>
                  </ol>
                  <p className={styles.helper}>
                    {targetApplication?.status === "pending"
                      ? "申請已送達管理員，現在可以先離開。下次登入仍能查看進度。"
                      : "確認這是你要加入的收容所，再送出申請。管理員將核對身分並設定工作權限。"}
                  </p>
                  <Button
                    disabled={
                      busy ||
                      targetApplication?.status === "pending" ||
                      inCooldown
                    }
                    onClick={() =>
                      void run(async () => {
                        await accountRequest("/v1/auth/join-applications", {
                          method: "POST",
                          body: { organization_id: target.id },
                        });
                        setNotice("申請已送出，等待收容所管理員審核。");
                        await load();
                      })
                    }
                  >
                    {targetApplication?.status === "pending" ? (
                      <>
                        <Check size={16} aria-hidden="true" />
                        已送出申請
                      </>
                    ) : inCooldown ? (
                      "一天後可重新申請"
                    ) : (
                      "送出加入申請"
                    )}
                  </Button>
                  {targetApplication?.status === "pending" && (
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          await load();
                          setNotice("已更新申請狀態。");
                        })
                      }
                    >
                      <RefreshCw size={14} aria-hidden="true" />
                      更新狀態
                    </Button>
                  )}
                </section>
              )}
              {profile.user.platform_role === "PLATFORM_ADMIN" && (
                <section className={styles.card}>
                  <div className={styles.cardTitle}>
                    <span className={styles.icon}>
                      <ShieldCheck aria-hidden="true" />
                    </span>
                    <div>
                      <h2>平台管理</h2>
                      <p className={styles.helper}>管理收容所與平台治理。</p>
                    </div>
                  </div>
                  <Link className={styles.textLink} href="/platform-admins">
                    進入平台管理 <ArrowRight size={16} aria-hidden="true" />
                  </Link>
                </section>
              )}
              {profile.organizations.map((org) => (
                <section className={styles.card} key={org.id}>
                  <div className={styles.cardTop}>
                    <div className={styles.cardTitle}>
                      <span className={styles.icon}>
                        <Building2 aria-hidden="true" />
                      </span>
                      <h2>{org.name}</h2>
                    </div>
                    <span className={styles.badge}>
                      {roleLabel[org.role] ?? "成員"}
                    </span>
                  </div>
                  <div className={styles.cardActions}>
                    <Button
                      disabled={busy}
                      onClick={() => void run(() => enter(org))}
                    >
                      進入工作台 <ArrowRight size={16} aria-hidden="true" />
                    </Button>
                    {["SHELTER_ADMIN", "PLATFORM_ADMIN"].includes(org.role) && (
                      <Link
                        className={styles.textLink}
                        href={`/account/invitations?organization=${org.id}`}
                      >
                        加入申請
                      </Link>
                    )}
                  </div>
                </section>
              ))}
              {!target &&
                !profile.organizations.length &&
                !pending.length &&
                profile.user.platform_role !== "PLATFORM_ADMIN" && (
                  <section className={`${styles.card} ${styles.empty}`}>
                    <span className={styles.icon}>
                      <Building2 aria-hidden="true" />
                    </span>
                    <h2>下一步，加入你的收容所</h2>
                    <p>
                      請向收容所管理員取得申請連結。開啟連結後，就能確認收容所並送出加入申請。
                    </p>
                  </section>
                )}
              {history.length > 0 && (
                <section aria-label="申請進度">
                  <div className={styles.sectionHeading}>
                    <h2>申請進度</h2>
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          await load();
                          setNotice("已更新申請狀態。");
                        })
                      }
                    >
                      <RefreshCw size={14} aria-hidden="true" />
                      更新狀態
                    </Button>
                  </div>
                  <div className={styles.stack}>
                    {history.map((item) => (
                      <article key={item.id} className={styles.card}>
                        <div className={styles.cardTop}>
                          <h3>{item.organization_name}</h3>
                          <span
                            className={`${styles.badge} ${item.status === "pending" ? styles.pending : item.status === "rejected" ? styles.rejected : ""}`}
                          >
                            {item.status === "pending" ? (
                              <>
                                <Clock3 size={13} aria-hidden="true" />
                                等待審核
                              </>
                            ) : item.status === "approved" ? (
                              "已核准"
                            ) : (
                              "未通過"
                            )}
                          </span>
                        </div>
                        <p className={styles.helper}>
                          {item.status === "pending"
                            ? "管理員確認後，這裡會出現工作台入口。"
                            : item.status === "approved"
                              ? "已取得權限，可從上方收容所卡片進入工作台。"
                              : "如需了解原因，請聯絡收容所管理員。一天後可透過申請連結重新送出。"}
                        </p>
                      </article>
                    ))}
                  </div>
                </section>
              )}
            </div>
            <aside className={styles.note}>
              <h2>一個帳號，與不同團隊一起工作</h2>
              <p>
                每間收容所分別管理人員權限。加入新的收容所，不會改變你在其他團隊的資格。
              </p>
              <p>等待審核期間，可以登出並稍後回來查看。</p>
              <details className={styles.identity}>
                <summary>查看我的帳號識別</summary>
                <code>{profile.user.id}</code>
                <p>管理員核對身分時，可提供這組識別碼。</p>
              </details>
            </aside>
          </div>
        )
      )}
    </IdentityShell>
  );
}
