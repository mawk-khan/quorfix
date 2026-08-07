"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { AccessState } from "@/components/access-state";
import { ApiError } from "@/lib/api/client";
import { cancelInvitation, createInvitation, listInvitations } from "@/lib/api/invitations";
import { listMembers, removeMember, updateMemberRole } from "@/lib/api/members";
import type { CommunityRole } from "@/lib/api/types";
import { useSession } from "@/lib/auth/session-provider";
import { usePageTitle } from "@/lib/use-page-title";

import { InviteForm } from "./invite-form";
import { MembersTable } from "./members-table";

function describeError(error: unknown): string {
  if (
    error instanceof ApiError &&
    typeof error.body === "object" &&
    error.body !== null &&
    "detail" in error.body
  ) {
    return String((error.body as { detail: unknown }).detail);
  }
  return "Something went wrong.";
}

export default function TeamPage() {
  usePageTitle("Team");
  const { session, isLoading: sessionLoading } = useSession();
  const isAdmin = session?.role === "administrator";
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastInviteUrl, setLastInviteUrl] = useState<string | null>(null);

  const membersQuery = useQuery({
    queryKey: ["members"],
    queryFn: () => listMembers(),
    enabled: !!session?.authenticated,
  });
  const invitationsQuery = useQuery({
    queryKey: ["invitations"],
    queryFn: listInvitations,
    enabled: isAdmin,
  });

  const roleMutation = useMutation({
    mutationFn: ({ id, role }: { id: string; role: CommunityRole }) => updateMemberRole(id, role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["members"] }),
    onError: (error) => setActionError(describeError(error)),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => removeMember(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["members"] }),
    onError: (error) => setActionError(describeError(error)),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) => cancelInvitation(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["invitations"] }),
  });

  const inviteMutation = useMutation({
    mutationFn: createInvitation,
    onSuccess: (invitation) => {
      queryClient.invalidateQueries({ queryKey: ["invitations"] });
      // The raw invite token is only ever returned here, at creation time —
      // the list endpoint deliberately can't reconstruct it. Surfacing it
      // now is what makes invites usable without SMTP configured.
      setLastInviteUrl(invitation.invite_url ?? null);
    },
    onError: (error) => setActionError(describeError(error)),
  });

  if (sessionLoading || membersQuery.isLoading) {
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <p>Loading team…</p>
      </main>
    );
  }

  if (!session?.authenticated) {
    return (
      <main id="main-content" tabIndex={-1} className="p-8">
        <AccessState
          heading="Sign in required"
          message="You must sign in to view this page."
          action={{ href: "/sign-in", label: "Go to sign in" }}
        />
      </main>
    );
  }

  return (
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-3xl space-y-8 p-8">
      <h1 className="text-xl font-semibold">Team</h1>

      {actionError && (
        <p role="alert" className="text-sm text-red-700">
          {actionError}
        </p>
      )}

      <section aria-labelledby="members-heading">
        <h2 id="members-heading" className="text-lg font-medium">
          Members
        </h2>
        <MembersTable
          members={membersQuery.data ?? []}
          isAdmin={isAdmin}
          onRoleChange={(id, role) => roleMutation.mutate({ id, role })}
          onRemove={(id) => removeMutation.mutate(id)}
        />
      </section>

      {isAdmin && (
        <section aria-labelledby="invitations-heading">
          <h2 id="invitations-heading" className="text-lg font-medium">
            Pending invitations
          </h2>
          {!invitationsQuery.data || invitationsQuery.data.length === 0 ? (
            <p className="text-sm text-gray-500">No pending invitations.</p>
          ) : (
            <ul className="mt-2 space-y-2 text-sm">
              {invitationsQuery.data.map((invitation) => (
                <li
                  key={invitation.id}
                  className="flex items-center justify-between border-t py-2"
                >
                  <span>
                    {invitation.email} — {invitation.role}
                  </span>
                  <button
                    type="button"
                    onClick={() => cancelMutation.mutate(invitation.id)}
                    className="text-sm text-red-700 underline"
                  >
                    Cancel
                  </button>
                </li>
              ))}
            </ul>
          )}

          {lastInviteUrl && (
            <p role="status" className="mt-2 text-sm text-green-700">
              Invitation created. Share this link (shown only once):{" "}
              <a href={lastInviteUrl} className="underline">
                {lastInviteUrl}
              </a>
            </p>
          )}

          <InviteForm
            onSubmit={(values) => {
              setLastInviteUrl(null);
              inviteMutation.mutate(values);
            }}
            isSubmitting={inviteMutation.isPending}
          />
        </section>
      )}
    </main>
  );
}
