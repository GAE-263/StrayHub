"use client";

import React from "react";

export function AnimalTodaySummary({
  localToday,
  hasActivity,
  pendingCount,
  overdueCount,
  state,
  error,
}: {
  localToday?: string;
  hasActivity: boolean;
  pendingCount: number;
  overdueCount: number;
  state?: "no_activity" | "events_no_todos" | "pending" | "overdue";
  error?: string;
}) {
  if (error)
    return (
      <section className="ui-card ui-card-padded" role="alert">
        <h2>今日摘要載入失敗</h2>
        <p>{error}</p>
      </section>
    );
  const label =
    state === "overdue" || overdueCount
      ? "有逾期待辦"
      : state === "pending" || pendingCount
        ? "今天仍有待辦"
        : state === "events_no_todos" || hasActivity
          ? "今天有事件但沒有待辦"
          : "今天沒有任何事件";
  const tone =
    state === "overdue" || overdueCount
      ? "overdue"
      : state === "pending" || pendingCount
        ? "pending"
        : "clear";
  return (
    <section
      className="ui-card ui-card-padded animal-today-summary"
      data-tone={tone}
      aria-live="polite"
    >
      <div className="animal-today-heading">
        <span className="eyebrow">TODAY · 今日照護</span>
        {localToday ? <time dateTime={localToday}>{localToday}</time> : null}
      </div>
      <div className="animal-today-message">
        <span className="animal-today-indicator" aria-hidden="true" />
        <div>
          <h2>{label}</h2>
          <p>
            {tone === "overdue"
              ? "先處理逾期項目，再確認今天的照護安排。"
              : tone === "pending"
                ? "完成後記得更新狀態，讓下一班人員接得上。"
                : "目前沒有需要立即處理的照護事項。"}
          </p>
        </div>
      </div>
      <dl className="animal-today-counts">
        <div>
          <dt>今日待辦</dt>
          <dd>{pendingCount}</dd>
        </div>
        <div>
          <dt>已逾期</dt>
          <dd>{overdueCount}</dd>
        </div>
      </dl>
    </section>
  );
}
