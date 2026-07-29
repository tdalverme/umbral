import { cookies } from "next/headers";

import { forwardIdentityRequest } from "@/lib/api/server";

export async function identitySessionRequest(): Promise<Response> {
  const store = await cookies();
  const cookieName = process.env.SESSION_COOKIE_NAME || "umbral_local_session";
  const token = store.get(cookieName)?.value;
  return forwardIdentityRequest("/api/v1/auth/session", {
    headers: token ? { Cookie: `${cookieName}=${token}` } : undefined,
  });
}
