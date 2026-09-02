import { describe, expect, it } from "vitest";
import nextConfig, {
  liffHandoffE2EMockEnabled,
  shouldEnableLiffHandoffE2EMock,
} from "./next.config";

describe("Next.js visual runtime", () => {
  it("disables the development indicator so screenshots contain only product UI", () => {
    expect(nextConfig.devIndicators).toBe(false);
  });

  it("keeps the handoff-only LIFF mock disabled in the normal test runtime", () => {
    expect(liffHandoffE2EMockEnabled).toBe(false);
    expect(nextConfig.distDir).toBeUndefined();
  });

  it("allows the mock only outside production with an explicit opt-in", () => {
    expect(
      shouldEnableLiffHandoffE2EMock({
        NODE_ENV: "development",
        LIFF_HANDOFF_E2E_MOCK: "1",
      }),
    ).toBe(true);
    expect(
      shouldEnableLiffHandoffE2EMock({
        NODE_ENV: "production",
        LIFF_HANDOFF_E2E_MOCK: "1",
      }),
    ).toBe(false);
    expect(
      shouldEnableLiffHandoffE2EMock({
        NODE_ENV: "test",
        LIFF_HANDOFF_E2E_MOCK: "1",
      }),
    ).toBe(false);
    expect(shouldEnableLiffHandoffE2EMock({ NODE_ENV: "development" })).toBe(
      false,
    );
  });
});
