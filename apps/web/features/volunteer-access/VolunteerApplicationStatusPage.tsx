"use client";

import React, { useEffect, useMemo, useState } from "react";

import { Alert } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { formatTaiwanDateTime, safeVolunteerError } from "./volunteerAccess";

const DIAGNOSTICS_ENABLED = process.env.NODE_ENV !== "production";

function diagnostic(event: string, metadata?: Record<string, unknown>) {
  if (!DIAGNOSTICS_ENABLED) return;
  console.debug(`[volunteer-liff] ${event}`, metadata ?? {});
}

type OwnApplicationStatus = {
  organization: { id: string; name: string; address: string | null };
  application: {
    id: string;
    status: "pending" | "approved" | "rejected" | "withdrawn";
    submitted_at: string;
    decision_reason?: string | null;
  };
  service_dates: Array<{ service_date: string; status: string }>;
  grant: {
    status: string;
    valid_from: string;
    expires_at: string;
  } | null;
  effective_status: string;
};

type Props = {
  idToken: string;
  focusedOrganizationId?: string;
  onStartApplication: () => void;
  onReturnToLine: () => void;
};

const STATUS_LABEL: Record<string, string> = {
  pending: "審核中",
  upcoming: "已核准・尚未開始",
  active: "已核准・授權中",
  expired: "授權已到期",
  revoked: "授權已撤銷",
  rejected: "未通過",
  withdrawn: "已撤回",
  none: "待收容所確認",
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(`${value}T12:00:00+08:00`));
}

export function VolunteerApplicationStatusPage({
  idToken,
  focusedOrganizationId,
  onStartApplication,
  onReturnToLine,
}: Props) {
  const [items, setItems] = useState<OwnApplicationStatus[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setItems(null);
    setError("");
    diagnostic("status-fetch:start");
    void fetch("/v1/volunteer-applications/self-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw body;
        return body as { items: OwnApplicationStatus[] };
      })
      .then((body) => {
        if (!active) return;
        const categories = body.items.reduce<Record<string, number>>(
          (counts, item) => {
            counts[item.application.status] =
              (counts[item.application.status] ?? 0) + 1;
            return counts;
          },
          {},
        );
        diagnostic("status-fetch:success", {
          applicationCount: body.items.length,
          statusCategories: categories,
        });
        setItems(body.items);
      })
      .catch((reason) => {
        if (active) {
          diagnostic("status-fetch:error");
          setError(safeVolunteerError(reason?.code));
        }
      });
    return () => {
      active = false;
    };
  }, [idToken]);

  const dataState = error
    ? "error"
    : items === null
      ? "loading"
      : items.length === 0
        ? "empty"
        : "ready";

  useEffect(() => {
    diagnostic("render-mode", { view: "status", dataState });
  }, [dataState]);

  const orderedItems = useMemo(() => {
    if (!focusedOrganizationId || !items) return items;
    return [...items].sort(
      (left, right) =>
        Number(right.organization.id === focusedOrganizationId) -
        Number(left.organization.id === focusedOrganizationId),
    );
  }, [focusedOrganizationId, items]);

  return (
    <main className="volunteer-application-page volunteer-status-page">
      <header className="volunteer-application-heading">
        <span className="eyebrow">LINE 志工服務</span>
        <h1>我的志工申請</h1>
        <p>每間收容所的申請與授權狀態分開顯示。</p>
      </header>

      {!orderedItems && !error ? (
        <p role="status" aria-live="polite">
          正在載入申請紀錄…
        </p>
      ) : null}

      {error ? (
        <div className="volunteer-application-actions">
          <Alert role="alert">{error}</Alert>
          <Button type="button" onClick={() => window.location.reload()}>
            重新整理
          </Button>
          <Button variant="secondary" type="button" onClick={onReturnToLine}>
            返回 LINE
          </Button>
        </div>
      ) : null}

      {orderedItems?.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>目前沒有志工申請紀錄</CardTitle>
            <p>你已進入「我的申請」，尚未向任何收容所送出報名。</p>
          </CardHeader>
          <CardContent className="volunteer-application-actions">
            <Button type="button" onClick={onStartApplication}>
              前往志工報名
            </Button>
            <Button variant="secondary" type="button" onClick={onReturnToLine}>
              返回 LINE
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {orderedItems?.map((item) => (
        <Card
          key={item.application.id}
          className="volunteer-status-card"
          data-focused={item.organization.id === focusedOrganizationId}
        >
          <CardHeader>
            <div className="volunteer-status-card-title">
              <CardTitle>{item.organization.name}</CardTitle>
              <span className="volunteer-status-badge">
                {STATUS_LABEL[item.effective_status] ?? item.application.status}
              </span>
            </div>
            {item.organization.address ? (
              <p>{item.organization.address}</p>
            ) : null}
          </CardHeader>
          <CardContent>
            <dl className="volunteer-grant-summary">
              <div>
                <dt>服務日期</dt>
                <dd>
                  {item.service_dates.length
                    ? item.service_dates
                        .map((serviceDate) =>
                          formatDate(serviceDate.service_date),
                        )
                        .join("、")
                    : "未指定"}
                </dd>
              </div>
              <div>
                <dt>申請日期</dt>
                <dd>{formatTaiwanDateTime(item.application.submitted_at)}</dd>
              </div>
              {item.grant ? (
                <div>
                  <dt>授權期間</dt>
                  <dd>
                    {formatTaiwanDateTime(item.grant.valid_from)} ～{" "}
                    {formatTaiwanDateTime(item.grant.expires_at)}
                  </dd>
                </div>
              ) : null}
            </dl>
            {item.application.decision_reason ? (
              <Alert>{item.application.decision_reason}</Alert>
            ) : null}
          </CardContent>
        </Card>
      ))}

      {orderedItems && orderedItems.length > 0 ? (
        <div className="volunteer-application-actions">
          <Button type="button" onClick={onStartApplication}>
            前往其他收容所報名
          </Button>
          <Button variant="secondary" type="button" onClick={onReturnToLine}>
            返回 LINE
          </Button>
        </div>
      ) : null}
    </main>
  );
}
