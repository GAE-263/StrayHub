import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchMedicalRecords, fetchCareAgenda } from "./api";

describe("medical care API boundaries", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("serializes filters without leaking the previous tenant", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ items: [], next_cursor: null }), {
        status: 200,
      }),
    );
    await fetchMedicalRecords("animal-a", {
      search: "皮膚",
      includeArchived: true,
    });
    expect(fetchMock.mock.calls[0]?.[0]).toContain("search=%E7%9A%AE%E8%86%9A");
    expect(fetchMock.mock.calls[0]?.[0]).toContain("include_archived=true");
  });

  it.each([401, 403, 409])("surfaces HTTP %s for agenda", async (status) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("{}", { status }),
    );
    await expect(fetchCareAgenda({ date: "2026-08-16" })).rejects.toThrow();
  });
});
