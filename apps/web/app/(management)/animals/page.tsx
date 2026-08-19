"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { authFetch } from "../../../lib/auth";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PermissionDeniedState,
} from "../../../components/management/StateViews";
import { statusLabel } from "../../../components/management/ui-status";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Field } from "../../../components/ui/field";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import { Table } from "../../../components/ui/table";
import { buildAnimalsQuery } from "../management-query";

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
  const [permissionDenied, setPermissionDenied] = useState(false);
  const latestRequest = useRef(0);

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
    const requestId = ++latestRequest.current;
    const params = buildAnimalsQuery({ page, query, status, areaId });
    setLoading(true);
    setError("");
    setPermissionDenied(false);
    void authFetch(`/v1/management/animals?${params}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 403) {
          if (requestId !== latestRequest.current) return;
          setData(null);
          setPermissionDenied(true);
          return;
        }
        if (!response.ok)
          throw new Error(`動物清單載入失敗（HTTP ${response.status}）`);
        const nextData = (await response.json()) as ListResponse;
        if (requestId === latestRequest.current) setData(nextData);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setError(
            requestError instanceof Error
              ? requestError.message
              : "動物清單載入失敗",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted && requestId === latestRequest.current)
          setLoading(false);
      });
    return () => controller.abort();
  }, [areaId, page, query, status]);

  return (
    <section aria-labelledby="animals-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">ANIMAL DIRECTORY</span>
          <h1 id="animals-title">動物檔案</h1>
          <p>搜尋名稱、收容編號與 Cage／Area，進入完整照護歷程。</p>
        </div>
      </div>
      <section className="ui-card ui-card-padded">
        <div className="toolbar" aria-label="動物清單篩選">
          <Field>
            <label htmlFor="animal-query">搜尋</label>
            <Input
              id="animal-query"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder="名稱或收容編號"
            />
          </Field>
          <Field>
            <label htmlFor="animal-area">Cage／Area</label>
            <Select
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
            </Select>
          </Field>
          <Field>
            <label htmlFor="animal-status">狀態</label>
            <Select
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
            </Select>
          </Field>
        </div>
        {loading ? <LoadingState title="正在載入動物清單…" /> : null}
        {permissionDenied ? (
          <PermissionDeniedState description="請切換到已授權收容所，或聯絡收容所管理者。" />
        ) : null}
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
          <Table>
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
                    <Link className="text-link" href={`/animals/${animal.id}`}>
                      {animal.name}
                    </Link>
                  </td>
                  <td>{animal.shelter_number}</td>
                  <td>{animal.area_name ?? "未分配"}</td>
                  <td>
                    <Badge>{statusLabel(animal.status)}</Badge>
                  </td>
                  <td>
                    <Link
                      className="text-link"
                      href={`/animals/${animal.id}/timeline`}
                    >
                      近期歷程 →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : null}
        {data && data.total > data.page_size ? (
          <div className="toolbar pagination">
            <Button
              variant="secondary"
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              上一頁
            </Button>
            <span className="muted">
              第 {data.page} 頁，共 {data.total} 筆
            </span>
            <Button
              variant="secondary"
              type="button"
              disabled={page * data.page_size >= data.total}
              onClick={() => setPage((value) => value + 1)}
            >
              下一頁
            </Button>
          </div>
        ) : null}
      </section>
    </section>
  );
}
