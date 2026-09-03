import { describe, expect, it } from "vitest";
import { buildQrCodesQuery } from "./management-query";

describe("QR management query contract", () => {
  it("trims search and preserves explicit status and pagination", () => {
    const query = buildQrCodesQuery({
      page: 3,
      pageSize: 20,
      query: "  小黑 A-013  ",
      status: "active",
    });

    expect(query.toString()).toBe(
      "page=3&page_size=20&status=active&query=%E5%B0%8F%E9%BB%91+A-013",
    );
  });

  it("omits an empty search and clamps page to one", () => {
    const query = buildQrCodesQuery({
      page: 0,
      query: "   ",
      status: "all",
    });

    expect(query.toString()).toBe("page=1&page_size=20&status=all");
    expect(query.has("query")).toBe(false);
  });

  it("supports the revoked status contract", () => {
    expect(
      buildQrCodesQuery({ page: 2, query: "", status: "revoked" }).get(
        "status",
      ),
    ).toBe("revoked");
  });
});
