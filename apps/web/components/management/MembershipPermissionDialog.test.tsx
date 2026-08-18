import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MembershipPermissionDialog } from "./MembershipPermissionDialog";

describe("MembershipPermissionDialog", () => {
  it("shows target, before/after values and admin count impact", () => {
    const html = renderToStaticMarkup(
      <MembershipPermissionDialog
        open
        shelterName="收容所 A"
        identity="本機工作人員 A"
        operation="提升為收容所管理員"
        before="工作人員／已停用"
        after="收容所管理員／啟用中"
        adminCountBefore={1}
        adminCountAfter={2}
        onClose={() => undefined}
        onConfirm={() => undefined}
      />,
    );

    expect(html).toContain('role="alertdialog"');
    expect(html).toContain("收容所 A");
    expect(html).toContain("本機工作人員 A");
    expect(html).toContain("1 → 2 人");
    expect(html).toContain("確認調整");
  });
});
