"use client";

import React from "react";
import Link from "next/link";
import { Button } from "../../components/ui/button";
import type { AgendaItem } from "./types";

export function ReminderCard({
  item,
  timezone,
  onProcess,
}: {
  item: AgendaItem;
  timezone: string;
  onProcess: () => void;
}) {
  const scheduled = new Intl.DateTimeFormat("zh-TW", {
    timeZone: timezone,
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(item.scheduled_at));
  return (
    <article className="list-card">
      <div>
        <strong>{item.animal_name || "未命名動物"}</strong>
        <span className="muted">　{item.shelter_number || "無收容編號"}</span>
        <p>{item.title}</p>
        <small>
          {item.reminder_type} · {scheduled} · {item.status}
        </small>
      </div>
      <Link className="text-link" href={`/animals/${item.animal_id}`}>
        查看動物
      </Link>
      {item.status === "pending" ? (
        <Button type="button" onClick={onProcess}>
          處理
        </Button>
      ) : null}
    </article>
  );
}
