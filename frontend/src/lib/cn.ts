type ClassValue = string | false | null | undefined;

/** Joins conditional class names — deliberately not clsx/tailwind-merge:
 * every component here uses fixed variant maps rather than freeform
 * combining, so string-dedup/merge semantics are never needed. */
export function cn(...classes: ClassValue[]): string {
  return classes.filter(Boolean).join(" ");
}
