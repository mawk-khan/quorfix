"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { acceptInvitation, getInvitation } from "@/lib/api/invitations";
import { useSession } from "@/lib/auth/session-provider";
import {
  acceptInvitationSchema,
  type AcceptInvitationFormValues,
} from "@/lib/validation/invitations";

// A client component rather than a server-fetched one: the typed API client
// (src/lib/api/client.ts) issues relative /api/* requests meant to go through
// Next's browser-side rewrite proxy, and every other Phase 1 page follows the
// same client-fetch pattern — introducing server-side absolute-URL fetching
// just for this page would be an inconsistent one-off for no real benefit,
// since this page has no SEO value and a brief loading state is fine.
export default function InvitationAcceptPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const router = useRouter();
  const { refetch } = useSession();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    data: invitation,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => getInvitation(token),
    retry: false,
  });

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AcceptInvitationFormValues>({ resolver: zodResolver(acceptInvitationSchema) });

  const onSubmit = async (values: AcceptInvitationFormValues) => {
    setFormError(null);
    try {
      await acceptInvitation(token, values);
      refetch();
      router.push("/");
    } catch {
      setFormError("This invitation is no longer valid.");
    }
  };

  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p>Loading invitation…</p>
      </main>
    );
  }

  if (isError || !invitation) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p role="alert">This invitation is invalid or has expired.</p>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <form
        onSubmit={handleSubmit(onSubmit)}
        className="w-full max-w-sm space-y-4"
        aria-label="Accept invitation"
      >
        <h1 className="text-xl font-semibold">Join {invitation.organization_name}</h1>
        <p className="text-sm text-gray-500">
          You&apos;ve been invited as {invitation.role} ({invitation.email}). Set a password
          to continue.
        </p>

        <div>
          <label htmlFor="password" className="block text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            className="mt-1 w-full rounded border px-3 py-2"
            {...register("password")}
          />
          {errors.password && (
            <p role="alert" className="mt-1 text-sm text-red-700">
              {errors.password.message}
            </p>
          )}
        </div>

        {formError && (
          <p role="alert" className="text-sm text-red-700">
            {formError}
          </p>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded bg-black px-3 py-2 text-white disabled:opacity-50"
        >
          {isSubmitting ? "Joining…" : "Accept invitation"}
        </button>
      </form>
    </main>
  );
}
