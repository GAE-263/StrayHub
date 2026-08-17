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
      <section className="panel ui-card" role="alert">
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
  return (
    <section className="panel ui-card" aria-live="polite">
      <h2>今天發生什麼</h2>
      <p>
        {localToday ? `${localToday}：` : ""}
        {label}
      </p>
    </section>
  );
}
