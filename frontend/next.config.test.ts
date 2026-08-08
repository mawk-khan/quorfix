import { afterEach, describe, expect, it, vi } from "vitest";

import nextConfig from "./next.config";

// next.config.ts computes its CSP's 'unsafe-eval' inclusion once at module
// import time from process.env.NODE_ENV — dynamically re-importing the
// module after changing that env var (with the module cache reset in
// between) is the only way to observe both branches in one test run,
// mirroring how `next build` vs. `next dev` actually differ at process
// start, not per-request.
async function loadConfigWithNodeEnv(nodeEnv: string) {
  // vi.stubEnv (not a direct process.env.NODE_ENV assignment) sidesteps
  // @types/node typing NODE_ENV as read-only, and vi.unstubAllEnvs below
  // restores the original value automatically rather than this function
  // having to remember it.
  vi.stubEnv("NODE_ENV", nodeEnv);
  vi.resetModules();
  try {
    const mod = await import("./next.config");
    return mod.default;
  } finally {
    vi.unstubAllEnvs();
  }
}

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

  it("sends a Content-Security-Policy", async () => {
    const headers = await getHeaders();
    expect(headers["Content-Security-Policy"]).toBeDefined();
  });

  afterEach(() => {
    vi.resetModules();
  });

  it("omits unsafe-eval in production — Turbopack's production output never calls eval()", async () => {
    const prodConfig = await loadConfigWithNodeEnv("production");
    const entries = await prodConfig.headers!();
    const csp = entries[0]?.headers.find((h) => h.key === "Content-Security-Policy")?.value ?? "";
    expect(csp).not.toContain("unsafe-eval");
  });

  it("allows unsafe-eval outside production — next dev's React Fast Refresh needs eval()", async () => {
    const devConfig = await loadConfigWithNodeEnv("development");
    const entries = await devConfig.headers!();
    const csp = entries[0]?.headers.find((h) => h.key === "Content-Security-Policy")?.value ?? "";
    expect(csp).toContain("'unsafe-eval'");
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
