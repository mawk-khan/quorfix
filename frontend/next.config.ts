import type { NextConfig } from "next";

const backendInternalUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Django's URLs use a trailing slash (APPEND_SLASH). Next's default
  // trailing-slash redirect runs before rewrites and would fight with that,
  // so it's disabled for requests proxied to the backend.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        // The wildcard capture drops any trailing slash from the incoming
        // request, so it's added back explicitly — Django's URLs require it.
        source: "/api/:path*",
        destination: `${backendInternalUrl}/api/:path*/`,
      },
    ];
  },
};

export default nextConfig;
