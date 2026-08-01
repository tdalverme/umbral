export const PUBLIC_HEALTH_PATH = "/health";

export const PUBLIC_ANONYMOUS_PATHS = [
  PUBLIC_HEALTH_PATH,
  "/login",
  "/auth/capture",
  "/auth/confirm",
  "/api/auth/magic-link-requests",
  "/api/webhooks/email",
] as const;

export type WebAccessMode = "cloudflare" | "product_session";

export function resolveWebAccessMode(value: string | undefined): WebAccessMode | null {
  if (value === undefined || value === "cloudflare") return "cloudflare";
  if (value === "product_session") return "product_session";
  return null;
}

export function isPublicAnonymousPath(pathname: string): boolean {
  return PUBLIC_ANONYMOUS_PATHS.includes(pathname as (typeof PUBLIC_ANONYMOUS_PATHS)[number]);
}
