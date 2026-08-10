"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  clearAuth,
  storeActiveOrganization,
  storeSession,
  type AuthOrganization,
} from "../../lib/auth";

type LoginResponse = {
  access_token: string;
  refresh_token: string;
  session_id: string;
  organizations?: AuthOrganization[];
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
  const [organizations, setOrganizations] = useState<AuthOrganization[]>([]);
  const [selectedOrganizationId, setSelectedOrganizationId] = useState("");
  const [pendingLogin, setPendingLogin] = useState<LoginResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const activateContext = async (
    login: LoginResponse,
    organization: AuthOrganization,
  ) => {
    storeSession(login);
    const contextResponse = await fetch("/v1/auth/active-shelter-context", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${login.access_token}`,
      },
      body: JSON.stringify({ organization_id: organization.id }),
    });
    if (!contextResponse.ok) throw new Error(await readError(contextResponse));
    storeActiveOrganization(organization);
    router.replace("/");
  };

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
      const availableOrganizations = login.organizations ?? [];
      setOrganizations(availableOrganizations);
      const organization = availableOrganizations[0];
      if (!organization) {
        throw new Error("此帳號沒有可用的收容所授權，無法進入管理工作台。");
      }
      storeSession(login);
      if (availableOrganizations.length > 1) {
        setPendingLogin(login);
        setSelectedOrganizationId(organization.id);
        return;
      }
      await activateContext(login, organization);
    } catch (submitError) {
      clearAuth();
      setError(submitError instanceof Error ? submitError.message : "登入失敗");
    } finally {
      setSubmitting(false);
    }
  };

  const confirmContext = async () => {
    const organization = organizations.find(
      (item) => item.id === selectedOrganizationId,
    );
    if (!pendingLogin || !organization) return;
    setSubmitting(true);
    setError("");
    try {
      await activateContext(pendingLogin, organization);
    } catch (contextError) {
      clearAuth();
      setPendingLogin(null);
      setError(
        contextError instanceof Error
          ? contextError.message
          : "Context 設定失敗",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main aria-labelledby="login-title">
      <h1 id="login-title">浪浪森友會管理入口</h1>
      <p>登入後會建立 Active Shelter Context，進入角色感知管理工作台。</p>
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
        {pendingLogin && organizations.length > 1 ? (
          <>
            <label htmlFor="organization">目前收容所</label>
            <select
              id="organization"
              value={selectedOrganizationId || organizations[0]?.id}
              onChange={(event) =>
                setSelectedOrganizationId(event.target.value)
              }
              required
            >
              {organizations.map((organization) => (
                <option key={organization.id} value={organization.id}>
                  {organization.name}（{organization.code}）
                </option>
              ))}
            </select>
          </>
        ) : null}
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
        <button type="submit" disabled={submitting || Boolean(pendingLogin)}>
          {submitting ? "登入中…" : "登入"}
        </button>
      </form>
      {pendingLogin && organizations.length > 1 ? (
        <section
          className="panel login-context-panel"
          aria-labelledby="context-title"
        >
          <h2 id="context-title">確認目前收容所</h2>
          <p className="muted">
            請選擇這次工作的 Active Shelter Context；後端會重新驗證 Membership。
          </p>
          <button
            className="button"
            type="button"
            disabled={submitting}
            onClick={() => void confirmContext()}
          >
            {submitting ? "設定中…" : "進入管理工作台"}
          </button>
        </section>
      ) : null}
    </main>
  );
}
