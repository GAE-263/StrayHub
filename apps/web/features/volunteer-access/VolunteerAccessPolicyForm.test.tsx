// @vitest-environment jsdom

import React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { VolunteerAccessPolicyForm } from "./VolunteerAccessPolicyForm";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const policy = {
  organization_id: "org-a",
  applications_enabled: true,
  default_grant_duration_hours: 168,
  daily_application_limit: 20,
  version: 1,
};

describe("VolunteerAccessPolicyForm", () => {
  it("shows the seven-day initial policy and non-retroactive warning", () => {
    const html = renderToStaticMarkup(
      <VolunteerAccessPolicyForm policy={policy} />,
    );
    expect(html).toContain("預設授權期限（天）");
    expect(html).toContain('value="7"');
    expect(html).toContain("只影響後續建立的授權");
    expect(html).toContain("ui-checkbox");
    expect(html).toContain("ui-field");
    expect(html).toContain("ui-input");
    expect(html).toContain("ui-button ui-button-default");
    expect(html).not.toContain('<p role="status" aria-live="polite"></p>');
  });

  it("recovers from save failure and reports a later success", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const onSave = vi
      .fn()
      .mockRejectedValueOnce(new Error("儲存暫時失敗"))
      .mockResolvedValueOnce(undefined);
    await act(async () =>
      root.render(
        <VolunteerAccessPolicyForm policy={policy} onSave={onSave} />,
      ),
    );
    const submit = () =>
      [...container.querySelectorAll("button")].find((button) =>
        button.textContent?.includes("儲存"),
      ) as HTMLButtonElement;
    const submitForm = () =>
      container
        .querySelector("form")
        ?.dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        );

    await act(async () => submitForm());
    expect(container.querySelector('[role="alert"]')?.textContent).toContain(
      "儲存暫時失敗",
    );
    expect(submit().disabled).toBe(false);
    await act(async () => submitForm());
    expect(container.querySelector('[role="status"]')?.textContent).toContain(
      "設定已儲存",
    );
    expect(onSave).toHaveBeenCalledTimes(2);
    expect(onSave).toHaveBeenLastCalledWith(
      expect.objectContaining({ default_grant_duration_hours: 168 }),
    );
    await act(async () => root.unmount());
  });

  it("preserves an explicit fourteen-day policy", () => {
    const html = renderToStaticMarkup(
      <VolunteerAccessPolicyForm
        policy={{ ...policy, default_grant_duration_hours: 336 }}
      />,
    );

    expect(html).toContain('value="14"');
  });
});
