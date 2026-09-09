"use client";

import React from "react";
import { Badge } from "../../components/ui/badge";
import { EmptyState } from "../../components/management/StateViews";
import type { AgendaItem } from "./types";
import { ReminderCard } from "./ReminderCard";
import { Button } from "../../components/ui/button";

export function ReminderSection({
  id,
  title,
  items,
  timezone,
  onProcess,
  total,
  nextCursor,
  loadingMore = false,
  onLoadMore,
}: {
  id: string;
  title: string;
  items: AgendaItem[];
  timezone: string;
  onProcess?: (item: AgendaItem) => void;
  total: number;
  nextCursor: string | null;
  loadingMore?: boolean;
  onLoadMore?: () => void;
}) {
  return (
    <section
      className="ui-card ui-card-padded"
      aria-labelledby={`agenda-${id}`}
    >
      <div className="section-heading">
        <h2 id={`agenda-${id}`}>{title}</h2>
        <Badge>
          {items.length === total ? total : `${items.length} / ${total}`}
        </Badge>
      </div>
      {items.length === 0 ? (
        <EmptyState title="沒有項目" description="目前沒有符合條件的提醒。" />
      ) : (
        <div className="stack-sm">
          <div className="reminder-card-grid">
            {items.map((item) => (
              <ReminderCard
                key={item.occurrence_id}
                item={item}
                timezone={timezone}
                onProcess={onProcess ? () => onProcess(item) : undefined}
              />
            ))}
          </div>
          {nextCursor && onLoadMore ? (
            <Button type="button" disabled={loadingMore} onClick={onLoadMore}>
              {loadingMore
                ? "正在載入更多…"
                : `載入更多（尚有 ${Math.max(0, total - items.length)} 筆）`}
            </Button>
          ) : null}
        </div>
      )}
    </section>
  );
}
