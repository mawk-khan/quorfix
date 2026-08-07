"use client";

import { Menu } from "lucide-react";

import { NotificationBell } from "@/components/notification-bell";
import type { Session } from "@/lib/api/types";

export interface TopBarProps {
  session: Session;
  onOpenMobileNav: () => void;
  onSignOut: () => void;
}

/** Quiet and compact — does not repeat the sidebar's nav links. Only a
 * mobile nav toggle, signed-in context, the notification bell, and
 * sign-out. No global search: no search functionality exists yet, and a
 * decorative search box that does nothing would be a fake feature. */
export function TopBar({ session, onOpenMobileNav, onSignOut }: TopBarProps) {
  return (
    <header className="flex h-14 flex-none items-center justify-between gap-4 border-b border-border bg-surface px-4 sm:px-6">
      <button
        type="button"
        onClick={onOpenMobileNav}
        aria-label="Open navigation menu"
        className="rounded-field p-1.5 text-text-secondary hover:bg-page md:hidden"
      >
        <Menu aria-hidden="true" className="size-5" />
      </button>

      <div className="min-w-0 flex-1" />

      <div className="flex items-center gap-4">
        {session.user && session.organization && (
          <p className="hidden truncate text-sm text-text-secondary lg:block">
            Signed in as {session.user.email} ({session.role}) — {session.organization.name}
          </p>
        )}
        <NotificationBell />
        <button
          type="button"
          onClick={onSignOut}
          className="text-sm font-medium text-text-secondary underline-offset-2 hover:text-text-primary hover:underline"
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
