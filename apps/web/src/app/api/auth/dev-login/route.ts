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
  try {
    const body = await request.text();
    const previewToken = process.env.PREVIEW_DEV_LOGIN_TOKEN || "";
    // Never expose preview token to client; BFF injects it from server env.
    if (!previewToken) {
      return NextResponse.json(
        { code: "web.dev_login_disabled", detail: "preview dev login not configured" },
        { status: 404, headers: { "Cache-Control": "no-store" } },
      );
    }
    let response: Response;
    try {
      response = await forwardIdentityRequest("/api/v1/auth/dev-login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Umbral-Preview-Dev-Token": previewToken,
        },
        body,
        signal: AbortSignal.timeout(10000),
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
    const text = await response.text();
    return new NextResponse(text, { status: response.status, headers });
  } catch (error) {
    return NextResponse.json(
      { code: "web.dev_login_failed", detail: String(error) },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
