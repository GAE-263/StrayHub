"use client";

import React from "react";
import { Button } from "../../components/ui/button";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";

export function CareAgendaFilters({
  date,
  reminderType,
  status,
  animalId,
  assigneeMembershipId,
  onDateChange,
  onReminderTypeChange,
  onStatusChange,
  onAnimalIdChange,
  onAssigneeChange,
  onToday,
}: {
  date: string;
  reminderType: string;
  status: string;
  animalId: string;
  assigneeMembershipId: string;
  onDateChange: (value: string) => void;
  onReminderTypeChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onAnimalIdChange: (value: string) => void;
  onAssigneeChange: (value: string) => void;
  onToday: () => void;
}) {
  const shift = (days: number) => {
    const next = new Date(`${date}T12:00:00`);
    next.setDate(next.getDate() + days);
    onDateChange(next.toISOString().slice(0, 10));
  };
  return (
    <section className="panel ui-card toolbar" aria-label="照護行事曆篩選">
      <Field>
        <label htmlFor="care-calendar-date">指定日期</label>
        <Input
          id="care-calendar-date"
          type="date"
          value={date}
          onChange={(event) => onDateChange(event.target.value)}
        />
      </Field>
      <div className="cluster">
        <Button type="button" variant="secondary" onClick={() => shift(-1)}>
          上一日
        </Button>
        <Button type="button" variant="secondary" onClick={onToday}>
          回到今天
        </Button>
        <Button type="button" variant="secondary" onClick={() => shift(1)}>
          下一日
        </Button>
      </div>
      <Field>
        <label htmlFor="care-calendar-animal">動物 ID（選填）</label>
        <Input
          id="care-calendar-animal"
          value={animalId}
          onChange={(event) => onAnimalIdChange(event.target.value)}
        />
      </Field>
      <Field>
        <label htmlFor="care-calendar-assignee">負責人 ID（選填）</label>
        <Input
          id="care-calendar-assignee"
          value={assigneeMembershipId}
          onChange={(event) => onAssigneeChange(event.target.value)}
        />
      </Field>
      <Field>
        <label htmlFor="care-calendar-type">提醒類型</label>
        <select
          id="care-calendar-type"
          className="ui-input"
          value={reminderType}
          onChange={(event) => onReminderTypeChange(event.target.value)}
        >
          <option value="">全部類型</option>
          <option value="medication">吃藥</option>
          <option value="follow_up">回診</option>
          <option value="weight">量體重</option>
          <option value="vaccination">疫苗</option>
          <option value="examination">檢查</option>
          <option value="other">其他</option>
        </select>
      </Field>
      <Field>
        <label htmlFor="care-calendar-status">狀態</label>
        <select
          id="care-calendar-status"
          className="ui-input"
          value={status}
          onChange={(event) => onStatusChange(event.target.value)}
        >
          <option value="">全部狀態</option>
          <option value="pending">待處理</option>
          <option value="completed">已完成</option>
          <option value="skipped">已略過</option>
          <option value="cancelled">已取消</option>
        </select>
      </Field>
    </section>
  );
}
