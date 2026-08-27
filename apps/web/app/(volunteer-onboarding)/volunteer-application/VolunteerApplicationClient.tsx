"use client";

import liff from "@line/liff";
import { useSearchParams } from "next/navigation";
import React, { useEffect, useMemo, useRef, useState } from "react";

import { Alert } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";
import { VolunteerApplicationPage } from "../../../features/volunteer-access/VolunteerApplicationPage";
import { VolunteerApplicationStatusPage } from "../../../features/volunteer-access/VolunteerApplicationStatusPage";
import { parseVolunteerLiffEntryIntent } from "../../../features/volunteer-access/volunteerLiffEntryIntent";
import {
  canonicalVolunteerLiffStatusQuery,
  clearVolunteerLiffStatusIntent,
  persistVolunteerLiffStatusIntent,
  resolveVolunteerLiffLifecycleIntent,
} from "../../../features/volunteer-access/volunteerLiffIntentLifecycle";

type Shelter = { id: string; name: string; address: string | null };
type Region = { name: string; organizations: Shelter[] };
type Directory = { regions: Region[] };
type Props = { liffId: string };

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DIAGNOSTICS_ENABLED = process.env.NODE_ENV !== "production";

function diagnostic(event: string, metadata?: Record<string, unknown>) {
  if (!DIAGNOSTICS_ENABLED) return;
  console.debug(`[volunteer-liff] ${event}`, metadata ?? {});
}

export default function VolunteerApplicationClient({ liffId }: Props) {
  const searchParams = useSearchParams();
  const query = searchParams.toString();
  const parsedIntent = useMemo(
    () => parseVolunteerLiffEntryIntent(query),
    [query],
  );
  const [intent, setIntent] = useState(parsedIntent);
  const view = intent.view;
  const hintedOrganizationId = intent.organizationId ?? "";
  const [idToken, setIdToken] = useState("");
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [regionName, setRegionName] = useState("");
  const [selected, setSelected] = useState<Shelter | null>(null);
  const [hintUnavailable, setHintUnavailable] = useState(false);
  const [ignoreHint, setIgnoreHint] = useState(false);
  const [error, setError] = useState("");
  const lifecycleInitialized = useRef(false);
  const applicationRenderLogged = useRef(false);

  useEffect(() => {
    if (lifecycleInitialized.current) return;
    lifecycleInitialized.current = true;
    const raw = new URLSearchParams(query);
    diagnostic("mount");
    diagnostic("raw-query", {
      viewPresent: raw.has("view"),
      liffStatePresent: raw.has("liff.state"),
      organizationIdPresent: raw.has("organization_id"),
      entryReferencePresent:
        raw.has("entry") || raw.has("shelter_entry_reference"),
    });
    const resolved = resolveVolunteerLiffLifecycleIntent(
      query,
      window.sessionStorage,
    );
    diagnostic("parsed-intent", {
      view: resolved.view,
      targetSource: resolved.organizationId
        ? "organization"
        : resolved.shelterEntryReference
          ? "entry-reference"
          : "none",
      targetConflict: resolved.targetConflict,
      restoredAfterRedirect:
        parsedIntent.view === "application" && resolved.view === "status",
    });
    if (resolved.view === "status") {
      persistVolunteerLiffStatusIntent(resolved, window.sessionStorage);
    }
    if (resolved.view !== parsedIntent.view) {
      diagnostic("view-transition", {
        from: parsedIntent.view,
        to: resolved.view,
        reason: "secondary_redirect_restore",
      });
    }
    setIntent(resolved);
    // Intentionally latch the entry intent for this mount. Query changes caused
    // by LIFF initialization must not reset status back to application mode.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let active = true;
    if (!liffId) {
      clearVolunteerLiffStatusIntent(window.sessionStorage);
      setError("志工申請服務尚未完成設定，請聯絡工作人員。");
      return () => {
        active = false;
      };
    }
    if (liffId === "fake-liff-id") {
      diagnostic("liff-init:skipped", { reason: "local_fake_identity" });
      diagnostic("identity:start");
      setIdToken("local-id-token:volunteer-liff-browser-demo");
      diagnostic("identity:ready");
      return () => {
        active = false;
      };
    }
    diagnostic("liff-init:start");
    void liff
      .init({ liffId })
      .then(() => {
        if (!active) return;
        diagnostic("liff-init:ready");
        diagnostic("identity:start");
        if (!liff.isLoggedIn()) {
          diagnostic("identity:login-required");
          liff.login({ redirectUri: window.location.href });
          return;
        }
        const token = liff.getIDToken();
        if (!token) throw new Error("missing_id_token");
        setIdToken(token);
        diagnostic("identity:ready");
      })
      .catch(() => {
        if (active) {
          diagnostic("identity:error");
          clearVolunteerLiffStatusIntent(window.sessionStorage);
          setError("目前無法確認 LINE 身分，請稍後再試。");
        }
      });
    return () => {
      active = false;
    };
  }, [liffId]);

  useEffect(() => {
    if (!idToken || intent.view !== "status") return;
    const canonicalQuery = canonicalVolunteerLiffStatusQuery(intent);
    const canonicalUrl = `${window.location.pathname}?${canonicalQuery}`;
    if (window.location.search !== `?${canonicalQuery}`) {
      window.history.replaceState(null, "", canonicalUrl);
      diagnostic("url-canonicalized", {
        view: "status",
        organizationIdPresent: Boolean(intent.organizationId),
      });
    }
    clearVolunteerLiffStatusIntent(window.sessionStorage);
  }, [idToken, intent]);

  useEffect(() => {
    let active = true;
    if (!idToken || view !== "application" || directory) {
      return () => {
        active = false;
      };
    }
    diagnostic("application-flow:init", { reason: "resolved_entry_intent" });
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
  }, [directory, idToken, view]);

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

  function startApplication() {
    diagnostic("view-transition", {
      from: intent.view,
      to: "application",
      reason: "user_action",
    });
    clearVolunteerLiffStatusIntent(window.sessionStorage);
    setIntent({ view: "application", targetConflict: false });
    setError("");
    window.history.replaceState({}, "", window.location.pathname);
  }

  function showStatus(organizationId: string) {
    const statusIntent = {
      view: "status" as const,
      organizationId,
      targetConflict: false,
    };
    diagnostic("view-transition", {
      from: intent.view,
      to: "status",
      reason: "user_action",
    });
    setIntent(statusIntent);
    setError("");
    const canonicalQuery = canonicalVolunteerLiffStatusQuery(statusIntent);
    window.history.replaceState(
      {},
      "",
      `${window.location.pathname}?${canonicalQuery}`,
    );
  }

  useEffect(() => {
    if (
      view === "application" &&
      idToken &&
      directory &&
      !applicationRenderLogged.current
    ) {
      applicationRenderLogged.current = true;
      diagnostic("render-mode", { view: "application", dataState: "ready" });
    }
  }, [directory, idToken, view]);

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
  if (!idToken) {
    return (
      <main className="volunteer-application-page">
        <p role="status" aria-live="polite">
          正在確認 LINE 身分…
        </p>
      </main>
    );
  }
  if (view === "status") {
    return (
      <VolunteerApplicationStatusPage
        idToken={idToken}
        focusedOrganizationId={intent.organizationId}
        onStartApplication={startApplication}
        onReturnToLine={() => liff.closeWindow()}
      />
    );
  }
  if (!directory) {
    return (
      <main className="volunteer-application-page">
        <p role="status" aria-live="polite">
          正在載入開放報名的收容所…
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
        onViewStatus={() => showStatus(selected.id)}
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
      {intent.targetConflict ? (
        <Alert role="alert">連結中的收容所目標互相衝突，請重新選擇。</Alert>
      ) : null}
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
