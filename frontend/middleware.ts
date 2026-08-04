import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Presence-only check for UX (avoids a flash of protected content) — never
// a security boundary. The backend enforces real authorization on every
// request regardless of what this middleware decides.
export function middleware(request: NextRequest) {
  const hasSessionCookie = request.cookies.has("sessionid");
  if (!hasSessionCookie) {
    const signInUrl = new URL("/sign-in", request.url);
    signInUrl.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(signInUrl);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/team/:path*"],
};
