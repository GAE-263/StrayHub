import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AlertDialog } from "./alert-dialog";
import { Dialog } from "./dialog";
import { Sheet } from "./sheet";

describe("overlay accessibility contract", () => {
  it("exposes a modal Dialog with an explicit close control", () => {
    const html = renderToStaticMarkup(
      <Dialog open title="編輯資料" onClose={() => undefined}>
        <button type="button">取消</button>
      </Dialog>,
    );

    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('aria-label="關閉"');
    expect(html).toContain("取消");
  });

  it("uses alertdialog semantics for blocking confirmation", () => {
    const html = renderToStaticMarkup(
      <AlertDialog open title="確認封存" onClose={() => undefined}>
        <p>此操作只改變狀態，不會刪除歷史資料。</p>
      </AlertDialog>,
    );

    expect(html).toContain('role="alertdialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain("確認封存");
  });

  it("gives every overlay a unique accessible title relationship", () => {
    const html = renderToStaticMarkup(
      <>
        <Dialog open title="建立帳號" onClose={() => undefined}>
          <p>建立內容</p>
        </Dialog>
        <Dialog open title="替換帳號" onClose={() => undefined}>
          <p>替換內容</p>
        </Dialog>
        <Sheet open title="管理導覽" onClose={() => undefined}>
          <nav>導覽內容</nav>
        </Sheet>
      </>,
    );

    const labelledBy = Array.from(
      html.matchAll(/aria-labelledby="([^"]+)"/g),
      (match) => match[1],
    );
    const titleIds = Array.from(
      html.matchAll(/<h2 id="([^"]+)"/g),
      (match) => match[1],
    );

    expect(labelledBy).toHaveLength(3);
    expect(new Set(labelledBy).size).toBe(3);
    expect(labelledBy).toEqual(titleIds);
  });
});
