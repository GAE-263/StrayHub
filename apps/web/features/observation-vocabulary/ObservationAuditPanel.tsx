import React, { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";
import { Alert } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { ObservationOption } from "./observationVocabulary";

type AuditRecord = {
  id: string;
  organization_id: string;
  actor_user_id: string;
  operation_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  source_channel: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reason: string | null;
  result: string;
  created_at: string;
};

type Props = { option: ObservationOption; onClose: () => void };

export function ObservationAuditPanel({ option, onClose }: Props) {
  const [items, setItems] = useState<AuditRecord[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await authFetch(
        `/v1/management/audit?resource_type=ObservationOption&resource_id=${option.id}`,
      );
      if (!response.ok) throw new Error("變更紀錄載入失敗，請重新載入。");
      setItems(((await response.json()) as { items: AuditRecord[] }).items);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "變更紀錄載入失敗。",
      );
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, [option.id]);
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);
  return (
    <Dialog
      open
      title={`變更紀錄：${option.display_name}`}
      onClose={onClose}
      className="p1-audit-dialog"
    >
      <p className="muted">只顯示目前收容所此自訂選項的唯讀紀錄。</p>
      {loading ? <p role="status">正在載入變更紀錄…</p> : null}
      {error ? (
        <Alert role="alert">
          <strong>{error}</strong>
          <Button variant="secondary" type="button" onClick={() => void load()}>
            重新載入
          </Button>
        </Alert>
      ) : null}
      {!loading && !error && items.length === 0 ? (
        <p className="muted">目前沒有變更紀錄。</p>
      ) : null}
      {!loading && !error && items.length > 0 ? (
        <Table>
          <TableHeader>
            <tr>
              <TableHead>時間</TableHead>
              <TableHead>操作</TableHead>
              <TableHead>操作者</TableHead>
              <TableHead>結果</TableHead>
              <TableHead>變更內容</TableHead>
            </tr>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>
                  {new Date(item.created_at).toLocaleString("zh-TW")}
                </TableCell>
                <TableCell>{item.action}</TableCell>
                <TableCell>{item.actor_user_id}</TableCell>
                <TableCell>
                  {item.result === "success" ? "成功" : item.result}
                </TableCell>
                <TableCell>
                  <details>
                    <summary>查看前後內容</summary>
                    <pre>
                      {JSON.stringify(
                        { before: item.before, after: item.after },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
    </Dialog>
  );
}
