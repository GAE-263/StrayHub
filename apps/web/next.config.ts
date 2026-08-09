import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    const apiOrigin = (
      process.env.API_INTERNAL_URL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      "http://127.0.0.1:8000"
    ).replace(/\/$/, "");
    return [
      {
        source: "/v1/:path*",
        destination: `${apiOrigin}/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
