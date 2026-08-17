"use client";

import React, {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import {
  archiveMedicalRecord,
  createMedicalRecord,
  fetchMedicalRecords,
  updateMedicalRecord,
} from "./api";
import type { MedicalRecord } from "./types";

const recordTypeLabels: Record<string, string> = {
  visit: "就醫",
  medication: "用藥",
  vaccination: "疫苗",
  examination: "檢查",
  weight: "體重",
  surgery: "手術",
  other: "其他",
};

function localDate(value: string, timezone: string) {
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: timezone,
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export function MedicalHistoryPanel({ animalId }: { animalId: string }) {
  const [items, setItems] = useState<MedicalRecord[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [recordType, setRecordType] = useState("other");
  const [weight, setWeight] = useState("");
  const [occurredAt, setOccurredAt] = useState("");
  const [clinic, setClinic] = useState("");
  const [veterinarian, setVeterinarian] = useState("");
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError("");
      try {
        const page = await fetchMedicalRecords(
          animalId,
          {
            recordType: filterType || undefined,
            search: search.trim() || undefined,
            includeArchived,
          },
          signal,
        );
        if (!signal?.aborted) setItems(page.items);
      } catch (loadError) {
        if (!signal?.aborted)
          setError(
            loadError instanceof Error ? loadError.message : "醫療歷史載入失敗",
          );
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [animalId, filterType, includeArchived, search],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const clearForm = () => {
    setTitle("");
    setContent("");
    setWeight("");
    setOccurredAt("");
    setClinic("");
    setVeterinarian("");
    setRecordType("other");
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await createMedicalRecord(animalId, {
        occurred_at: occurredAt
          ? new Date(occurredAt).toISOString()
          : new Date().toISOString(),
        record_type: recordType,
        title: title.trim(),
        content: content.trim(),
        clinic: clinic.trim() || undefined,
        veterinarian: veterinarian.trim() || undefined,
        weight_kg: weight ? Number(weight) : null,
      });
      clearForm();
      setMessage("已儲存醫療紀錄");
      await load();
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "醫療紀錄儲存失敗",
      );
      // Keep all entered text so an attachment or network failure is recoverable.
    } finally {
      setBusy(false);
    }
  }

  function beginEdit(item: MedicalRecord) {
    setEditingId(item.id);
    setEditTitle(item.title);
    setEditContent(item.content);
    setReason("");
    setMessage("");
  }

  async function saveEdit(item: MedicalRecord) {
    if (busy || !reason.trim()) return;
    setBusy(true);
    setError("");
    try {
      await updateMedicalRecord(item.id, {
        expected_version: item.version,
        title: editTitle.trim(),
        content: editContent.trim(),
        reason: reason.trim(),
      });
      setEditingId(null);
      setMessage("已更新醫療紀錄");
      await load();
    } catch (updateError) {
      setError(
        updateError instanceof Error ? updateError.message : "醫療紀錄更新失敗",
      );
    } finally {
      setBusy(false);
    }
  }

  async function archive(item: MedicalRecord) {
    if (busy || !reason.trim()) return;
    setBusy(true);
    setError("");
    try {
      await archiveMedicalRecord(item.id, {
        expected_version: item.version,
        reason: reason.trim(),
      });
      setEditingId(null);
      setMessage("已封存醫療紀錄");
      await load();
    } catch (archiveError) {
      setError(
        archiveError instanceof Error
          ? archiveError.message
          : "醫療紀錄封存失敗",
      );
    } finally {
      setBusy(false);
    }
  }

  const emptyMessage = useMemo(() => {
    if (search || filterType) return "找不到符合條件的醫療紀錄。";
    return includeArchived
      ? "目前沒有醫療紀錄。"
      : "目前沒有未封存的醫療紀錄。";
  }, [filterType, includeArchived, search]);

  return (
    <section className="panel ui-card" aria-labelledby="medical-history-title">
      <div className="section-heading">
        <div>
          <h2 id="medical-history-title">醫療歷史</h2>
          <p className="muted">保留實際發生時間與人工輸入內容，供後續查詢。</p>
        </div>
        <Badge>{items.length} 筆</Badge>
      </div>

      <form className="stack-sm" onSubmit={submit}>
        <div className="toolbar">
          <Field>
            <label htmlFor="medical-occurred">發生時間</label>
            <Input
              id="medical-occurred"
              type="datetime-local"
              value={occurredAt}
              onChange={(event) => setOccurredAt(event.target.value)}
            />
          </Field>
          <Field>
            <label htmlFor="medical-type">類型</label>
            <Select
              id="medical-type"
              value={recordType}
              onChange={(event) => setRecordType(event.target.value)}
            >
              {Object.entries(recordTypeLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="toolbar">
          <Field>
            <label htmlFor="medical-title">標題</label>
            <Input
              id="medical-title"
              required
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </Field>
          <Field>
            <label htmlFor="medical-weight">體重（公斤，選填）</label>
            <Input
              id="medical-weight"
              type="number"
              min="0.001"
              step="0.001"
              value={weight}
              onChange={(event) => setWeight(event.target.value)}
            />
          </Field>
        </div>
        <div className="toolbar">
          <Field>
            <label htmlFor="medical-clinic">診所（選填）</label>
            <Input
              id="medical-clinic"
              value={clinic}
              onChange={(event) => setClinic(event.target.value)}
            />
          </Field>
          <Field>
            <label htmlFor="medical-veterinarian">獸醫（選填）</label>
            <Input
              id="medical-veterinarian"
              value={veterinarian}
              onChange={(event) => setVeterinarian(event.target.value)}
            />
          </Field>
        </div>
        <Field>
          <label htmlFor="medical-content">內容</label>
          <Textarea
            id="medical-content"
            required
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
        </Field>
        <p className="muted">
          內容為管理員人工輸入；體重只保存紀錄，不會自動計算或調整藥量。
        </p>
        <Button type="submit" disabled={busy}>
          {busy ? "儲存中…" : "新增醫療紀錄"}
        </Button>
      </form>

      <div className="toolbar" aria-label="醫療歷史篩選">
        <Field>
          <label htmlFor="medical-search">搜尋標題或內容</label>
          <Input
            id="medical-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </Field>
        <Field>
          <label htmlFor="medical-filter-type">篩選類型</label>
          <Select
            id="medical-filter-type"
            value={filterType}
            onChange={(event) => setFilterType(event.target.value)}
          >
            <option value="">全部類型</option>
            {Object.entries(recordTypeLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(event) => setIncludeArchived(event.target.checked)}
          />
          顯示已封存
        </label>
      </div>

      <p className="muted" role="status" aria-live="polite">
        {loading ? "正在載入醫療歷史…" : message}
      </p>
      {error ? (
        <div className="notice error" role="alert">
          {error}
          <Button type="button" variant="secondary" onClick={() => void load()}>
            重新載入
          </Button>
        </div>
      ) : null}
      {!loading && !error && items.length === 0 ? <p>{emptyMessage}</p> : null}

      <div className="stack-sm">
        {items.map((item) => (
          <article className="list-card" key={item.id}>
            {editingId === item.id ? (
              <div className="stack-sm">
                <Field>
                  <label htmlFor={`medical-edit-title-${item.id}`}>標題</label>
                  <Input
                    id={`medical-edit-title-${item.id}`}
                    value={editTitle}
                    onChange={(event) => setEditTitle(event.target.value)}
                  />
                </Field>
                <Field>
                  <label htmlFor={`medical-edit-content-${item.id}`}>
                    內容
                  </label>
                  <Textarea
                    id={`medical-edit-content-${item.id}`}
                    value={editContent}
                    onChange={(event) => setEditContent(event.target.value)}
                  />
                </Field>
                <Field>
                  <label htmlFor={`medical-reason-${item.id}`}>
                    修改或封存原因
                  </label>
                  <Input
                    id={`medical-reason-${item.id}`}
                    required
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                  />
                </Field>
                <div className="cluster">
                  <Button
                    type="button"
                    disabled={busy}
                    onClick={() => void saveEdit(item)}
                  >
                    儲存修改
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    disabled={busy}
                    onClick={() => void archive(item)}
                  >
                    封存紀錄
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setEditingId(null)}
                  >
                    取消
                  </Button>
                </div>
              </div>
            ) : (
              <div>
                <div className="section-heading">
                  <strong>{item.title}</strong>
                  <Badge>
                    {item.status === "archived" ? "已封存" : "有效"}
                  </Badge>
                </div>
                <p>{item.content}</p>
                <small>
                  {localDate(item.occurred_at, item.occurred_timezone)} ·{" "}
                  {recordTypeLabels[item.record_type] ?? "其他"}
                  {item.weight_kg != null ? ` · ${item.weight_kg} 公斤` : ""}
                  {item.clinic ? ` · ${item.clinic}` : ""}
                </small>
                {item.status === "active" ? (
                  <div>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => beginEdit(item)}
                    >
                      修改／封存
                    </Button>
                  </div>
                ) : null}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
