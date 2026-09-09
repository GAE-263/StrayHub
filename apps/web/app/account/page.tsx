"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, KeyRound, ShieldCheck } from "lucide-react";
import {
  accountRequest,
  joinAccountPath,
  type AccountProfile,
} from "../../lib/google-auth";
import { clearAuth, getAccessToken } from "../../lib/auth";
import { GoogleSignIn } from "../../components/auth/GoogleSignIn";
import {
  IdentityShell,
  IdentityNotice,
} from "../../components/auth/IdentityShell";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import styles from "../../components/auth/identity.module.css";

export default function AccountPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const join = joinAccountPath();
    if (join) {
      router.replace(join);
      return;
    }
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    const next = await accountRequest<AccountProfile>("/v1/auth/account");
    if (!next.login_methods.password) {
      router.replace("/access");
      return;
    }
    setProfile(next);
  }, [router]);
  useEffect(() => {
    void load().catch(() =>
      setError("無法載入登入設定，請重新整理或重新登入。"),
    );
  }, [load]);
  return (
    <IdentityShell
      title="登入設定"
      eyebrow="舊帳號也能輕鬆登入"
      description="保留原本的帳號與工作紀錄，讓下次登入更方便。"
      back={{ href: "/access", label: "回我的收容所" }}
    >
      <div className={styles.settings}>
        {error && (
          <IdentityNotice error>
            {error}
            <Button
              variant="link"
              onClick={() =>
                void load().catch(() => setError("仍無法載入，請重新登入。"))
              }
            >
              重試
            </Button>
          </IdentityNotice>
        )}
        {notice && <IdentityNotice>{notice}</IdentityNotice>}
        {!profile && !error && (
          <div className={styles.loading} role="status">
            正在確認登入方式…
          </div>
        )}
        {profile && (
          <div className={styles.stack}>
            <section className={styles.card}>
              <div className={styles.cardTitle}>
                <span className={styles.icon}>
                  <KeyRound aria-hidden="true" />
                </span>
                <div>
                  <h2>{profile.user.display_name}</h2>
                  <p className={styles.helper}>
                    原帳號：{profile.user.username ?? "已設定帳密登入"}
                  </p>
                </div>
              </div>
              <p className={styles.helper}>
                原帳密可以繼續使用。連結 Google
                後，收容所權限與歷史紀錄都會保留。
              </p>
            </section>
            <section className={styles.card}>
              {profile.login_methods.google ? (
                <>
                  <div className={styles.cardTop}>
                    <h2>Google 登入已啟用</h2>
                    <span className={styles.badge}>
                      <Check size={14} aria-hidden="true" />
                      已連結
                    </span>
                  </div>
                  <p className={styles.helper}>
                    下次可直接使用 Google 登入同一個帳號。
                  </p>
                  <details className={styles.passwordDetails}>
                    <summary>管理 Google 連結</summary>
                    <form
                      className={styles.form}
                      onSubmit={async (event) => {
                        event.preventDefault();
                        setBusy(true);
                        setError("");
                        try {
                          await accountRequest("/v1/auth/google/binding", {
                            method: "DELETE",
                            body: { password },
                          });
                          setPassword("");
                          clearAuth();
                          router.replace("/login");
                        } catch (cause) {
                          setError(
                            cause instanceof Error
                              ? cause.message
                              : "無法解除連結，請再試一次。",
                          );
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      <p className={styles.helper}>
                        解除後，所有裝置都會登出。請先確認你記得原帳號密碼。
                      </p>
                      <Label htmlFor="unlink-password">原帳號密碼</Label>
                      <Input
                        id="unlink-password"
                        type="password"
                        autoComplete="current-password"
                        required
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                      />
                      <Button
                        variant="secondary"
                        disabled={busy || !password}
                        type="submit"
                      >
                        {busy ? "正在解除…" : "驗證並解除連結"}
                      </Button>
                    </form>
                  </details>
                </>
              ) : (
                <GoogleSignIn
                  link
                  onLinked={() => {
                    setNotice("Google 已連結，下次可以直接使用 Google 登入。");
                    void load();
                  }}
                />
              )}
            </section>
            <p className={styles.helper}>
              <ShieldCheck size={15} aria-hidden="true" />{" "}
              連結前需驗證原密碼，確保操作的是你的帳號。
            </p>
          </div>
        )}
      </div>
    </IdentityShell>
  );
}
