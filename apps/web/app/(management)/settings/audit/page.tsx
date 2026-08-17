"use client";

import { useEffect, useState } from "react";
import { authFetch } from "../../../../lib/auth";
import {
  EmptyState,
  LoadingState,
} from "../../../../components/management/StateViews";
import { Alert } from "../../../../components/ui/alert";
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
      <Card>
        <CardHeader>
          <CardTitle>唯讀查詢條件</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="p1-form-grid">
            <Field>
              <label htmlFor="audit-action">Action</label>
              <Input
                id="audit-action"
                value={action}
                onChange={(event) => setAction(event.target.value)}
                placeholder="例如 care_report.corrected"
              />
            </Field>
            <Field>
              <label htmlFor="audit-resource">Resource type</label>
              <Input
                id="audit-resource"
                value={resourceType}
                onChange={(event) => setResourceType(event.target.value)}
                placeholder="例如 CareReport"
              />
            </Field>
          </div>
          {loading ? (
            <LoadingState title="正在查詢 Audit…" />
          ) : error ? (
            <Alert role="alert">{error}</Alert>
          ) : items.length === 0 ? (
            <EmptyState title="目前沒有符合條件的 Audit" />
          ) : (
            <Table>
              <TableHeader>
                <tr>
                  <TableHead>時間</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>資源</TableHead>
                  <TableHead>操作者</TableHead>
                  <TableHead>原因</TableHead>
                </tr>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      {new Date(item.created_at).toLocaleString("zh-TW")}
                    </TableCell>
                    <TableCell>{item.action}</TableCell>
                    <TableCell>
                      {item.resource_type} {item.resource_id?.slice(0, 8)}
                    </TableCell>
                    <TableCell>
                      {item.actor_user_id?.slice(0, 8) ?? "system"}
                    </TableCell>
                    <TableCell>{item.reason ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
