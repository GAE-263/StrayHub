"use client";

import liff from "@line/liff";
import { useSearchParams } from "next/navigation";
import React, { useEffect, useMemo, useState } from "react";

import { Alert } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";
import { VolunteerApplicationPage } from "../../../features/volunteer-access/VolunteerApplicationPage";

type Shelter = { id: string; name: string; address: string | null };
type Region = { name: string; organizations: Shelter[] };
type Directory = { regions: Region[] };
type Props = { liffId: string };

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default function VolunteerApplicationClient({ liffId }: Props) {
  const searchParams = useSearchParams();
  const hintedOrganizationId =
    searchParams.get("organization_id")?.trim() ?? "";
  const [idToken, setIdToken] = useState("");
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [regionName, setRegionName] = useState("");
  const [selected, setSelected] = useState<Shelter | null>(null);
  const [hintUnavailable, setHintUnavailable] = useState(false);
  const [ignoreHint, setIgnoreHint] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    if (!liffId) {
      setError("志工申請服務尚未完成設定，請聯絡工作人員。");
      return () => {
        active = false;
      };
    }
    if (liffId === "fake-liff-id") {
      setIdToken("local-id-token:volunteer-liff-browser-demo");
      void fetch("/v1/public/volunteer-organizations")
        .then(async (response) => {
          if (!response.ok) throw new Error("directory_unavailable");
          if (active) setDirectory((await response.json()) as Directory);
        })
        .catch(() => {
          if (active) setError("目前無法開啟志工申請，請稍後再試。");
        });
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
        if (!token) throw new Error("missing_id_token");
        setIdToken(token);
        return fetch("/v1/public/volunteer-organizations");
      })
      .then(async (response) => {
        if (!response || !active) return;
        if (!response.ok) throw new Error("directory_unavailable");
        setDirectory((await response.json()) as Directory);
      })
      .catch(() => {
        if (active) setError("目前無法開啟志工申請，請稍後再試。");
      });
    return () => {
      active = false;
    };
  }, [liffId]);

  const allShelters = useMemo(
    () => directory?.regions.flatMap((region) => region.organizations) ?? [],
    [directory],
  );

  useEffect(() => {
    if (
      !directory ||
      !hintedOrganizationId ||
      selected ||
      hintUnavailable ||
      ignoreHint
    )
      return;
    if (!UUID_PATTERN.test(hintedOrganizationId)) {
      setHintUnavailable(true);
      return;
    }
    const shelter = allShelters.find(
      (candidate) => candidate.id === hintedOrganizationId,
    );
    if (shelter) setSelected(shelter);
    else setHintUnavailable(true);
  }, [
    allShelters,
    directory,
    hintedOrganizationId,
    hintUnavailable,
    ignoreHint,
    selected,
  ]);

  function reselect() {
    setSelected(null);
    setRegionName("");
    setHintUnavailable(false);
    setIgnoreHint(true);
    window.history.replaceState({}, "", window.location.pathname);
  }

  if (error) {
    return (
      <main className="volunteer-application-page">
        <header className="volunteer-application-heading">
          <span className="eyebrow">志工報名</span>
          <h1>目前無法使用</h1>
        </header>
        <Alert role="alert">{error}</Alert>
        <Button type="button" onClick={() => window.location.reload()}>
          重新載入
        </Button>
      </main>
    );
  }
  if (!idToken || !directory) {
    return (
      <main className="volunteer-application-page">
        <p role="status" aria-live="polite">
          正在確認 LINE 身分與開放報名的收容所…
        </p>
      </main>
    );
  }
  if (hintUnavailable) {
    return (
      <main className="volunteer-application-page">
        <header className="volunteer-application-heading">
          <span className="eyebrow">志工報名</span>
          <h1>此收容所目前無法報名</h1>
        </header>
        <Alert role="alert">連結已失效，或該收容所目前未開放志工申請。</Alert>
        <Button type="button" onClick={reselect}>
          重新選擇地區與收容所
        </Button>
      </main>
    );
  }
  if (selected) {
    return (
      <VolunteerApplicationPage
        key={selected.id}
        idToken={idToken}
        organizationId={selected.id}
        onReselect={reselect}
        onReturnToLine={() => liff.closeWindow()}
      />
    );
  }
  const region = directory.regions.find((item) => item.name === regionName);
  return (
    <main className="volunteer-application-page volunteer-directory-page">
      <header className="volunteer-application-heading">
        <span className="eyebrow">志工報名</span>
        <h1>{region ? "選擇想服務的收容所" : "選擇想服務的地區"}</h1>
        <p>{region ? region.name : "只顯示目前開放志工申請的地區"}</p>
      </header>
      {directory.regions.length === 0 ? (
        <Alert>目前沒有開放志工申請的收容所，請稍後再回來查看。</Alert>
      ) : region ? (
        <div className="volunteer-directory-list">
          {region.organizations.map((shelter) => (
            <Card key={shelter.id}>
              <CardHeader>
                <CardTitle>{shelter.name}</CardTitle>
                <p>{shelter.address || "地址由收容所提供"}</p>
                <span className="volunteer-open-badge">開放報名</span>
              </CardHeader>
              <CardContent>
                <Button type="button" onClick={() => setSelected(shelter)}>
                  向這間收容所報名
                </Button>
              </CardContent>
            </Card>
          ))}
          <Button
            variant="secondary"
            type="button"
            onClick={() => setRegionName("")}
          >
            返回地區選擇
          </Button>
        </div>
      ) : (
        <div className="volunteer-region-grid">
          {directory.regions.map((item) => (
            <button
              key={item.name}
              type="button"
              onClick={() => setRegionName(item.name)}
            >
              <span>{item.name}</span>
              <small>{item.organizations.length} 間收容所開放申請</small>
            </button>
          ))}
        </div>
      )}
    </main>
  );
}
