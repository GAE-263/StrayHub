import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("HomePage", () => {
  it("renders the management home client", () => {
    const page = HomePage();
    expect(page.type.name).toBe("ManagementHome");
  });
});
