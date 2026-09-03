"use client";

import React, {
  FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { QrCode, Search } from "lucide-react";
import { useVolunteerShelterContext } from "../../../components/auth/VolunteerShelterContext";
import { Button } from "../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../components/ui/card";
import { Dialog } from "../../../components/ui/dialog";
import { Field } from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { AnimalConfirmationCard } from "../../../features/animal-selection/AnimalConfirmationCard";
import {
  animalQrPayloadFromLocation,
  parseAnimalQrPayload,
  type AnimalQrPayload,
} from "../../../lib/animal-qr-payload";
import { authFetch } from "../../../lib/auth";
import type { SafeAnimalProfile } from "../../../lib/animal-profile";
import {
  isLiffScannerAvailable,
  scanAnimalQr,
} from "../../../lib/liff-scanner";
import {
  attemptCareReportLineTrigger,
  closeLiffWindow,
} from "../../../lib/liff-line-handoff";

type AnimalCandidate = SafeAnimalProfile & {
  id: string;
  name: string;
  shelter_number: string | null;
  photo_url?: string | null;
  cage?: string | null;
  area?: string | null;
  organization_id: string;
  can_report: boolean;
};

type AnimalConfirmation = AnimalCandidate & { confirmation_token: string };
type HandoffSource = "liff_scan" | "qr_deeplink" | "shelter_number";
type Phase =
  | "initializing"
  | "idle"
  | "scanning"
  | "authorizing-shelter"
  | "switching-shelter"
  | "resolving-animal"
  | "confirming-animal"
  | "creating-handoff"
  | "triggering-line"
  | "success";

type CandidateState = {
  animal: AnimalCandidate;
  shelterName: string;
  source: HandoffSource;
};

type PendingSwitch = {
  payload: AnimalQrPayload;
  source: HandoffSource;
  organizationId: string;
  organizationName: string;
};

type SuccessState = {
  animalName: string;
  shelterName: string;
  outcome: "triggering" | "auto" | "manual" | "failed";
  canClose: boolean;
};

class ApiResponseError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
  }
}

async function responseData<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = "操作失敗";
    let code: string | undefined;
    try {
      const body = (await response.json()) as {
        code?: string;
        message?: string;
      };
      message = body.message ?? message;
      code = body.code;
    } catch {
      // Keep a safe generic error when the response is not JSON.
    }
    throw new ApiResponseError(message, response.status, code);
  }
  return response.json() as Promise<T>;
}

function phaseMessage(phase: Phase): string | null {
  const messages: Partial<Record<Phase, string>> = {
    initializing: "正在確認掃描功能…",
    scanning: "正在開啟掃描器…",
    "authorizing-shelter": "正在確認收容所權限…",
    "switching-shelter": "正在切換收容所…",
    "resolving-animal": "正在取得動物資料…",
    "confirming-animal": "正在確認動物…",
    "creating-handoff": "正在準備照護回報…",
    "triggering-line": "已確認動物，正在返回 LINE…",
  };
  return messages[phase] ?? null;
}

export default function AnimalConfirmationPage() {
  const shelterContext = useVolunteerShelterContext();
  const operationEpoch = useRef(0);
  const scanButtonRef = useRef<HTMLButtonElement>(null);
  const successRef = useRef<HTMLElement>(null);
  const directPayloadHandled = useRef(false);
  const confirmationInFlight = useRef(false);
  const [activeShelter, setActiveShelter] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [scannerAvailable, setScannerAvailable] = useState<boolean | null>(
    null,
  );
  const [phase, setPhase] = useState<Phase>("initializing");
  const [candidate, setCandidate] = useState<CandidateState | null>(null);
  const [pendingSwitch, setPendingSwitch] = useState<PendingSwitch | null>(
    null,
  );
  const [success, setSuccess] = useState<SuccessState | null>(null);
  const [exactNumber, setExactNumber] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<AnimalCandidate[]>([]);
  const [fallbackMode, setFallbackMode] = useState<"none" | "exact" | "search">(
    "none",
  );
  const [errorMessage, setErrorMessage] = useState("");

  const request = useCallback(async <T,>(path: string, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    headers.set("Content-Type", "application/json");
    return responseData<T>(await authFetch(path, { ...init, headers }));
  }, []);

  const clearTransient = useCallback(() => {
    setCandidate(null);
    setPendingSwitch(null);
    setSuccess(null);
    setSearchResults([]);
    setErrorMessage("");
  }, []);

  const beginOperation = useCallback(() => {
    const epoch = operationEpoch.current + 1;
    operationEpoch.current = epoch;
    clearTransient();
    return epoch;
  }, [clearTransient]);

  const isCurrent = (epoch: number) => operationEpoch.current === epoch;

  const showSafeError = useCallback((error: unknown, fallback: string) => {
    if (error instanceof ApiResponseError && error.status === 401) {
      setCandidate(null);
      setPendingSwitch(null);
    }
    setErrorMessage(fallback);
    setPhase("idle");
  }, []);

  const resolveInActiveShelter = useCallback(
    async (
      payload: AnimalQrPayload,
      source: HandoffSource,
      epoch: number,
      shelter: { id: string; name: string },
    ) => {
      setPhase("resolving-animal");
      const animal = await request<AnimalCandidate>("/v1/qr-tokens/resolve", {
        method: "POST",
        body: JSON.stringify({ qr_token: payload.token }),
      });
      if (!isCurrent(epoch)) return;
      if (animal.organization_id !== shelter.id || !animal.can_report) {
        throw new ApiResponseError("動物目前無法回報", 404);
      }
      setCandidate({ animal, shelterName: shelter.name, source });
      setPhase("idle");
    },
    [request],
  );

  const handleQrPayload = useCallback(
    async (payload: AnimalQrPayload, source: HandoffSource) => {
      if (!activeShelter) return;
      const epoch = beginOperation();
      try {
        if (
          payload.candidateOrganizationId &&
          payload.candidateOrganizationId !== activeShelter.id
        ) {
          setPhase("authorizing-shelter");
          const authorized = await request<{
            organization_id: string;
            organization_name: string;
          }>("/v1/qr-tokens/candidate-organization", {
            method: "POST",
            body: JSON.stringify({
              qr_token: payload.token,
              candidate_organization_id: payload.candidateOrganizationId,
            }),
          });
          if (!isCurrent(epoch)) return;
          setPendingSwitch({
            payload,
            source,
            organizationId: authorized.organization_id,
            organizationName: authorized.organization_name,
          });
          setPhase("idle");
          return;
        }
        await resolveInActiveShelter(payload, source, epoch, activeShelter);
      } catch (error) {
        if (!isCurrent(epoch)) return;
        const unauthorized =
          error instanceof ApiResponseError &&
          [401, 403].includes(error.status);
        showSafeError(
          error,
          unauthorized
            ? "目前無法使用此收容所進行照護回報。"
            : "無法辨識此動物 QR Code。請確認 QR Code 或改用收容編號。",
        );
      }
    },
    [
      activeShelter,
      beginOperation,
      request,
      resolveInActiveShelter,
      showSafeError,
    ],
  );

  useEffect(() => {
    setScannerAvailable(isLiffScannerAvailable());
    setPhase("idle");
  }, []);

  useEffect(() => {
    operationEpoch.current += 1;
    clearTransient();
    setActiveShelter(
      shelterContext
        ? {
            id: shelterContext.organizationId,
            name: shelterContext.organizationName ?? "目前收容所",
          }
        : null,
    );
  }, [
    clearTransient,
    shelterContext?.organizationId,
    shelterContext?.organizationName,
  ]);

  useEffect(() => {
    if (!activeShelter || directPayloadHandled.current) return;
    const payload = animalQrPayloadFromLocation(window.location);
    if (!payload) return;
    directPayloadHandled.current = true;
    window.history.replaceState({}, "", window.location.pathname);
    void handleQrPayload(payload, "qr_deeplink");
  }, [activeShelter, handleQrPayload]);

  useEffect(
    () => () => {
      operationEpoch.current += 1;
    },
    [],
  );

  useEffect(() => {
    if (success) successRef.current?.focus();
  }, [success]);

  const launchScanner = async () => {
    if (!scannerAvailable) {
      setFallbackMode("exact");
      setErrorMessage("此裝置目前無法直接掃描 QR Code。請改用完整收容編號。");
      return;
    }
    const epoch = beginOperation();
    setPhase("scanning");
    try {
      const raw = await scanAnimalQr();
      if (!isCurrent(epoch)) return;
      if (raw === null) {
        setPhase("idle");
        scanButtonRef.current?.focus();
        return;
      }
      const payload = parseAnimalQrPayload(raw);
      if (!payload) {
        showSafeError(
          null,
          "無法辨識此動物 QR Code。請確認 QR Code 或改用收容編號。",
        );
        return;
      }
      await handleQrPayload(payload, "liff_scan");
    } catch {
      if (!isCurrent(epoch)) return;
      setPhase("idle");
      scanButtonRef.current?.focus();
    }
  };

  const cancelSwitch = () => {
    operationEpoch.current += 1;
    setPendingSwitch(null);
    setCandidate(null);
    setErrorMessage("");
    setPhase("idle");
    window.setTimeout(() => scanButtonRef.current?.focus(), 0);
  };

  const confirmSwitch = async () => {
    if (!pendingSwitch || !activeShelter) return;
    const switchTarget = pendingSwitch;
    const epoch = operationEpoch.current;
    setPhase("switching-shelter");
    setErrorMessage("");
    try {
      const switched = await request<{
        organization_id: string;
        organization_name: string;
      }>("/v1/auth/active-shelter-context", {
        method: "PUT",
        body: JSON.stringify({ organization_id: switchTarget.organizationId }),
      });
      if (!isCurrent(epoch)) return;
      const nextShelter = {
        id: switched.organization_id,
        name: switched.organization_name,
      };
      setActiveShelter(nextShelter);
      setPendingSwitch(null);
      await resolveInActiveShelter(
        switchTarget.payload,
        switchTarget.source,
        epoch,
        nextShelter,
      );
    } catch (error) {
      if (!isCurrent(epoch)) return;
      setPendingSwitch(null);
      setCandidate(null);
      showSafeError(error, "目前無法切換收容所，請稍後再試。");
    }
  };

  const exactLookup = async (event: FormEvent) => {
    event.preventDefault();
    if (!activeShelter) return;
    const normalized = exactNumber.trim();
    const epoch = beginOperation();
    setPhase("resolving-animal");
    try {
      const data = await request<{ items: AnimalCandidate[] }>(
        `/v1/animals/search?query=${encodeURIComponent(normalized)}&page_size=100`,
      );
      if (!isCurrent(epoch)) return;
      const exact = data.items.filter(
        (item) =>
          item.shelter_number?.localeCompare(normalized, undefined, {
            sensitivity: "accent",
          }) === 0,
      );
      if (exact.length !== 1) {
        throw new ApiResponseError("找不到完整收容編號", 404);
      }
      setCandidate({
        animal: exact[0],
        shelterName: activeShelter.name,
        source: "shelter_number",
      });
      setPhase("idle");
    } catch (error) {
      if (isCurrent(epoch))
        showSafeError(error, "找不到這個完整收容編號，請確認後再試。");
    }
  };

  const partialSearch = async (event: FormEvent) => {
    event.preventDefault();
    const epoch = beginOperation();
    setPhase("resolving-animal");
    try {
      const data = await request<{ items: AnimalCandidate[] }>(
        `/v1/animals/search?query=${encodeURIComponent(searchQuery.trim())}`,
      );
      if (!isCurrent(epoch)) return;
      setSearchResults(data.items);
      setPhase("idle");
    } catch (error) {
      if (isCurrent(epoch))
        showSafeError(error, "目前無法搜尋動物，請稍後再試。");
    }
  };

  const confirmAnimalAndCreateHandoff = async () => {
    if (!candidate || confirmationInFlight.current) return;
    confirmationInFlight.current = true;
    const confirmedCandidate = candidate;
    const epoch = operationEpoch.current + 1;
    operationEpoch.current = epoch;
    setErrorMessage("");
    try {
      setPhase("confirming-animal");
      const confirmed = await request<AnimalConfirmation>(
        `/v1/animals/${candidate.animal.id}/confirm`,
        { method: "POST" },
      );
      if (!isCurrent(epoch)) return;
      setPhase("creating-handoff");
      await request<{ id: string; status: "pending"; expires_at: string }>(
        "/v1/care-report-handoffs",
        {
          method: "POST",
          body: JSON.stringify({
            animal_id: confirmed.id,
            confirmation_token: confirmed.confirmation_token,
            source: candidate.source,
          }),
        },
      );
      if (!isCurrent(epoch)) return;
      setSuccess({
        animalName: confirmedCandidate.animal.name,
        shelterName: confirmedCandidate.shelterName,
        outcome: "triggering",
        canClose: false,
      });
      setCandidate(null);
      setPendingSwitch(null);
      setSearchResults([]);
      setPhase("triggering-line");

      const trigger = await attemptCareReportLineTrigger();
      if (!isCurrent(epoch)) return;
      if (trigger.status === "sent") {
        setSuccess((current) =>
          current
            ? { ...current, outcome: "auto", canClose: trigger.canClose }
            : current,
        );
        setPhase("success");
        if (trigger.canClose && !closeLiffWindow()) {
          if (!isCurrent(epoch)) return;
          setSuccess((current) =>
            current ? { ...current, outcome: "failed" } : current,
          );
        }
      } else {
        setSuccess((current) =>
          current
            ? {
                ...current,
                outcome: trigger.status === "failed" ? "failed" : "manual",
                canClose: trigger.canClose,
              }
            : current,
        );
        setPhase("success");
      }
    } catch (error) {
      if (!isCurrent(epoch)) return;
      setPhase("idle");
      setErrorMessage(
        error instanceof ApiResponseError &&
          error.code === "animal_no_longer_available"
          ? "這隻動物目前無法進行照護回報。"
          : "目前無法準備照護回報，請重新確認動物後再試。",
      );
    } finally {
      if (isCurrent(epoch)) confirmationInFlight.current = false;
    }
  };

  const returnToLine = () => {
    if (!closeLiffWindow()) {
      setSuccess((current) =>
        current ? { ...current, outcome: "failed" } : current,
      );
    }
  };

  const statusMessage = phaseMessage(phase);
  const scanDisabled = [
    "initializing",
    "scanning",
    "switching-shelter",
    "confirming-animal",
    "creating-handoff",
    "triggering-line",
  ].includes(phase);

  if (success) {
    return (
      <main
        ref={successRef}
        className="volunteer-page"
        aria-labelledby="handoff-success-title"
        tabIndex={-1}
      >
        <Card className="handoff-success-card">
          <CardHeader>
            <span className="eyebrow">VOLUNTEER CARE</span>
            <CardTitle id="handoff-success-title">動物已確認</CardTitle>
          </CardHeader>
          <CardContent className="handoff-success-content">
            <strong>{success.animalName}</strong>
            <span>{success.shelterName}</span>
            {success.outcome === "triggering" || success.outcome === "auto" ? (
              <>
                <p role="status" aria-live="polite">
                  正在返回 LINE 繼續照護回報…
                </p>
                <p className="muted">
                  若未自動返回，請回到 LINE 再點一次「照護回報」。
                </p>
              </>
            ) : (
              <div
                role={success.outcome === "failed" ? "alert" : "status"}
                aria-live={
                  success.outcome === "failed" ? "assertive" : "polite"
                }
              >
                {success.outcome === "failed" && (
                  <p>動物已確認，但目前無法自動返回 LINE。</p>
                )}
                <p>已準備好照護回報。</p>
                <p>
                  請回到 LINE，再點一次「照護回報」
                  <br />
                  或輸入「開始散步回報」。
                </p>
                <p className="muted">此確認將保留約 15 分鐘。</p>
              </div>
            )}
            {success.canClose && (
              <Button type="button" onClick={returnToLine}>
                返回 LINE
              </Button>
            )}
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main
      className="volunteer-page"
      aria-labelledby="animal-confirmation-title"
    >
      <div className="volunteer-page-heading">
        <span className="eyebrow">VOLUNTEER CARE</span>
        <h1 id="animal-confirmation-title">照護回報</h1>
        <p>
          掃描動物上的 QR Code
          <br />
          即可開始本次照護紀錄。
        </p>
        {activeShelter && (
          <p role="status">目前協助收容所：{activeShelter.name}</p>
        )}
      </div>

      {statusMessage && (
        <p className="notice" role="status" aria-live="polite">
          {statusMessage}
        </p>
      )}
      {errorMessage && (
        <p className="notice error" role="alert">
          {errorMessage}
        </p>
      )}

      <Card className="scanner-first-card">
        <CardContent className="scanner-first-content">
          <Button
            ref={scanButtonRef}
            type="button"
            className="scanner-primary-action"
            onClick={() => void launchScanner()}
            disabled={scanDisabled || scannerAvailable === null}
          >
            <QrCode aria-hidden="true" />
            掃描動物 QR Code
          </Button>
          {scannerAvailable === false && (
            <p className="muted">
              此裝置目前無法直接掃描 QR Code。請改用完整收容編號。
            </p>
          )}
          <div className="scanner-fallback-actions">
            <span>沒有 QR Code？</span>
            <Button
              variant="secondary"
              type="button"
              onClick={() => setFallbackMode("exact")}
            >
              輸入完整收容編號
            </Button>
            <span>需要協助？</span>
            <Button
              variant="secondary"
              type="button"
              onClick={() => setFallbackMode("search")}
            >
              <Search aria-hidden="true" />
              搜尋動物
            </Button>
          </div>
        </CardContent>
      </Card>

      {fallbackMode === "exact" && (
        <Card aria-labelledby="exact-number-title">
          <CardHeader>
            <CardTitle id="exact-number-title">輸入完整收容編號</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="volunteer-search-form"
              aria-label="exact-shelter-number-form"
              onSubmit={(event) => void exactLookup(event)}
            >
              <Field>
                <label htmlFor="exact-shelter-number">完整收容編號</label>
                <Input
                  id="exact-shelter-number"
                  value={exactNumber}
                  onChange={(event) => setExactNumber(event.target.value)}
                  required
                />
              </Field>
              <Button type="submit" disabled={phase !== "idle"}>
                確認收容編號
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {fallbackMode === "search" && (
        <Card aria-labelledby="animal-search-title">
          <CardHeader>
            <CardTitle id="animal-search-title">搜尋動物</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="volunteer-search-form"
              aria-label="animal-search-form"
              onSubmit={(event) => void partialSearch(event)}
            >
              <Field>
                <label htmlFor="animal-search-query">動物名稱或收容編號</label>
                <Input
                  id="animal-search-query"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  required
                />
              </Field>
              <Button type="submit" disabled={phase !== "idle"}>
                搜尋
              </Button>
            </form>
            {searchResults.length > 0 && (
              <ul className="volunteer-candidate-list" aria-label="搜尋結果">
                {searchResults.map((animal) => (
                  <li
                    className="volunteer-candidate-item list-card"
                    key={animal.id}
                  >
                    <span>
                      {animal.name}／{animal.shelter_number ?? "未維護"}
                    </span>
                    <Button
                      variant="secondary"
                      type="button"
                      onClick={() => {
                        const epoch = beginOperation();
                        setCandidate({
                          animal,
                          shelterName: activeShelter?.name ?? "目前收容所",
                          source: "shelter_number",
                        });
                        setPhase("idle");
                        operationEpoch.current = epoch;
                      }}
                    >
                      查看確認卡
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {pendingSwitch && activeShelter && (
        <Dialog
          open
          title="切換收容所"
          onClose={cancelSwitch}
          closeLabel="取消切換收容所"
          closeDisabled={phase !== "idle"}
          className="shelter-switch-dialog"
        >
          <>
            <p>這隻動物屬於「{pendingSwitch.organizationName}」。</p>
            <p>你目前正在協助「{activeShelter.name}」。</p>
            <p>是否切換至「{pendingSwitch.organizationName}」並繼續？</p>
            <div className="animal-confirmation-actions">
              <Button
                type="button"
                onClick={() => void confirmSwitch()}
                disabled={phase !== "idle"}
              >
                切換並繼續
              </Button>
              <Button variant="secondary" type="button" onClick={cancelSwitch}>
                取消
              </Button>
            </div>
          </>
        </Dialog>
      )}

      {candidate && (
        <AnimalConfirmationCard
          animal={{
            id: candidate.animal.id,
            name: candidate.animal.name,
            shelterNumber: candidate.animal.shelter_number,
            photoUrl: candidate.animal.photo_url,
            cage: candidate.animal.cage,
            area: candidate.animal.area,
            shelterName: candidate.shelterName,
            canReport: candidate.animal.can_report,
            sex: candidate.animal.sex,
            breed: candidate.animal.breed,
            birth_date: candidate.animal.birth_date,
            birth_date_estimated: candidate.animal.birth_date_estimated,
            age_description: candidate.animal.age_description,
            care_guidance: candidate.animal.care_guidance,
          }}
          busy={phase === "confirming-animal" || phase === "creating-handoff"}
          onConfirm={() => void confirmAnimalAndCreateHandoff()}
          onReselect={() => {
            beginOperation();
            setPhase("idle");
            scanButtonRef.current?.focus();
          }}
        />
      )}
    </main>
  );
}
