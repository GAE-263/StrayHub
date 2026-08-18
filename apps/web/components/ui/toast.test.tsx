import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Toast } from "./toast";

describe("Toast", () => {
  it("uses status semantics and the bottom-left styling hook", () => {
    const html = renderToStaticMarkup(
      <Toast>已完成權限調整：本機工作人員 A</Toast>,
    );

    expect(html).toContain('class="ui-toast"');
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain("已完成權限調整：本機工作人員 A");
    expect(html).not.toContain("bafda56b-f781-48dc-bcd4-e02dc10573d9");
  });
});
