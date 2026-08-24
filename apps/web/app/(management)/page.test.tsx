import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("management root route", () => {
  it("renders the management home inside the management route group", () => {
    const page = HomePage();
    expect(page.type.name).toBe("ManagementHome");
  });
});
