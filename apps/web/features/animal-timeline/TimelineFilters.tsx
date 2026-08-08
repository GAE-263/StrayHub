"use client";

import React, { useState } from "react";

type Props = {
  onChange: (value: string) => void;
  onRangeChange?: (range: { start: string; end: string }) => void;
  disabled?: boolean;
};

export function TimelineFilters({ onChange, onRangeChange, disabled }: Props) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  return (
    <fieldset>
      <legend>歷程查詢</legend>
      <label>
        指定日期
        <input
          type="date"
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
      <label>
        起始日期
        <input
          type="date"
          value={start}
          disabled={disabled}
          onChange={(event) => {
            const nextStart = event.target.value;
            setStart(nextStart);
            onRangeChange?.({ start: nextStart, end });
          }}
        />
      </label>
      <label>
        結束日期
        <input
          type="date"
          value={end}
          disabled={disabled}
          onChange={(event) => {
            const nextEnd = event.target.value;
            setEnd(nextEnd);
            onRangeChange?.({ start, end: nextEnd });
          }}
        />
      </label>
    </fieldset>
  );
}
