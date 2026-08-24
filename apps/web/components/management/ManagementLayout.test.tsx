import { describe, expect, it } from "vitest";

import { resolveOrganizationLabel } from "./ManagementLayout";

describe("resolveOrganizationLabel", () => {
  const organizations = [{ id: "org-a", code: "ORG-A", name: "南港收容所" }];

  it("uses the server-confirmed organization name", () => {
    expect(resolveOrganizationLabel(organizations, "org-a", false)).toBe(
      "南港收容所",
    );
  });

  it("does not fall back to a client organization code", () => {
    expect(resolveOrganizationLabel(organizations, "org-b", false)).toBe(
      "未選擇收容所",
    );
  });

  it("labels platform governance separately", () => {
    expect(resolveOrganizationLabel(organizations, null, true)).toBe(
      "平台治理",
    );
  });
});
