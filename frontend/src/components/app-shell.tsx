"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";

import { logout } from "@/lib/api/auth";
import { useSession } from "@/lib/auth/session-provider";
import { PRODUCT_NAME } from "@/lib/branding";

import { NotificationBell } from "./notification-bell";

// Routes that must never show authenticated chrome, checked by pathname
// alone (synchronous, no session round-trip) so there is no window in which
// the shell could flash on them while a session query resolves.
const PUBLIC_ROUTE_PREFIXES = ["/sign-in", "/setup", "/invitations"];

function isPublicRoute(pathname: string): boolean {
  return PUBLIC_ROUTE_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, refetch } = useSession();

  // Next's App Router doesn't move focus on client-side navigation the way
  // a full page load moves it to the document — without this, focus stays
  // on whatever link/button was just clicked, on a now-unmounted or
  // unrelated part of the new page. Moving it to the new page's own <main
  // id="main-content"> (every page renders one) puts a screen reader user
  // at the start of the new page's actual content, the same landmark the
  // skip link above targets. Skipped on first mount — there's nothing to
  // move focus *from* yet, and stealing it from the URL bar on initial load
  // would be actively wrong.
  const previousPathname = useRef(pathname);
  useEffect(() => {
    if (previousPathname.current === pathname) return;
    previousPathname.current = pathname;
    document.getElementById("main-content")?.focus();
  }, [pathname]);

  const handleSignOut = async () => {
    await logout();
    refetch();
    router.push("/sign-in");
  };

  // Gated on the session provider's resolved `authenticated` flag, not on
  // whether a session cookie merely exists — a present-but-expired/invalid
  // cookie must not render authenticated chrome. While the session query is
  // still loading, session is undefined and the shell stays hidden, so a
  // protected page shows no shell for a moment rather than a wrong one.
  const showShell = !isPublicRoute(pathname) && session?.authenticated === true;

  if (!showShell) {
    return <>{children}</>;
  }

  const navLinks = [
    { href: "/bugs", label: "Bugs" },
    { href: "/projects", label: "Projects" },
    { href: "/team", label: "Team" },
    { href: "/notifications", label: "Notifications" },
  ];

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-black focus:shadow-lg focus:outline focus:outline-2 focus:outline-blue-600"
      >
        Skip to main content
      </a>
      <header className="border-b">
        <nav
          aria-label="Primary"
          className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-8"
        >
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <Link href="/" className="font-semibold">
              {PRODUCT_NAME}
            </Link>
            <ul className="flex flex-wrap items-center gap-4 text-sm">
              {navLinks.map((link) => {
                const isCurrent = pathname === link.href || pathname.startsWith(`${link.href}/`);
                return (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      aria-current={isCurrent ? "page" : undefined}
                      className={isCurrent ? "font-semibold underline" : undefined}
                    >
                      {link.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
          <div className="flex items-center gap-4">
            {session?.user && session.organization && (
              <p className="hidden text-sm text-gray-500 sm:block">
                Signed in as {session.user.email} ({session.role}) — {session.organization.name}
              </p>
            )}
            <NotificationBell />
            <button type="button" onClick={handleSignOut} className="text-sm underline">
              Sign out
            </button>
          </div>
        </nav>
      </header>
      {/* Not <main> — every page already renders its own <main> landmark;
          nesting a second one here would be an invalid duplicate landmark. */}
      <div className="flex-1">{children}</div>
    </div>
  );
}
