import { describe, expect, it } from "vitest";
import { iconMap } from "./icon-map";

describe("management icon map", () => {
  it("contains semantic actions used by core flows", () => {
    expect(iconMap.search).toBeDefined();
    expect(iconMap.retry).toBeDefined();
    expect(iconMap.permission).toBeDefined();
    expect(iconMap.ai).toBeDefined();
  });
});
