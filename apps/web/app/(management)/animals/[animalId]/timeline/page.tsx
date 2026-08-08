"use client";

import { use, useCallback, useEffect, useState } from "react";
import {
  AnimalTimeline,
  TimelineDay,
} from "../../../../../features/animal-timeline/AnimalTimeline";
import { TimelineFilters } from "../../../../../features/animal-timeline/TimelineFilters";

type ApiReport = {
  id: string;
  submitted_at?: string;
  volunteer_user_id?: string;
  note?: string | null;
  observations?: Record<string, string>;
  media_ids?: string[];
  ai_job_status?: string;
  status?: string;
};

type ApiDay = {
  date: string;
  has_report: boolean;
  report_count: number;
  reports?: ApiReport[];
};

type Props = { params: Promise<{ animalId: string }> };

function mapDays(days: ApiDay[]): TimelineDay[] {
  return days.map((day) => ({
    date: day.date,
    hasReport: day.has_report,
    reportCount: day.report_count,
    reports: day.reports?.map((report) => ({
      id: report.id,
      submittedAt: report.submitted_at,
      volunteerUserId: report.volunteer_user_id,
      note: report.note,
      observations: report.observations,
      mediaIds: report.media_ids,
      aiJobStatus: report.ai_job_status,
      status: report.status,
    })),
  }));
}

export default function AnimalTimelinePage({ params }: Props) {
  const { animalId } = use(params);
  const [days, setDays] = useState<TimelineDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [range, setRange] = useState({ start: "", end: "" });

  const loadTimeline = useCallback(
    async (nextRange = range) => {
      setLoading(true);
      setError("");
      const query = new URLSearchParams();
      if (nextRange.start) query.set("start_date", nextRange.start);
      if (nextRange.end) query.set("end_date", nextRange.end);
      try {
        const suffix = query.toString() ? `?${query.toString()}` : "";
        const response = await fetch(`/v1/animals/${animalId}/timeline${suffix}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as { days: ApiDay[] };
        setDays(mapDays(data.days));
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "無法載入");
      } finally {
        setLoading(false);
      }
    },
    [animalId, range],
  );

  useEffect(() => {
    void loadTimeline({ start: "", end: "" });
  }, [loadTimeline]);

  const changeDate = (date: string) => {
    const nextRange = { start: date, end: date };
    setRange(nextRange);
    void loadTimeline(nextRange);
  };

  return (
    <main>
      <h1>動物近期歷程</h1>
      <p>可查看近 14 日每日狀態、同日多筆原始回報與 AI／人工狀態。</p>
      <TimelineFilters
        disabled={loading}
        onChange={changeDate}
        onRangeChange={(nextRange) => {
          setRange(nextRange);
          if (nextRange.start && nextRange.end) void loadTimeline(nextRange);
        }}
      />
      <AnimalTimeline days={days} loading={loading} error={error} />
    </main>
  );
}
