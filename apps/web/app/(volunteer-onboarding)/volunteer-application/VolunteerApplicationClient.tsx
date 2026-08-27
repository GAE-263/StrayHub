"use client";

import liff from "@line/liff";
import { useSearchParams } from "next/navigation";
import React, { useEffect, useState } from "react";

import { Alert } from "../../../components/ui/alert";
import { VolunteerApplicationPage } from "../../../features/volunteer-access/VolunteerApplicationPage";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type Props = {
  liffId: string;
};

export default function VolunteerApplicationClient({ liffId }: Props) {
  const searchParams = useSearchParams();
  const organizationId = searchParams.get("organization_id")?.trim() ?? "";
  const [idToken, setIdToken] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setIdToken("");
    setError("");
    if (!UUID_PATTERN.test(organizationId)) {
      setError("此收容所目前無法接受志工申請，請回到 LINE 重新選擇。");
      return () => {
        active = false;
      };
    }
    if (!liffId) {
      setError("志工申請服務尚未完成設定，請聯絡工作人員。");
      return () => {
        active = false;
      };
    }
    void liff
      .init({ liffId })
      .then(() => {
        if (!active) return;
        if (!liff.isLoggedIn()) {
          liff.login({ redirectUri: window.location.href });
          return;
        }
        const token = liff.getIDToken();
        if (!token) {
          setError("無法確認 LINE 身分，請回到 LINE 重新開啟志工申請。");
          return;
        }
        setIdToken(token);
      })
      .catch(() => {
        if (active) {
          setError("目前無法開啟志工申請，請稍後再試。");
        }
      });
    return () => {
      active = false;
    };
  }, [liffId, organizationId]);

  if (error) {
    return (
      <main className="volunteer-application-page">
        <header className="volunteer-application-heading">
          <span className="eyebrow">志工申請</span>
          <h1>目前無法使用</h1>
        </header>
        <Alert role="alert">{error}</Alert>
      </main>
    );
  }
  if (!idToken) {
    return (
      <main className="volunteer-application-page">
        <p role="status" aria-live="polite">
          正在確認 LINE 身分與申請收容所…
        </p>
      </main>
    );
  }
  return (
    <VolunteerApplicationPage
      key={organizationId}
      idToken={idToken}
      organizationId={organizationId}
    />
  );
}
