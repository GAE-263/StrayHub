// @vitest-environment jsdom

import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { authFetch } from "../../../lib/auth";
import { buildAnimalsQuery } from "../management-query";
import AnimalsPage from "./page";

vi.mock("../../../lib/auth", () => ({ authFetch: vi.fn() }));

const fetchWithAuth = vi.mocked(authFetch);
let root: ReturnType<typeof createRoot> | undefined;
(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  root = undefined;
  document.body.replaceChildren();
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("animals management query contract", () => {
  it("preserves search, area, status and pagination in the API query", () => {
    const query = buildAnimalsQuery({
      page: 2,
      query: "  小森  ",
      status: "active",
      areaId: "area-1",
    });

    expect(query.toString()).toBe(
      "page=2&page_size=20&status=active&query=%E5%B0%8F%E6%A3%AE&area_id=area-1",
    );
  });

  it("does not send empty optional filters", () => {
    const query = buildAnimalsQuery({
      page: 1,
      query: "  ",
      status: "all",
      areaId: "",
    });

    expect(query.has("query")).toBe(false);
    expect(query.has("area_id")).toBe(false);
  });

  it("isolates multiple thumbnails, null photos and one failed photo", async () => {
    window.sessionStorage.setItem("active_organization_id", "org-a");
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:animal-a"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    fetchWithAuth.mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/areas")) {
        return new Response(JSON.stringify({ items: [] }), { status: 200 });
      }
      if (url.includes("/management/animals?")) {
        return new Response(
          JSON.stringify({
            page: 1,
            page_size: 20,
            total: 3,
            items: [
              {
                id: "animal-a",
                name: "小森",
                shelter_number: "A-1",
                breed: "米克斯",
                sex: "male",
                status: "active",
                photo_url: "/v1/management/animals/animal-a/photo",
              },
              {
                id: "animal-b",
                name: "小雨",
                shelter_number: "A-2",
                breed: null,
                sex: "female",
                status: "active",
                photo_url: null,
              },
              {
                id: "animal-c",
                name: "小光",
                shelter_number: "A-3",
                breed: null,
                sex: "unknown",
                status: "active",
                photo_url: "/v1/management/animals/animal-c/photo",
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.endsWith("/animal-a/photo")) {
        return new Response(new Blob(["jpeg"]), { status: 200 });
      }
      return new Response(null, { status: 404 });
    });
    const container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => root?.render(<AnimalsPage />));

    expect(container.querySelectorAll("tbody tr")).toHaveLength(3);
    expect(container.querySelectorAll("img")).toHaveLength(1);
    expect(container.textContent).toContain("小雨");
    expect(container.textContent).toContain("小光");
    expect(container.textContent).toContain("照片暫時無法顯示");
  });
});
