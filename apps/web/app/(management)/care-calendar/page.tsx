"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CareAgenda } from "../../../features/medical-care/CareAgenda";
import { CareAgendaFilters } from "../../../features/medical-care/CareAgendaFilters";
import { fetchCareAgenda } from "../../../features/medical-care/api";
import type {
  AgendaBucket,
  CareAgenda as CareAgendaData,
} from "../../../features/medical-care/types";

function todayString() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Taipei" }).format(
    new Date(),
  );
}

export default function CareCalendarPage() {
  const [date, setDate] = useState(todayString);
  const [data, setData] = useState<CareAgendaData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reminderType, setReminderType] = useState("");
  const [status, setStatus] = useState("");
  const [assigneeMembershipId, setAssigneeMembershipId] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [loadingBucket, setLoadingBucket] = useState<AgendaBucket | null>(null);
  const [paginationError, setPaginationError] = useState("");
  const searchParams = useSearchParams();
  const animalIdFromUrl = searchParams.get("animal_id") ?? "";
  const [animalId, setAnimalId] = useState(animalIdFromUrl);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setPaginationError("");
    void fetchCareAgenda(
      {
        date,
        animalId: animalId || undefined,
        reminderType,
        status,
        assigneeMembershipId: assigneeMembershipId || undefined,
      },
      controller.signal,
    )
      .then(setData)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(reason instanceof Error ? reason.message : "載入失敗");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [animalId, assigneeMembershipId, date, reminderType, refreshKey, status]);

  async function loadMore(bucket: AgendaBucket) {
    const cursor = data?.pages?.[bucket]?.next_cursor;
    if (!cursor || loadingBucket) return;
    setLoadingBucket(bucket);
    setPaginationError("");
    try {
      const nextPage = await fetchCareAgenda({
        date,
        animalId: animalId || undefined,
        reminderType,
        status,
        assigneeMembershipId: assigneeMembershipId || undefined,
        cursors: { [bucket]: cursor },
      });
      setData((current) => {
        if (!current) return nextPage;
        const seen = new Set(
          current.buckets[bucket].map((item) => item.occurrence_id),
        );
        const appended = nextPage.buckets[bucket].filter(
          (item) => !seen.has(item.occurrence_id),
        );
        return {
          ...current,
          buckets: {
            ...current.buckets,
            [bucket]: [...current.buckets[bucket], ...appended],
          },
          totals: nextPage.totals,
          pages: current.pages
            ? {
                ...current.pages,
                [bucket]: nextPage.pages?.[bucket] ?? current.pages[bucket],
              }
            : nextPage.pages,
        };
      });
    } catch (reason: unknown) {
      setPaginationError(
        reason instanceof Error ? reason.message : "載入更多提醒失敗",
      );
    } finally {
      setLoadingBucket(null);
    }
  }
  return (
    <section aria-labelledby="care-calendar-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">CARE CALENDAR</span>
          <h1 id="care-calendar-title">照護行事曆</h1>
          <p>查看今天待辦、逾期、已處理與未來七天的照護提醒。</p>
        </div>
      </div>
      <CareAgendaFilters
        date={date}
        reminderType={reminderType}
        status={status}
        animalId={animalId}
        assigneeMembershipId={assigneeMembershipId}
        onDateChange={setDate}
        onReminderTypeChange={setReminderType}
        onStatusChange={setStatus}
        onAnimalIdChange={setAnimalId}
        onAssigneeChange={setAssigneeMembershipId}
        onToday={() => setDate(todayString())}
      />
      <CareAgenda
        data={data}
        loading={loading}
        error={error}
        onChanged={() => setRefreshKey((value) => value + 1)}
        onLoadMore={(bucket) => void loadMore(bucket)}
        loadingBucket={loadingBucket}
        paginationError={paginationError}
      />
    </section>
  );
}
