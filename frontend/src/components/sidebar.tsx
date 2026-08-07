"use client";

import { Bug, FolderKanban, LayoutDashboard, Users as UsersIcon, Bell as BellIcon, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { Avatar } from "@/components/ui/avatar";
import type { Session } from "@/lib/api/types";
import { PRODUCT_NAME } from "@/lib/branding";
import { cn } from "@/lib/cn";

// Only routes that actually exist in this app — no Reports/Settings, which
// the visual references show but Community does not implement (see
// CLAUDE.md's Community/Professional boundary and this redesign's own "no
// fake routes" constraint).
const NAV_LINKS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { href: "/bugs", label: "Bugs", icon: Bug },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/team", label: "Team", icon: UsersIcon },
  { href: "/notifications", label: "Notifications", icon: BellIcon },
];

function isCurrent(pathname: string, link: (typeof NAV_LINKS)[number]): boolean {
  if (link.exact) return pathname === link.href;
  return pathname === link.href || pathname.startsWith(`${link.href}/`);
}

function SidebarContent({ pathname, session }: { pathname: string; session: Session }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <span className="flex size-8 flex-none items-center justify-center rounded-field bg-primary text-sm font-bold text-white">
          {PRODUCT_NAME[0]}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold text-text-primary">{PRODUCT_NAME}</span>
          <span className="block truncate text-xs text-text-secondary">Community Edition</span>
        </span>
      </div>

      <nav aria-label="Primary" className="flex-1 space-y-0.5 px-3">
        {NAV_LINKS.map((link) => {
          const current = isCurrent(pathname, link);
          const Icon = link.icon;
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={current ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-field px-3 py-2 text-sm font-medium transition-colors",
                current
                  ? "bg-primary-subtle text-primary"
                  : "text-text-secondary hover:bg-page hover:text-text-primary",
              )}
            >
              <Icon aria-hidden="true" className="size-[18px] flex-none" />
              {link.label}
            </Link>
          );
        })}
      </nav>

      {session.user && session.organization && (
        <div className="flex items-center gap-2.5 border-t border-border px-4 py-4">
          <Avatar user={session.user} size="md" />
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium text-text-primary">
              {session.user.first_name} {session.user.last_name}
            </span>
            <span className="block truncate text-xs capitalize text-text-secondary">{session.role}</span>
          </span>
        </div>
      )}
    </div>
  );
}

export interface SidebarProps {
  pathname: string;
  session: Session;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ pathname, session, mobileOpen, onCloseMobile }: SidebarProps) {
  const drawerRef = useRef<HTMLDivElement>(null);

  // Same Escape-to-close contract as NotificationBell's popover — mobile
  // drawer is dismissible without a mouse.
  useEffect(() => {
    if (!mobileOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onCloseMobile();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen, onCloseMobile]);

  return (
    <>
      {/* Desktop: persistent, no toggle. */}
      <aside className="hidden w-60 flex-none border-r border-border bg-surface md:block">
        <SidebarContent pathname={pathname} session={session} />
      </aside>

      {/* Mobile/tablet: off-canvas drawer with backdrop, shown only when
          mobileOpen — the sidebar's persistent desktop counterpart above is
          simply hidden below `md`, this is a separate mounted instance
          rather than one CSS-repositioned element, since the two need
          different interaction models (static vs. dismissible overlay). */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            aria-label="Close navigation menu"
            onClick={onCloseMobile}
            className="absolute inset-0 bg-gray-900/40"
          />
          <div
            ref={drawerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Primary navigation"
            className="absolute inset-y-0 left-0 w-64 bg-surface shadow-lg"
          >
            <div className="flex justify-end px-3 pt-3">
              <button
                type="button"
                onClick={onCloseMobile}
                aria-label="Close navigation menu"
                className="rounded-field p-1.5 text-text-secondary hover:bg-page"
              >
                <X aria-hidden="true" className="size-5" />
              </button>
            </div>
            <SidebarContent pathname={pathname} session={session} />
          </div>
        </div>
      )}
    </>
  );
}
