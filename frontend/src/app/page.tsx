"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { logout } from "@/lib/api/auth";
import { useSession } from "@/lib/auth/session-provider";

export default function HomePage() {
  const { session, isLoading, refetch } = useSession();
  const router = useRouter();

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p>Loading…</p>
      </main>
    );
  }

  if (!session?.authenticated) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
        <h1 className="text-2xl font-semibold">Bug Fixer</h1>
        <Link href="/sign-in" className="underline">
          Sign in
        </Link>
      </main>
    );
  }

  const handleSignOut = async () => {
    await logout();
    refetch();
    router.push("/sign-in");
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold">Bug Fixer</h1>
      <p className="text-sm text-gray-500">
        Signed in as {session.user?.email} ({session.role}) — {session.organization?.name}
      </p>
      <Link href="/team" className="underline">
        Team
      </Link>
      <Link href="/projects" className="underline">
        Projects
      </Link>
      <Link href="/bugs" className="underline">
        Bugs
      </Link>
      <button type="button" onClick={handleSignOut} className="text-sm underline">
        Sign out
      </button>
    </main>
  );
}
