import type { NextConfig } from "next";

const backendInternalUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

// Next dev's default allowed-origin allowlist only trusts localhost variants
// and rejects cross-origin asset requests (403) from anywhere else — e.g.
// testing against the dev server from another device on the LAN, or from a
// container reaching the host via a non-localhost address. Opt-in only, dev
// server only (has no effect on `next build`/`next start`), unset by default.
const allowedDevOrigins = process.env.NEXT_ALLOWED_DEV_ORIGINS?.split(",").filter(Boolean);

const nextConfig: NextConfig = {
  ...(allowedDevOrigins?.length ? { allowedDevOrigins } : {}),
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
