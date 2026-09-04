// @vitest-environment jsdom

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import LoginPage from "./LoginClient";
import { hasForbiddenLoginQuery } from "./login-url-policy";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

describe("LoginPage", () => {
  function renderLoginForm() {
    const html = renderToStaticMarkup(<LoginPage />);
    document.body.innerHTML = html;
    const form = document.querySelector("form");
    const username = document.querySelector<HTMLInputElement>("#username");
    const password = document.querySelector<HTMLInputElement>("#password");
    const submit = document.querySelector<HTMLButtonElement>(
      'button[type="submit"]',
    );

    expect(form).not.toBeNull();
    expect(username).not.toBeNull();
    expect(password).not.toBeNull();
    expect(submit).not.toBeNull();

    return {
      document,
      form: form!,
      username: username!,
      password: password!,
      submit: submit!,
    };
  }

  it("exposes the localized form contract and saving announcement", () => {
    const { document } = renderLoginForm();
    const html = document.documentElement.outerHTML;
    expect(html).toContain("浪浪森友會管理入口");
    expect(html).toContain('for="username"');
    expect(html).toContain('for="password"');
    expect(html).toContain("登入");
    expect(html).toContain("目前收容所");
  });

  it("fails closed before hydration and preserves password-manager semantics", () => {
    const { form, username, password, submit } = renderLoginForm();

    expect(form.method).toBe("post");
    expect(form.getAttribute("action")).toBe("/login");
    expect(submit.disabled).toBe(true);
    expect(username.value).toBe("");
    expect(password.value).toBe("");
    expect(username.autocomplete).toBe("username");
    expect(password.autocomplete).toBe("current-password");
  });

  it.each([
    "username",
    "password",
    "temporary_password",
    "temporary-password",
    "access_token",
    "refresh_token",
    "id_token",
    "authorization",
    "PASSWORD",
  ])("classifies %s as forbidden login query input", (key) => {
    expect(
      hasForbiddenLoginQuery(new URLSearchParams([[key, "sentinel"]])),
    ).toBe(true);
  });

  it("classifies duplicate and percent-encoded credential keys without reading values", () => {
    expect(
      hasForbiddenLoginQuery(
        new URLSearchParams("view=login&password=first&password=second"),
      ),
    ).toBe(true);
    expect(
      hasForbiddenLoginQuery(new URLSearchParams("pass%77ord=sentinel")),
    ).toBe(true);
  });

  it("does not treat ordinary query keys as login input", () => {
    expect(
      hasForbiddenLoginQuery(new URLSearchParams("view=login&page=2")),
    ).toBe(false);
  });
});
