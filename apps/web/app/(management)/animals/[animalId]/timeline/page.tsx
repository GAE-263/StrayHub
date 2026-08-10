"use client";

import { use, useCallback, useEffect, useState } from "react";
import {
  AnimalTimeline,
  TimelineDay,
} from "../../../../../features/animal-timeline/AnimalTimeline";
import { TimelineFilters } from "../../../../../features/animal-timeline/TimelineFilters";
import { authFetch } from "../../../../../lib/auth";
import {
  mapDays,
  type ApiDay,
} from "../../../../../features/animal-timeline/timelineMapping";
import { Breadcrumbs } from "../../../../../components/management/Breadcrumbs";

type Props = { params: Promise<{ animalId: string }> };

export default function AnimalTimelinePage({ params }: Props) {
  const { animalId } = use(params);
  const [days, setDays] = useState<TimelineDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [range, setRange] = useState({ start: "", end: "" });

  const loadTimeline = useCallback(
    async (
      nextRange: { start: string; end: string } = { start: "", end: "" },
    ) => {
      setLoading(true);
      setError("");
      const query = new URLSearchParams();
      if (nextRange.start) query.set("start_date", nextRange.start);
      if (nextRange.end) query.set("end_date", nextRange.end);
      try {
        const suffix = query.toString() ? `?${query.toString()}` : "";
        const response = await authFetch(
          `/v1/animals/${animalId}/timeline${suffix}`,
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = (await response.json()) as { days: ApiDay[] };
        setDays(mapDays(data.days));
      } catch (requestError) {
        setError(
          requestError instanceof Error ? requestError.message : "無法載入",
        );
      } finally {
        setLoading(false);
      }
    },
    [animalId],
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
      <Breadcrumbs
        items={[
          { label: "動物檔案", href: "/animals" },
          { label: animalId, href: `/animals/${animalId}` },
          { label: "近期歷程" },
        ]}
      />
      <div className="page-heading">
        <div>
          <span className="eyebrow">CARE TIMELINE</span>
          <h1>動物近期歷程</h1>
          <p>可查看近 14 日每日狀態、同日多筆原始回報與 AI／人工狀態。</p>
        </div>
        <a className="button button-secondary" href={`/animals/${animalId}`}>
          回到動物檔案
        </a>
      </div>
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
