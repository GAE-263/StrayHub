import { describe, expect, it } from "vitest";
import { buildReportsQuery } from "../management-query";

describe("reports management query contract", () => {
  it("preserves date and status filters", () => {
    const query = buildReportsQuery({
      fromDate: "2026-08-01",
      toDate: "2026-08-14",
      status: "saved",
    });

    expect(query.toString()).toBe(
      "page=1&page_size=50&from_date=2026-08-01&to_date=2026-08-14&status=saved",
    );
  });

  it("keeps the inbox query stable when filters are cleared", () => {
    const query = buildReportsQuery({ fromDate: "", toDate: "", status: "" });
    expect(query.toString()).toBe("page=1&page_size=50");
  });
});
