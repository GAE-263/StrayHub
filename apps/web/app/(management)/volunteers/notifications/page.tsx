"use client";

import { useEffect, useState } from "react";

import {
  NotificationFailureQueue,
  type NotificationFailure,
} from "../../../../features/volunteer-access/NotificationFailureQueue";
import { authFetch } from "../../../../lib/auth";

export default function VolunteerNotificationsPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [items, setItems] = useState<NotificationFailure[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [eventType, setEventType] = useState("");
  const [status, setStatus] = useState("");
  const [failedFrom, setFailedFrom] = useState("");
  const [failedTo, setFailedTo] = useState("");
  const [error, setError] = useState("");

  async function load(id: string, cursor?: string | null, append = false) {
    const query = new URLSearchParams({ limit: "100" });
    if (eventType) query.set("event_type", eventType);
    if (status) query.set("status", status);
    if (failedFrom)
      query.set("failed_from", new Date(failedFrom).toISOString());
    if (failedTo) query.set("failed_to", new Date(failedTo).toISOString());
    if (cursor) query.set("cursor", cursor);
    const response = await authFetch(
      `/v1/organizations/${id}/volunteer-notifications?${query.toString()}`,
    );
    if (!response.ok) throw new Error("無法載入通知失敗佇列");
    const page = (await response.json()) as {
      items: NotificationFailure[];
      next_cursor: string | null;
    };
    setItems((current) => (append ? [...current, ...page.items] : page.items));
    setNextCursor(page.next_cursor);
    setError("");
  }

  useEffect(() => {
    const id = window.sessionStorage.getItem("active_organization_id") ?? "";
    setOrganizationId(id);
    if (id) void load(id).catch((reason) => setError(reason.message));
    // Initial load intentionally uses empty filters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function retry(operationId: string, notificationIds: string[]) {
    const response = await authFetch(
      `/v1/organizations/${organizationId}/volunteer-notifications/retry`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          operation_id: operationId,
          notification_ids: notificationIds,
        }),
      },
    );
    if (!response.ok) throw new Error("通知重試提交失敗，選取已保留");
    const result = await response.json();
    await load(organizationId);
    return result;
  }

  return (
    <main>
      <div className="page-heading">
        <div>
          <span className="eyebrow">VOLUNTEER NOTIFICATIONS</span>
          <h1>志工通知失敗</h1>
          <p>統一查看目前收容所的失敗投遞，人工重試不會重做核准或撤銷。</p>
        </div>
      </div>
      <form
        className="panel ui-card mb-4 flex flex-wrap items-end gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void load(organizationId).catch((reason) => setError(reason.message));
        }}
      >
        <label>
          事件
          <input
            value={eventType}
            onChange={(event) => setEventType(event.target.value)}
          />
        </label>
        <label>
          狀態
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">全部</option>
            <option value="failed">failed</option>
            <option value="retry_wait">retry_wait</option>
          </select>
        </label>
        <label>
          失敗時間起
          <input
            type="datetime-local"
            value={failedFrom}
            onChange={(event) => setFailedFrom(event.target.value)}
          />
        </label>
        <label>
          失敗時間迄
          <input
            type="datetime-local"
            value={failedTo}
            onChange={(event) => setFailedTo(event.target.value)}
          />
        </label>
        <button type="submit">套用篩選</button>
      </form>
      {error ? <p role="alert">{error}</p> : null}
      <NotificationFailureQueue
        notifications={items}
        nextCursor={nextCursor}
        onRetry={retry}
        onLoadMore={() => load(organizationId, nextCursor, true)}
      />
    </main>
  );
}
