"use client";

import React, { useMemo, useRef, useState } from "react";

import { formatTaiwanDateTime } from "./volunteerAccess";

export type NotificationFailure = {
  id: string;
  recipient_display_name: string;
  event_type: string;
  status: "retry_wait" | "failed";
  attempt_count: number;
  last_error_code?: string | null;
  last_failed_at?: string | null;
};

export function NotificationFailureQueue({
  notifications,
  nextCursor,
  onRetry,
  onLoadMore,
}: {
  notifications: NotificationFailure[];
  nextCursor?: string | null;
  onRetry: (
    operationId: string,
    notificationIds: string[],
  ) => Promise<{
    requeued_count: number;
    conflict_count: number;
  }>;
  onLoadMore?: () => Promise<void>;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const operationId = useRef<string | null>(null);
  const selectedSet = useMemo(() => new Set(selected), [selected]);

  async function retry(ids: string[]) {
    if (!ids.length) return;
    operationId.current ??= crypto.randomUUID();
    try {
      const result = await onRetry(operationId.current, ids.slice(0, 500));
      operationId.current = null;
      setSelected([]);
      setMessage(
        `已重新排入 ${result.requeued_count} 筆；${result.conflict_count} 筆狀態已改變，未重試。`,
      );
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "通知重試失敗，選取已保留",
      );
    }
  }

  return (
    <section
      className="ui-card ui-card-padded"
      aria-labelledby="notification-title"
    >
      <h2 id="notification-title">通知失敗佇列</h2>
      <p>
        只顯示最少收件人資訊；retry_wait 會自動重試，只有 failed 可人工選取。
      </p>
      <div className="ui-table-wrap">
        <table className="ui-table">
          <thead>
            <tr>
              <th className="ui-table-head">選取</th>
              <th className="ui-table-head">收件人</th>
              <th className="ui-table-head">事件／狀態</th>
              <th className="ui-table-head">最近失敗</th>
              <th className="ui-table-head">操作</th>
            </tr>
          </thead>
          <tbody>
            {notifications.map((notification) => (
              <tr key={notification.id}>
                <td className="ui-table-cell">
                  <input
                    type="checkbox"
                    aria-label={`選取 ${notification.recipient_display_name} 通知`}
                    disabled={notification.status !== "failed"}
                    checked={selectedSet.has(notification.id)}
                    onChange={(event) =>
                      setSelected((current) =>
                        event.target.checked
                          ? [...current, notification.id]
                          : current.filter((id) => id !== notification.id),
                      )
                    }
                  />
                </td>
                <td className="ui-table-cell">
                  {notification.recipient_display_name}
                </td>
                <td className="ui-table-cell">
                  {notification.event_type}／{notification.status}
                  {notification.status === "retry_wait"
                    ? "（等待自動重試）"
                    : ""}
                </td>
                <td className="ui-table-cell">
                  {notification.last_failed_at
                    ? formatTaiwanDateTime(notification.last_failed_at)
                    : "—"}
                  <br />
                  嘗試 {notification.attempt_count} 次
                </td>
                <td className="ui-table-cell">
                  <button
                    type="button"
                    disabled={notification.status !== "failed"}
                    onClick={() => retry([notification.id])}
                  >
                    重試這一筆
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        disabled={!selected.length}
        onClick={() => retry(selected)}
      >
        重試已選取（{selected.length}）
      </button>
      {nextCursor && onLoadMore ? (
        <button type="button" onClick={() => void onLoadMore()}>
          載入更多
        </button>
      ) : null}
      <p role="status" aria-live="polite">
        {message}
      </p>
    </section>
  );
}
