import { NextResponse } from "next/server";

import { forwardIdentityRequest } from "@/lib/api/server";

function allowedSetCookie(value: string | null): string | null {
  if (!value) return null;
  const cookieName = process.env.SESSION_COOKIE_NAME || "umbral_local_session";
  const first = value.split(/,(?=[^;,=]+=[^;,]+)/, 1)[0]?.trim() || "";
  if (!first.startsWith(`${cookieName}=`)) return null;
  if (/\bDomain=/i.test(first) || !/\bHttpOnly\b/i.test(first) || !/\bPath=\//i.test(first)) return null;
  return first;
}

export async function POST(request: Request): Promise<NextResponse> {
  let response: Response;
  try {
    response = await forwardIdentityRequest("/api/v1/auth/magic-link-confirmations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      signal: AbortSignal.timeout(30000),
    });
  } catch (error) {
    return NextResponse.json(
      { code: "web.proxy_failed", detail: String(error) },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
  const headers = new Headers({ "Cache-Control": "private, no-store" });
  const setCookie = allowedSetCookie(response.headers.get("set-cookie"));
  if (setCookie) headers.set("Set-Cookie", setCookie);
  if (response.status === 204) return new NextResponse(null, { status: 204, headers });
  headers.set("Content-Type", response.headers.get("content-type") || "application/problem+json");
  return new NextResponse(await response.text(), { status: response.status, headers });
}
