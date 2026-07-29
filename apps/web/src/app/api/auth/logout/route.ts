import { NextResponse } from "next/server";

import { forwardIdentityRequest } from "@/lib/api/server";

export async function POST(request: Request): Promise<NextResponse> {
  const response = await forwardIdentityRequest("/api/v1/auth/logout", {
    method: "POST",
    headers: { Cookie: request.headers.get("cookie") || "" },
  });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      "Cache-Control": "private, no-store",
      ...(response.headers.get("set-cookie") ? { "Set-Cookie": response.headers.get("set-cookie")! } : {}),
    },
  });
}
