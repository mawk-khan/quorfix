"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { AccessState } from "@/components/access-state";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { cancelInvitation, createInvitation, listInvitations } from "@/lib/api/invitations";
import { listMembers, removeMember, updateMemberRole } from "@/lib/api/members";
import type { CommunityRole } from "@/lib/api/types";
import { useSession } from "@/lib/auth/session-provider";
import { usePageTitle } from "@/lib/use-page-title";

import { InviteForm } from "./invite-form";
import { MembersTable } from "./members-table";
import { ROLE_LABELS } from "./role-labels";

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
      <main id="main-content" tabIndex={-1} className="mx-auto max-w-4xl space-y-6 p-8">
        <Skeleton className="h-64" />
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
    <main id="main-content" tabIndex={-1} className="mx-auto max-w-4xl space-y-6 p-8">
      <PageHeader title="Team" />

      {actionError && (
        <p role="alert" className="rounded-field border border-danger/20 bg-danger-subtle p-3 text-sm text-danger">
          {actionError}
        </p>
      )}

      <Card>
        <CardHeader title="Members" />
        <MembersTable
          members={membersQuery.data ?? []}
          isAdmin={isAdmin}
          onRoleChange={(id, role) => roleMutation.mutate({ id, role })}
          onRemove={(id) => removeMutation.mutate(id)}
        />
      </Card>

      {isAdmin && (
        <Card>
          <CardHeader title="Pending invitations" />
          <CardContent className="space-y-4">
            {!invitationsQuery.data || invitationsQuery.data.length === 0 ? (
              <p className="text-sm text-text-secondary">No pending invitations.</p>
            ) : (
              <ul className="divide-y divide-border">
                {invitationsQuery.data.map((invitation) => (
                  <li key={invitation.id} className="flex items-center justify-between py-2 text-sm first:pt-0">
                    <span className="text-text-primary">
                      {invitation.email} — {ROLE_LABELS[invitation.role]}
                    </span>
                    <button
                      type="button"
                      onClick={() => cancelMutation.mutate(invitation.id)}
                      className="font-medium text-danger underline"
                    >
                      Cancel
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {lastInviteUrl && (
              <p role="status" className="text-sm text-success">
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
          </CardContent>
        </Card>
      )}
    </main>
  );
}
