import { describe, expect, it } from "vitest";

import HomePage from "./page";

describe("HomePage", () => {
  it("renders the StrayHub title", () => {
    const page = HomePage();
    const children = page.props.children as Array<{
      props?: { children?: unknown };
    }>;

    expect(children[0].props?.children).toBe("浪浪森友會");
  });
});
