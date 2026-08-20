import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import LoginPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

describe("LoginPage", () => {
  it("exposes the localized form contract and saving announcement", () => {
    const html = renderToStaticMarkup(<LoginPage />);
    expect(html).toContain("浪浪森友會管理入口");
    expect(html).toContain('for="username"');
    expect(html).toContain('for="password"');
    expect(html).toContain("登入");
    expect(html).toContain("目前收容所");
  });
});
