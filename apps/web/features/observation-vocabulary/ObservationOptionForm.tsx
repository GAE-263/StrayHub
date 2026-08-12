import React, { FormEvent, useEffect, useState } from "react";
import {
  Category,
  categoryLabel,
  ObservationOption,
} from "./observationVocabulary";

type FormValue = {
  category_id: string;
  code: string;
  display_name: string;
  description: string;
  display_order: string;
  requires_note: boolean;
};

type Props = {
  categories: Category[];
  option?: ObservationOption | null;
  onSubmit: (value: FormValue) => Promise<void>;
  onCancel: () => void;
};

const emptyValue: FormValue = {
  category_id: "",
  code: "",
  display_name: "",
  description: "",
  display_order: "0",
  requires_note: false,
};

export function ObservationOptionForm({
  categories,
  option,
  onSubmit,
  onCancel,
}: Props) {
  const [value, setValue] = useState<FormValue>(emptyValue);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setValue(
      option
        ? {
            category_id: option.category_id,
            code: option.code,
            display_name: option.display_name,
            description: option.description,
            display_order: String(option.display_order),
            requires_note: option.requires_note,
          }
        : { ...emptyValue, category_id: categories[0]?.id ?? "" },
    );
  }, [categories, option]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onCancel, saving]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!value.display_name.trim()) {
      setError("請輸入中文名稱。");
      return;
    }
    const order = Number(value.display_order);
    if (!Number.isInteger(order) || order < 0) {
      setError("排序必須是 0 或以上的整數。");
      return;
    }
    if (!/^[a-z][a-z0-9_.]*$/.test(value.code.trim())) {
      setError(
        "stable code 必須以小寫英文字母開頭，只能使用小寫英文字母、數字、底線或句點。",
      );
      return;
    }
    setSaving(true);
    try {
      await onSubmit(value);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "儲存失敗，請稍後再試。",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="presentation">
      <dialog
        className="observation-dialog"
        open
        aria-modal="true"
        aria-labelledby="observation-form-title"
      >
        <div className="panel-heading">
          <h2 id="observation-form-title">
            {option ? "編輯觀察選項" : "新增選項"}
          </h2>
          <button
            className="button button-quiet"
            type="button"
            onClick={onCancel}
          >
            取消
          </button>
        </div>
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="option-category">觀察類別</label>
            <select
              id="option-category"
              value={value.category_id}
              disabled={Boolean(option)}
              onChange={(event) =>
                setValue({ ...value, category_id: event.target.value })
              }
              required
            >
              <option value="">請選擇類別</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {categoryLabel(category)}（{category.code}）
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="option-code">stable code</label>
            <input
              id="option-code"
              value={value.code}
              maxLength={120}
              readOnly={Boolean(option?.has_historical_usage)}
              onChange={(event) =>
                setValue({ ...value, code: event.target.value })
              }
              aria-describedby="option-code-help"
              required
            />
            <span id="option-code-help" className="field-help">
              使用小寫英文字母、數字、底線或句點；已有歷史回報使用的 code
              會鎖定。
            </span>
          </div>
          <div className="field">
            <label htmlFor="option-display-name">中文名稱</label>
            <input
              id="option-display-name"
              value={value.display_name}
              maxLength={200}
              onChange={(event) =>
                setValue({ ...value, display_name: event.target.value })
              }
              required
            />
          </div>
          <div className="field">
            <label htmlFor="option-description">說明</label>
            <textarea
              id="option-description"
              value={value.description}
              maxLength={500}
              onChange={(event) =>
                setValue({ ...value, description: event.target.value })
              }
            />
          </div>
          <div className="form-grid form-grid-compact">
            <div className="field">
              <label htmlFor="option-order">排序</label>
              <input
                id="option-order"
                type="number"
                min="0"
                value={value.display_order}
                onChange={(event) =>
                  setValue({ ...value, display_order: event.target.value })
                }
              />
            </div>
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={value.requires_note}
                onChange={(event) =>
                  setValue({ ...value, requires_note: event.target.checked })
                }
              />
              是否需要補充說明
            </label>
          </div>
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="dialog-actions">
            <button
              className="button button-secondary"
              type="button"
              onClick={onCancel}
            >
              取消
            </button>
            <button className="button" type="submit" disabled={saving}>
              {saving ? "儲存中…" : "儲存"}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
}

export type { FormValue };
