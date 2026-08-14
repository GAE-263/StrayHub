import { describe, expect, it } from "vitest";
import { buildAnimalsQuery } from "../management-query";

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
});
