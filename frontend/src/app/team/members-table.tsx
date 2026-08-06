"use client";

import type { CommunityRole, Membership } from "@/lib/api/types";

const ROLES: CommunityRole[] = ["administrator", "developer", "qa", "reporter", "viewer"];

interface MembersTableProps {
  members: Membership[];
  isAdmin: boolean;
  onRoleChange: (id: string, role: CommunityRole) => void;
  onRemove: (id: string) => void;
}

export function MembersTable({ members, isAdmin, onRoleChange, onRemove }: MembersTableProps) {
  if (members.length === 0) {
    return <p className="text-sm text-gray-500">No members yet.</p>;
  }

  return (
    <table className="mt-2 w-full text-left text-sm">
      <caption className="sr-only">Team members</caption>
      <thead>
        <tr>
          <th scope="col" className="pb-2">
            Name
          </th>
          <th scope="col" className="pb-2">
            Email
          </th>
          <th scope="col" className="pb-2">
            Role
          </th>
          {isAdmin && (
            <th scope="col" className="pb-2">
              Actions
            </th>
          )}
        </tr>
      </thead>
      <tbody>
        {members.map((member) => (
          <tr key={member.id} className="border-t">
            <td className="py-2">
              {member.user.first_name} {member.user.last_name}
            </td>
            <td className="py-2">{member.user.email}</td>
            <td className="py-2">
              {isAdmin ? (
                <select
                  aria-label={`Role for ${member.user.email}`}
                  value={member.role}
                  onChange={(event) => onRoleChange(member.id, event.target.value as CommunityRole)}
                  className="rounded border px-2 py-1"
                >
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              ) : (
                member.role
              )}
            </td>
            {isAdmin && (
              <td className="py-2">
                <button
                  type="button"
                  onClick={() => onRemove(member.id)}
                  className="text-sm text-red-700 underline"
                >
                  Remove
                </button>
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
