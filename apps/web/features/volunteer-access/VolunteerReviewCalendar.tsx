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
      className="ui-card ui-card-padded volunteer-review-calendar"
      aria-labelledby="review-calendar-title"
    >
      <div className="review-calendar-header">
        <span className="eyebrow">REVIEW AGENDA</span>
        <h2 id="review-calendar-title">審核日期</h2>
      </div>
      {loading ? (
        <p className="review-calendar-state" role="status" aria-live="polite">
          載入審核日期中…
        </p>
      ) : error ? (
        <p className="review-calendar-state" role="alert">
          {error}
        </p>
      ) : dates.length === 0 ? (
        <p className="review-calendar-state" role="status">
          目前沒有待審核的服務日期。
        </p>
      ) : (
        <div
          className="review-calendar-dates"
          role="list"
          aria-label="待審核服務日期"
        >
          {dates.map((item) => {
            const selected = item.service_date === selectedDate;
            return (
              <button
                key={item.service_date}
                type="button"
                aria-label={`${item.service_date}，${item.pending_count} 筆待審核申請`}
                aria-pressed={selected}
                className={`review-calendar-date${selected ? " is-selected" : ""}`}
                onClick={() => onSelectDate(item.service_date)}
              >
                <span className="review-calendar-date-value">
                  {item.service_date}
                </span>
                <span className="review-calendar-date-count">
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
