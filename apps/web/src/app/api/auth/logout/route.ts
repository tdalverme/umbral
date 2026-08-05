import { NextResponse } from "next/server";

import { forwardIdentityRequest } from "@/lib/api/server";

export async function POST(request: Request): Promise<NextResponse> {
  const response = await forwardIdentityRequest("/api/v1/auth/logout", {
    method: "POST",
    headers: { Cookie: request.headers.get("cookie") || "" },
  });
  const headers = new Headers({ "Cache-Control": "private, no-store" });
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) headers.set("Set-Cookie", setCookie);
  if (response.status === 204) return new NextResponse(null, { status: 204, headers });
  return new NextResponse(await response.text(), { status: response.status, headers });
}
