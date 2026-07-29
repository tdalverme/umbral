import { NextResponse } from "next/server";

import { forwardIdentityRequest } from "@/lib/api/server";
import { originFingerprint } from "@/lib/auth/origin";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.json();
  const response = await forwardIdentityRequest("/api/v1/auth/magic-link-requests", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Umbral-Origin-Fingerprint": originFingerprint(request),
    },
    body: JSON.stringify({ email: body.email }),
  });
  return NextResponse.json(await response.json(), { status: response.status, headers: { "Cache-Control": "no-store" } });
}
