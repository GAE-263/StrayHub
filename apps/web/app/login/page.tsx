"use client";

import React from "react";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import {
  clearAuth,
  storeActiveOrganization,
  storeSession,
  type AuthOrganization,
} from "../../lib/auth";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Select } from "../../components/ui/select";
import { LOGIN_STATE_COPY } from "../../components/management/route-state";

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
        throw new Error(
          `${LOGIN_STATE_COPY.noShelterAccess.label}：${LOGIN_STATE_COPY.noShelterAccess.nextStep}`,
        );
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
          : `${LOGIN_STATE_COPY.contextFailure.label}：${LOGIN_STATE_COPY.contextFailure.nextStep}`,
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-page" aria-labelledby="login-title">
      <Card className="login-card">
        <span className="eyebrow">STRAYHUB CRM</span>
        <h1 id="login-title">浪浪森友會管理入口</h1>
        <p className="muted">
          登入後會設定目前收容所，進入角色感知管理工作台。
        </p>
        <form
          onSubmit={submit}
          aria-describedby={error ? "login-error" : undefined}
        >
          <Label htmlFor="username">帳號</Label>
          <Input
            id="username"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
          {pendingLogin && organizations.length > 1 ? (
            <>
              <Label htmlFor="organization">目前收容所</Label>
              <Select
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
              </Select>
            </>
          ) : null}
          <Label htmlFor="password">密碼</Label>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {error ? (
            <p id="login-error" className="form-error" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" disabled={submitting || Boolean(pendingLogin)}>
            <LogIn size={16} aria-hidden="true" />
            {submitting ? `${LOGIN_STATE_COPY.saving.label}…` : "登入"}
          </Button>
        </form>
        {pendingLogin && organizations.length > 1 ? (
          <section
            className="panel login-context-panel"
            aria-labelledby="context-title"
          >
            <h2 id="context-title">確認目前收容所</h2>
            <p className="muted">
              請選擇這次工作的目前收容所；後端會重新驗證成員資格。
            </p>
            <Button
              type="button"
              disabled={submitting}
              onClick={() => void confirmContext()}
            >
              {submitting
                ? `${LOGIN_STATE_COPY.saving.label}…`
                : "進入管理工作台"}
            </Button>
          </section>
        ) : null}
        {submitting ? (
          <p className="sr-only" role="status" aria-live="polite">
            {LOGIN_STATE_COPY.saving.nextStep}
          </p>
        ) : null}
      </Card>
    </main>
  );
}
