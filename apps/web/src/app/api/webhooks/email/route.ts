import { NextResponse } from "next/server";

import { forwardIdentityRequest } from "@/lib/api/server";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.arrayBuffer();
  const response = await forwardIdentityRequest("/api/v1/integrations/email/resend-events", {
    method: "POST",
    headers: { "Content-Type": request.headers.get("content-type") || "application/json" },
    body,
  });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "Cache-Control": "no-store", "Content-Type": response.headers.get("content-type") || "text/plain" },
  });
}
