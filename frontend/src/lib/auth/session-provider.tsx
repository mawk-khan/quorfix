"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";

import { getSession } from "@/lib/api/auth";
import type { Session } from "@/lib/api/types";

interface SessionContextValue {
  session: Session | undefined;
  isLoading: boolean;
  refetch: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  // Fetched unconditionally on every route — including /setup and
  // /invitations/[token] — since this call is also what seeds the CSRF
  // cookie those pages' forms need before they can submit.
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["session"],
    queryFn: getSession,
  });

  return (
    <SessionContext.Provider value={{ session: data, isLoading, refetch }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return context;
}
