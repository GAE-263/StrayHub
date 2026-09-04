import type { NextConfig } from "next";
import path from "node:path";

const lineDemoWebOriginHost = process.env.LINE_DEMO_WEB_ORIGIN_HOST?.trim();

export function shouldEnableLiffHandoffE2EMock(env: NodeJS.ProcessEnv) {
  return env.NODE_ENV === "development" && env.LIFF_HANDOFF_E2E_MOCK === "1";
}

export const liffHandoffE2EMockEnabled = shouldEnableLiffHandoffE2EMock(
  process.env,
);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  output: "standalone",
  distDir: liffHandoffE2EMockEnabled ? ".next-liff-handoff-e2e" : undefined,
  allowedDevOrigins: lineDemoWebOriginHost
    ? [lineDemoWebOriginHost]
    : undefined,
  async headers() {
    return [
      {
        source: "/login",
        headers: [
          { key: "Cache-Control", value: "no-store" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
  webpack(config) {
    if (liffHandoffE2EMockEnabled) {
      config.resolve.alias["@line/liff"] = path.resolve(
        process.cwd(),
        "e2e/support/liff-sdk-mock.ts",
      );
    }
    return config;
  },
};

export default nextConfig;
