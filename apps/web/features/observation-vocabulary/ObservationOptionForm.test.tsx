import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ObservationOptionForm } from "./ObservationOptionForm";

describe("ObservationOptionForm", () => {
  it("labels editable fields and explains the historical stable-code lock", () => {
    const html = renderToStaticMarkup(
      React.createElement(ObservationOptionForm, {
        categories: [
          {
            id: "emotion",
            code: "emotion",
            display_name: "情緒",
            description: "",
            status: "active",
            display_order: 0,
            source: "platform_default",
          },
        ],
        option: null,
        onSubmit: async () => undefined,
        onCancel: () => undefined,
      }),
    );

    expect(html).toContain("觀察類別");
    expect(html).toContain("中文名稱");
    expect(html).toContain("是否需要補充說明");
    expect(html).toContain("已有歷史回報使用的 code 會鎖定");
    expect(html).toContain("儲存");
    expect(html).toContain("取消");
    expect(html).toContain("ui-dialog");
    expect(html).toContain("ui-input");
  });
});
