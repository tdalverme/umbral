import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { forwardIdentityRequest } from "@/lib/api/server";
import { Providers } from "@/lib/query/providers";

export default async function ProtectedLayout({ children }: Readonly<{ children: ReactNode }>): Promise<ReactNode> {
  const cookieStore = await cookies();
  const rawMock = process.env.NEXT_PUBLIC_USE_MOCKS ?? process.env.USE_MOCKS;
  const isDevPreview =
    rawMock === "1" || rawMock === "true" || process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_USE_MOCKS === "1";
  if (isDevPreview) {
    return <Providers>{children}</Providers>;
  }
  // fallback preview cookie for manual "document.cookie=..."
  const previewCookie = cookieStore.get("umbral_preview")?.value ?? cookieStore.get("umbral_local_session")?.value;
  if (previewCookie === "dev-preview" || previewCookie === "preview") {
    return <Providers>{children}</Providers>;
  }
  const session = cookieStore.get(process.env.SESSION_COOKIE_NAME || "umbral_local_session")?.value;
  if (!session) redirect("/login");
  const response = await forwardIdentityRequest("/api/v1/auth/session", { headers: { Cookie: `${process.env.SESSION_COOKIE_NAME || "umbral_local_session"}=${session}` } });
  if (!response.ok) redirect("/login");
  return <Providers>{children}</Providers>;
}
