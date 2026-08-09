"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ACCESS_TOKEN_KEY,
  ACTIVE_ORGANIZATION_CODE_KEY,
  ACTIVE_ORGANIZATION_ID_KEY,
  REFRESH_TOKEN_KEY,
  SESSION_ID_KEY,
  clearAuth,
} from "../../lib/auth";

type Organization = {
  id: string;
  code: string;
  name: string;
  role: string;
};

type LoginResponse = {
  access_token: string;
  refresh_token: string;
  session_id: string;
  organizations?: Organization[];
};

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { message?: string };
    return body.message ?? `登入失敗（HTTP ${response.status}）`;
  } catch {
    return `登入失敗（HTTP ${response.status}）`;
  }
}

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("local-staff-a");
  const [password, setPassword] = useState("local-only-password");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    clearAuth();
    try {
      const loginResponse = await fetch("/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!loginResponse.ok) throw new Error(await readError(loginResponse));
      const login = (await loginResponse.json()) as LoginResponse;
      const organization = login.organizations?.find(
        (item) => item.code === "ORG-A",
      );
      if (!organization) {
        throw new Error("此帳號沒有 ORG-A 的有效授權，無法進入管理首頁。");
      }

      window.sessionStorage.setItem(ACCESS_TOKEN_KEY, login.access_token);
      window.sessionStorage.setItem(REFRESH_TOKEN_KEY, login.refresh_token);
      window.sessionStorage.setItem(SESSION_ID_KEY, login.session_id);

      const contextResponse = await fetch("/v1/auth/active-shelter-context", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${login.access_token}`,
        },
        body: JSON.stringify({ organization_id: organization.id }),
      });
      if (!contextResponse.ok)
        throw new Error(await readError(contextResponse));
      window.sessionStorage.setItem(
        ACTIVE_ORGANIZATION_ID_KEY,
        organization.id,
      );
      window.sessionStorage.setItem(
        ACTIVE_ORGANIZATION_CODE_KEY,
        organization.code,
      );
      router.replace("/");
    } catch (submitError) {
      clearAuth();
      setError(submitError instanceof Error ? submitError.message : "登入失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main aria-labelledby="login-title">
      <h1 id="login-title">浪浪森友會管理入口</h1>
      <p>登入後會自動切換至 ORG-A，並開啟動物近期歷程。</p>
      <form onSubmit={submit}>
        <label htmlFor="username">帳號</label>
        <input
          id="username"
          name="username"
          autoComplete="username"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          required
        />
        <label htmlFor="password">密碼</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
        {error ? <p role="alert">{error}</p> : null}
        <button type="submit" disabled={submitting}>
          {submitting ? "登入中…" : "登入"}
        </button>
      </form>
    </main>
  );
}
