import { beforeEach, describe, expect, it, vi } from "vitest";
import { authFetch } from "../../lib/auth";
import { fetchGrowthDiaryEntries } from "./api";

vi.mock("../../lib/auth", () => ({ authFetch: vi.fn() }));

const mockedAuthFetch = vi.mocked(authFetch);

beforeEach(() => mockedAuthFetch.mockReset());

describe("growth diary list API", () => {
  it("encodes trimmed server-side filters and pagination without an organization id", async () => {
    mockedAuthFetch.mockResolvedValue(
      new Response(
        JSON.stringify({ items: [], page: 3, page_size: 25, total: 0 }),
      ),
    );

    await fetchGrowthDiaryEntries({
      query: "  Mi Gao  ",
      mood: "concern",
      page: 3,
      pageSize: 25,
    });

    const url = String(mockedAuthFetch.mock.calls[0][0]);
    expect(url).toContain("query=Mi+Gao");
    expect(url).toContain("mood=concern");
    expect(url).toContain("page=3");
    expect(url).toContain("page_size=25");
    expect(url).not.toMatch(/organization|shelter/i);
  });

  it("omits empty and all filters", async () => {
    mockedAuthFetch.mockResolvedValue(
      new Response(
        JSON.stringify({ items: [], page: 1, page_size: 50, total: 0 }),
      ),
    );

    await fetchGrowthDiaryEntries({ query: "   ", mood: "all" });

    const url = String(mockedAuthFetch.mock.calls[0][0]);
    expect(url).not.toContain("query=");
    expect(url).not.toContain("mood=");
  });
});
