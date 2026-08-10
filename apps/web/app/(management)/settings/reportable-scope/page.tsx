"use client";

import { FormEvent, useEffect, useState } from "react";
import { authFetch } from "../../../../lib/auth";
import {
  ErrorState,
  LoadingState,
} from "../../../../components/management/StateViews";

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
    <main aria-labelledby="scope-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">REPORTABLE SCOPE</span>
          <h1 id="scope-title">可回報範圍</h1>
          <p>限制志工今天可看到的動物、Cage／Area 與指定帳號。</p>
        </div>
      </div>
      {message ? (
        <p className="notice success" role="status">
          {message}
        </p>
      ) : null}
      {error ? <ErrorState title="操作無法完成" description={error} /> : null}
      <section className="panel">
        <h2>建立範圍</h2>
        <form className="form-grid" onSubmit={create}>
          <div className="field">
            <label htmlFor="scope-animal">Animal ID（可選）</label>
            <input
              id="scope-animal"
              value={animalId}
              onChange={(event) => setAnimalId(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="scope-area">Cage／Area ID（可選）</label>
            <input
              id="scope-area"
              value={areaId}
              onChange={(event) => setAreaId(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="scope-volunteer">
              指定 Volunteer User ID（可選）
            </label>
            <input
              id="scope-volunteer"
              value={volunteerUserId}
              onChange={(event) => setVolunteerUserId(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="scope-start">開始時間</label>
            <input
              id="scope-start"
              type="datetime-local"
              value={startsAt}
              onChange={(event) => setStartsAt(event.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="scope-end">結束時間</label>
            <input
              id="scope-end"
              type="datetime-local"
              value={endsAt}
              onChange={(event) => setEndsAt(event.target.value)}
              required
            />
          </div>
          <div>
            <button className="button" type="submit">
              建立可回報範圍
            </button>
          </div>
        </form>
      </section>
      <section className="panel">
        <h2>目前範圍</h2>
        {loading ? (
          <LoadingState title="正在載入範圍…" />
        ) : items.length === 0 ? (
          <p className="muted">目前沒有設定。</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>目標</th>
                  <th>有效期間</th>
                  <th>狀態</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((scope) => (
                  <tr key={scope.id}>
                    <td>
                      {scope.animal_id
                        ? `Animal ${scope.animal_id.slice(0, 8)}`
                        : scope.area_id
                          ? `Area ${scope.area_id.slice(0, 8)}`
                          : "未指定目標"}
                    </td>
                    <td>
                      {new Date(scope.starts_at).toLocaleString("zh-TW")} —{" "}
                      {new Date(scope.ends_at).toLocaleString("zh-TW")}
                    </td>
                    <td>
                      <span className="badge">{scope.status}</span>
                    </td>
                    <td>
                      <button
                        className="button button-secondary"
                        type="button"
                        disabled={scope.status !== "active"}
                        onClick={() => void deactivate(scope)}
                      >
                        停用
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
