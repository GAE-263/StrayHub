import React, { useEffect, useRef, useState } from "react";
import { authFetch } from "../../lib/auth";
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
  const closeRef = useRef<HTMLButtonElement>(null);
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
    closeRef.current?.focus();
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
    <div className="dialog-backdrop" role="presentation">
      <dialog
        className="observation-dialog observation-audit-panel"
        open
        aria-modal="true"
        aria-labelledby="audit-panel-title"
      >
        <div className="panel-heading">
          <div>
            <h2 id="audit-panel-title">變更紀錄：{option.display_name}</h2>
            <p className="muted">只顯示目前收容所此自訂選項的唯讀紀錄。</p>
          </div>
          <button
            ref={closeRef}
            className="button button-quiet"
            type="button"
            onClick={onClose}
          >
            關閉
          </button>
        </div>
        {loading ? <p role="status">正在載入變更紀錄…</p> : null}
        {error ? (
          <div className="state-card error-state" role="alert">
            <strong>{error}</strong>
            <button
              className="button button-secondary"
              type="button"
              onClick={() => void load()}
            >
              重新載入
            </button>
          </div>
        ) : null}
        {!loading && !error && items.length === 0 ? (
          <p className="muted">目前沒有變更紀錄。</p>
        ) : null}
        {!loading && !error && items.length > 0 ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>時間</th>
                  <th>操作</th>
                  <th>操作者</th>
                  <th>結果</th>
                  <th>變更內容</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{new Date(item.created_at).toLocaleString("zh-TW")}</td>
                    <td>{item.action}</td>
                    <td>{item.actor_user_id}</td>
                    <td>{item.result === "success" ? "成功" : item.result}</td>
                    <td>
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
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </dialog>
    </div>
  );
}
