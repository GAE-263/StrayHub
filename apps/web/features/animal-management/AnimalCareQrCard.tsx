"use client";

import React from "react";
import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { authFetch, type CurrentUser } from "../../lib/auth";
import { canManageCareQr } from "../../lib/management-capabilities";
import { Alert } from "../../components/ui/alert";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Dialog } from "../../components/ui/dialog";

type AnimalSummary = {
  id: string;
  organizationId: string;
  name: string;
  shelterNumber: string;
  status: string;
  areaName: string | null;
};

type QrRecord = {
  id: string;
  organization_id: string;
  animal_id: string;
  status: string;
  revoked: boolean;
  token: string | null;
  deep_link: string | null;
};

type Phase = "loading" | "idle" | "creating" | "regenerating" | "error";

function absoluteDeepLink(deepLink: string): string {
  return new URL(deepLink, window.location.origin).toString();
}

export function AnimalCareQrCard({ animal }: { animal: AnimalSummary }) {
  const previewRef = useRef<HTMLElement>(null);
  const [qr, setQr] = useState<QrRecord | null>(null);
  const [organizationName, setOrganizationName] = useState("目前收容所");
  const [canManage, setCanManage] = useState(false);
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState("");
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [replacementGuidanceOpen, setReplacementGuidanceOpen] = useState(false);

  useEffect(() => {
    setQr(null);
    setRegenerateOpen(false);
    setReplacementGuidanceOpen(false);
    setError("");
    setCanManage(false);
    setOrganizationName("目前收容所");
    setPhase("loading");
    if (animal.status !== "active") {
      setPhase("idle");
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    void Promise.all([
      authFetch(
        `/v1/management/qr-codes?animal_id=${encodeURIComponent(animal.id)}`,
        { signal: controller.signal },
      ),
      authFetch("/v1/auth/active-shelter-context", {
        signal: controller.signal,
      }),
      authFetch("/v1/auth/me", { signal: controller.signal }),
    ])
      .then(async ([qrResponse, contextResponse, profileResponse]) => {
        if (!qrResponse.ok || !contextResponse.ok || !profileResponse.ok)
          throw new Error("load failed");
        const qrData = (await qrResponse.json()) as { items: QrRecord[] };
        const context = (await contextResponse.json()) as {
          organization_id: string;
          organization_name?: string;
        };
        const profile = (await profileResponse.json()) as CurrentUser;
        if (
          context.organization_id !== animal.organizationId ||
          qrData.items.some(
            (item) =>
              item.organization_id !== animal.organizationId ||
              item.animal_id !== animal.id,
          )
        ) {
          throw new Error("tenant mismatch");
        }
        if (cancelled) return;
        setOrganizationName(context.organization_name ?? "目前收容所");
        setCanManage(canManageCareQr(profile, context.organization_id));
        setQr(
          qrData.items.find(
            (item) => item.status === "active" && !item.revoked,
          ) ?? null,
        );
        setPhase("idle");
      })
      .catch(() => {
        if (!cancelled) {
          setError("目前無法載入照護 QR Code，請稍後再試。");
          setPhase("error");
        }
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [animal.id, animal.organizationId, animal.status]);

  useEffect(() => {
    if (qr?.deep_link) previewRef.current?.focus();
  }, [qr]);

  const generate = async () => {
    setPhase("creating");
    setError("");
    try {
      const response = await authFetch("/v1/management/qr-codes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ animal_id: animal.id }),
      });
      if (!response.ok) throw new Error("create failed");
      const value = (await response.json()) as QrRecord;
      if (
        value.organization_id !== animal.organizationId ||
        value.animal_id !== animal.id
      ) {
        throw new Error("tenant mismatch");
      }
      setQr(value);
      setPhase("idle");
    } catch {
      setError("目前無法產生 QR Code，請稍後再試。");
      setPhase("error");
    }
  };

  const regenerate = async () => {
    if (!qr) return;
    setRegenerateOpen(false);
    setPhase("regenerating");
    setError("");
    try {
      const response = await authFetch(
        `/v1/management/qr-codes/${qr.id}/regenerate`,
        { method: "POST" },
      );
      if (!response.ok) throw new Error("regenerate failed");
      const value = (await response.json()) as QrRecord;
      if (
        value.organization_id !== animal.organizationId ||
        value.animal_id !== animal.id
      ) {
        throw new Error("tenant mismatch");
      }
      setQr(value);
      setPhase("idle");
      setReplacementGuidanceOpen(true);
    } catch {
      setError("目前無法重新產生 QR Code，請稍後再試。");
      setPhase("error");
    }
  };

  const printableLink = qr?.deep_link ? absoluteDeepLink(qr.deep_link) : null;
  const busy = phase === "creating" || phase === "regenerating";

  return (
    <Card
      className="animal-care-qr-card"
      aria-labelledby="animal-care-qr-title"
    >
      <CardHeader>
        <div className="animal-care-qr-heading">
          <div>
            <CardTitle id="animal-care-qr-title">照護 QR Code</CardTitle>
            <p className="muted">
              讓已核准的志工掃描此 QR Code，確認動物後開始照護回報。
            </p>
          </div>
          <Badge>
            {qr?.status === "active" && !qr.revoked ? "已啟用" : "尚未建立"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="animal-care-qr-content">
        {animal.status !== "active" ? (
          <Alert role="status">
            動物目前非啟用狀態，無法建立或列印照護 QR Code。
          </Alert>
        ) : phase === "loading" ? (
          <p role="status" aria-live="polite">
            正在載入照護 QR Code…
          </p>
        ) : (
          <>
            {error ? <Alert role="alert">{error}</Alert> : null}
            {busy ? (
              <p role="status" aria-live="polite">
                {phase === "creating"
                  ? "正在產生 QR Code…"
                  : "正在重新產生 QR Code…"}
              </p>
            ) : printableLink ? (
              <>
                <section
                  ref={previewRef}
                  className="animal-qr-print-label"
                  aria-label={`${animal.name}的照護回報 QR Code 標籤`}
                  tabIndex={-1}
                >
                  <header>
                    <strong>StrayHub</strong>
                    <span>照護回報 QR Code</span>
                  </header>
                  <div className="animal-care-qr-image">
                    <QRCodeSVG
                      value={printableLink}
                      size={280}
                      level="M"
                      marginSize={4}
                      title={`${animal.name}的照護回報 QR Code`}
                    />
                  </div>
                  <dl>
                    <div>
                      <dt>動物名稱</dt>
                      <dd>{animal.name}</dd>
                    </div>
                    <div>
                      <dt>收容編號</dt>
                      <dd>{animal.shelterNumber}</dd>
                    </div>
                    <div>
                      <dt>收容所</dt>
                      <dd>{organizationName}</dd>
                    </div>
                    {animal.areaName ? (
                      <div>
                        <dt>位置</dt>
                        <dd>{animal.areaName}</dd>
                      </div>
                    ) : null}
                  </dl>
                </section>
                <div className="animal-care-qr-actions print-hidden">
                  <Button type="button" onClick={() => window.print()}>
                    重新列印
                  </Button>
                  {canManage ? (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => setRegenerateOpen(true)}
                    >
                      重新產生新 QR
                    </Button>
                  ) : null}
                </div>
              </>
            ) : qr ? (
              <div className="animal-care-qr-legacy-state">
                <p role="status">
                  這枚既有 QR Code 仍有效，但無法重新顯示列印圖。
                </p>
                <p className="muted">
                  如需重新列印，請重新產生並更換已張貼的舊標籤。
                </p>
                {canManage ? (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setRegenerateOpen(true)}
                  >
                    重新產生新 QR
                  </Button>
                ) : null}
              </div>
            ) : (
              <div className="animal-care-qr-empty-state">
                <p>尚未建立照護 QR Code</p>
                {canManage ? (
                  <Button type="button" onClick={() => void generate()}>
                    建立照護 QR
                  </Button>
                ) : null}
              </div>
            )}
          </>
        )}
      </CardContent>
      {canManage ? (
        <>
          <Dialog
            open={regenerateOpen}
            role="alertdialog"
            title="重新產生新的照護 QR？"
            onClose={() => setRegenerateOpen(false)}
          >
            <p className="dialog-description">
              重新產生後，目前的 QR 會立即失效。請列印新的
              QR，並更換現場舊標籤。
            </p>
            <div className="dialog-actions">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setRegenerateOpen(false)}
              >
                取消
              </Button>
              <Button type="button" onClick={() => void regenerate()}>
                確認重新產生新 QR
              </Button>
            </div>
          </Dialog>
          <Dialog
            open={replacementGuidanceOpen}
            role="dialog"
            title="新 QR 已建立，舊 QR 已失效"
            onClose={() => setReplacementGuidanceOpen(false)}
          >
            <p className="dialog-description">請完成現場標籤更換：</p>
            <ol>
              <li>列印新的 QR 標籤</li>
              <li>移除舊標籤</li>
              <li>將新標籤貼至正確籠位</li>
            </ol>
            <div className="dialog-actions">
              <Button type="button" onClick={() => window.print()}>
                列印新 QR
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setReplacementGuidanceOpen(false)}
              >
                完成
              </Button>
            </div>
          </Dialog>
        </>
      ) : null}
    </Card>
  );
}
