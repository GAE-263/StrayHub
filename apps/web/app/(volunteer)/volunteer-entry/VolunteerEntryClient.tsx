"use client";

import liff from "@line/liff";
import { useRouter, useSearchParams } from "next/navigation";
import React, { useCallback, useEffect, useRef, useState } from "react";

import { Alert } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";
import { VolunteerApplicationPage } from "../../../features/volunteer-access/VolunteerApplicationPage";
import {
  clearAuth,
  storeActiveOrganization,
  storeSession,
  storeSessionSource,
} from "../../../lib/auth";
import {
  beginLiffRecovery,
  claimLiffRecoveryExchange,
  getRecoveryEpoch,
  isValidLiffEntryReference,
  markLiffRecoveryRecovered,
  markLiffRecoveryTerminal,
  resetLiffRecovery,
  storeLiffEntryReference,
} from "../../../lib/liff-session";
import { scrubLegacyIdToken } from "./liffUrl";

type EntryState =
  | "INITIALIZING"
  | "LOGIN_REQUIRED"
  | "EXCHANGING"
  | "NEW"
  | "PENDING"
  | "ACTIVE"
  | "SUSPENDED"
  | "ERROR";

type Organization = {
  id: string;
  code: string;
  name: string;
};

const EXCHANGE_RESULT_STATES = [
  "NEW",
  "PENDING",
  "ACTIVE",
  "SUSPENDED",
] as const;
type ExchangeResultState = (typeof EXCHANGE_RESULT_STATES)[number];

type ExchangeResponse = {
  state?: string;
  access_token?: string;
  refresh_token?: string;
  session_id?: string;
  organization?: Organization;
  user?: { role: string };
};

type ActiveExchangeResponse = ExchangeResponse & {
  state: "ACTIVE";
  access_token: string;
  refresh_token: string;
  session_id: string;
  organization: Organization;
  user: { role: "VOLUNTEER" };
};

function isExchangeResultState(
  value: string | undefined,
): value is ExchangeResultState {
  return EXCHANGE_RESULT_STATES.some((state) => state === value);
}

function isNonEmptyString(value: string | undefined): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isValidActiveResponse(
  body: ExchangeResponse,
): body is ActiveExchangeResponse {
  return (
    body.state === "ACTIVE" &&
    isNonEmptyString(body.access_token) &&
    isNonEmptyString(body.refresh_token) &&
    isNonEmptyString(body.session_id) &&
    Boolean(body.organization) &&
    isNonEmptyString(body.organization?.id) &&
    isNonEmptyString(body.organization?.code) &&
    isNonEmptyString(body.organization?.name) &&
    body.user?.role === "VOLUNTEER"
  );
}

const STATE_COPY: Record<EntryState, { title: string; detail: string }> = {
  INITIALIZING: {
    title: "正在確認 LINE 身分…",
    detail: "請稍候，我們正在安全地開啟志工服務。",
  },
  LOGIN_REQUIRED: {
    title: "正在前往 LINE 登入…",
    detail: "登入完成後會自動回到這個收容所入口。",
  },
  EXCHANGING: {
    title: "正在確認志工服務資格…",
    detail: "確認完成前不會載入任何收容所照護資料。",
  },
  NEW: {
    title: "尚未完成志工報名",
    detail: "完成報名後，收容所工作人員會進行審核。",
  },
  PENDING: {
    title: "志工申請審核中",
    detail: "申請已送出，請耐心等候收容所工作人員審核。",
  },
  ACTIVE: {
    title: "志工資格確認完成",
    detail: "正在開啟動物確認流程。",
  },
  SUSPENDED: {
    title: "目前無法使用志工服務",
    detail: "請聯絡收容所工作人員協助確認資格。",
  },
  ERROR: {
    title: "無法開啟志工服務",
    detail: "請重新開啟志工服務，或稍後再試。",
  },
};

function safeExchangeError(status: number, code?: string): string {
  if (code === "entry_unavailable" || status === 403) {
    return "這個收容所志工入口已失效或目前無法使用，請向工作人員索取新入口。";
  }
  if (code === "invalid_line_id_token" || status === 401) {
    return "無法確認 LINE 身分，請重新開啟志工服務。";
  }
  if (status >= 500) {
    return "志工服務暫時無法使用，請稍後重新嘗試。";
  }
  return "無法確認志工資格，請重新開啟志工服務。";
}

type VolunteerEntryClientProps = {
  liffId: string;
};

let activeRecoveryEpochId: number | null = null;
let activeRecoveryExchangeController: AbortController | null = null;
let activeRecoveryClaimedAt = 0;
const RECOVERY_EXCHANGE_TIMEOUT_MS = 15_000;

function releaseActiveRecoveryClaim(abort = false): void {
  if (abort) activeRecoveryExchangeController?.abort();
  activeRecoveryExchangeController = null;
  activeRecoveryEpochId = null;
  activeRecoveryClaimedAt = 0;
}

function markRecoveryFailure(entryUrl: URL): void {
  const recoveryState = getRecoveryEpoch()?.state;
  const isRecovery =
    recoveryState === "recovering" || recoveryState === "exchanging";
  markLiffRecoveryTerminal();
  releaseActiveRecoveryClaim();
  if (!isRecovery) return;
  entryUrl.searchParams.set("recovery", "terminal");
  window.history.replaceState({}, "", entryUrl.toString());
}

export default function VolunteerEntryClient({
  liffId,
}: VolunteerEntryClientProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [state, setState] = useState<EntryState>("INITIALIZING");
  const [error, setError] = useState("");
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [idToken, setIdToken] = useState("");
  const [showApplication, setShowApplication] = useState(false);
  const runId = useRef(0);
  const cleanupGeneration = useRef(0);

  // prettier-ignore
  const bootstrap = useCallback(async (manualRetry = false) => {
    const existingEpoch = getRecoveryEpoch();
    if (existingEpoch?.state === "exchanging") {
      const sameActiveEpoch =
        activeRecoveryEpochId !== null &&
        activeRecoveryEpochId === existingEpoch.epochId;
      if (
        manualRetry &&
        sameActiveEpoch &&
        Date.now() - activeRecoveryClaimedAt < RECOVERY_EXCHANGE_TIMEOUT_MS
      )
        return;
      if (manualRetry) {
        if (sameActiveEpoch) releaseActiveRecoveryClaim(true);
        resetLiffRecovery();
      } else {
        setState("ERROR");
        setError("系統工作階段已失效，請重新嘗試進入志工服務。");
        return;
      }
    }
    const initialUrl = new URL(window.location.href);
    const currentRun = ++runId.current;
    setState("INITIALIZING");
    setError("");
    setShowApplication(false);

    const entryUrl = initialUrl;
    const entry = entryUrl.searchParams.get("entry")?.trim() ?? "";
    const recoveryMode = entryUrl.searchParams.get("recovery");
    const recoveryState = getRecoveryEpoch()?.state;
    let exchangeEpochId: number | null = null;
    if (recoveryMode === "terminal" && !manualRetry) {
      setState("ERROR");
      setError("系統工作階段已失效，請重新嘗試進入志工服務。");
      return;
    }
    if (recoveryState === "terminal" && !manualRetry) {
      setState("ERROR");
      setError("系統工作階段已失效，請重新嘗試進入志工服務。");
      return;
    }
    const recoveryEntry = getRecoveryEpoch()?.entryReference;
    const canAdoptRecoveringEpoch =
      recoveryState === "recovering" && recoveryEntry === entry;
    if (
      !manualRetry &&
      (recoveryState === "recovering" || recoveryState === "exchanging") &&
      recoveryMode !== "exchange" &&
      !canAdoptRecoveringEpoch
    ) {
      setState("ERROR");
      setError("系統工作階段已失效，請重新嘗試進入志工服務。");
      return;
    }
    if (manualRetry || getRecoveryEpoch()?.state === "recovered") {
      resetLiffRecovery();
      if (!manualRetry) {
        entryUrl.searchParams.delete("recovery");
        window.history.replaceState({}, "", entryUrl.toString());
      }
    }
    if (!scrubLegacyIdToken(entryUrl)) {
      markRecoveryFailure(entryUrl);
      setState("ERROR");
      setError("正在安全地重新開啟志工服務，請稍候。");
      return;
    }

    let exchangeTimeoutId: number | undefined;
    try {
      storeLiffEntryReference(entry);
      clearAuth({ preserveLiffSession: true });
    } catch {
      markRecoveryFailure(entryUrl);
      setState("ERROR");
      setError("無法清除舊的系統工作階段，請重新開啟志工服務。");
      return;
    }

    if (!liffId) {
      markRecoveryFailure(entryUrl);
      setState("ERROR");
      setError("志工服務尚未完成設定，請聯絡工作人員。");
      return;
    }
    if (!entry) {
      markRecoveryFailure(entryUrl);
      setState("ERROR");
      setError("缺少收容所入口資訊，請從 LINE Rich Menu 重新開啟。");
      return;
    }
    const shouldClaimExchange =
      manualRetry ||
      recoveryMode === "exchange" ||
      isValidLiffEntryReference(entry);
    const recoveryStart = shouldClaimExchange
      ? beginLiffRecovery(window.location.pathname)
      : "started";
    if (
      shouldClaimExchange &&
      (manualRetry || recoveryMode !== "exchange") &&
      recoveryStart !== "started" &&
      !(canAdoptRecoveringEpoch && recoveryStart === "in-flight")
    ) {
      setState("ERROR");
      setError("無法建立新的工作階段，請重新開啟志工服務。");
      return;
    }

    try {
      await liff.init({ liffId });
      if (currentRun !== runId.current) return;
      if (!liff.isLoggedIn()) {
        setState("LOGIN_REQUIRED");
        const redirectUri = entryUrl;
        redirectUri.searchParams.set("entry", entry);
        if (shouldClaimExchange) {
          redirectUri.searchParams.set("recovery", "exchange");
        }
        liff.login({ redirectUri: redirectUri.toString() });
        return;
      }

      const rawIdToken = liff.getIDToken();
      if (!rawIdToken) {
        markRecoveryFailure(entryUrl);
        setState("ERROR");
        setError("無法取得 LINE 身分資訊，請重新嘗試。");
        return;
      }
      setIdToken(rawIdToken);
      const claim = shouldClaimExchange
        ? claimLiffRecoveryExchange()
        : "claimed";
      if (claim !== "claimed") {
        if (claim === "unavailable") markRecoveryFailure(entryUrl);
        setState("ERROR");
        setError("系統工作階段已失效，請重新嘗試進入志工服務。");
        return;
      }
      activeRecoveryEpochId = getRecoveryEpoch()?.epochId ?? null;
      exchangeEpochId = activeRecoveryEpochId;
      const exchangeController = new AbortController();
      activeRecoveryExchangeController = exchangeController;
      activeRecoveryClaimedAt = Date.now();
      exchangeTimeoutId = window.setTimeout(
        () => exchangeController.abort(),
        RECOVERY_EXCHANGE_TIMEOUT_MS,
      );
      setState("EXCHANGING");
      const response = await fetch(`/v1/auth/liff/exchange`, {
        method: "POST",
        signal: exchangeController.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_token: rawIdToken,
          shelter_entry_reference: entry,
        }),
      });
      if (
        currentRun !== runId.current ||
        (exchangeEpochId !== null &&
          getRecoveryEpoch()?.epochId !== exchangeEpochId)
      )
        return;
      const body = (await response
        .json()
        .catch(() => ({}))) as ExchangeResponse & {
        code?: string;
      };
      window.clearTimeout(exchangeTimeoutId);
      if (
        currentRun !== runId.current ||
        (exchangeEpochId !== null &&
          getRecoveryEpoch()?.epochId !== exchangeEpochId)
      )
        return;
      if (!response.ok) {
        markRecoveryFailure(entryUrl);
        setState("ERROR");
        setError(safeExchangeError(response.status, body.code));
        return;
      }
      if (!isExchangeResultState(body.state)) {
        markRecoveryFailure(entryUrl);
        setState("ERROR");
        setError("無法確認志工資格，請重新開啟志工服務。");
        return;
      }
      if (body.state === "ACTIVE") {
        if (!isValidActiveResponse(body)) {
          markRecoveryFailure(entryUrl);
          clearAuth({ preserveLiffSession: true });
          setState("ERROR");
          setError("系統工作階段建立失敗，請重新嘗試。");
          return;
        }
        setOrganization(body.organization);
        setState(body.state);
        try {
          storeSession({
            access_token: body.access_token,
            refresh_token: body.refresh_token,
            session_id: body.session_id,
          });
          storeSessionSource("liff");
          if (shouldClaimExchange && !markLiffRecoveryRecovered()) {
            clearAuth({ preserveLiffSession: true });
            markRecoveryFailure(entryUrl);
            setState("ERROR");
            setError("無法保存系統工作階段，請重新嘗試。");
            return;
          }
          releaseActiveRecoveryClaim();
          storeActiveOrganization({
            ...body.organization,
            role: body.user.role,
          });
        } catch {
          markRecoveryFailure(entryUrl);
          clearAuth({ preserveLiffSession: true });
          setState("ERROR");
          setError("無法保存系統工作階段，請重新嘗試。");
          return;
        }
        router.replace("/animal-confirmation");
        return;
      }
      markRecoveryFailure(entryUrl);
      setOrganization(body.organization ?? null);
      setState(body.state);
    } catch {
      if (exchangeTimeoutId !== undefined) {
        window.clearTimeout(exchangeTimeoutId);
      }
      if (
        currentRun !== runId.current ||
        (exchangeEpochId !== null &&
          getRecoveryEpoch()?.epochId !== exchangeEpochId)
      )
        return;
      markRecoveryFailure(entryUrl);
      setState("ERROR");
      setError("目前無法連線確認志工資格，請稍後重新嘗試。");
    }
  }, [liffId, router]);

  useEffect(() => {
    cleanupGeneration.current += 1;
    void bootstrap();
    const effectGeneration = cleanupGeneration.current;
    return () => {
      queueMicrotask(() => {
        if (
          cleanupGeneration.current === effectGeneration &&
          getRecoveryEpoch()?.state !== "exchanging"
        ) {
          runId.current += 1;
        }
      });
    };
  }, [bootstrap, searchParams.toString()]);

  const entry =
    typeof window === "undefined"
      ? ""
      : (new URLSearchParams(window.location.search).get("entry") ?? "");

  if (showApplication && idToken && entry) {
    return (
      <VolunteerApplicationPage
        idToken={idToken}
        shelterEntryReference={entry}
      />
    );
  }

  const copy = STATE_COPY[state];
  return (
    <main
      className={`volunteer-page volunteer-entry-${state.toLowerCase()}`}
      aria-labelledby="volunteer-entry-title"
    >
      <div className="volunteer-page-heading">
        <span className="eyebrow">LINE VOLUNTEER ENTRY</span>
        <h1 id="volunteer-entry-title">{copy.title}</h1>
        <p>{copy.detail}</p>
        {organization ? <p>目前入口：{organization.name}</p> : null}
      </div>

      <Card
        aria-live="polite"
        aria-busy={state === "INITIALIZING" || state === "EXCHANGING"}
      >
        <CardHeader>
          <CardTitle>志工服務</CardTitle>
        </CardHeader>
        <CardContent className="volunteer-entry-content">
          {error ? (
            <Alert role="alert">{error}</Alert>
          ) : (
            <p role="status">{copy.detail}</p>
          )}
          {state === "NEW" ? (
            <Button type="button" onClick={() => setShowApplication(true)}>
              進入志工報名
            </Button>
          ) : null}
          {state === "ERROR" ? (
            <Button type="button" onClick={() => void bootstrap(true)}>
              重新嘗試
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </main>
  );
}
