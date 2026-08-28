"use client";

import { FormEvent, useEffect, useState } from "react";
import { Dialog } from "../../components/ui/dialog";
import { Button } from "../../components/ui/button";
import { Field } from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { Textarea } from "../../components/ui/textarea";
import { Checkbox } from "../../components/ui/checkbox";
import { Alert } from "../../components/ui/alert";
import { authFetch } from "../../lib/auth";

export type AdoptionProfile = {
  species: string | null;
  breed: string | null;
  size: string | null;
  energy: string | null;
  temperament: string[];
  is_adoptable: boolean;
  adoption_notes: string | null;
};

export function AdoptionProfileFormDialog({
  open,
  animalId,
  initial,
  onClose,
  onSaved,
}: {
  open: boolean;
  animalId: string;
  initial: AdoptionProfile;
  onClose: () => void;
  onSaved?: (message: string) => void;
}) {
  const [species, setSpecies] = useState(initial.species ?? "");
  const [breed, setBreed] = useState(initial.breed ?? "");
  const [size, setSize] = useState(initial.size ?? "");
  const [energy, setEnergy] = useState(initial.energy ?? "");
  const [temperament, setTemperament] = useState(
    initial.temperament.join("、"),
  );
  const [isAdoptable, setIsAdoptable] = useState(initial.is_adoptable);
  const [adoptionNotes, setAdoptionNotes] = useState(
    initial.adoption_notes ?? "",
  );
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSpecies(initial.species ?? "");
    setBreed(initial.breed ?? "");
    setSize(initial.size ?? "");
    setEnergy(initial.energy ?? "");
    setTemperament(initial.temperament.join("、"));
    setIsAdoptable(initial.is_adoptable);
    setAdoptionNotes(initial.adoption_notes ?? "");
    setMessage("");
  }, [open, initial]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    setBusy(true);
    try {
      const response = await authFetch(
        `/v1/management/animals/${animalId}/adoption-profile`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            species: species.trim() || null,
            breed: breed.trim() || null,
            size: size || null,
            energy: energy || null,
            temperament: temperament
              .split(/[、,]/)
              .map((item) => item.trim())
              .filter(Boolean),
            is_adoptable: isAdoptable,
            adoption_notes: adoptionNotes.trim() || null,
          }),
        },
      );
      if (!response.ok)
        throw new Error(`領養資料儲存失敗（HTTP ${response.status}）`);
    } catch {
      setMessage("領養資料儲存失敗，請檢查權限與欄位。");
      setBusy(false);
      return;
    }
    setBusy(false);
    onSaved?.("領養資料已更新");
    onClose();
  }

  return (
    <Dialog open={open} title="編輯領養資料" onClose={onClose}>
      <form className="stack-sm" onSubmit={submit}>
        <div className="toolbar">
          <Field>
            <label htmlFor="adoption-species">物種</label>
            <Input
              id="adoption-species"
              value={species}
              onChange={(e) => setSpecies(e.target.value)}
              placeholder="例如：狗"
            />
          </Field>
          <Field>
            <label htmlFor="adoption-breed">品種</label>
            <Input
              id="adoption-breed"
              value={breed}
              onChange={(e) => setBreed(e.target.value)}
              placeholder="例如：米克斯"
            />
          </Field>
        </div>
        <div className="toolbar">
          <Field>
            <label htmlFor="adoption-size">體型</label>
            <Select
              id="adoption-size"
              value={size}
              onChange={(e) => setSize(e.target.value)}
            >
              <option value="">未設定</option>
              <option value="small">小型</option>
              <option value="medium">中型</option>
              <option value="large">大型</option>
            </Select>
          </Field>
          <Field>
            <label htmlFor="adoption-energy">活動力</label>
            <Select
              id="adoption-energy"
              value={energy}
              onChange={(e) => setEnergy(e.target.value)}
            >
              <option value="">未設定</option>
              <option value="low">文靜</option>
              <option value="medium">適中</option>
              <option value="high">活潑好動</option>
            </Select>
          </Field>
        </div>
        <Field>
          <label htmlFor="adoption-temperament">個性標籤（以頓號或逗號分隔）</label>
          <Input
            id="adoption-temperament"
            value={temperament}
            onChange={(e) => setTemperament(e.target.value)}
            placeholder="例如：親人、親貓、適合有小孩的家庭"
          />
        </Field>
        <Field>
          <label className="checkbox-label" htmlFor="adoption-is-adoptable">
            <Checkbox
              id="adoption-is-adoptable"
              checked={isAdoptable}
              onChange={(e) => setIsAdoptable(e.target.checked)}
            />
            開放領養媒合（勾選後才會出現在領養媒合的動物清單／推薦名單中）
          </label>
        </Field>
        <Field>
          <label htmlFor="adoption-notes">領養備註</label>
          <Textarea
            id="adoption-notes"
            value={adoptionNotes}
            onChange={(e) => setAdoptionNotes(e.target.value)}
            placeholder="給工作人員或領養人參考的補充說明"
          />
        </Field>
        <Button type="submit" disabled={busy}>
          儲存領養資料
        </Button>
        {message ? <Alert role="alert">{message}</Alert> : null}
      </form>
    </Dialog>
  );
}
