import { NextResponse } from "next/server";

import { forwardIdentityRequest } from "@/lib/api/server";

function sessionCookie(request: Request): string {
  const name = process.env.SESSION_COOKIE_NAME || "umbral_local_session";
  const entry = (request.headers.get("cookie") || "").split(";").map((value) => value.trim())
    .find((value) => value.startsWith(`${name}=`));
  return entry || "";
}

export async function GET(request: Request): Promise<NextResponse> {
  const response = await forwardIdentityRequest("/api/v1/auth/session", {
    headers: { Cookie: sessionCookie(request) },
  });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      "Cache-Control": "private, no-store",
      "Content-Type": response.headers.get("content-type") || "application/json",
    },
  });
}
