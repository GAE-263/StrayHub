"use client";

import { useEffect, useRef, useState } from "react";

import { authFetch } from "../../../../lib/auth";
import { Button } from "../../../../components/ui/button";
import { Checkbox } from "../../../../components/ui/checkbox";
import { Field } from "../../../../components/ui/field";
import { Input } from "../../../../components/ui/input";
import { ApplicationBatchWorkbench } from "../../../../features/volunteer-access/ApplicationBatchWorkbench";
import { VolunteerApplicantDetail } from "../../../../features/volunteer-access/VolunteerApplicantDetail";
import {
  VolunteerReviewCalendar,
  type ReviewCalendarDate,
} from "../../../../features/volunteer-access/VolunteerReviewCalendar";
import {
  selectInitialServiceDate,
  type ServiceDateAvailability,
} from "./review-date";

type Application = {
  id: string;
  display_name: string;
  status: string;
  version: number;
};

type BatchItem = {
  application_id: string;
  expected_version: number;
  result: string;
  error_code?: string | null;
};

function todayLocalDate(): string {
  const value = new Date();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

function localDateTimeValue(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  const hours = String(value.getHours()).padStart(2, "0");
  const minutes = String(value.getMinutes()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}T${hours}:${minutes}`;
}

function defaultSubmittedFrom(): string {
  const value = new Date();
  value.setDate(value.getDate() - 7);
  return localDateTimeValue(value);
}

function defaultSubmittedTo(): string {
  return localDateTimeValue(new Date());
}

export default function VolunteerApplicationsPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [applications, setApplications] = useState<Application[]>([]);
  const [reviewCalendar, setReviewCalendar] = useState<ReviewCalendarDate[]>(
    [],
  );
  const [matchingCount, setMatchingCount] = useState(0);
  const [defaultGrantDurationHours, setDefaultGrantDurationHours] = useState<
    number | null
  >(null);
  const [serviceDate, setServiceDate] = useState(todayLocalDate);
  const [unassigned, setUnassigned] = useState(false);
  const [submittedFrom, setSubmittedFrom] = useState(defaultSubmittedFrom);
  const [submittedTo, setSubmittedTo] = useState(defaultSubmittedTo);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(false);
  const [detailApplicationId, setDetailApplicationId] = useState<string | null>(
    null,
  );
  const loadGeneration = useRef(0);

  async function loadApplications(
    id: string,
    from = submittedFrom,
    to = submittedTo,
    selectedServiceDate = serviceDate,
    selectedUnassigned = unassigned,
  ) {
    const generation = ++loadGeneration.current;
    setLoading(true);
    setApplications([]);
    setMatchingCount(0);
    try {
      const query = new URLSearchParams({ status: "pending", limit: "100" });
      if (selectedUnassigned) query.set("unassigned", "true");
      else if (selectedServiceDate)
        query.set("service_date", selectedServiceDate);
      if (from) query.set("submitted_from", new Date(from).toISOString());
      if (to) query.set("submitted_to", new Date(to).toISOString());
      const response = await authFetch(
        `/v1/organizations/${id}/volunteer-applications?${query.toString()}`,
      );
      if (!response.ok) {
        if (response.status === 403) {
          let code = "";
          try {
            code = ((await response.json()) as { code?: string }).code ?? "";
          } catch {
            // Preserve the safe permission fallback when the error body is absent.
          }
          if (code === "volunteer_management_denied" || !code) {
            throw new Error("需收容所管理員權限才能審核志工申請");
          }
        }
        throw new Error("無法載入志工報名名單");
      }
      const value = (await response.json()) as {
        items?: Application[];
        matching_count?: number;
        available_service_dates?: ServiceDateAvailability[];
        review_calendar?: ReviewCalendarDate[];
      };
      if (generation !== loadGeneration.current) return null;
      setApplications(value.items ?? []);
      setMatchingCount(value.matching_count ?? 0);
      setReviewCalendar(
        value.review_calendar ?? value.available_service_dates ?? [],
      );
      setLoadError("");
      return value;
    } catch (error) {
      if (generation === loadGeneration.current) {
        setLoadError(error instanceof Error ? error.message : "載入失敗");
      }
      return null;
    } finally {
      if (generation === loadGeneration.current) setLoading(false);
    }
  }

  async function loadPolicy(id: string) {
    const response = await authFetch(
      `/v1/organizations/${id}/volunteer-access-policy`,
    );
    if (!response.ok) throw new Error("無法載入志工授權設定");
    const value = (await response.json()) as {
      default_grant_duration_hours: number;
    };
    if (
      !Number.isInteger(value.default_grant_duration_hours) ||
      value.default_grant_duration_hours <= 0
    ) {
      throw new Error("志工授權設定無效");
    }
    setDefaultGrantDurationHours(value.default_grant_duration_hours);
  }

  useEffect(() => {
    const id = window.sessionStorage.getItem("active_organization_id") ?? "";
    setOrganizationId(id);
    if (!id) return;
    void loadPolicy(id).catch((error) =>
      setLoadError(error instanceof Error ? error.message : "載入失敗"),
    );
    const today = todayLocalDate();
    void loadApplications(id, submittedFrom, submittedTo, today)
      .then((value) => {
        if (!value) return;
        const selectedDate = selectInitialServiceDate(
          today,
          value.available_service_dates ?? [],
        );
        if (selectedDate === today) return;
        setServiceDate(selectedDate);
        return loadApplications(id, submittedFrom, submittedTo, selectedDate);
      })
      .catch((error) =>
        setLoadError(error instanceof Error ? error.message : "載入失敗"),
      );
    // Initial load uses the default local date-filter range.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function createBatch(payload: object) {
    const response = await authFetch(
      `/v1/organizations/${organizationId}/volunteer-decision-batches`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    if (!response.ok) throw new Error("批次建立失敗，請保留選取並重新載入狀態");
    return response.json();
  }

  async function loadItems(batchId: string) {
    const items: BatchItem[] = [];
    let cursor: string | null = null;
    do {
      const query = new URLSearchParams({ limit: "200" });
      if (cursor) query.set("cursor", cursor);
      const response = await authFetch(
        `/v1/organizations/${organizationId}/volunteer-decision-batches/${batchId}/items?${query.toString()}`,
      );
      if (!response.ok) throw new Error("逐筆結果載入失敗");
      const page = (await response.json()) as {
        items: BatchItem[];
        next_cursor: string | null;
      };
      items.push(...page.items);
      cursor = page.next_cursor;
    } while (cursor);
    return items;
  }

  async function loadBatch(batchId: string) {
    const response = await authFetch(
      `/v1/organizations/${organizationId}/volunteer-decision-batches/${batchId}`,
    );
    if (!response.ok) throw new Error("批次進度載入失敗");
    return response.json();
  }

  function invalidateLoadedApplications() {
    loadGeneration.current += 1;
    setApplications([]);
    setMatchingCount(0);
    setDetailApplicationId(null);
    setLoading(false);
    setLoadError("");
  }

  function selectReviewDate(selectedDate: string) {
    invalidateLoadedApplications();
    setUnassigned(false);
    setServiceDate(selectedDate);
    void loadApplications(
      organizationId,
      submittedFrom,
      submittedTo,
      selectedDate,
      false,
    );
  }

  return (
    <div className="volunteer-review-page">
      <div className="page-heading volunteer-review-heading">
        <div>
          <span className="eyebrow">VOLUNTEER APPLICATIONS</span>
          <h1>志工報名審核</h1>
          <p>選取申請後，批次核准或拒絕目前的服務日期。</p>
        </div>
      </div>
      <VolunteerReviewCalendar
        dates={reviewCalendar}
        selectedDate={unassigned ? "" : serviceDate}
        loading={loading && applications.length === 0}
        error={loadError}
        onSelectDate={selectReviewDate}
      />
      <form
        className="ui-card ui-card-padded volunteer-review-filters"
        aria-label="志工申請篩選"
        onSubmit={(event) => {
          event.preventDefault();
          void loadApplications(organizationId).catch((error) =>
            setLoadError(error instanceof Error ? error.message : "載入失敗"),
          );
        }}
      >
        <div className="volunteer-filter-grid">
          <Field>
            <label htmlFor="volunteer-service-date">審核服務日期</label>
            <Input
              id="volunteer-service-date"
              type="date"
              value={serviceDate}
              onChange={(event) => {
                invalidateLoadedApplications();
                setServiceDate(event.target.value);
              }}
              disabled={unassigned}
              required={!unassigned}
            />
          </Field>
          <Field>
            <label htmlFor="volunteer-submitted-from">送出時間起</label>
            <Input
              id="volunteer-submitted-from"
              type="datetime-local"
              value={submittedFrom}
              onChange={(event) => {
                invalidateLoadedApplications();
                setSubmittedFrom(event.target.value);
              }}
            />
          </Field>
          <Field>
            <label htmlFor="volunteer-submitted-to">送出時間迄</label>
            <Input
              id="volunteer-submitted-to"
              type="datetime-local"
              value={submittedTo}
              onChange={(event) => {
                invalidateLoadedApplications();
                setSubmittedTo(event.target.value);
              }}
            />
          </Field>
          <div className="volunteer-filter-toggle">
            <span className="ui-label">申請範圍</span>
            <label htmlFor="volunteer-unassigned" className="toggle-control">
              <Checkbox
                id="volunteer-unassigned"
                checked={unassigned}
                onChange={(event) => {
                  invalidateLoadedApplications();
                  setUnassigned(event.target.checked);
                }}
              />
              <span>未指定日期（既有歷史申請）</span>
            </label>
          </div>
          <div className="volunteer-filter-action">
            <Button type="submit">套用篩選</Button>
          </div>
        </div>
        <p
          className="volunteer-filter-status"
          role={loadError ? "alert" : "status"}
          aria-live="polite"
        >
          {loadError ||
            (!unassigned && serviceDate
              ? `目前顯示 ${serviceDate} 的待審核申請`
              : "")}
        </p>
      </form>
      {defaultGrantDurationHours === null ? (
        <p role="status">載入志工授權設定中…</p>
      ) : (
        <ApplicationBatchWorkbench
          key={`${serviceDate}:${unassigned}:${submittedFrom}:${submittedTo}`}
          applications={loading ? [] : applications}
          loading={loading}
          matchingCount={loading ? 0 : matchingCount}
          defaultGrantDurationHours={defaultGrantDurationHours}
          filter={{
            status: "pending",
            ...(unassigned
              ? { unassigned: true }
              : { service_date: serviceDate }),
            ...(submittedFrom
              ? { submitted_from: new Date(submittedFrom).toISOString() }
              : {}),
            ...(submittedTo
              ? { submitted_to: new Date(submittedTo).toISOString() }
              : {}),
          }}
          onSubmit={createBatch}
          onLoadItems={loadItems}
          onLoadBatch={loadBatch}
          onBatchTerminalSuccess={() => {
            void loadApplications(
              organizationId,
              submittedFrom,
              submittedTo,
              serviceDate,
              unassigned,
            );
          }}
          onViewApplicant={setDetailApplicationId}
        />
      )}
      <VolunteerApplicantDetail
        organizationId={organizationId}
        applicationId={detailApplicationId}
        open={detailApplicationId !== null}
        onClose={() => setDetailApplicationId(null)}
      />
    </div>
  );
}
