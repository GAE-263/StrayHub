import { describe, expect, it } from "vitest";
import { buildGrowthDiaryQuery } from "../management-query";

describe("growth diary management query contract", () => {
  it("preserves search, mood, status and date filters", () => {
    const query = buildGrowthDiaryQuery({
      page: 2,
      search: "旺來",
      mood: "concern",
      status: "new",
      fromDate: "2026-08-01",
      toDate: "2026-08-14",
    });

    expect(query.get("page")).toBe("2");
    expect(query.get("page_size")).toBe("20");
    expect(query.get("search")).toBe("旺來");
    expect(query.get("mood")).toBe("concern");
    expect(query.get("status")).toBe("new");
    expect(query.get("from_date")).toBe("2026-08-01");
    expect(query.get("to_date")).toBe("2026-08-14");
  });

  it("keeps the inbox query stable when filters are cleared", () => {
    const query = buildGrowthDiaryQuery({
      page: 1,
      search: "",
      mood: "",
      status: "",
      fromDate: "",
      toDate: "",
    });
    expect(query.toString()).toBe("page=1&page_size=20");
  });

  it("trims whitespace-only search text instead of sending an empty param", () => {
    const query = buildGrowthDiaryQuery({
      page: 1,
      search: "   ",
      mood: "",
      status: "",
      fromDate: "",
      toDate: "",
    });
    expect(query.toString()).toBe("page=1&page_size=20");
  });

  it("floors and clamps a non-positive page to 1", () => {
    const query = buildGrowthDiaryQuery({
      page: 0,
      search: "",
      mood: "",
      status: "",
      fromDate: "",
      toDate: "",
    });
    expect(query.get("page")).toBe("1");
  });
});
