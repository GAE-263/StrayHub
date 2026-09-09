import { describe, expect, it } from "vitest";

import {
  isPublicManagementProfile,
  resolveOrganizationLabel,
} from "./ManagementLayout";
import { visibleNavigationGroups } from "./AppSidebar";

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

  it("recognizes only server-supported shared profiles", () => {
    expect(isPublicManagementProfile("shared-demo-production")).toBe(true);
    expect(isPublicManagementProfile("shared-demo-dev")).toBe(true);
    expect(isPublicManagementProfile(null)).toBe(false);
    expect(isPublicManagementProfile("line-only")).toBe(false);
  });

  it("limits public navigation to reviewed core pages", () => {
    const hrefs = visibleNavigationGroups("STAFF", true).flatMap((group) =>
      group.links.map((link) => link.href),
    );
    expect(hrefs).toEqual([
      "/",
      "/animals",
      "/reports",
      "/care-calendar",
      "/ai-review",
    ]);
    expect(hrefs).not.toContain("/growth-diary");
    expect(hrefs).not.toContain("/settings/audit");
  });
});
