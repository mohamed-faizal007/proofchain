/** Only return to a same-origin internal path after login; never follow an absolute or protocol-relative URL. */
export function safeRedirectPath(path: string | null | undefined): string {
  if (!path) return "/";
  if (!path.startsWith("/") || path.startsWith("//") || path.startsWith("/\\")) return "/";
  return path;
}
