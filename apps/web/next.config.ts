import type { NextConfig } from "next";
import path from "node:path";

const lineDemoWebOriginHost = process.env.LINE_DEMO_WEB_ORIGIN_HOST?.trim();

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  output: "standalone",
  allowedDevOrigins: lineDemoWebOriginHost
    ? [lineDemoWebOriginHost]
    : undefined,
  webpack(config) {
    if (process.env.LIFF_HANDOFF_E2E_MOCK === "1") {
      config.resolve.alias["@line/liff"] = path.resolve(
        process.cwd(),
        "e2e/support/liff-sdk-mock.ts",
      );
    }
    return config;
  },
};

export default nextConfig;
