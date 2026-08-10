"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { authFetch } from "../../../lib/auth";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../../components/management/StateViews";

type Animal = {
  id: string;
  name: string;
  shelter_number: string;
  status: string;
  area_name: string | null;
  area_type: string | null;
};

type ListResponse = {
  items: Animal[];
  page: number;
  page_size: number;
  total: number;
};

export default function AnimalsPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("active");
  const [areaId, setAreaId] = useState("");
  const [areas, setAreas] = useState<
    Array<{ id: string; name: string; area_type: string }>
  >([]);
  const [data, setData] = useState<ListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const organizationId =
      typeof window !== "undefined"
        ? window.sessionStorage.getItem("active_organization_id")
        : null;
    if (!organizationId) return;
    void authFetch(`/v1/organizations/${organizationId}/areas`)
      .then((response) => (response.ok ? response.json() : { items: [] }))
      .then(
        (value: {
          items: Array<{ id: string; name: string; area_type: string }>;
        }) => setAreas(value.items),
      )
      .catch(() => setAreas([]));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      page: String(page),
      page_size: "20",
      status,
    });
    if (query.trim()) params.set("query", query.trim());
    if (areaId) params.set("area_id", areaId);
    setLoading(true);
    setError("");
    void authFetch(`/v1/management/animals?${params}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`動物清單載入失敗（HTTP ${response.status}）`);
        setData((await response.json()) as ListResponse);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "動物清單載入失敗",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [areaId, page, query, status]);

  return (
    <main aria-labelledby="animals-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">ANIMAL DIRECTORY</span>
          <h1 id="animals-title">動物檔案</h1>
          <p>搜尋名稱、收容編號與 Cage／Area，進入完整照護歷程。</p>
        </div>
      </div>
      <section className="panel">
        <div className="toolbar" aria-label="動物清單篩選">
          <div className="field">
            <label htmlFor="animal-query">搜尋</label>
            <input
              id="animal-query"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder="名稱或收容編號"
            />
          </div>
          <div className="field">
            <label htmlFor="animal-area">Cage／Area</label>
            <select
              id="animal-area"
              value={areaId}
              onChange={(event) => {
                setAreaId(event.target.value);
                setPage(1);
              }}
            >
              <option value="">全部區域</option>
              {areas.map((area) => (
                <option key={area.id} value={area.id}>
                  {area.name}（{area.area_type}）
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="animal-status">狀態</label>
            <select
              id="animal-status"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
            >
              <option value="active">啟用中</option>
              <option value="inactive">已停用</option>
              <option value="all">全部</option>
            </select>
          </div>
        </div>
        {loading ? <LoadingState title="正在載入動物清單…" /> : null}
        {error ? (
          <ErrorState title="無法載入動物清單" description={error} />
        ) : null}
        {!loading && !error && data?.items.length === 0 ? (
          <EmptyState
            title="找不到符合條件的動物"
            description="請調整搜尋或篩選條件。"
          />
        ) : null}
        {!loading && !error && data?.items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>名稱</th>
                  <th>收容編號</th>
                  <th>Cage／Area</th>
                  <th>狀態</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((animal) => (
                  <tr key={animal.id}>
                    <td>
                      <Link
                        className="text-link"
                        href={`/animals/${animal.id}`}
                      >
                        {animal.name}
                      </Link>
                    </td>
                    <td>{animal.shelter_number}</td>
                    <td>{animal.area_name ?? "未分配"}</td>
                    <td>
                      <span className="badge">{animal.status}</span>
                    </td>
                    <td>
                      <Link
                        className="text-link"
                        href={`/animals/${animal.id}/timeline`}
                      >
                        Timeline →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {data && data.total > data.page_size ? (
          <div className="toolbar pagination">
            <button
              className="button button-secondary"
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              上一頁
            </button>
            <span className="muted">
              第 {data.page} 頁，共 {data.total} 筆
            </span>
            <button
              className="button button-secondary"
              type="button"
              disabled={page * data.page_size >= data.total}
              onClick={() => setPage((value) => value + 1)}
            >
              下一頁
            </button>
          </div>
        ) : null}
      </section>
    </main>
  );
}
