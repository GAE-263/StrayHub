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
    expect(html).toContain('class="ui-dialog permission-confirmation-dialog"');
    expect(html).toContain("收容所 A");
    expect(html).toContain("本機工作人員 A");
    expect(html).toContain("1 → 2 人");
    expect(html).toContain("確認調整");
    expect(html).toContain('class="ui-button ui-button-secondary"');
    expect(html).toContain('class="ui-button ui-button-default"');
    expect(html).not.toContain("ui-button-primary");
  });

  it("uses the destructive variant for high-risk confirmation", () => {
    const html = renderToStaticMarkup(
      <MembershipPermissionDialog
        open
        identity="本機志工 A"
        operation="撤銷志工授權"
        before="授權中"
        after="已撤銷"
        destructive
        onClose={() => undefined}
        onConfirm={() => undefined}
      />,
    );

    expect(html).toContain('class="ui-button ui-button-destructive"');
  });
});
