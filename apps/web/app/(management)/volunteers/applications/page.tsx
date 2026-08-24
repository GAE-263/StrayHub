"use client";

import { useEffect, useRef, useState } from "react";

import { authFetch } from "../../../../lib/auth";
import { ApplicationBatchWorkbench } from "../../../../features/volunteer-access/ApplicationBatchWorkbench";
import { VolunteerApplicantDetail } from "../../../../features/volunteer-access/VolunteerApplicantDetail";
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

export default function VolunteerApplicationsPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [applications, setApplications] = useState<Application[]>([]);
  const [matchingCount, setMatchingCount] = useState(0);
  const [serviceDate, setServiceDate] = useState(todayLocalDate);
  const [unassigned, setUnassigned] = useState(false);
  const [submittedFrom, setSubmittedFrom] = useState("");
  const [submittedTo, setSubmittedTo] = useState("");
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
  ) {
    const generation = ++loadGeneration.current;
    setLoading(true);
    setApplications([]);
    setMatchingCount(0);
    try {
      const query = new URLSearchParams({ status: "pending", limit: "100" });
      if (unassigned) query.set("unassigned", "true");
      else if (selectedServiceDate)
        query.set("service_date", selectedServiceDate);
      if (from) query.set("submitted_from", new Date(from).toISOString());
      if (to) query.set("submitted_to", new Date(to).toISOString());
      const response = await authFetch(
        `/v1/organizations/${id}/volunteer-applications?${query.toString()}`,
      );
      if (!response.ok) throw new Error("無法載入志工報名名單");
      const value = (await response.json()) as {
        items?: Application[];
        matching_count?: number;
        available_service_dates?: ServiceDateAvailability[];
      };
      if (generation !== loadGeneration.current) return null;
      setApplications(value.items ?? []);
      setMatchingCount(value.matching_count ?? 0);
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

  useEffect(() => {
    const id = window.sessionStorage.getItem("active_organization_id") ?? "";
    setOrganizationId(id);
    if (!id) return;
    const today = todayLocalDate();
    void loadApplications(id, "", "", today)
      .then((value) => {
        if (!value) return;
        const selectedDate = selectInitialServiceDate(
          today,
          value.available_service_dates ?? [],
        );
        if (selectedDate === today) return;
        setServiceDate(selectedDate);
        return loadApplications(id, "", "", selectedDate);
      })
      .catch((error) =>
        setLoadError(error instanceof Error ? error.message : "載入失敗"),
      );
    // Initial load intentionally ignores local date-filter state.
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
    setLoading(false);
    setLoadError("");
  }

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">VOLUNTEER APPLICATIONS</span>
          <h1>志工報名審核</h1>
          <p>明確選取，或鎖定目前篩選結果的完整快照後批次核准／拒絕。</p>
        </div>
      </div>
      <form
        className="ui-card ui-card-padded mb-4 flex flex-wrap items-end gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void loadApplications(organizationId).catch((error) =>
            setLoadError(error instanceof Error ? error.message : "載入失敗"),
          );
        }}
      >
        <label>
          審核服務日期
          <input
            type="date"
            value={serviceDate}
            onChange={(event) => {
              invalidateLoadedApplications();
              setServiceDate(event.target.value);
            }}
            disabled={unassigned}
            required={!unassigned}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={unassigned}
            onChange={(event) => {
              invalidateLoadedApplications();
              setUnassigned(event.target.checked);
            }}
          />
          未指定日期（既有歷史申請）
        </label>
        <label>
          送出時間起
          <input
            type="datetime-local"
            value={submittedFrom}
            onChange={(event) => {
              invalidateLoadedApplications();
              setSubmittedFrom(event.target.value);
            }}
          />
        </label>
        <label>
          送出時間迄
          <input
            type="datetime-local"
            value={submittedTo}
            onChange={(event) => {
              invalidateLoadedApplications();
              setSubmittedTo(event.target.value);
            }}
          />
        </label>
        <button type="submit">套用篩選</button>
        <p role="status" aria-live="polite">
          {loadError ||
            (!unassigned && serviceDate
              ? `目前顯示 ${serviceDate} 的待審核申請`
              : "")}
        </p>
      </form>
      <ApplicationBatchWorkbench
        key={`${serviceDate}:${unassigned}:${submittedFrom}:${submittedTo}`}
        applications={loading ? [] : applications}
        matchingCount={loading ? 0 : matchingCount}
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
        onViewApplicant={setDetailApplicationId}
      />
      <VolunteerApplicantDetail
        organizationId={organizationId}
        applicationId={detailApplicationId}
        open={detailApplicationId !== null}
        onClose={() => setDetailApplicationId(null)}
      />
    </div>
  );
}
