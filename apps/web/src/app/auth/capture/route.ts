import { NextResponse } from "next/server";

import { CAPTURE_COOKIE, sealCapture } from "@/lib/auth/cookies";

export async function GET(request: Request): Promise<NextResponse> {
  const url = new URL(request.url);
  const attemptId = url.searchParams.get("attempt_id");
  const tokenHash = url.searchParams.get("token_hash");
  const validAttempt = attemptId && /^[0-9a-f-]{36}$/i.test(attemptId);
  const validHash = tokenHash && /^[A-Za-z0-9_-]{32,512}$/.test(tokenHash);
  const baseUrl = process.env.IDENTITY_CAPTURE_ORIGIN || new URL(request.url).origin;
  if (!validAttempt || !validHash) {
    return NextResponse.redirect(new URL("/auth/confirm?error=invalid", baseUrl), { status: 303, headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } });
  }
  const response = NextResponse.redirect(new URL("/auth/confirm", baseUrl), { status: 303, headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } });
  response.cookies.set(CAPTURE_COOKIE, sealCapture(attemptId, tokenHash), { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict", path: "/auth", maxAge: 300 });
  return response;
}
