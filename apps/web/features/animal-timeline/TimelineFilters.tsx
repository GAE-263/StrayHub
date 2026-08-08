"use client";

import React from "react";

type Props = {
  onChange: (value: string) => void;
  onRangeChange?: (range: { start: string; end: string }) => void;
  disabled?: boolean;
};

export function TimelineFilters({ onChange, onRangeChange, disabled }: Props) {
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
          disabled={disabled}
          onChange={(event) =>
            onRangeChange?.({ start: event.target.value, end: "" })
          }
        />
      </label>
      <label>
        結束日期
        <input
          type="date"
          disabled={disabled}
          onChange={(event) =>
            onRangeChange?.({ start: "", end: event.target.value })
          }
        />
      </label>
    </fieldset>
  );
}
