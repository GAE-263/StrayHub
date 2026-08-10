"use client";

import { useEffect, useState } from "react";
import { authFetch } from "../../../../lib/auth";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../../../components/management/StateViews";

type Audit = {
  id: string;
  actor_user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  reason: string | null;
  created_at: string;
};

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [items, setItems] = useState<Audit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const params = new URLSearchParams({ limit: "100" });
    if (action) params.set("action", action);
    if (resourceType) params.set("resource_type", resourceType);
    setLoading(true);
    void authFetch(`/v1/management/audit?${params}`)
      .then(async (response) => {
        if (!response.ok)
          throw new Error(`Audit Query 失敗（HTTP ${response.status}）`);
        setItems(((await response.json()) as { items: Audit[] }).items);
      })
      .catch((requestError: unknown) =>
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Audit Query 失敗",
        ),
      )
      .finally(() => setLoading(false));
  }, [action, resourceType]);
  return (
    <main aria-labelledby="audit-title">
      <div className="page-heading">
        <div>
          <span className="eyebrow">READ-ONLY AUDIT</span>
          <h1 id="audit-title">Audit Query</h1>
          <p>
            依目前 Scope
            追蹤操作者、資源、Action、原因與時間；此頁沒有修改或刪除操作。
          </p>
        </div>
      </div>
      <section className="panel">
        <div className="toolbar">
          <div className="field">
            <label htmlFor="audit-action">Action</label>
            <input
              id="audit-action"
              value={action}
              onChange={(event) => setAction(event.target.value)}
              placeholder="例如 care_report.corrected"
            />
          </div>
          <div className="field">
            <label htmlFor="audit-resource">Resource type</label>
            <input
              id="audit-resource"
              value={resourceType}
              onChange={(event) => setResourceType(event.target.value)}
              placeholder="例如 CareReport"
            />
          </div>
        </div>
        {loading ? (
          <LoadingState title="正在查詢 Audit…" />
        ) : error ? (
          <ErrorState title="無法查詢 Audit" description={error} />
        ) : items.length === 0 ? (
          <EmptyState title="目前沒有符合條件的 Audit" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>時間</th>
                  <th>Action</th>
                  <th>資源</th>
                  <th>操作者</th>
                  <th>原因</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{new Date(item.created_at).toLocaleString("zh-TW")}</td>
                    <td>{item.action}</td>
                    <td>
                      {item.resource_type} {item.resource_id?.slice(0, 8)}
                    </td>
                    <td>{item.actor_user_id?.slice(0, 8) ?? "system"}</td>
                    <td>{item.reason ?? "—"}</td>
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
