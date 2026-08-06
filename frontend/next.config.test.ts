import { describe, expect, it } from "vitest";

import nextConfig from "./next.config";

// Calls next.config.ts's own headers() function directly — the same
// function Next.js itself calls to build every response's header set — so
// a regression here (a dropped header, a reintroduced 'unsafe-eval', a CSP
// directive silently removed) is caught without needing a running server.
// See docs/SECURITY.md "Response headers" for why each of these exists and
// why the CSP allows 'unsafe-inline' specifically (documented, verified
// trade-off, not an oversight).
describe("next.config.ts headers()", () => {
  async function getHeaders() {
    if (!nextConfig.headers) {
      throw new Error("next.config.ts must define headers()");
    }
    const entries = await nextConfig.headers();
    expect(entries).toHaveLength(1);
    const headerList = entries[0]?.headers ?? [];
    return Object.fromEntries(headerList.map((h) => [h.key, h.value]));
  }

  it("applies to every path", async () => {
    const entries = await nextConfig.headers!();
    expect(entries[0]?.source).toBe("/:path*");
  });

  it("sends a Content-Security-Policy with no unsafe-eval", async () => {
    const headers = await getHeaders();
    expect(headers["Content-Security-Policy"]).toBeDefined();
    expect(headers["Content-Security-Policy"]).not.toContain("unsafe-eval");
  });

  it("restricts default-src, frame-ancestors, and object-src", async () => {
    const headers = await getHeaders();
    const csp = headers["Content-Security-Policy"] ?? "";
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("form-action 'self'");
  });

  it("sends X-Content-Type-Options: nosniff", async () => {
    const headers = await getHeaders();
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
  });

  it("sends Referrer-Policy: strict-origin-when-cross-origin", async () => {
    const headers = await getHeaders();
    expect(headers["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
  });

  it("sends X-Frame-Options: DENY", async () => {
    const headers = await getHeaders();
    expect(headers["X-Frame-Options"]).toBe("DENY");
  });

  it("sends a conservative Permissions-Policy", async () => {
    const headers = await getHeaders();
    const permissionsPolicy = headers["Permissions-Policy"] ?? "";
    for (const feature of ["camera", "microphone", "geolocation", "payment", "usb"]) {
      expect(permissionsPolicy).toContain(`${feature}=()`);
    }
  });

  it("never sends Strict-Transport-Security — that's the reverse proxy's job", async () => {
    const headers = await getHeaders();
    expect(headers["Strict-Transport-Security"]).toBeUndefined();
  });
});
