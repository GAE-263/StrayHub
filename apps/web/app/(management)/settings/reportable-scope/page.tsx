"use client";

import { FormEvent, useEffect, useState } from "react";
import { authFetch } from "../../../../lib/auth";
import { LoadingState } from "../../../../components/management/StateViews";
import { Alert } from "../../../../components/ui/alert";
import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../../../components/ui/card";
import { Field } from "../../../../components/ui/field";
import { Input } from "../../../../components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../../../components/ui/table";

type Scope = {
  id: string;
  animal_id: string | null;
  area_id: string | null;
  volunteer_user_id: string | null;
  starts_at: string;
  ends_at: string;
  status: string;
};

export default function ReportableScopePage() {
  const [items, setItems] = useState<Scope[]>([]);
  const [animalId, setAnimalId] = useState("");
  const [areaId, setAreaId] = useState("");
  const [volunteerUserId, setVolunteerUserId] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    void authFetch("/v1/management/reportable-scopes?include_inactive=true")
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`可回報範圍載入失敗（HTTP ${response.status}）`);
        setItems(((await response.json()) as { items: Scope[] }).items);
      })
      .catch((requestError: unknown) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "可回報範圍載入失敗",
        ),
      )
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const response = await authFetch("/v1/management/reportable-scopes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          animal_id: animalId || null,
          area_id: areaId || null,
          volunteer_user_id: volunteerUserId || null,
          starts_at: new Date(startsAt).toISOString(),
          ends_at: new Date(endsAt).toISOString(),
        }),
      });
      if (!response.ok) throw new Error(`建立失敗（HTTP ${response.status}）`);
      setMessage("可回報範圍已建立並寫入 Audit。");
      setAnimalId("");
      setAreaId("");
      setVolunteerUserId("");
      load();
    } catch (requestError: unknown) {
      setError(
        requestError instanceof Error ? requestError.message : "建立失敗",
      );
    }
  };

  const deactivate = async (scope: Scope) => {
    setError("");
    const response = await authFetch(
      `/v1/management/reportable-scopes/${scope.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "inactive" }),
      },
    );
    if (!response.ok) setError(`停用失敗（HTTP ${response.status}）`);
    else {
      setMessage("範圍已停用，歷史資料保留。");
      load();
    }
  };

  return (
    <section aria-labelledby="scope-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">REPORTABLE SCOPE</span>
          <h1 id="scope-title">可回報範圍</h1>
          <p>限制志工今天可看到的動物、Cage／Area 與指定帳號。</p>
        </div>
      </div>
      {message ? <Alert role="status">{message}</Alert> : null}
      {error ? <Alert role="alert">{error}</Alert> : null}
      <Card>
        <CardHeader>
          <CardTitle>建立範圍</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="p1-form-grid" onSubmit={create}>
            <Field>
              <label htmlFor="scope-animal">Animal ID（可選）</label>
              <Input
                id="scope-animal"
                value={animalId}
                onChange={(event) => setAnimalId(event.target.value)}
              />
            </Field>
            <Field>
              <label htmlFor="scope-area">Cage／Area ID（可選）</label>
              <Input
                id="scope-area"
                value={areaId}
                onChange={(event) => setAreaId(event.target.value)}
              />
            </Field>
            <Field>
              <label htmlFor="scope-volunteer">
                指定 Volunteer User ID（可選）
              </label>
              <Input
                id="scope-volunteer"
                value={volunteerUserId}
                onChange={(event) => setVolunteerUserId(event.target.value)}
              />
            </Field>
            <Field>
              <label htmlFor="scope-start">開始時間</label>
              <Input
                id="scope-start"
                type="datetime-local"
                value={startsAt}
                onChange={(event) => setStartsAt(event.target.value)}
                required
              />
            </Field>
            <Field>
              <label htmlFor="scope-end">結束時間</label>
              <Input
                id="scope-end"
                type="datetime-local"
                value={endsAt}
                onChange={(event) => setEndsAt(event.target.value)}
                required
              />
            </Field>
            <div>
              <Button type="submit">建立可回報範圍</Button>
            </div>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>目前範圍</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <LoadingState title="正在載入範圍…" />
          ) : items.length === 0 ? (
            <p className="muted">目前沒有設定。</p>
          ) : (
            <Table>
              <TableHeader>
                <tr>
                  <TableHead>目標</TableHead>
                  <TableHead>有效期間</TableHead>
                  <TableHead>狀態</TableHead>
                  <TableHead>操作</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {items.map((scope) => (
                  <TableRow key={scope.id}>
                    <TableCell>
                      {scope.animal_id
                        ? `Animal ${scope.animal_id.slice(0, 8)}`
                        : scope.area_id
                          ? `Area ${scope.area_id.slice(0, 8)}`
                          : "未指定目標"}
                    </TableCell>
                    <TableCell>
                      {new Date(scope.starts_at).toLocaleString("zh-TW")} —{" "}
                      {new Date(scope.ends_at).toLocaleString("zh-TW")}
                    </TableCell>
                    <TableCell>
                      <Badge>{scope.status}</Badge>
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="secondary"
                        type="button"
                        disabled={scope.status !== "active"}
                        onClick={() => void deactivate(scope)}
                      >
                        停用
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
