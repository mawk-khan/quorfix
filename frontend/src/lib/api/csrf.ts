export function getCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  const value = match?.[1];
  return value ? decodeURIComponent(value) : null;
}
