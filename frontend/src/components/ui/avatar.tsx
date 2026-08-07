import { cn } from "@/lib/cn";

export interface AvatarUser {
  first_name: string;
  last_name: string;
  email: string;
}

export function initialsFor(user: AvatarUser): string {
  const first = user.first_name.trim()[0];
  const last = user.last_name.trim()[0];
  if (first || last) return `${first ?? ""}${last ?? ""}`.toUpperCase();
  return user.email[0]?.toUpperCase() ?? "?";
}

// Deterministic per-person color (hashed from email, the one identity field
// guaranteed present and stable) — not decorative variety for its own sake:
// distinct colors make a list of avatars scannable at a glance. Solid,
// moderately saturated tones only (never the soft/tinted badge palette),
// text is always white so contrast never depends on which tone is picked.
const AVATAR_TONES = [
  "bg-blue-600",
  "bg-indigo-600",
  "bg-violet-600",
  "bg-purple-600",
  "bg-rose-600",
  "bg-amber-700",
  "bg-teal-600",
  "bg-green-600",
] as const;

function toneFor(identity: string): string {
  let hash = 0;
  for (let i = 0; i < identity.length; i++) hash = (hash * 31 + identity.charCodeAt(i)) >>> 0;
  return AVATAR_TONES[hash % AVATAR_TONES.length] ?? AVATAR_TONES[0];
}

export interface AvatarProps {
  user: AvatarUser;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZES = {
  sm: "size-6 text-[10px]",
  md: "size-8 text-xs",
  lg: "size-10 text-sm",
};

export function Avatar({ user, size = "md", className }: AvatarProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex flex-none items-center justify-center rounded-full font-semibold text-white",
        SIZES[size],
        toneFor(user.email),
        className,
      )}
    >
      {initialsFor(user)}
    </span>
  );
}
