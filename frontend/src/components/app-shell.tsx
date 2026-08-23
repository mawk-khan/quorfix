"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { DemoBanner } from "@/components/demo-banner";
import { DemoPersonaBanner } from "@/components/demo-persona-banner";
import { Sidebar } from "@/components/sidebar";
import { TopBar } from "@/components/top-bar";
import { logout } from "@/lib/api/auth";
import { useSession } from "@/lib/auth/session-provider";
import { demoRoleLabel, isDemoPersonaSession } from "@/lib/demo";

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
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

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

  // Closes the mobile drawer on every navigation — otherwise a link tap
  // would leave the overlay open on top of the new page. Adjusted during
  // render (React's documented "reset state when a prop changes" pattern —
  // state, not a ref, since refs may not be read/written during render),
  // not in an effect: an effect here would have no external system to
  // synchronize with, just a derived reset, and would cost an extra
  // post-commit render pass for something render-time adjustment already
  // handles in one pass.
  const [prevPathnameForNav, setPrevPathnameForNav] = useState(pathname);
  if (prevPathnameForNav !== pathname) {
    setPrevPathnameForNav(pathname);
    if (mobileNavOpen) setMobileNavOpen(false);
  }

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

  // Rendered on every route, public or authenticated — /setup and /sign-in
  // are exactly where a demo visitor first decides whether to enter real
  // information, so the notice must not be limited to the authenticated
  // shell below. Empty/absent on a normal installation (see
  // DEMO_BANNER_MESSAGE in config/settings/base.py), so this renders
  // nothing there.
  const banner = session?.demo_banner ? <DemoBanner message={session.demo_banner} /> : null;

  // Distinct from the generic banner above — only shown inside the
  // authenticated shell (a demo persona identity is meaningless before
  // sign-in), and only when the backend's demo mode is actually enabled, not
  // merely because an organization happens to be slugged "quorfix-demo".
  const demoPersonaBanner =
    showShell && session?.demo_mode === true && session.role && isDemoPersonaSession(session) ? (
      <DemoPersonaBanner roleLabel={demoRoleLabel(session.role)} onSwitchRole={handleSignOut} />
    ) : null;

  if (!showShell) {
    return (
      <>
        {banner}
        {children}
      </>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      {banner}
      {demoPersonaBanner}
      <div className="flex min-h-0 flex-1">
        {/* A <nav> landmark, not a bare <a> — a skip link floating directly in
            the body lands outside every landmark, which axe's "region" rule
            (correctly) flags: a landmark-navigation user has no way to jump
            straight to it. Wrapping it in its own labeled nav is the
            standard fix and costs nothing else — the link's own behavior
            (focus-visible only, jumps to #main-content) is unchanged. */}
        <nav aria-label="Skip links">
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-field focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-text-primary focus:shadow-lg focus:outline focus:outline-2 focus:outline-primary"
          >
            Skip to main content
          </a>
        </nav>

        <Sidebar
          pathname={pathname}
          session={session}
          mobileOpen={mobileNavOpen}
          onCloseMobile={() => setMobileNavOpen(false)}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar
            session={session}
            onOpenMobileNav={() => setMobileNavOpen(true)}
            onSignOut={handleSignOut}
          />
          {/* Not <main> — every page already renders its own <main> landmark;
              nesting a second one here would be an invalid duplicate landmark. */}
          <div className="min-w-0 flex-1 bg-page">{children}</div>
        </div>
      </div>
    </div>
  );
}
