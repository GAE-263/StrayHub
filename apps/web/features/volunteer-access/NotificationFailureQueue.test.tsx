// @vitest-environment jsdom

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { NotificationFailureQueue } from "./NotificationFailureQueue";

describe("NotificationFailureQueue", () => {
  it("only enables failed deliveries and explains automatic retry wait", () => {
    const html = renderToStaticMarkup(
      <NotificationFailureQueue
        notifications={[
          {
            id: "failed",
            recipient_display_name: "志工 A",
            event_type: "approved",
            status: "failed",
            attempt_count: 5,
          },
          {
            id: "waiting",
            recipient_display_name: "志工 B",
            event_type: "expired",
            status: "retry_wait",
            attempt_count: 2,
          },
        ]}
        onRetry={vi.fn()}
      />,
    );
    expect(html).toContain("等待自動重試");
    expect(html).toContain("重試已選取");
    expect(html).toContain("disabled");
    expect(html).toContain("ui-checkbox");
    expect(html).toContain("ui-table notification-table");
    expect(html).toContain("ui-button-secondary");
    expect(html).not.toContain('<p role="status" aria-live="polite"></p>');
    expect(html).not.toContain("line_user_id");
  });
});
