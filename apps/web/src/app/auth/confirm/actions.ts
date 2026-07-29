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
    body: JSON.stringify(capture),
  });
  store.delete(CAPTURE_COOKIE);
  if (!response.ok) redirect(`/login?error=${response.status === 410 ? "expired" : "denied"}`);
  redirect("/");
}
