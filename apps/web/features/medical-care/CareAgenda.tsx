"use client";

import React from "react";
import {
  ErrorState,
  LoadingState,
} from "../../components/management/StateViews";
import type { AgendaBucket, CareAgenda } from "./types";
import { useState } from "react";
import { ReminderActionDialog } from "./ReminderActionDialog";
import type { AgendaItem } from "./types";
import { ReminderSection } from "./ReminderSection";
import { Toast } from "../../components/ui/toast";

const sections: Array<[AgendaBucket, string]> = [
  ["today_pending", "今天待處理"],
  ["overdue", "已逾期"],
  ["today_resolved", "今天已完成／略過／取消"],
  ["next_seven_days", "未來七天"],
];

export function CareAgenda({
  data,
  loading,
  error,
  onChanged,
  onLoadMore,
  loadingBucket = null,
  paginationError = "",
}: {
  data: CareAgenda | null;
  loading: boolean;
  error: string;
  onChanged?: () => void;
  onLoadMore?: (bucket: AgendaBucket) => void;
  loadingBucket?: AgendaBucket | null;
  paginationError?: string;
}) {
  const [selected, setSelected] = useState<AgendaItem | null>(null);
  const [toast, setToast] = useState("");
  if (loading) return <LoadingState title="正在載入照護行事曆…" />;
  if (error)
    return <ErrorState title="無法載入照護行事曆" description={error} />;
  if (!data) return null;
  return (
    <div className="stack-lg" aria-live="polite">
      <p className="muted">
        收容所時區：{data.timezone}　日期：{data.local_today}
      </p>
      {paginationError ? <p role="alert">{paginationError}</p> : null}
      {sections.map(([bucket, title]) => {
        const items = data.buckets[bucket] ?? [];
        return (
          <ReminderSection
            key={bucket}
            id={bucket}
            title={title}
            items={items}
            timezone={data.timezone}
            onProcess={setSelected}
            total={data.totals[bucket] ?? items.length}
            nextCursor={data.pages?.[bucket]?.next_cursor ?? null}
            loadingMore={loadingBucket === bucket}
            onLoadMore={onLoadMore ? () => onLoadMore(bucket) : undefined}
          />
        );
      })}
      <ReminderActionDialog
        item={selected}
        onClose={() => setSelected(null)}
        onSaved={(message) => {
          setToast(message);
          onChanged?.();
        }}
      />
      {toast ? (
        <Toast messageKey={toast} onClose={() => setToast("")}>
          {toast}
        </Toast>
      ) : null}
    </div>
  );
}
