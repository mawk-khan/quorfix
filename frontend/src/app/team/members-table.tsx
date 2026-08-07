"use client";

import { Avatar } from "@/components/ui/avatar";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/select";
import type { CommunityRole, Membership } from "@/lib/api/types";

import { ROLE_LABELS } from "./role-labels";

const ROLES: CommunityRole[] = ["administrator", "developer", "qa", "reporter", "viewer"];

interface MembersTableProps {
  members: Membership[];
  isAdmin: boolean;
  onRoleChange: (id: string, role: CommunityRole) => void;
  onRemove: (id: string) => void;
}

export function MembersTable({ members, isAdmin, onRoleChange, onRemove }: MembersTableProps) {
  if (members.length === 0) {
    return <EmptyState title="No members yet" />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Team members</caption>
        <thead>
          <tr className="border-b border-border">
            <th scope="col" className="whitespace-nowrap px-4 py-2.5 pl-5 text-xs font-medium text-text-secondary">
              Name
            </th>
            <th scope="col" className="whitespace-nowrap px-4 py-2.5 text-xs font-medium text-text-secondary">
              Email
            </th>
            <th scope="col" className="whitespace-nowrap px-4 py-2.5 text-xs font-medium text-text-secondary last:pr-5">
              Role
            </th>
            {isAdmin && (
              <th scope="col" className="whitespace-nowrap px-4 py-2.5 pr-5 text-xs font-medium text-text-secondary">
                Actions
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {members.map((member) => (
            <tr key={member.id} className="border-b border-border last:border-b-0 hover:bg-page">
              <td className="whitespace-nowrap px-4 py-3 pl-5">
                <div className="flex items-center gap-2.5">
                  <Avatar user={member.user} size="sm" />
                  <span className="font-medium text-text-primary">
                    {member.user.first_name} {member.user.last_name}
                  </span>
                </div>
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-text-secondary">{member.user.email}</td>
              <td className="whitespace-nowrap px-4 py-3 last:pr-5">
                {isAdmin ? (
                  <Select
                    aria-label={`Role for ${member.user.email}`}
                    value={member.role}
                    onChange={(event) => onRoleChange(member.id, event.target.value as CommunityRole)}
                    className="w-40"
                  >
                    {ROLES.map((role) => (
                      <option key={role} value={role}>
                        {ROLE_LABELS[role]}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <span className="text-text-primary">{ROLE_LABELS[member.role]}</span>
                )}
              </td>
              {isAdmin && (
                <td className="whitespace-nowrap px-4 py-3 pr-5">
                  <button
                    type="button"
                    onClick={() => onRemove(member.id)}
                    className="font-medium text-danger underline"
                  >
                    Remove
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
