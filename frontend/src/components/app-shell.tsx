"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useSession } from "@/lib/auth/session-provider";

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
  const { session } = useSession();

  // Gated on the session provider's resolved `authenticated` flag, not on
  // whether a session cookie merely exists — a present-but-expired/invalid
  // cookie must not render authenticated chrome. While the session query is
  // still loading, session is undefined and the shell stays hidden, so a
  // protected page shows no shell for a moment rather than a wrong one.
  const showShell = !isPublicRoute(pathname) && session?.authenticated === true;

  if (!showShell) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b">
        <nav
          aria-label="Primary"
          className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-8"
        >
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <Link href="/bugs" className="font-semibold">
              Bug Fixer
            </Link>
            <ul className="flex flex-wrap items-center gap-4 text-sm">
              <li>
                <Link href="/bugs">Bugs</Link>
              </li>
              <li>
                <Link href="/projects">Projects</Link>
              </li>
              <li>
                <Link href="/team">Team</Link>
              </li>
              <li>
                <Link href="/notifications">Notifications</Link>
              </li>
            </ul>
          </div>
          <NotificationBell />
        </nav>
      </header>
      {/* Not <main> — every page already renders its own <main> landmark;
          nesting a second one here would be an invalid duplicate landmark. */}
      <div className="flex-1">{children}</div>
    </div>
  );
}
