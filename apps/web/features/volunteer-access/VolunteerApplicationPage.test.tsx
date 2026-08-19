// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { VolunteerApplicationPage } from "./VolunteerApplicationPage";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

describe("VolunteerApplicationPage", () => {
  it("requires confirmation before withdrawal and shows a success toast", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        organization: {
          id: "org-a",
          name: "收容所 A",
          applications_enabled: true,
        },
        application: { id: "app-a", status: "withdrawn", version: 2 },
        grant: null,
        effective_status: "withdrawn",
        next_actions: ["reapply"],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close() {
      this.open = false;
    };
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <VolunteerApplicationPage
          initialStatus={{
            organization: {
              id: "org-a",
              name: "收容所 A",
              applications_enabled: true,
            },
            application: { id: "app-a", status: "pending", version: 1 },
            grant: null,
            effective_status: "pending",
            next_actions: ["wait", "withdraw"],
          }}
          idToken="id-token"
          shelterEntryReference="entry"
        />,
      );
    });
    const button = (name: string) =>
      Array.from(container.querySelectorAll("button")).find(
        (item) => item.textContent?.trim() === name,
      ) as HTMLButtonElement;

    await act(async () => button("撤回報名").click());
    expect(fetchMock).not.toHaveBeenCalled();
    expect(container.querySelector("dialog[open]")).not.toBeNull();
    await act(async () => button("保留報名").click());
    expect(fetchMock).not.toHaveBeenCalled();

    await act(async () => button("撤回報名").click());
    await act(async () => {
      button("確認撤回").click();
      await Promise.resolve();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(container.textContent).toContain("志工報名已撤回");
    expect(container.querySelector("dialog[open]")).toBeNull();

    await act(async () => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("uses semantic application primitives instead of hard-coded color utilities", () => {
    const html = renderToStaticMarkup(
      <VolunteerApplicationPage
        initialStatus={{
          organization: {
            id: "org-a",
            name: "收容所 A",
            applications_enabled: true,
          },
          application: null,
          grant: null,
          effective_status: "none",
          next_actions: ["apply"],
        }}
        idToken="id-token"
        shelterEntryReference="entry"
      />,
    );
    expect(html).toContain("ui-card");
    expect(html).toContain("ui-checkbox");
    expect(html).toContain("ui-button ui-button-default");
    expect(html).not.toMatch(/(?:emerald|slate|red)-/);
  });

  it.each([
    ["none", "立即報名"],
    ["pending", "等待收容所審核"],
    ["rejected", "再次報名"],
    ["withdrawn", "再次報名"],
    ["expired", "授權已到期"],
  ])(
    "renders Traditional Chinese state %s without protected content",
    (status, copy) => {
      const html = renderToStaticMarkup(
        <VolunteerApplicationPage
          initialStatus={{
            organization: {
              id: "org-a",
              name: "收容所 A",
              applications_enabled: true,
            },
            application:
              status === "none" ? null : { id: "app-a", status, version: 1 },
            grant: null,
            effective_status: status,
            next_actions:
              status === "pending" ? ["wait", "withdraw"] : ["reapply"],
          }}
          idToken="id-token"
          shelterEntryReference="entry"
        />,
      );
      expect(html).toContain(copy);
      expect(html).not.toContain("狗狗名單");
      expect(html).not.toContain("管理後台");
    },
  );

  it("shows upcoming/active grant period in Taiwan time and only active handoff", () => {
    const status = {
      organization: {
        id: "org-a",
        name: "收容所 A",
        applications_enabled: true,
      },
      application: { id: "app-a", status: "approved", version: 2 },
      grant: {
        id: "grant-a",
        status: "active",
        valid_from: "2026-08-15T04:00:00Z",
        expires_at: "2026-08-22T04:00:00Z",
        version: 1,
      },
      effective_status: "active",
      next_actions: ["enter_care"],
    };
    const active = renderToStaticMarkup(
      <VolunteerApplicationPage
        initialStatus={status}
        idToken="id-token"
        shelterEntryReference="entry"
      />,
    );
    expect(active).toContain("收容所 A");
    expect(active).toContain("2026/08/15");
    expect(active).toContain("12:00");
    expect(active).toContain("進入照護流程");

    const upcoming = renderToStaticMarkup(
      <VolunteerApplicationPage
        initialStatus={{ ...status, effective_status: "upcoming" }}
        idToken="id-token"
        shelterEntryReference="entry"
      />,
    );
    expect(upcoming).not.toContain("進入照護流程</a>");
  });
});
