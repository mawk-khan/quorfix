import type { NextConfig } from "next";

const backendInternalUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

// Next dev's default allowed-origin allowlist only trusts localhost variants
// and rejects cross-origin asset requests (403) from anywhere else — e.g.
// testing against the dev server from another device on the LAN, or from a
// container reaching the host via a non-localhost address. Opt-in only, dev
// server only (has no effect on `next build`/`next start`), unset by default.
const allowedDevOrigins = process.env.NEXT_ALLOWED_DEV_ORIGINS?.split(",").filter(Boolean);

// Verified against this app's actual production output (`next build` +
// inspecting the rendered HTML — see the Chunk G completion report for the
// exact commands), not assumed from Next.js documentation alone:
//   - No <style> tags or inline style="" attributes anywhere in rendered
//     HTML from Tailwind's own output, but Recharts (used by the dashboard)
//     is documented upstream to render inline `style` attributes on its
//     SVG/wrapper elements for responsive sizing — style-src therefore
//     needs 'unsafe-inline'. This is a materially lower-risk relaxation
//     than script-src: CSS injection alone cannot execute script or read
//     application data the way inline JS can.
//   - script-src DOES need 'unsafe-inline': Next.js App Router's React
//     Server Components streaming payload (`self.__next_f.push(...)`) is
//     delivered via genuinely inline, non-nonce'd <script> tags on every
//     page — this is Next's own framework output, not app code. The
//     documented alternative is a nonce issued per-request from
//     middleware.ts, but that forces every route in this app into dynamic
//     (per-request) rendering — several routes here (/, /bugs, /projects,
//     /sign-in, /setup, /team, ...) are currently statically generated
//     (see `next build`'s own route summary), and trading that away
//     app-wide is a real architecture change out of scope for a
//     security-headers pass. 'unsafe-inline' for script-src is the
//     documented, honest trade-off this specific constraint requires — not
//     a default reached without checking the alternative.
//   - No unsafe-eval in production: production Turbopack output does not
//     use eval() (that's a dev-server-only source-map mechanism). next dev
//     itself does use eval() for React's Fast Refresh / stack-trace
//     reconstruction, so 'unsafe-eval' is appended to script-src below only
//     when NODE_ENV !== "production" — the header list runs at config-time
//     against this same env var, not per-request, so it can't drift from
//     which server actually started.
//   - No data: URIs and no external font/script/style CDNs anywhere in this
//     app — next/font (Inter, see app/layout.tsx) self-hosts the font files
//     at build time and serves them from this app's own origin, never a
//     runtime request to fonts.googleapis.com, so img-src/font-src need
//     nothing beyond 'self'.
const isProduction = process.env.NODE_ENV === "production";

const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isProduction ? "" : " 'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self'",
  "font-src 'self'",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  // Traced, minimal-dependency build output (.next/standalone) used by the
  // production Docker image (frontend/Dockerfile's `runner` stage) — a
  // self-contained server.js plus only the node_modules that build actually
  // traced as used, instead of the full node_modules tree. No effect on
  // `next dev` or plain `next build && next start` outside Docker.
  output: "standalone",
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
  // Applies to every response this server sends, HTML and static assets
  // alike — a config-time header list, not per-request middleware, so it
  // has no effect on which routes are statically vs. dynamically rendered.
  //
  // No Strict-Transport-Security here deliberately: this server is never
  // the TLS-terminating edge (see docker-compose.prod.yml — only the
  // frontend's own plain-HTTP port is published, and an operator's own
  // reverse proxy is expected to terminate TLS in front of it). HSTS is
  // that reverse proxy's responsibility — sending it here would be a false
  // promise this process cannot itself guarantee. See docs/SECURITY.md.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
