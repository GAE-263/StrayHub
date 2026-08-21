// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import CareReportPage from "./page";
import { VolunteerShelterContext } from "../../../components/auth/VolunteerShelterContext";

(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | undefined;
let container: HTMLDivElement | undefined;

afterEach(async () => {
  await act(async () => root?.unmount());
  root = undefined;
  container?.remove();
  container = undefined;
  vi.unstubAllGlobals();
});

describe("care report LIFF page", () => {
  it("renders resume and save-oriented fallback shell", () => {
    const page = React.createElement(CareReportPage);
    expect(page.type).toBe(CareReportPage);
    const html = renderToStaticMarkup(<CareReportPage />);
    expect(html).toContain("正在恢復回報草稿");
    expect(html).toContain("state-card");
    expect(html).toContain('role="status"');
  });

  it("shows the server-confirmed shelter and clears a draft when context changes", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: "draft-a",
          answers: { appetite: "good" },
          current_step: "appetite",
        }),
      } as Response)
      .mockResolvedValueOnce({ ok: true, status: 404 } as Response);
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(
        <VolunteerShelterContext.Provider
          value={{ organizationId: "org-a", organizationName: "南港收容所" }}
        >
          <CareReportPage />
        </VolunteerShelterContext.Provider>,
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.textContent).toContain("目前協助收容所：南港收容所");
    expect(container.textContent).toContain("目前步驟：appetite");

    await act(async () => {
      root?.render(
        <VolunteerShelterContext.Provider
          value={{ organizationId: "org-b", organizationName: "北投收容所" }}
        >
          <CareReportPage />
        </VolunteerShelterContext.Provider>,
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.textContent).toContain("目前協助收容所：北投收容所");
    expect(container.textContent).not.toContain("目前步驟：appetite");
  });

  it("ignores a pending save response from the previous shelter", async () => {
    let resolveSave!: (response: Response) => void;
    const pendingSave = new Promise<Response>((resolve) => {
      resolveSave = resolve;
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          id: "draft-a",
          answers: { appetite: "good" },
          current_step: "appetite",
        }),
      } as Response)
      .mockReturnValueOnce(pendingSave)
      .mockResolvedValueOnce({ ok: true, status: 404 } as Response);
    vi.stubGlobal("fetch", fetchMock);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(
        <VolunteerShelterContext.Provider
          value={{ organizationId: "org-a", organizationName: "南港收容所" }}
        >
          <CareReportPage />
        </VolunteerShelterContext.Provider>,
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await act(async () => {
      const button = Array.from(
        container?.querySelectorAll("button") ?? [],
      ).find((item) => item.textContent === "儲存並繼續");
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
    });

    await act(async () => {
      root?.render(
        <VolunteerShelterContext.Provider
          value={{ organizationId: "org-b", organizationName: "北投收容所" }}
        >
          <CareReportPage />
        </VolunteerShelterContext.Provider>,
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
      resolveSave({
        ok: true,
        status: 200,
        json: async () => ({
          id: "draft-a",
          answers: { appetite: "old" },
          current_step: "appetite",
        }),
      } as Response);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container?.textContent).not.toContain("目前步驟：appetite");
  });
});
