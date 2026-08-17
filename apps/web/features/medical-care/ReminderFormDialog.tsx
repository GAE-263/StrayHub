"use client";

import React from "react";
import { FormEvent, useState } from "react";
import { Dialog } from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import { createReminderSeries } from "./api";

export function ReminderFormDialog({
  open,
  animalId,
  onClose,
  onSaved,
}: {
  open: boolean;
  animalId: string;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const [title, setTitle] = useState("");
  const [reminderType, setReminderType] = useState("other");
  const [instructions, setInstructions] = useState("");
  const [firstExecutionAt, setFirstExecutionAt] = useState("");
  const [frequency, setFrequency] = useState("none");
  const [interval, setInterval] = useState("1");
  const [endLocalDate, setEndLocalDate] = useState("");
  const [message, setMessage] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    try {
      await createReminderSeries(animalId, {
        reminder_type: reminderType as "medication",
        title,
        instructions,
        first_execution_at: new Date(firstExecutionAt).toISOString(),
        frequency: frequency as "none",
        interval: Number(interval),
        end_local_date: endLocalDate || null,
      });
    } catch {
      setMessage("提醒建立失敗，請檢查權限與欄位。");
      return;
    }
    setMessage("提醒已建立");
    onSaved?.();
    onClose();
  }
  return (
    <Dialog open={open} title="建立照護提醒" onClose={onClose}>
      <form className="stack-sm" onSubmit={submit}>
        <Field>
          <label htmlFor="reminder-type">提醒類型</label>
          <Select
            id="reminder-type"
            value={reminderType}
            onChange={(e) => setReminderType(e.target.value)}
          >
            <option value="medication">吃藥</option>
            <option value="follow_up">回診</option>
            <option value="weight">量體重</option>
            <option value="vaccination">疫苗</option>
            <option value="examination">檢查</option>
            <option value="other">其他</option>
          </Select>
        </Field>
        <Field>
          <label htmlFor="reminder-title">標題</label>
          <Input
            id="reminder-title"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field>
          <label htmlFor="reminder-instructions">說明或執行指示</label>
          <Textarea
            id="reminder-instructions"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </Field>
        <Field>
          <label htmlFor="reminder-first">第一次執行</label>
          <Input
            id="reminder-first"
            required
            type="datetime-local"
            value={firstExecutionAt}
            onChange={(e) => setFirstExecutionAt(e.target.value)}
          />
        </Field>
        <div className="toolbar">
          <Field>
            <label htmlFor="reminder-frequency">重複週期</label>
            <Select
              id="reminder-frequency"
              value={frequency}
              onChange={(e) => setFrequency(e.target.value)}
            >
              <option value="none">不重複</option>
              <option value="daily">每天</option>
              <option value="weekly">每週</option>
              <option value="monthly">每月</option>
              <option value="yearly">每年</option>
            </Select>
          </Field>
          <Field>
            <label htmlFor="reminder-interval">間隔</label>
            <Input
              id="reminder-interval"
              type="number"
              min="1"
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
            />
          </Field>
          {frequency !== "none" ? (
            <Field>
              <label htmlFor="reminder-end">結束日期（選填）</label>
              <Input
                id="reminder-end"
                type="date"
                value={endLocalDate}
                onChange={(e) => setEndLocalDate(e.target.value)}
              />
            </Field>
          ) : null}
        </div>
        <p className="muted">
          週期日期由收容所時區計算；系統不會依體重計算藥量。
        </p>
        <Button type="submit">建立提醒</Button>
        {message ? <p role="status">{message}</p> : null}
      </form>
    </Dialog>
  );
}
