import { describe, expect, it } from "vitest";
import { buildTimelineQuery } from "../../../management-query";

describe("animal timeline route query contract", () => {
  it("sends a selected date range without losing either boundary", () => {
    const query = buildTimelineQuery({
      start: "2026-08-01",
      end: "2026-08-14",
    });
    expect(query.toString()).toBe("start_date=2026-08-01&end_date=2026-08-14");
  });

  it("keeps the default timeline request unfiltered", () => {
    expect(buildTimelineQuery({ start: "", end: "" }).toString()).toBe("");
  });
});
