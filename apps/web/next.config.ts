import type { NextConfig } from "next";

const lineDemoWebOriginHost = process.env.LINE_DEMO_WEB_ORIGIN_HOST?.trim();

const nextConfig: NextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  output: "standalone",
  allowedDevOrigins: lineDemoWebOriginHost ? [lineDemoWebOriginHost] : undefined,
};

export default nextConfig;
