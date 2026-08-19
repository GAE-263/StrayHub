import { describe, expect, it } from "vitest";
import nextConfig from "./next.config";

describe("Next.js visual runtime", () => {
  it("disables the development indicator so screenshots contain only product UI", () => {
    expect(nextConfig.devIndicators).toBe(false);
  });
});
