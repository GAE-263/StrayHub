"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { accountRequest, joinAccountPath } from "../../lib/google-auth";
import { clearAuth, storeSession, storeSessionSource } from "../../lib/auth";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import styles from "./identity.module.css";

type Gis = {
  accounts: {
    id: {
      initialize: (options: {
        client_id: string;
        nonce: string;
        ux_mode: "popup";
        auto_select: false;
        callback: (result: { credential: string }) => void;
      }) => void;
      renderButton: (
        element: HTMLElement,
        options: {
          type: "standard";
          theme: "outline";
          size: "large";
          shape?: "pill";
          width?: number;
          locale?: string;
        },
      ) => void;
    };
  };
};
declare global {
  interface Window {
    google?: Gis;
  }
}
let scriptPromise: Promise<Gis> | null = null;
function loadGis(): Promise<Gis> {
  if (window.google) return Promise.resolve(window.google);
  if (!scriptPromise)
    scriptPromise = new Promise<Gis>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      // GIS localhost setup requires a referrer; the script has no credential URL.
      script.referrerPolicy = "strict-origin-when-cross-origin";
      const timer = setTimeout(() => {
        script.remove();
        reject(new Error("Google 載入逾時，請稍後再試。"));
      }, 10000);
      script.onload = () => {
        clearTimeout(timer);
        window.google
          ? resolve(window.google)
          : reject(new Error("Google 載入失敗。"));
      };
      script.onerror = () => {
        clearTimeout(timer);
        script.remove();
        reject(new Error("Google 載入失敗，請確認網路。"));
      };
      document.head.appendChild(script);
    }).catch((error: unknown) => {
      scriptPromise = null;
      throw error;
    });
  return scriptPromise;
}

export function GoogleSignIn({
  link = false,
  onLinked,
  onAvailability,
}: {
  link?: boolean;
  onLinked?: () => void;
  onAvailability?: (enabled: boolean) => void;
}) {
  const router = useRouter();
  const [enabled, setEnabled] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [register, setRegister] = useState(false);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const target = useRef<HTMLDivElement>(null);
  const epoch = useRef(0);
  useEffect(() => {
    let active = true;
    void accountRequest<{ enabled: boolean }>("/v1/auth/google/config", {
      authenticated: false,
    })
      .then((config) => {
        if (active) {
          setEnabled(config.enabled);
          setConfigured(true);
          onAvailability?.(config.enabled);
        }
      })
      .catch(() => {
        if (active) {
          setConfigured(true);
          onAvailability?.(false);
        }
      });
    return () => {
      active = false;
      epoch.current++;
    };
  }, [onAvailability]);

  const begin = async () => {
    const generation = ++epoch.current;
    setError("");
    setBusy(true);
    setReady(false);
    target.current?.replaceChildren();
    try {
      const gis = await loadGis();
      const transaction = await accountRequest<{
        transaction_id: string;
        nonce: string;
        csrf_token: string;
        client_id: string;
      }>("/v1/auth/google/transactions", {
        method: "POST",
        authenticated: link,
        body: {
          purpose: link ? "link" : "login",
          ...(link
            ? { password }
            : register
              ? { display_name: name.trim() }
              : {}),
        },
      });
      setPassword("");
      if (generation !== epoch.current || !target.current) return;
      gis.accounts.id.initialize({
        client_id: transaction.client_id,
        nonce: transaction.nonce,
        ux_mode: "popup",
        auto_select: false,
        callback: (result) => {
          if (generation !== epoch.current) return;
          setBusy(true);
          setReady(false);
          target.current?.replaceChildren();
          void accountRequest<{
            access_token: string;
            refresh_token: string;
            session_id: string;
          }>("/v1/auth/google/exchange", {
            method: "POST",
            authenticated: link,
            csrf: transaction.csrf_token,
            body: {
              transaction_id: transaction.transaction_id,
              credential: result.credential,
            },
          })
            .then((session) => {
              if (generation !== epoch.current) return;
              if (link) {
                onLinked?.();
                return;
              }
              clearAuth();
              storeSession(session);
              storeSessionSource("local");
              router.replace(joinAccountPath() ?? "/access?entry=1");
            })
            .catch((cause: unknown) => {
              if (generation === epoch.current)
                setError(
                  cause instanceof Error ? cause.message : "Google 登入失敗。",
                );
            })
            .finally(() => {
              if (generation === epoch.current) setBusy(false);
            });
        },
      });
      gis.accounts.id.renderButton(target.current, {
        type: "standard",
        theme: "outline",
        size: "large",
        shape: "pill",
        width: Math.min(340, target.current.clientWidth || 280),
        locale: "zh_TW",
      });
      setReady(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Google 登入失敗。");
    } finally {
      if (generation === epoch.current) setBusy(false);
    }
  };
  // Prepare an ordinary login once per selected mode, never for each name/password keystroke.
  useEffect(() => {
    if (enabled && !link && !register) void begin();
    return () => {
      epoch.current++;
    };
  }, [enabled, link, register]);
  useEffect(() => {
    if (!ready) return;
    const timeout = setTimeout(() => {
      epoch.current++;
      target.current?.replaceChildren();
      setReady(false);
      setError("登入已逾時，請重新載入 Google 按鈕。");
    }, 290000);
    return () => clearTimeout(timeout);
  }, [ready]);
  if (!enabled)
    return link && configured ? (
      <p className={styles.helper}>
        Google 登入目前未開放，請稍後再試。原帳密仍可正常使用。
      </p>
    ) : null;
  const changeMode = (next: boolean) => {
    epoch.current++;
    target.current?.replaceChildren();
    setReady(false);
    setError("");
    setBusy(false);
    setRegister(next);
  };
  return (
    <section
      className={styles.google}
      aria-label={link ? "綁定 Google" : "Google 登入"}
    >
      {link ? (
        <h2>連結 Google，讓下次登入更輕鬆</h2>
      ) : (
        <div className={styles.tabs} aria-label="Google 登入方式">
          <button
            type="button"
            aria-pressed={!register}
            disabled={busy}
            onClick={() => {
              if (register) changeMode(false);
            }}
          >
            Google 登入
          </button>
          <button
            type="button"
            aria-pressed={register}
            disabled={busy}
            onClick={() => {
              if (!register) changeMode(true);
            }}
          >
            第一次使用
          </button>
        </div>
      )}
      {link ? (
        <>
          <Label htmlFor="google-password">重新驗證原帳號密碼</Label>
          <Input
            id="google-password"
            type="password"
            autoComplete="current-password"
            value={password}
            disabled={busy || ready}
            onChange={(event) => setPassword(event.target.value)}
          />
        </>
      ) : (
        <>
          {register && (
            <>
              <Label htmlFor="google-name">怎麼稱呼你？</Label>
              <Input
                id="google-name"
                maxLength={200}
                autoComplete="name"
                placeholder="填寫方便管理員辨識的姓名"
                value={name}
                disabled={busy || ready}
                onChange={(event) => setName(event.target.value)}
              />
              <p className={styles.googleHint}>
                我們會保存 Google
                登入識別與你填寫的姓名。完成註冊後，可申請加入收容所，等待管理員審核。
              </p>
            </>
          )}
        </>
      )}
      {!ready && (link || register || error) && (
        <Button
          type="button"
          disabled={
            busy || (!ready && (link ? !password : register && !name.trim()))
          }
          onClick={() => {
            if (ready) {
              epoch.current++;
              target.current?.replaceChildren();
              setReady(false);
            } else void begin();
          }}
        >
          {busy
            ? "處理中…"
            : ready
              ? "重新開始"
              : link
                ? "確認密碼並繼續"
                : register
                  ? "下一步：選擇 Google 帳號"
                  : "重新載入 Google 按鈕"}
        </Button>
      )}
      <div className={styles.googleTarget} ref={target} />
      {busy && (
        <p className={styles.googleHint} role="status">
          正在安全連線，請稍候…
        </p>
      )}
      {ready && (
        <>
          {register || link ? (
            <p className={styles.googleHint} role="status">
              請點選 Google 按鈕完成{link ? "連結" : "註冊"}。
            </p>
          ) : (
            <p className={styles.googleHint}>
              使用已連結的 Google 帳號，繼續你的工作。
            </p>
          )}
          {(register || link) && (
            <Button
              variant="ghost"
              type="button"
              onClick={() => changeMode(register)}
            >
              返回修改
            </Button>
          )}
        </>
      )}
      {error && (
        <p className={styles.noticeError} role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
