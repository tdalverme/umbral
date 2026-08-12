"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { forwardIdentityRequest } from "@/lib/api/server";
import { CAPTURE_COOKIE, unsealCapture } from "@/lib/auth/cookies";

export async function confirmCapture(): Promise<never> {
  const store = await cookies();
  const capture = unsealCapture(store.get(CAPTURE_COOKIE)?.value);
  if (!capture) redirect("/login?error=expired");
  const response = await forwardIdentityRequest("/api/v1/auth/magic-link-confirmations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      attempt_id: capture.attemptId,
      token_hash: capture.tokenHash,
    }),
  });
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) {
    const pair = setCookie.split(";")[0] ?? "";
    const eq = pair.indexOf("=");
    if (eq > 0) {
      store.set(pair.slice(0, eq).trim(), pair.slice(eq + 1).trim(), {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        path: "/",
      });
    }
  }
  store.delete(CAPTURE_COOKIE);
  if (!response.ok) redirect(`/login?error=${response.status === 410 ? "expired" : "denied"}`);
  redirect("/");
}
