"use client";

import React, { useRef, useState } from "react";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import { authFetch } from "../../lib/auth";
import {
  animalAgeLabel,
  animalSexLabel,
  profileDateLabel,
  type AnimalProfileUpdate,
  type ManagementAnimal,
} from "../../lib/animal-profile";
import styles from "./animal-profile.module.css";
import { AnimalPhoto } from "./AnimalPhoto";

export function AnimalBasicProfile({
  animal,
  onSaved,
}: {
  animal: ManagementAnimal;
  onSaved: (animal: ManagementAnimal) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const editButton = useRef<HTMLButtonElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);

  function finish() {
    setEditing(false);
    requestAnimationFrame(() => editButton.current?.focus());
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const nullable = (name: string) =>
      String(data.get(name) ?? "").trim() || null;
    const payload: AnimalProfileUpdate = {
      sex: data.get("sex") as AnimalProfileUpdate["sex"],
      breed: nullable("breed"),
      intake_date: nullable("intake_date"),
      birth_date: nullable("birth_date"),
      birth_date_estimated: data.get("birth_date_estimated") === "on",
      age_description: nullable("age_description"),
      behavior_notes: nullable("behavior_notes"),
      care_guidance: nullable("care_guidance"),
    };
    setError("");
    setBusy(true);
    try {
      if (
        payload.birth_date &&
        payload.intake_date &&
        payload.birth_date > payload.intake_date
      )
        throw new Error("出生日期不得晚於入園日期。");
      if (payload.birth_date_estimated && !payload.birth_date)
        throw new Error("請填寫估計的出生日期，或取消估計值勾選。");
      const response = await authFetch(
        `/v1/management/animals/${animal.id}/profile`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(
          body?.message || "基本資料儲存失敗，請確認欄位或稍後重試。",
        );
      }
      const result = (await response.json()) as { animal: ManagementAnimal };
      onSaved(result.animal);
      setSaved(true);
      finish();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "基本資料儲存失敗。");
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="ui-card-padded" aria-labelledby="animal-basic-title">
      <div className="animal-profile-section-heading">
        <h2 id="animal-basic-title">基本資料</h2>
        <Button
          ref={editButton}
          type="button"
          variant="secondary"
          hidden={editing}
          onClick={() => {
            setEditing(true);
            setSaved(false);
            setError("");
          }}
        >
          編輯基本資料
        </Button>
      </div>
      {saved && <p role="status">基本資料已儲存</p>}
      {editing ? (
        <form onSubmit={save} aria-label="編輯動物基本資料">
          {error && (
            <p role="alert" tabIndex={-1} ref={errorRef}>
              {error}
            </p>
          )}
          <fieldset disabled={busy} className={styles.formFields}>
            <legend className="sr-only">動物基本資料</legend>
            <Field>
              <label htmlFor="profile-sex">性別</label>
              <Select
                id="profile-sex"
                name="sex"
                defaultValue={animal.sex ?? "unknown"}
                autoFocus
              >
                <option value="unknown">未知</option>
                <option value="male">公</option>
                <option value="female">母</option>
              </Select>
            </Field>
            <Field>
              <label htmlFor="profile-breed">品種</label>
              <Input
                id="profile-breed"
                name="breed"
                defaultValue={animal.breed ?? ""}
                maxLength={120}
              />
            </Field>
            <Field>
              <label htmlFor="profile-intake">入園日期</label>
              <Input
                id="profile-intake"
                name="intake_date"
                type="date"
                defaultValue={animal.intake_date ?? ""}
              />
            </Field>
            <Field>
              <label htmlFor="profile-birth">出生日期</label>
              <Input
                id="profile-birth"
                name="birth_date"
                type="date"
                defaultValue={animal.birth_date ?? ""}
              />
            </Field>
            <label className={styles.fullWidth}>
              <input
                name="birth_date_estimated"
                type="checkbox"
                defaultChecked={animal.birth_date_estimated}
              />{" "}
              出生日期為估計值
            </label>
            <Field className={styles.fullWidth}>
              <label htmlFor="profile-age">年齡描述</label>
              <Input
                id="profile-age"
                name="age_description"
                defaultValue={animal.age_description ?? ""}
                maxLength={120}
                aria-describedby="profile-age-hint"
              />
              <small id="profile-age-hint">
                僅在未填出生日期時顯示，例如「5歲以上」；不要推測出生日期。
              </small>
            </Field>
            <Field className={styles.fullWidth}>
              <label htmlFor="profile-behavior">個性與行為</label>
              <Textarea
                id="profile-behavior"
                name="behavior_notes"
                defaultValue={animal.behavior_notes ?? ""}
                maxLength={4000}
                rows={4}
                aria-describedby="profile-behavior-hint"
              />
              <small id="profile-behavior-hint">
                僅管理端可見的描述，不是醫療紀錄。
              </small>
            </Field>
            <Field className={styles.fullWidth}>
              <label htmlFor="profile-care">照護提醒</label>
              <Textarea
                id="profile-care"
                name="care_guidance"
                defaultValue={animal.care_guidance ?? ""}
                maxLength={4000}
                rows={4}
                aria-describedby="profile-care-hint"
              />
              <small id="profile-care-hint">
                會顯示於志工確認卡，請只填寫可公開的安全操作指引。
              </small>
            </Field>
          </fieldset>
          <div className="toolbar">
            <Button type="submit" disabled={busy}>
              {busy ? "儲存中…" : "儲存基本資料"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={finish}
            >
              取消
            </Button>
          </div>
        </form>
      ) : (
        <>
          {animal.photo_url && (
            <AnimalPhoto
              className={styles.portrait}
              photoUrl={animal.photo_url}
              alt={`${animal.name} 的照片`}
            />
          )}
          <dl className={`detail-list ${styles.facts}`}>
            <div>
              <dt>名稱</dt>
              <dd>{animal.name}</dd>
            </div>
            <div>
              <dt>收容編號</dt>
              <dd>{animal.shelter_number ?? "未提供"}</dd>
            </div>
            <div>
              <dt>性別</dt>
              <dd>{animalSexLabel(animal.sex)}</dd>
            </div>
            <div>
              <dt>品種</dt>
              <dd>{animal.breed ?? "未提供"}</dd>
            </div>
            <div>
              <dt>入園日期</dt>
              <dd>{profileDateLabel(animal.intake_date)}</dd>
            </div>
            <div>
              <dt>年齡</dt>
              <dd>{animalAgeLabel(animal)}</dd>
            </div>
            {animal.birth_date && (
              <div>
                <dt>出生日期</dt>
                <dd>
                  {profileDateLabel(animal.birth_date)}
                  {animal.birth_date_estimated ? "（估計）" : ""}
                </dd>
              </div>
            )}
            <div>
              <dt>區域</dt>
              <dd>{animal.area_path ?? animal.area_name ?? "未分配"}</dd>
            </div>
          </dl>
          <section className={styles.notes}>
            <h3>個性與行為</h3>
            <p>{animal.behavior_notes ?? "尚未提供個性與行為描述。"}</p>
          </section>
          <section
            className={animal.care_guidance ? styles.careWarning : styles.notes}
          >
            <h3>
              <span aria-hidden="true">⚠ </span>照護提醒
            </h3>
            <p>
              {animal.care_guidance ?? "尚未提供特別指引，互動前請依現場安排。"}
            </p>
          </section>
        </>
      )}
    </Card>
  );
}
