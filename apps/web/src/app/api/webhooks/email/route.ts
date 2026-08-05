import { NextResponse } from "next/server";

import { forwardIdentityRequest } from "@/lib/api/server";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.arrayBuffer();
  const forwardedHeaders = new Headers({
    "content-type": request.headers.get("content-type") ?? "application/json",
    "svix-id": request.headers.get("svix-id") ?? "",
    "svix-timestamp": request.headers.get("svix-timestamp") ?? "",
    "svix-signature": request.headers.get("svix-signature") ?? "",
  });
  const response = await forwardIdentityRequest("/api/v1/integrations/email/resend-events", {
    method: "POST",
    headers: forwardedHeaders,
    body,
  });
  return new NextResponse(response.status === 204 ? null : await response.text(), {
    status: response.status,
    headers: { "Cache-Control": "no-store", "Content-Type": response.headers.get("content-type") || "text/plain" },
  });
}
