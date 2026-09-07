"use client";

import React, { useEffect, useState } from "react";
import {
  Check,
  Copy,
  Link2,
  RefreshCw,
  UserRound,
  UsersRound,
} from "lucide-react";
import { accountRequest, type JoinApplication } from "../../../lib/google-auth";
import {
  IdentityShell,
  IdentityNotice,
} from "../../../components/auth/IdentityShell";
import { Button } from "../../../components/ui/button";
import { Label } from "../../../components/ui/label";
import { Select } from "../../../components/ui/select";
import styles from "../../../components/auth/identity.module.css";

export default function ApplicationsPage() {
  const [organization, setOrganization] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [items, setItems] = useState<JoinApplication[]>([]);
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [link, setLink] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [copied, setCopied] = useState(false);
  const load = async (id: string) => {
    const context = await accountRequest<{ organization_name?: string }>(
      "/v1/auth/active-shelter-context",
      { method: "PUT", body: { organization_id: id } },
    );
    const next = await accountRequest<JoinApplication[]>(
      `/v1/organizations/${id}/join-applications`,
    );
    setItems(next);
    setOrganizationName(
      context.organization_name ?? next[0]?.organization_name ?? "目前收容所",
    );
    setLink(`${window.location.origin}/access?join=${id}`);
    setLoaded(true);
  };
  useEffect(() => {
    const id =
      new URL(window.location.href).searchParams.get("organization") ?? "";
    if (!/^[0-9a-f-]{36}$/i.test(id)) {
      setError("請從「我的收容所」選擇要管理的收容所。");
      return;
    }
    setOrganization(id);
    void load(id).catch(() =>
      setError("無法載入申請，請確認你已登入並有此收容所的管理權限。"),
    );
  }, []);
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await load(organization);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "暫時無法完成，請重新整理。",
      );
    } finally {
      setBusy(false);
    }
  };
  const review = (item: JoinApplication, approve: boolean) =>
    void run(async () => {
      await accountRequest(
        `/v1/organizations/${organization}/join-applications/${item.id}/decision`,
        {
          method: "POST",
          body: approve
            ? { approve: true, role: roles[item.id] }
            : { approve: false },
        },
      );
      setRejecting(null);
      setNotice(
        approve
          ? `已核准 ${item.display_name ?? "申請人"} 加入，權限為${roles[item.id] === "SHELTER_ADMIN" ? "收容所管理員" : "工作人員"}。`
          : `已否決 ${item.display_name ?? "申請人"} 的申請，並移出待審清單。`,
      );
    });
  return (
    <IdentityShell
      title="加入申請"
      eyebrow={organizationName || "團隊管理"}
      description="確認新夥伴的身分，再為他安排合適的工作權限。"
      back={{ href: "/access", label: "回我的收容所" }}
      actions={
        <>
          {link && (
            <a href="#join-link">
              <Link2 size={15} aria-hidden="true" />
              分享連結
            </a>
          )}
          <Button
            variant="secondary"
            disabled={busy || !organization}
            onClick={() => void run(async () => {})}
          >
            <RefreshCw size={15} aria-hidden="true" />
            重新整理申請
          </Button>
        </>
      }
    >
      {error && <IdentityNotice error>{error}</IdentityNotice>}
      {notice && <IdentityNotice>{notice}</IdentityNotice>}
      {!loaded && !error && (
        <div className={styles.loading} role="status">
          正在載入加入申請…
        </div>
      )}
      {loaded && (
        <div className={styles.grid}>
          <section aria-label="待審申請">
            <div className={styles.sectionHeading}>
              <h2>
                等待審核 <span className={styles.badge}>{items.length}</span>
              </h2>
            </div>
            {!items.length && (
              <div className={`${styles.card} ${styles.empty}`}>
                <span className={styles.icon}>
                  <Check aria-hidden="true" />
                </span>
                <h2>目前沒有待審申請</h2>
                <p>
                  新夥伴送出申請後，會出現在這裡。將申請連結分享給團隊，就能開始加入流程。
                </p>
              </div>
            )}
            <div className={styles.stack}>
              {items.map((item) => (
                <article
                  className={styles.card}
                  key={item.id}
                  aria-label={`${item.display_name ?? "申請人"}的申請`}
                >
                  <div className={styles.cardTop}>
                    <div className={styles.cardTitle}>
                      <span className={styles.icon}>
                        <UserRound aria-hidden="true" />
                      </span>
                      <div>
                        <h3>{item.display_name ?? "申請人"}</h3>
                        <p className={styles.helper}>
                          申請加入 {item.organization_name}
                        </p>
                      </div>
                    </div>
                    <span className={`${styles.badge} ${styles.pending}`}>
                      待審核
                    </span>
                  </div>
                  <p className={styles.helper}>
                    申請日期：
                    {new Date(item.created_at).toLocaleDateString("zh-TW", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })}
                  </p>
                  <details className={styles.identity}>
                    <summary>核對帳號識別</summary>
                    <code>{item.user_id}</code>
                  </details>
                  <div className={styles.reviewControls}>
                    <Label htmlFor={`role-${item.id}`}>核准後權限</Label>
                    <div className={styles.reviewRow}>
                      <Select
                        id={`role-${item.id}`}
                        value={roles[item.id] ?? ""}
                        disabled={busy}
                        onChange={(event) =>
                          setRoles((previous) => ({
                            ...previous,
                            [item.id]: event.target.value,
                          }))
                        }
                      >
                        <option value="">選擇工作權限</option>
                        <option value="STAFF">工作人員</option>
                        <option value="SHELTER_ADMIN">收容所管理員</option>
                      </Select>
                      <Button
                        disabled={busy || !roles[item.id]}
                        onClick={() => review(item, true)}
                      >
                        核准加入 <Check size={15} aria-hidden="true" />
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={busy}
                        aria-expanded={rejecting === item.id}
                        onClick={() => setRejecting(item.id)}
                      >
                        否決
                      </Button>
                    </div>
                    <p className={styles.googleHint}>
                      {roles[item.id] === "SHELTER_ADMIN"
                        ? "收容所管理員可管理人員與設定，每間最多兩名。"
                        : "工作人員可使用日常管理功能；人員授權由收容所管理員處理。"}
                    </p>
                  </div>
                  {rejecting === item.id && (
                    <div className={styles.confirm}>
                      <p>
                        確定否決 {item.display_name ?? "此人員"}{" "}
                        的申請？申請將移出清單，帳號與其他收容所權限不受影響。
                      </p>
                      <div className={styles.actions}>
                        <Button
                          variant="destructive"
                          disabled={busy}
                          onClick={() => review(item, false)}
                        >
                          確認否決
                        </Button>
                        <Button
                          variant="ghost"
                          disabled={busy}
                          onClick={() => setRejecting(null)}
                        >
                          取消
                        </Button>
                      </div>
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>
          <aside className={styles.stack}>
            <section className={styles.card} id="join-link">
              <span className={styles.icon}>
                <Link2 aria-hidden="true" />
              </span>
              <h2 style={{ marginTop: 16 }}>邀請夥伴加入</h2>
              <p className={styles.helper}>
                分享同一個申請連結即可，不需要為每位人員建立邀請碼。
              </p>
              <a className={styles.linkField} href={link}>
                {link}
              </a>
              <Button
                variant="secondary"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(link);
                    setCopied(true);
                  } catch {
                    setError("無法自動複製，請選取上方申請連結後手動複製。");
                  }
                }}
              >
                {copied ? (
                  <Check size={15} aria-hidden="true" />
                ) : (
                  <Copy size={15} aria-hidden="true" />
                )}
                {copied ? "已複製連結" : "複製申請連結"}
              </Button>
              {copied && (
                <span role="status" className={styles.helper}>
                  {" "}
                  連結已複製
                </span>
              )}
            </section>
            <div className={styles.note}>
              <h2>
                <UsersRound size={15} aria-hidden="true" /> 由你確認，才加入團隊
              </h2>
              <p>
                申請者目前只能查看自己的申請狀態。核准後，才會取得這間收容所的工作權限。
              </p>
            </div>
          </aside>
        </div>
      )}
    </IdentityShell>
  );
}
