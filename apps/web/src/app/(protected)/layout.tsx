import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { forwardIdentityRequest } from "@/lib/api/server";

export default async function ProtectedLayout({ children }: Readonly<{ children: ReactNode }>): Promise<ReactNode> {
  const cookieStore = await cookies();
  const session = cookieStore.get(process.env.SESSION_COOKIE_NAME || "umbral_local_session")?.value;
  if (!session) redirect("/login");
  const response = await forwardIdentityRequest("/api/v1/auth/session", { headers: { Cookie: `${process.env.SESSION_COOKIE_NAME || "umbral_local_session"}=${session}` } });
  if (!response.ok) redirect("/login");
  return <>{children}</>;
}
