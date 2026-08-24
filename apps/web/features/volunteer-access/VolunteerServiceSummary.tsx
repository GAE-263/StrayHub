"use client";

import React from "react";

import { Alert } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";

export type ServiceSummaryItem = {
  organization_id: string;
  organization_name: string;
  service_date: string;
  service_status: "recorded" | "archived";
  record_count: number;
  source: "care_report";
};

export function VolunteerServiceSummary({
  loaded,
  items,
  nextCursor,
  loading,
  error,
  onLoad,
  onLoadMore,
}: {
  loaded: boolean;
  items: ServiceSummaryItem[];
  nextCursor: string | null;
  loading: boolean;
  error: string;
  onLoad: () => void;
  onLoadMore: () => void;
}) {
  return (
    <section
      className="space-y-2 border-t pt-3"
      aria-labelledby="service-summary-title"
    >
      <h3 id="service-summary-title">跨收容所服務紀錄</h3>
      {!loaded ? (
        <Button type="button" onClick={onLoad} disabled={loading}>
          {loading ? "載入服務紀錄中…" : "載入服務紀錄"}
        </Button>
      ) : null}
      {error ? <Alert role="alert">{error}</Alert> : null}
      {loaded && !loading && !error && items.length === 0 ? (
        <p role="status">目前沒有可顯示的服務紀錄。</p>
      ) : null}
      {items.length ? (
        <ul aria-label="跨收容所服務紀錄列表" className="space-y-2">
          {items.map((item) => (
            <li
              key={`${item.organization_id}:${item.service_date}:${item.service_status}`}
              className="rounded border p-3"
            >
              <strong>{item.organization_name}</strong>
              <span className="ml-2">{item.service_date}</span>
              <span className="ml-2">
                {item.service_status === "archived" ? "已封存" : "已記錄"}
              </span>
              <span className="ml-2">{item.record_count} 筆紀錄</span>
            </li>
          ))}
        </ul>
      ) : null}
      {loading && loaded ? <p role="status">載入服務紀錄中…</p> : null}
      {loaded && nextCursor ? (
        <Button type="button" onClick={onLoadMore} disabled={loading}>
          載入更多服務紀錄
        </Button>
      ) : null}
    </section>
  );
}
