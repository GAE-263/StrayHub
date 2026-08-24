"use client";

import React from "react";

export type ReviewCalendarDate = {
  service_date: string;
  pending_count: number;
};

type VolunteerReviewCalendarProps = {
  dates: ReviewCalendarDate[];
  selectedDate: string;
  loading?: boolean;
  error?: string;
  onSelectDate: (serviceDate: string) => void;
};

export function VolunteerReviewCalendar({
  dates,
  selectedDate,
  loading = false,
  error = "",
  onSelectDate,
}: VolunteerReviewCalendarProps) {
  return (
    <section
      className="ui-card ui-card-padded mb-4"
      aria-labelledby="review-calendar-title"
    >
      <div className="mb-3">
        <span className="eyebrow">REVIEW AGENDA</span>
        <h2 id="review-calendar-title">審核日期</h2>
      </div>
      {loading ? (
        <p role="status" aria-live="polite">
          載入審核日期中…
        </p>
      ) : error ? (
        <p role="alert">{error}</p>
      ) : dates.length === 0 ? (
        <p role="status">目前沒有待審核的服務日期。</p>
      ) : (
        <div className="flex max-w-full gap-3 overflow-x-auto pb-2" role="list">
          {dates.map((item) => {
            const selected = item.service_date === selectedDate;
            return (
              <button
                key={item.service_date}
                type="button"
                role="listitem"
                aria-label={`${item.service_date}，${item.pending_count} 筆待審核申請`}
                aria-pressed={selected}
                className={`min-w-32 rounded border px-4 py-3 text-left ${
                  selected
                    ? "border-slate-900 bg-slate-100"
                    : "border-slate-300"
                }`}
                onClick={() => onSelectDate(item.service_date)}
              >
                <span className="block text-sm">{item.service_date}</span>
                <span className="block font-semibold">
                  {item.pending_count} 筆待審核
                </span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
