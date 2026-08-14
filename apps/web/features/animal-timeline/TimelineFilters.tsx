"use client";

import React, { useState } from "react";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";

type Props = {
  onChange: (value: string) => void;
  onRangeChange?: (range: { start: string; end: string }) => void;
  disabled?: boolean;
};

export function TimelineFilters({ onChange, onRangeChange, disabled }: Props) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  return (
    <fieldset className="ui-card timeline-filters">
      <legend>歷程查詢</legend>
      <Field>
        <label htmlFor="timeline-date">指定日期</label>
        <Input
          id="timeline-date"
          type="date"
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
      </Field>
      <Field>
        <label htmlFor="timeline-start">起始日期</label>
        <Input
          id="timeline-start"
          type="date"
          value={start}
          disabled={disabled}
          onChange={(event) => {
            const nextStart = event.target.value;
            setStart(nextStart);
            onRangeChange?.({ start: nextStart, end });
          }}
        />
      </Field>
      <Field>
        <label htmlFor="timeline-end">結束日期</label>
        <Input
          id="timeline-end"
          type="date"
          value={end}
          disabled={disabled}
          onChange={(event) => {
            const nextEnd = event.target.value;
            setEnd(nextEnd);
            onRangeChange?.({ start, end: nextEnd });
          }}
        />
      </Field>
    </fieldset>
  );
}
